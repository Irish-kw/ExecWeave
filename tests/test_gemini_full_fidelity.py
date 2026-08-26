from __future__ import annotations

import json
from pathlib import Path

import execweave.gemini_hook_cli as hook_cli
from execweave.content_store import FullFidelityContentStore
from execweave.gemini_full_fidelity import gemini_hook_to_content_events


def _base(event: str) -> dict:
    return {
        "cwd": "/repo",
        "hook_event_name": event,
        "session_id": "gemini-session-1",
        "timestamp": "2026-08-26T12:00:00Z",
        "transcript_path": "/private/transcript.json",
    }


def _read_content(root: Path, event: dict) -> object:
    path = root / event["attributes"]["content_path"]
    if path.suffix == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    return path.read_text(encoding="utf-8")


def test_before_agent_preserves_large_prompt_verbatim(tmp_path: Path) -> None:
    prompt = "A" * 12000 + "\x00tail"
    events = gemini_hook_to_content_events(
        {**_base("BeforeAgent"), "prompt": prompt},
        store=FullFidelityContentStore(tmp_path),
    )
    prompt_event = next(event for event in events if event["relation"] == "RECEIVED_USER_PROMPT")
    assert _read_content(tmp_path, prompt_event) == prompt
    assert prompt_event["attributes"]["content_complete_from_source"] is True
    assert prompt not in json.dumps(prompt_event)


def test_before_model_preserves_full_request_and_application_fields(tmp_path: Path) -> None:
    request = {
        "model": "gemini-2.5-pro",
        "messages": [{"role": "user", "content": "inspect everything"}],
        "config": {"temperature": 0.2, "api_key": "inside-request-must-survive"},
        "toolConfig": {"mode": "AUTO", "allowedFunctionNames": ["read_file"]},
    }
    events = gemini_hook_to_content_events(
        {**_base("BeforeModel"), "llm_request": request},
        store=FullFidelityContentStore(tmp_path),
    )
    event = next(event for event in events if event["attributes"]["observed_field"] == "llm_request")
    assert _read_content(tmp_path, event) == request
    assert event["attributes"]["final_request_after_all_hooks_asserted"] is False


def test_after_model_preserves_request_response_chunk_and_usage(tmp_path: Path) -> None:
    request = {"model": "gemini-2.5-pro", "messages": [{"role": "user", "content": "x"}]}
    response = {
        "candidates": [
            {"content": {"role": "model", "parts": ["chunk text"]}, "finishReason": "STOP"}
        ],
        "usageMetadata": {"totalTokenCount": 42},
    }
    events = gemini_hook_to_content_events(
        {**_base("AfterModel"), "llm_request": request, "llm_response": response},
        store=FullFidelityContentStore(tmp_path),
    )
    response_event = next(
        event for event in events if event["relation"] == "RECEIVED_LLM_RESPONSE_CHUNK"
    )
    assert _read_content(tmp_path, response_event) == response
    assert response_event["attributes"]["streaming_chunk"] is True


def test_after_tool_preserves_full_input_and_output_without_direct_link_claim(tmp_path: Path) -> None:
    tool_input = {"path": "secret.txt", "api_key": "tool-content-must-survive"}
    tool_response = {
        "llmContent": "complete tool output",
        "returnDisplay": "display output",
        "error": None,
    }
    events = gemini_hook_to_content_events(
        {
            **_base("AfterTool"),
            "tool_name": "read_file",
            "tool_input": tool_input,
            "tool_response": tool_response,
        },
        store=FullFidelityContentStore(tmp_path),
    )
    input_event = next(event for event in events if event["attributes"]["observed_field"] == "tool_input")
    output_event = next(event for event in events if event["attributes"]["observed_field"] == "tool_response")
    assert _read_content(tmp_path, input_event) == tool_input
    assert _read_content(tmp_path, output_event) == tool_response
    assert input_event["attributes"]["direct_before_after_linkage_asserted"] is False
    assert output_event["source"]["type"] == "tool_call_observation"


def test_provider_metadata_is_complete_except_transport_credentials(tmp_path: Path) -> None:
    payload = {
        **_base("BeforeTool"),
        "tool_name": "mcp_acme_search",
        "tool_input": {"query": "x"},
        "authorization": "Bearer top-level-secret",
        "mcp_context": {
            "server_name": "acme",
            "tool_name": "search",
            "command": "npx",
            "args": ["--token", "application-level-value"],
            "url": "https://example.invalid/mcp",
            "authorization": "Bearer nested-secret",
        },
    }
    events = gemini_hook_to_content_events(
        payload,
        store=FullFidelityContentStore(tmp_path),
    )
    metadata_event = next(
        event for event in events if event["relation"] == "OBSERVED_PROVIDER_METADATA"
    )
    metadata = _read_content(tmp_path, metadata_event)
    assert metadata["mcp_context"]["command"] == "npx"
    assert metadata["mcp_context"]["args"] == ["--token", "application-level-value"]
    assert metadata["mcp_context"]["url"] == "https://example.invalid/mcp"
    assert "authorization" not in metadata
    assert "authorization" not in metadata["mcp_context"]
    assert metadata_event["attributes"]["transport_credentials_excluded"] == [
        "authorization",
        "mcp_context.authorization",
    ]


def test_after_agent_preserves_final_response(tmp_path: Path) -> None:
    response = "final answer with full detail"
    events = gemini_hook_to_content_events(
        {**_base("AfterAgent"), "prompt": "question", "prompt_response": response},
        store=FullFidelityContentStore(tmp_path),
    )
    final_event = next(
        event for event in events if event["relation"] == "PRODUCED_ASSISTANT_RESPONSE"
    )
    assert _read_content(tmp_path, final_event) == response


def test_identical_prompt_values_dedupe_to_same_content_hash(tmp_path: Path) -> None:
    prompt = "same prompt"
    store = FullFidelityContentStore(tmp_path)
    before = gemini_hook_to_content_events(
        {**_base("BeforeAgent"), "prompt": prompt},
        store=store,
    )
    after = gemini_hook_to_content_events(
        {**_base("AfterAgent"), "prompt": prompt, "prompt_response": "done"},
        store=store,
    )
    before_prompt = next(event for event in before if event["attributes"]["observed_field"] == "prompt")
    after_prompt = next(event for event in after if event["attributes"]["observed_field"] == "prompt")
    assert before_prompt["attributes"]["content_sha256"] == after_prompt["attributes"]["content_sha256"]
    assert before_prompt["attributes"]["content_path"] == after_prompt["attributes"]["content_path"]


def test_hook_cli_is_fail_open_after_summary_is_written(tmp_path: Path, monkeypatch) -> None:
    sidecar = tmp_path / "semantic.jsonl"
    payload = {**_base("BeforeTool"), "tool_name": "run_shell_command", "tool_input": {"command": "echo hi"}}
    summary = {
        "timestamp": payload["timestamp"],
        "event_type": "semantic.gemini.tool.requested",
        "relation": "REQUESTED_TOOL_CALL",
        "source": {"type": "agent", "id": "agent:Gemini CLI", "name": "Gemini CLI", "attributes": {}},
        "target": {"type": "tool_call", "id": "tool-call:test", "name": "run_shell_command", "attributes": {}},
        "attributes": {"provider": "gemini", "backend": "semantic", "causal": False},
    }
    monkeypatch.setattr(hook_cli, "read_hook_payload", lambda: payload)
    monkeypatch.setattr(hook_cli, "gemini_hook_to_semantic_events", lambda *_args, **_kwargs: [summary])
    monkeypatch.setattr(
        hook_cli,
        "gemini_hook_to_content_events",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("content store failed")),
    )
    assert hook_cli.main(["--sidecar", str(sidecar)]) == 0
    lines = [json.loads(line) for line in sidecar.read_text(encoding="utf-8").splitlines()]
    assert lines == [summary]
