"""Provider-shaped recordings for the dashboard graph-invariant regression.

Each case drives the real provider integration (hook CLI, HTTP proxy recorder,
SDK/runtime/gateway adapter, or framework adapter inside ``record_to_viewer``)
into a semantic sidecar beside collector-shaped runtime events, and builds the
final graph the way ``execweave record`` does.  The expectations next to each
case are read off the same inputs: which models were used, which provider
session each model served, and which concrete things (tools, files, runtimes,
gateways, framework agents, subagents) the user must be able to find.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import sys
from contextlib import contextmanager, redirect_stdout
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

import execweave
import execweave.live  # noqa: F401 - production live/final renderer wiring
from execweave import (
    anthropic,
    antigravity_hook_cli,
    claude_hook_cli,
    codex_hook_cli,
    cursor_hook_cli,
    inference_gateway,
    live_core,
    model_runtime,
    openai_compatible,
    opencode_hook_cli,
)
from execweave import http_proxy  # noqa: F401 - installs the REQUESTED_MODEL proxy seam
from execweave._http_proxy_base import ProxyConfig
from execweave._http_proxy_stage import record_exchange_fail_open
from execweave.agent_topology import root_topology
from execweave.collector import infer_agent_name
from execweave.schema import Entity, RuntimeEvent
from execweave.semantic import merge_semantic_sidecar

FIXTURES = Path(__file__).parent / "fixtures" / "hooks"
# Feeding marker for a session no observed model fed: the root records it directly.
ROOT = "<root>"


@dataclass(frozen=True)
class ProviderCase:
    name: str
    command: tuple[str, ...]
    # One entry per provider session: the model names that fed it (ROOT when none did).
    feeds: tuple[frozenset[str], ...]
    # (node type, node name) pairs that must render.
    required: tuple[tuple[str, str], ...] = ()
    framework: str | None = None


@dataclass
class ProviderRun:
    case: ProviderCase
    root: Path
    graph: dict[str, Any]
    events: Path
    semantic: Path
    extra: dict[str, Any] = field(default_factory=dict)


def _now(offset: float = 0.0) -> str:
    stamp = datetime.now(timezone.utc) + timedelta(seconds=offset)
    return stamp.isoformat().replace("+00:00", "Z")


def _fixture(provider: str) -> list[dict[str, Any]]:
    return json.loads((FIXTURES / f"{provider}.json").read_text(encoding="utf-8"))["payloads"]


def _hook(main: Callable[[list[str]], int], payload: dict[str, Any], sidecar: Path, *extra: str) -> None:
    stdin = sys.stdin
    sys.stdin = io.StringIO(json.dumps(payload))
    try:
        with redirect_stdout(io.StringIO()):
            code = main(["--sidecar", str(sidecar), "--strict", *extra])
    finally:
        sys.stdin = stdin
    assert code == 0, f"{main.__module__} rejected {payload.get('hook_event_name', extra)}"


def _append(sidecar: Path, records: list[dict[str, Any]]) -> None:
    with sidecar.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record) + "\n")


@contextmanager
def _env(name: str, value: str) -> Iterator[None]:
    previous = os.environ.get(name)
    os.environ[name] = value
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = previous


# ---------------------------------------------------------------- CLI agents


def _claude_fixture(sidecar: Path) -> None:
    for payload in _fixture("claude"):
        _hook(claude_hook_cli.main, payload, sidecar)


def _claude_served_switch(old: str, new: str) -> list[dict[str, Any]]:
    """What claude_model_observer emits when the transcript shows a new served model."""

    def model(name: str) -> dict[str, Any]:
        return {
            "type": "model",
            "id": f"model:claude:{name}",
            "name": name,
            "attributes": {"provider": "claude", "served_model_observation": True},
        }

    main = {"type": "agent", "id": "agent:Claude Code", "name": "Claude Code", "attributes": {}}
    attributes = {
        "provider": "claude",
        "backend": "semantic",
        "attribution": "claude_transcript",
        "evidence_source": "provider_transcript",
        "causal": False,
        "inferred": False,
        "session_id": "fixture-claude-session",
        "previous_served_model": old,
        "runtime_model_transition": True,
    }
    stamp = _now()
    return [
        {
            "timestamp": stamp,
            "event_type": "semantic.claude.model.served",
            "relation": "SERVED_BY_MODEL",
            "source": main,
            "target": model(new),
            "attributes": dict(attributes),
        },
        {
            "timestamp": stamp,
            "event_type": "semantic.claude.model.switched",
            "relation": "SWITCHED_MODEL",
            "source": model(old),
            "target": model(new),
            "attributes": {**attributes, "transition_basis": "consecutive_served_model_observations"},
        },
    ]


def _claude_switch(sidecar: Path, *, archived_root: bool) -> None:
    start, before, after = _fixture("claude")
    _hook(claude_hook_cli.main, {**start, "model": "claude-opus-4-1"}, sidecar)
    _hook(claude_hook_cli.main, before, sidecar)
    _hook(claude_hook_cli.main, after, sidecar)
    _append(sidecar, _claude_served_switch("claude-opus-4-1", "claude-sonnet-4-5"))
    _hook(claude_hook_cli.main, {**before, "tool_use_id": "fixture-call-2"}, sidecar)
    _hook(claude_hook_cli.main, {**after, "tool_use_id": "fixture-call-2"}, sidecar)
    if archived_root:
        # The root entity conversation_archive emits at SessionEnd.
        root = {
            "type": "agent",
            "id": "agent:Claude Code",
            "name": "Claude Code",
            "attributes": {"provider": "claude", "session_id": "fixture-claude-session", **root_topology()},
        }
        _append(
            sidecar,
            [
                {
                    "timestamp": _now(),
                    "event_type": "semantic.claude.conversation.transcript.archived",
                    "relation": "HAS_CONVERSATION_TRANSCRIPT",
                    "source": root,
                    "target": {
                        "type": "observed_content",
                        "id": "observed-content:sha256:" + "a" * 64,
                        "name": "transcript",
                        "attributes": {"content_kind": "claude.conversation_transcript.main"},
                    },
                    "attributes": {"provider": "claude", "backend": "semantic", "causal": False, "inferred": False},
                }
            ],
        )


def _claude_new_session(sidecar: Path) -> None:
    payloads = _fixture("claude")
    for payload in payloads:
        _hook(claude_hook_cli.main, payload, sidecar)
    # /clear (or a second `claude`) inside the same recording.
    for payload in payloads:
        payload = {**payload, "session_id": "fixture-claude-session-2"}
        if payload.get("hook_event_name") == "SessionStart":
            payload.update(model="claude-sonnet-4-5", source="clear")
        if "tool_use_id" in payload:
            payload["tool_use_id"] = f"{payload['tool_use_id']}-s2"
        _hook(claude_hook_cli.main, payload, sidecar)


def _codex_switch(sidecar: Path) -> None:
    start, before, after = _fixture("codex")[:3]
    for payload in (start, before, after):
        _hook(codex_hook_cli.main, payload, sidecar)
    # A resumed SessionStart naming another model on the same provider session.
    _hook(codex_hook_cli.main, {**start, "model": "gpt-5.6-mini", "source": "resume"}, sidecar)
    _hook(
        codex_hook_cli.main,
        {**before, "model": "gpt-5.6-mini", "tool_use_id": "fixture-call-2", "turn_id": "fixture-turn-2"},
        sidecar,
    )


def _codex_new_session(sidecar: Path) -> None:
    payloads = _fixture("codex")[:3]
    for payload in payloads:
        _hook(codex_hook_cli.main, payload, sidecar)
    for payload in payloads:
        payload = {**payload, "session_id": "fixture-codex-session-2", "model": "gpt-5.6-mini"}
        for key in ("tool_use_id", "turn_id"):
            if key in payload:
                payload[key] = f"{payload[key]}-s2"
        _hook(codex_hook_cli.main, payload, sidecar)


def _codex_subagents(sidecar: Path) -> None:
    import test_codex_real_multi_agent_conversation as recorded

    home = sidecar.parent / "codex-home"
    sessions = home / "sessions" / "2026" / "08" / "29"
    sessions.mkdir(parents=True, exist_ok=True)

    def staged(value: str) -> str:
        return str(sessions / Path(value.replace("\\", "/")).name)

    payloads = [
        {key: staged(value) if key.endswith("transcript_path") else value for key, value in payload.items()}
        for payload in recorded._hook_payloads()
    ]
    end = next(p for p in payloads if p["hook_event_name"] == "SessionEnd")
    Path(end["transcript_path"]).write_text(
        (recorded.FIXTURES / "rollout-main.jsonl").read_text(encoding="utf-8"), encoding="utf-8"
    )
    for payload in payloads:
        if payload.get("agent_id") and payload.get("agent_transcript_path"):
            records = recorded._child_rollout_records(payload["agent_id"], recorded.CHILDREN[payload["agent_id"]])
            Path(payload["agent_transcript_path"]).write_text(
                "".join(json.dumps(record) + "\n" for record in records), encoding="utf-8"
            )
    start = {
        **_fixture("codex")[0],
        "session_id": recorded.SESSION_ID,
        "model": "gpt-5.6-terra",
        "transcript_path": end["transcript_path"],
        "cwd": end["cwd"],
    }
    order = [
        start,
        *(p for p in payloads if p["hook_event_name"] == "SubagentStart"),
        *(p for p in payloads if p["hook_event_name"] == "SubagentStop"),
        end,
    ]
    with _env("CODEX_HOME", str(home)):
        for payload in order:
            _hook(codex_hook_cli.main, payload, sidecar)


def _cursor_payloads() -> list[dict[str, Any]]:
    payloads = []
    for payload in _fixture("cursor"):
        if payload.get("hook_event_name") == "sessionStart":
            # The sanitized fixture omits it; the strict contract requires it.
            payload = {**payload, "is_background_agent": False}
        payloads.append(payload)
    return payloads


def _cursor_fixture(sidecar: Path) -> None:
    for payload in _cursor_payloads():
        _hook(cursor_hook_cli.main, payload, sidecar)


def _cursor_switch(sidecar: Path) -> None:
    payloads = _cursor_payloads()
    for payload in payloads:
        _hook(cursor_hook_cli.main, payload, sidecar)
    for payload in payloads:
        payload = {**payload, "model": "gpt-5", "model_id": "gpt-5", "generation_id": "fixture-cursor-generation-2"}
        if "tool_use_id" in payload:
            payload["tool_use_id"] = f"{payload['tool_use_id']}-2"
        _hook(cursor_hook_cli.main, payload, sidecar)


def _opencode_switch(sidecar: Path) -> None:
    payloads = _fixture("opencode")
    for payload in payloads:
        _hook(opencode_hook_cli.main, payload, sidecar)
    _hook(
        opencode_hook_cli.main,
        {
            **payloads[0],
            "messageID": "fixture-message-2",
            "model": {"providerID": "anthropic", "modelID": "claude-sonnet-4-5"},
        },
        sidecar,
    )


def _antigravity_switch_and_new_conversation(sidecar: Path) -> None:
    def invocation(conversation: str, model: str, number: int) -> dict[str, Any]:
        return {
            "conversationId": conversation,
            "executionNum": number,
            "modelName": model,
            "workspacePaths": ["/workspace/x"],
        }

    for event, payload in (
        ("PreInvocation", invocation("conv-A", "gemini-3-pro", 1)),
        ("PostInvocation", invocation("conv-A", "gemini-3-pro", 1)),
        ("PreInvocation", invocation("conv-A", "gemini-3-flash", 2)),  # same conversation, new model
        ("PostInvocation", invocation("conv-A", "gemini-3-flash", 2)),
        ("PreInvocation", invocation("conv-B", "gemini-3-flash", 1)),  # a new conversation
    ):
        _hook(antigravity_hook_cli.main, payload, sidecar, "--event", event)


# ------------------------------------------------- custom scripts and runtimes


def _proxy(sidecar: Path, mode: str, provider: str, upstream: str, models: list[str], path: str) -> None:
    config = ProxyConfig(upstream=upstream, sidecar=sidecar, mode=mode, provider_name=provider)
    for index, model in enumerate(models):
        if mode == "ollama":
            request = {"model": model, "messages": [{"role": "user", "content": f"hi {index}"}], "stream": False}
            response = {
                "model": model,
                "message": {"role": "assistant", "content": "ok"},
                "done": True,
                "done_reason": "stop",
                "created_at": _now(),
                "eval_count": 3,
                "prompt_eval_count": 5,
            }
        else:
            request = {"model": model, "messages": [{"role": "user", "content": f"hi {index}"}]}
            response = {
                "id": f"chatcmpl-{index}",
                "object": "chat.completion",
                "model": model,
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 1, "total_tokens": 6},
            }
        # The proxy handler's two-phase record: request first, then the response.
        common = dict(
            exchange_id=f"ex-{index}",
            request_body=json.dumps(request).encode(),
            request_content_type="application/json",
            method="POST",
            request_path=path,
        )
        recorded = record_exchange_fail_open(
            config, **common, status=None, response_body=b"", response_content_type=None, request_only=True
        )
        answered = record_exchange_fail_open(
            config,
            **common,
            status=200,
            response_body=json.dumps(response).encode(),
            response_content_type="application/json",
            request_recorded=recorded,
        )
        assert recorded and answered, f"proxy did not record {model}"


def _python_openai_proxy(sidecar: Path) -> None:
    _proxy(sidecar, "openai-compatible", "openai", "http://127.0.0.1:9", ["gpt-4.1", "gpt-4.1-mini"], "/v1/chat/completions")


def _python_ollama_proxy(sidecar: Path) -> None:
    _proxy(sidecar, "ollama", "ollama", "http://127.0.0.1:11434", ["llama3.2", "qwen3"], "/api/chat")


def _ollama_interactive(sidecar: Path) -> None:
    _proxy(sidecar, "ollama", "ollama", "http://127.0.0.1:11434", ["llama3.2"], "/api/chat")
    _append(
        sidecar,
        model_runtime.ollama_ps_to_events(
            {"models": [{"name": "llama3.2", "model": "llama3.2", "size": 1}]},
            endpoint="http://localhost:11434",
            timestamp=_now(),
        ),
    )


def _anthropic_sdk(sidecar: Path) -> None:
    records: list[dict[str, Any]] = []
    for index, model in enumerate(["claude-opus-4-1", "claude-sonnet-4-5"]):
        records += anthropic.response_to_events(
            {
                "id": f"msg_{index}",
                "type": "message",
                "model": model,
                "role": "assistant",
                "content": [{"type": "text", "text": "ok"}],
                "usage": {"input_tokens": 3, "output_tokens": 1},
            },
            endpoint="https://api.anthropic.com",
            requested_model=model,
            timestamp=_now(),
        )
    _append(sidecar, records)


def _openai_sdk(sidecar: Path) -> None:
    records: list[dict[str, Any]] = []
    for index, model in enumerate(["gpt-4.1", "gpt-4.1-mini"]):
        records += openai_compatible.response_to_events(
            {"id": f"cmpl-{index}", "model": model, "choices": [], "usage": {"prompt_tokens": 1}},
            endpoint="https://api.openai.com/v1",
            provider_name="openai",
            requested_model=model,
            timestamp=_now(),
        )
    _append(sidecar, records)


def _litellm_gateway(sidecar: Path) -> None:
    _append(
        sidecar,
        inference_gateway.gateway_response_to_events(
            {"id": "gw-1", "model": "openai/gpt-4.1"},
            gateway_name="litellm",
            endpoint="http://127.0.0.1:4000",
            requested_model="smart",
            resolved_model="openai/gpt-4.1",
            provider_name="openai",
            timestamp=_now(),
        ),
    )


def _openrouter(sidecar: Path) -> None:
    records: list[dict[str, Any]] = []
    for index, (requested, resolved, provider) in enumerate(
        [
            ("openrouter/auto", "anthropic/claude-sonnet-4.5", "anthropic"),
            ("openai/gpt-4.1", "openai/gpt-4.1", "openai"),
        ]
    ):
        records += inference_gateway.openrouter_response_to_events(
            {"id": f"gen-{index}", "model": resolved},
            requested_model=requested,
            resolved_model=resolved,
            provider_name=provider,
            timestamp=_now(),
        )
    _append(sidecar, records)


def _ollama_runtime_probe(sidecar: Path) -> None:
    _append(
        sidecar,
        model_runtime.ollama_response_to_events(
            {"model": "llama3.2", "created_at": _now(), "done": True, "eval_count": 2}, timestamp=_now()
        ),
    )
    _append(
        sidecar,
        model_runtime.ollama_ps_to_events(
            {"models": [{"name": "llama3.2", "model": "llama3.2"}, {"name": "qwen3", "model": "qwen3"}]},
            endpoint="http://localhost:11434",
            timestamp=_now(),
        ),
    )


def _local_server(runtime: str, port: int, models_to_events: Callable[..., list[dict[str, Any]]], models: list[str]):
    def produce(sidecar: Path) -> None:
        _append(
            sidecar,
            models_to_events(
                {"object": "list", "data": [{"id": model, "object": "model"} for model in models]},
                endpoint=f"http://127.0.0.1:{port}",
                timestamp=_now(),
            ),
        )
        _proxy(sidecar, "openai-compatible", runtime, f"http://127.0.0.1:{port}", models, "/v1/chat/completions")

    return produce


# ------------------------------------------------------------- frameworks

FRAMEWORK_CODE = {
    "camel_framework": """
from execweave.framework_adapters import AdapterContext, CAMELAdapter
ad = CAMELAdapter(AdapterContext.from_environment("camel", capture_mode="prompt_and_response"))
planner = ad.agent_created("planner", name="Planner", role="planner")
worker = ad.agent_created("worker", name="Worker", role="worker")
task = ad.task_created("task-1", name="Summarize", content="Summarize the report")
ad.task_assigned(task, worker)
ad.message("m1", planner, worker, content="Please summarize.", role="assistant", task=task)
ad.model_call("c1", worker, "llama3.2", request={"messages": [{"role": "user", "content": "hi"}]}, status="request", task=task)
ad.model_call("c1", worker, "llama3.2", response={"content": "done"}, status="response", task=task)
ad.model_call("c2", worker, "qwen3", request={"messages": [{"role": "user", "content": "again"}]}, status="request", task=task)
ad.model_call("c2", worker, "qwen3", response={"content": "done2"}, status="response", task=task)
ad.message("m2", worker, planner, content="Summary ready.", role="assistant", task=task)
""",
    "camel_children": """
from execweave.framework_adapters import AdapterContext, CAMELAdapter
ad = CAMELAdapter(AdapterContext.from_environment("camel", capture_mode="prompt_and_response"))
coord = ad.agent_created("coordinator", name="Coordinator", role="coordinator")
a = ad.agent_created("researcher", name="Researcher", role="worker", parent=coord)
b = ad.agent_created("writer", name="Writer", role="worker", parent=coord)
t1 = ad.task_created("t1", name="Research", content="Find sources", owner=coord)
t2 = ad.task_created("t2", name="Write", content="Write summary", owner=coord)
ad.task_assigned(t1, a); ad.task_assigned(t2, b)
ad.message("m1", coord, a, content="Go research", task=t1)
ad.model_call("c1", a, "qwen3", request={"q": 1}, status="request", task=t1)
ad.model_call("c1", a, "qwen3", response={"a": 1}, status="response", task=t1)
ad.message("m2", a, b, content="Sources", task=t2)
ad.model_call("c2", b, "qwen3", request={"q": 2}, status="request", task=t2)
ad.model_call("c2", b, "qwen3", response={"a": 2}, status="response", task=t2)
ad.message("m3", b, coord, content="Done", task=t2)
ad.task_completed(t2, b)
""",
    "autogen_framework": """
from execweave.framework_adapters import AdapterContext, AutoGenAdapter
ad = AutoGenAdapter(AdapterContext.from_environment("autogen", capture_mode="prompt_and_response"))
user = ad.observe_agent("user_proxy", name="UserProxy", role="user_proxy")
asst = ad.observe_agent("assistant", name="Assistant", role="assistant")
task = ad.observe_task("t1", owner=user, name="Weather", content="Weather in Taipei?")
ad.observe_message("m1", source=user, target=asst, content="Weather in Taipei?", task=task)
ad.observe_message("m1", source=user, target=asst, content="Weather in Taipei?", task=task, received=True)
ad.observe_model_call("c1", agent=asst, model_id="gpt-4.1-mini", request={"messages": ["w"]}, status="request")
ad.observe_model_call("c1", agent=asst, model_id="gpt-4.1-mini", response={"tool": "get_weather"}, status="response")
ad.observe_tool_call("k1", agent=asst, tool_id="get_weather", arguments={"city": "Taipei"}, status="call")
ad.observe_tool_call("k1", agent=asst, tool_id="get_weather", result={"temp": 30}, status="result")
ad.observe_tool_call("k2", agent=asst, tool_id="get_weather", arguments={"city": "?"}, status="call")
ad.observe_tool_call("k2", agent=asst, tool_id="get_weather", result="bad city", status="failed")
ad.observe_model_call("c2", agent=asst, model_id="gpt-4.1", request={"messages": ["w2"]}, status="request")
ad.observe_model_call("c2", agent=asst, model_id="gpt-4.1", response="rate limited", status="failed")
ad.observe_model_call("c3", agent=asst, model_id="gpt-4.1", request={"messages": ["w3"]}, status="request")
ad.observe_model_call("c3", agent=asst, model_id="gpt-4.1", response={"content": "30C"}, status="response")
ad.observe_message("m2", source=asst, target=user, content="30C", task=task)
ad.observe_message("m2", source=asst, target=user, content="30C", task=task, received=True)
ad.observe_task("t1", owner=asst, status="completed")
""",
    "metagpt_framework": """
from execweave.framework_adapters import AdapterContext, MetaGPTAdapter
ad = MetaGPTAdapter(AdapterContext.from_environment("metagpt", capture_mode="prompt_and_response"))
pm = ad.observe_role("pm", name="Alice", role="ProductManager")
eng = ad.observe_role("eng", name="Bob", role="Engineer")
task = ad.observe_task("req", owner=pm, name="Build CLI", content="Build a CLI")
ad.observe_message("u1", source=ad.entity("user", "user", name="user"), target=pm, content="Build a CLI", received=True)
ad.observe_action("WritePRD", owner=pm, task=task)
ad.observe_model_call("c1", role=pm, model_id="qwen3", request={"p": "prd"}, status="request")
ad.observe_model_call("c1", role=pm, model_id="qwen3", response={"prd": "x"}, status="response")
ad.observe_action("WritePRD", owner=pm, task=task, status="completed")
ad.observe_message("m1", source=pm, target=eng, content="PRD ready")
ad.observe_message("m1", source=pm, target=eng, content="PRD ready", received=True)
ad.observe_model_call("c2", role=eng, model_id="llama3.2", request={"p": "code"}, status="request")
ad.observe_parser_failure("p1", role=eng, error="bad json", task=task)
ad.observe_retry("r1", role=eng, task=task)
ad.observe_model_call("c2", role=eng, model_id="llama3.2", response={"code": "y"}, status="response")
ad.observe_message("m2", source=eng, target=pm, content="Code ready")
""",
    # A user's own CAMEL script whose model calls go through the Ollama proxy.
    "camel_ollama": """
import json, os
from pathlib import Path
from execweave.framework_adapters import AdapterContext, CAMELAdapter
from execweave import http_proxy  # noqa: F401
from execweave._http_proxy_base import ProxyConfig
from execweave._http_proxy_stage import record_exchange_fail_open
cfg = ProxyConfig(upstream="http://127.0.0.1:11434", sidecar=Path(os.environ["EXECWEAVE_SEMANTIC_SIDECAR"]), mode="ollama", provider_name="ollama")
def wire(i, m):
    req = {"model": m, "messages": [{"role": "user", "content": f"hi {i}"}], "stream": False}
    resp = {"model": m, "message": {"role": "assistant", "content": "ok"}, "done": True, "done_reason": "stop", "eval_count": 3, "prompt_eval_count": 5}
    common = dict(exchange_id=f"ex-{i}", request_body=json.dumps(req).encode(), request_content_type="application/json", method="POST", request_path="/api/chat")
    rec = record_exchange_fail_open(cfg, **common, status=None, response_body=b"", response_content_type=None, request_only=True)
    assert rec and record_exchange_fail_open(cfg, **common, status=200, response_body=json.dumps(resp).encode(), response_content_type="application/json", request_recorded=rec)
ad = CAMELAdapter(AdapterContext.from_environment("camel", capture_mode="prompt_and_response"))
planner = ad.agent_created("planner", name="Planner", role="planner")
worker = ad.agent_created("worker", name="Worker", role="worker")
ad.message("m1", planner, worker, content="Please summarize.", role="assistant")
ad.model_call("c1", worker, "llama3.2", request={"messages": [{"role": "user", "content": "hi"}]}, status="request")
wire(1, "llama3.2")
ad.model_call("c1", worker, "llama3.2", response={"content": "done"}, status="response")
ad.model_call("c2", planner, "qwen3", request={"messages": [{"role": "user", "content": "again"}]}, status="request")
wire(2, "qwen3")
ad.model_call("c2", planner, "qwen3", response={"content": "done2"}, status="response")
ad.message("m2", worker, planner, content="Summary ready.", role="assistant")
""",
}


# ------------------------------------------------------------------ cases


def _f(*models: str) -> frozenset[str]:
    return frozenset(models)


_CLAUDE_TOOL = ("tool", _fixture("claude")[1]["tool_name"])
_CODEX_MODEL = _fixture("codex")[0]["model"]
_CURSOR_MODEL = _fixture("cursor")[0]["model_id"]
_CURSOR_TOOL = ("tool", _fixture("cursor")[1]["tool_name"])
_OPENCODE_FIRST = _fixture("opencode")[0]["model"]
_OPENCODE_MODEL = f"{_OPENCODE_FIRST['providerID']}/{_OPENCODE_FIRST['modelID']}"
_OPENCODE_TOOL = ("tool", _fixture("opencode")[1]["tool"])
_CODEX_SUBAGENTS = (
    ("agent", "/root/rain_forecast"),
    ("agent", "/root/official_alerts"),
    ("agent", "/root/hydrology"),
    ("agent", "/root/forecast_consensus"),
)

_PRODUCERS: dict[str, Callable[[Path], None]] = {}


def _case(name: str, command: list[str], produce: Callable[[Path], None] | None, feeds, required=(), framework=None):
    if produce is not None:
        _PRODUCERS[name] = produce
    return ProviderCase(name, tuple(command), tuple(feeds), tuple(required), framework)


CASES: tuple[ProviderCase, ...] = (
    _case("claude_fixture", ["claude"], _claude_fixture, [_f(ROOT)], [_CLAUDE_TOOL]),
    _case(
        "claude_switch_root",
        ["claude"],
        lambda sidecar: _claude_switch(sidecar, archived_root=True),
        [_f("claude-opus-4-1", "claude-sonnet-4-5")],
        [_CLAUDE_TOOL],
    ),
    _case(
        "claude_switch_noroot",
        ["claude"],
        lambda sidecar: _claude_switch(sidecar, archived_root=False),
        [_f("claude-opus-4-1", "claude-sonnet-4-5")],
        [_CLAUDE_TOOL],
    ),
    _case("claude_newsession", ["claude"], _claude_new_session, [_f(ROOT), _f("claude-sonnet-4-5")], [_CLAUDE_TOOL]),
    _case("codex_switch", ["codex"], _codex_switch, [_f(_CODEX_MODEL, "gpt-5.6-mini")], [("tool", "Bash")]),
    _case("codex_newsession", ["codex"], _codex_new_session, [_f(_CODEX_MODEL), _f("gpt-5.6-mini")], [("tool", "Bash")]),
    _case("codex_subagents", ["codex"], _codex_subagents, [_f("gpt-5.6-terra")], _CODEX_SUBAGENTS),
    _case("cursor_fixture", ["cursor-agent"], _cursor_fixture, [_f(_CURSOR_MODEL)], [_CURSOR_TOOL]),
    _case("cursor_switch", ["cursor-agent"], _cursor_switch, [_f(_CURSOR_MODEL, "gpt-5")], [_CURSOR_TOOL]),
    _case(
        "opencode_switch",
        ["opencode"],
        _opencode_switch,
        [_f(_OPENCODE_MODEL, "anthropic/claude-sonnet-4-5")],
        [_OPENCODE_TOOL],
    ),
    _case(
        "antigravity_switch_newconv",
        ["agy"],
        _antigravity_switch_and_new_conversation,
        [_f("gemini-3-pro", "gemini-3-flash"), _f("gemini-3-flash")],
    ),
    _case("python_openai_proxy", ["python", "script.py"], _python_openai_proxy, [_f("gpt-4.1", "gpt-4.1-mini")]),
    _case("python_ollama_proxy", ["python", "script.py"], _python_ollama_proxy, [_f("llama3.2", "qwen3")]),
    _case(
        "ollama_interactive",
        ["ollama", "run", "llama3.2"],
        _ollama_interactive,
        [_f("llama3.2")],
        [("model_runtime", "ollama")],
    ),
    _case(
        "anthropic_sdk",
        ["python", "script.py"],
        _anthropic_sdk,
        [_f("claude-opus-4-1", "claude-sonnet-4-5")],
        [("inference_api", "anthropic")],
    ),
    _case(
        "openai_sdk",
        ["python", "script.py"],
        _openai_sdk,
        [_f("gpt-4.1", "gpt-4.1-mini")],
        [("inference_api", "openai")],
    ),
    _case(
        "litellm_gateway",
        ["python", "script.py"],
        _litellm_gateway,
        [_f("openai/gpt-4.1")],
        [("inference_gateway", "litellm"), ("inference_provider", "openai")],
    ),
    _case(
        "openrouter",
        ["python", "script.py"],
        _openrouter,
        [_f("anthropic/claude-sonnet-4.5", "openai/gpt-4.1")],
        [("inference_gateway", "openrouter"), ("inference_provider", "openai"), ("inference_provider", "anthropic")],
    ),
    _case(
        "ollama_runtime_probe",
        ["python", "script.py"],
        _ollama_runtime_probe,
        [_f("llama3.2")],
        [("model_runtime", "ollama"), ("model", "qwen3")],
    ),
    _case(
        "llamacpp_server",
        ["llama-server", "-m", "qwen3-8b.gguf"],
        _local_server("llamacpp", 8080, model_runtime.llamacpp_models_to_events, ["qwen3-8b.gguf", "llama3.2-3b.gguf"]),
        [_f("qwen3-8b.gguf", "llama3.2-3b.gguf")],
        [("model_runtime", "llamacpp")],
    ),
    _case(
        "vllm_server",
        ["vllm", "serve", "Qwen/Qwen3-8B"],
        _local_server("vllm", 8000, model_runtime.vllm_models_to_events, ["Qwen/Qwen3-8B", "meta-llama/Llama-3.2-3B"]),
        [_f("Qwen/Qwen3-8B", "meta-llama/Llama-3.2-3B")],
        [("model_runtime", "vllm")],
    ),
    _case(
        "lmstudio_server",
        ["lms", "server", "start"],
        _local_server("lmstudio", 1234, model_runtime.lmstudio_models_to_events, ["qwen3-8b", "llama-3.2-3b"]),
        [_f("qwen3-8b", "llama-3.2-3b")],
        [("model_runtime", "lmstudio")],
    ),
    _case(
        "camel_framework",
        ["python"],
        None,
        [_f("llama3.2", "qwen3")],
        [("agent", "Planner"), ("agent", "Worker")],
        framework="camel_framework",
    ),
    _case(
        "camel_children",
        ["python"],
        None,
        [_f("qwen3")],
        [("agent", "Coordinator"), ("agent", "Researcher"), ("agent", "Writer")],
        framework="camel_children",
    ),
    _case(
        "autogen_framework",
        ["python"],
        None,
        [_f("gpt-4.1-mini", "gpt-4.1")],
        [("agent", "UserProxy"), ("agent", "Assistant"), ("tool", "get_weather")],
        framework="autogen_framework",
    ),
    _case(
        "metagpt_framework",
        ["python"],
        None,
        [_f("qwen3", "llama3.2")],
        [("agent", "Alice"), ("agent", "Bob")],
        framework="metagpt_framework",
    ),
    _case(
        "camel_ollama",
        ["python"],
        None,
        [_f("llama3.2", "qwen3")],
        [("agent", "Planner"), ("agent", "Worker")],
        framework="camel_ollama",
    ),
)


def _write_events(path: Path, events: list[RuntimeEvent], start: int) -> int:
    with path.open("a", encoding="utf-8") as handle:
        for offset, event in enumerate(events, start=1):
            record = event.to_dict()
            record["sequence"] = start + offset
            handle.write(json.dumps(record, sort_keys=True) + "\n")
    return start + len(events)


def build(case: ProviderCase, root: Path) -> ProviderRun:
    """Record one case under ``root`` and build its final graph."""
    root.mkdir(parents=True, exist_ok=True)
    if case.framework is not None:
        return _build_framework(case, root)
    session_id = f"run-{case.name}"
    events = root / "events.jsonl"
    sidecar = root / "semantic.jsonl"
    command = list(case.command)
    agent_name = infer_agent_name(command)
    agent = Entity(type="agent", id=f"agent:{agent_name}", name=agent_name)
    session = Entity(type="session", id=f"session:{session_id}", name=session_id, attributes={"command": command})
    process = Entity(type="process", id=f"process:{session_id}:4242", name=command[0], attributes={"pid": 4242})
    output = f"/workspace/{case.name}/out.txt"
    changed = Entity(type="file", id=f"file:{output}", name="out.txt", attributes={"path": output})
    sequence = _write_events(
        events,
        [
            RuntimeEvent.create(
                session_id=session_id,
                event_type="session.started",
                relation="STARTED_SESSION",
                source=agent,
                target=session,
                timestamp=_now(-5),
            ),
            RuntimeEvent.create(
                session_id=session_id,
                event_type="process.started",
                relation="LAUNCHED",
                source=session,
                target=process,
                timestamp=_now(-4),
            ),
        ],
        0,
    )
    sidecar.touch()
    _PRODUCERS[case.name](sidecar)
    _write_events(
        events,
        [
            RuntimeEvent.create(
                session_id=session_id,
                event_type="filesystem.modified",
                relation="OBSERVED_FILE_CHANGE",
                source=session,
                target=changed,
                timestamp=_now(1),
            ),
            RuntimeEvent.create(
                session_id=session_id,
                event_type="session.finished",
                relation="FINISHED_SESSION",
                source=session,
                timestamp=_now(5),
            ),
        ],
        sequence,
    )
    merged = root / "events.semantic.jsonl"
    merge_semantic_sidecar(events, sidecar, merged)
    graph = live_core.build_execution_graph(merged).to_dict()
    required = (*case.required, ("process", command[0]), ("file", "out.txt"))
    return ProviderRun(case, root, graph, events, sidecar, {"required": required})


def _build_framework(case: ProviderCase, root: Path) -> ProviderRun:
    from execweave.workflow import record_to_viewer

    source = Path(execweave.__file__).resolve().parent.parent
    code = f"import sys\nsys.path.insert(0, {str(source)!r})\n" + FRAMEWORK_CODE[case.framework]
    output = root / "rec"
    result = record_to_viewer(
        [sys.executable, "-c", code],
        watch_root=root,
        output_dir=output,
        backend="portable",
        poll_interval=0.05,
        collect_filesystem=False,
        collect_network=False,
        open_browser=False,
    )
    assert result.return_code == 0, f"{case.name} framework script failed"
    graph = json.loads(Path(result.graph).read_text(encoding="utf-8"))
    return ProviderRun(
        case,
        root,
        graph,
        output / "events.jsonl",
        output / "semantic.jsonl",
        {"required": case.required},
    )


def live_inputs(run: ProviderRun, directory: Path) -> tuple[str, Path, Path]:
    """The same streams as they stand mid-recording (before session.finished)."""
    directory.mkdir(parents=True, exist_ok=True)
    events = [
        json.loads(line)
        for line in run.events.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    events = [event for event in events if event.get("event_type") != "session.finished"]
    event_path = directory / "events.jsonl"
    event_path.write_text("".join(json.dumps(e, sort_keys=True) + "\n" for e in events), encoding="utf-8")
    semantic_path = directory / "semantic.jsonl"
    shutil.copyfile(run.semantic, semantic_path)
    return events[0]["session_id"], event_path, semantic_path
