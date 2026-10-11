"""Offline contract tests for custom OpenAI SDK single/multi-agent instrumentation.

No credentials or network access required. SDK-compatible dummy interfaces exercise
sync and async Responses/Chat Completions, roles, handoffs and bounded capture.
"""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from execweave.graph import GraphAccumulator
from execweave.investigation_index import build_investigation_index
from execweave.openai_agents import OpenAIAgentRecorder


class _Responses:
    def create(self, **kwargs):
        if kwargs.get("model") == "fail":
            raise RuntimeError("DUMMY_SECRET_DO_NOT_LOG")
        return SimpleNamespace(model_dump=lambda **_: {
            "id": "resp-test", "model": kwargs.get("model"),
            "output_text": "hello", "api_key": "DUMMY_KEY_SHOULD_REDACT",
        })


class _AsyncResponses:
    async def create(self, **kwargs):
        return {"id": "async-test", "model": kwargs.get("model"), "output": []}


class _AwaitableChat:
    """SDK-like callable that returns a coroutine but is not async def."""
    def create(self, **kwargs):
        async def request():
            await asyncio.sleep(0)
            if kwargs.get("model") == "fail":
                raise RuntimeError("PRIVATE_BAD_REQUEST_DETAILS")
            return {"id": "chat-async", "model": kwargs.get("model"), "result": "real"}
        return request()


class _Client:
    def __init__(self):
        self.responses = _Responses()
        self.chat = SimpleNamespace(completions=_Responses())


class _AsyncClient:
    def __init__(self):
        self.responses = _AsyncResponses()
        self.chat = SimpleNamespace(completions=_AwaitableChat())


def _environment(monkeypatch, tmp_path):
    monkeypatch.setenv("EXECWEAVE_SEMANTIC_SIDECAR", str(tmp_path / "semantic.jsonl"))
    monkeypatch.setenv("EXECWEAVE_SESSION_ID", "custom-openai")
    monkeypatch.setenv("EXECWEAVE_RUN_ID", "custom-openai")


def _read(tmp_path):
    path = tmp_path / "semantic.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_openai_single_agent_model_call_metadata_only(tmp_path, monkeypatch):
    _environment(monkeypatch, tmp_path)
    recorder = OpenAIAgentRecorder()
    client = recorder.wrap(_Client())
    client.responses.create(model="gpt-test", input="SENSITIVE_PROMPT")
    events = _read(tmp_path)
    kinds = [event["event_type"] for event in events]
    assert kinds.count("MODEL_REQUEST") == 1
    assert kinds.count("MODEL_RESPONSE") == 1
    assert kinds.count("AGENT_CREATED") == 1
    data = (tmp_path / "semantic.jsonl").read_text(encoding="utf-8")
    assert "SENSITIVE_PROMPT" not in data
    assert "DUMMY_KEY_SHOULD_REDACT" not in data
    assert "gpt-test" in data
    requests = [e for e in events if e["event_type"] == "MODEL_REQUEST"]
    assert requests[0]["attributes"]["requesting_agent_id"]


def test_openai_multi_agent_handoff_and_content_redaction(tmp_path, monkeypatch):
    _environment(monkeypatch, tmp_path)
    recorder = OpenAIAgentRecorder(capture_mode="prompt_and_response")
    client = recorder.wrap(_Client())
    with recorder.agent("Engineer"):
        client.chat.completions.create(
            model="gpt-test", messages=[{"role": "user", "content": "do work"}],
            api_key="DUMMY_KEY_SHOULD_REDACT",
        )
        tool_id = recorder.tool_started("test", arguments={"x": 1, "api_key": "HIDE_ME"})
        recorder.tool_finished(tool_id, result={"ok": True})
    recorder.sent("missing", "Engineer", "Reviewer", content="Please review")
    recorder.sent("delivered", "Engineer", "Reviewer")
    recorder.received("delivered", "Engineer", "Reviewer")
    events = _read(tmp_path)
    kinds = [event["event_type"] for event in events]
    for kind in ("MODEL_REQUEST", "MODEL_RESPONSE", "TOOL_CALL", "TOOL_RESULT",
                 "MESSAGE_SENT", "MESSAGE_RECEIVED"):
        assert kind in kinds
    assert kinds.count("MESSAGE_SENT") == 2
    assert kinds.count("MESSAGE_RECEIVED") == 1
    text = (tmp_path / "semantic.jsonl").read_text(encoding="utf-8")
    assert "DUMMY_KEY_SHOULD_REDACT" not in text
    assert "HIDE_ME" not in text
    # Credential filtering must also apply to opt-in content-store artifacts.
    for artifact in (tmp_path / "content").rglob("*"):
        if artifact.is_file():
            value = artifact.read_bytes()
            assert b"DUMMY_KEY_SHOULD_REDACT" not in value
            assert b"HIDE_ME" not in value
    accumulator = GraphAccumulator(
        session_id="custom-openai", source_path=tmp_path / "events.jsonl",
    )
    for i, event in enumerate(events):
        accumulator.apply({**event, "session_id": "custom-openai", "sequence": i})
    report = build_investigation_index(accumulator.to_dict(), tmp_path)
    handoffs = report["messages"]
    assert len(handoffs) == 2
    assert sorted(tuple(row["phases"]) for row in handoffs) == [
        ("sent",), ("sent", "received"),
    ]
    agent_names = {n["name"] for n in accumulator.to_dict()["nodes"]
                   if n["type"] == "agent"}
    assert {"Engineer", "Reviewer"}.issubset(agent_names)


def test_openai_async_and_failure_no_exception_text(tmp_path, monkeypatch):
    _environment(monkeypatch, tmp_path)
    recorder = OpenAIAgentRecorder()
    sync_client = recorder.wrap(_Client())
    try:
        sync_client.responses.create(model="fail")
    except RuntimeError:
        pass
    else:
        raise AssertionError("failure should propagate")
    async def run():
        async_client = recorder.wrap(_AsyncClient())
        with recorder.agent("AsyncWorker"):
            return await async_client.responses.create(model="async-gpt", input="secret")
    asyncio.run(run())
    events = _read(tmp_path)
    assert any(e["event_type"] == "MODEL_FAILURE" and
               e["attributes"]["error_type"] == "RuntimeError" for e in events)
    assert any(e["event_type"] == "MODEL_RESPONSE" for e in events)
    assert "DUMMY_SECRET_DO_NOT_LOG" not in (tmp_path / "semantic.jsonl").read_text()

    # AsyncOpenAI.chat.completions.create is NOT necessarily declared async.
    # Never materialize its coroutine as a successful MODEL_RESPONSE.
    async def check_chat():
        async_client = recorder.wrap(_AsyncClient())
        with recorder.agent("ChatWorker"):
            success = await async_client.chat.completions.create(model="chat-success")
            assert success["id"] == "chat-async"
            try:
                await async_client.chat.completions.create(model="fail")
            except RuntimeError:
                pass
            else:
                raise AssertionError("an awaited chat HTTP failure must propagate")
    asyncio.run(check_chat())
    events = _read(tmp_path)
    chat_requests = [e for e in events if e["event_type"] == "MODEL_REQUEST"
                     and e["attributes"].get("sdk_surface") == "chat.completions"]
    assert len(chat_requests) == 2
    chat_responses = [e for e in events if e["event_type"] == "MODEL_RESPONSE"
                      and e["target"] and e["target"].get("name") == "chat-success"]
    chat_failures = [e for e in events if e["event_type"] == "MODEL_FAILURE"
                     and e["target"] and e["target"].get("name") == "fail"]
    assert len(chat_responses) == 1
    assert len(chat_failures) == 1
    assert chat_failures[0]["attributes"]["error_type"] == "RuntimeError"
    assert "PRIVATE_BAD_REQUEST_DETAILS" not in (tmp_path / "semantic.jsonl").read_text()



def test_non_execweave_python_is_noop(monkeypatch):
    monkeypatch.delenv("EXECWEAVE_SESSION_ID", raising=False)
    monkeypatch.delenv("EXECWEAVE_SEMANTIC_SIDECAR", raising=False)
    client = _Client()
    recorder = OpenAIAgentRecorder()
    assert recorder.wrap(client) is client
    with recorder.agent("User"):
        assert client.responses.create(model="gpt-test", input="hello")
    recorder.sent("x", "User", "Reviewer")


def test_streaming_does_not_fake_completed_response(tmp_path, monkeypatch):
    _environment(monkeypatch, tmp_path)
    recorder = OpenAIAgentRecorder()
    client = recorder.wrap(_Client())
    client.responses.create(model="stream", stream=True)
    events = _read(tmp_path)
    assert any(e["event_type"] == "MODEL_REQUEST" for e in events)
    assert not any(e["event_type"] == "MODEL_RESPONSE" for e in events)


def test_record_command_merges_custom_python_openai_semantics(tmp_path):
    """Run a real child interpreter through the ordinary record command."""
    import sys
    from execweave.workflow import record_to_viewer

    program = tmp_path / "custom_agent.py"
    program.write_text(
        "from execweave.openai_agents import OpenAIAgentRecorder\n"
        "class Responses:\n"
        "    def create(self, **kwargs):\n"
        "        return {'id': 'mock-response', 'output': 'ok'}\n"
        "class Client:\n"
        "    responses = Responses()\n"
        "record = OpenAIAgentRecorder()\n"
        "client = record.wrap(Client())\n"
        "with record.agent('Planner'):\n"
        "    client.responses.create(model='dummy-local-model', input='hello')\n"
        "record.sent('handoff-1', 'Planner', 'Reviewer')\n"
        "record.received('handoff-1', 'Planner', 'Reviewer')\n",
        encoding="utf-8",
    )
    result = record_to_viewer([sys.executable, str(program)],
                              watch_root=tmp_path, backend="portable")
    assert result.return_code == 0
    assert result.semantic_event_count >= 5
    graph = json.loads(result.graph.read_text(encoding="utf-8"))
    kinds = {kind for node in graph.get("nodes", []) for kind in node.get("event_types", [])}
    assert {"MESSAGE_SENT", "MESSAGE_RECEIVED", "MODEL_REQUEST", "MODEL_RESPONSE"} <= kinds
    assert "api_key" not in result.event_stream.read_text(encoding="utf-8")
