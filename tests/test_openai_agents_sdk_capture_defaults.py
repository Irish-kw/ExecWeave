"""Regression gates for the opt-in Agents SDK recorder's local content default.

Uses synthetic SDK callback objects and a private temporary run; no LLM call.
"""
from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path
from types import SimpleNamespace as NS

from execweave.openai_agents_sdk import (
    AgentsSDKTraceProcessor,
    install_agents_sdk_tracing,
)


def _setup(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("EXECWEAVE_SESSION_ID", "sdk-local-default-fixture")
    monkeypatch.setenv("EXECWEAVE_RUN_ID", "sdk-local-default-fixture")
    monkeypatch.setenv("EXECWEAVE_SEMANTIC_SIDECAR", str(tmp_path / "semantic.jsonl"))


def _capture(mode=None):
    processor = AgentsSDKTraceProcessor() if mode is None else AgentsSDKTraceProcessor(capture_mode=mode)
    trace = NS(trace_id="default-content-fixture", group_id=None)
    agent = NS(
        trace_id=trace.trace_id, span_id="agent1", parent_id=None, error=None,
        span_data=NS(type="agent", name="FixtureAgent", tools=["ping"]),
    )
    model = NS(
        trace_id=trace.trace_id, span_id="model1", parent_id="agent1", error=None,
        span_data=NS(
            type="generation", model="fixture-model",
            input=[{
                "role": "user", "content": "SAFE_VISIBLE_PROMPT",
                "api_key": "DUMMY_API_KEY_VALUE",
                "Authorization": "DUMMY_AUTHORIZATION_VALUE",
                "Cookie": "DUMMY_COOKIE_VALUE",
            }],
            output=[{
                "content": "SAFE_VISIBLE_RESPONSE",
                "access_token": "DUMMY_TOKEN_VALUE",
                "reasoning": "DUMMY_PRIVATE_REASONING",
            }],
        ),
    )
    tool = NS(
        trace_id=trace.trace_id, span_id="tool1", parent_id="agent1", error=None,
        span_data=NS(type="function", name="ping", input="{}", output="EXECWEAVE_PONG_OK"),
    )
    processor.on_trace_start(trace)
    for span in (agent, model, tool):
        processor.on_span_start(span)
    for span in (tool, model, agent):
        processor.on_span_end(span)
    processor.on_trace_end(trace)
    assert processor.callback_errors == 0
    return processor


def _events(tmp_path: Path):
    return [
        json.loads(line)
        for line in (tmp_path / "semantic.jsonl").read_text(encoding="utf-8").splitlines()
    ]


def test_sdk_install_api_and_processor_default_to_local_prompt_response(tmp_path, monkeypatch):
    _setup(monkeypatch, tmp_path)
    assert inspect.signature(install_agents_sdk_tracing).parameters["capture_mode"].default == "prompt_and_response"
    processor = _capture()
    assert processor.capture_mode == "prompt_and_response"
    events = _events(tmp_path)
    assert any(e["event_type"] == "MODEL_REQUEST" for e in events)
    assert any(e["event_type"] == "MODEL_RESPONSE" for e in events)
    assert any(e["event_type"] == "TOOL_RESULT" for e in events)

    content_events = [
        e for e in events if e["event_type"] in ("MODEL_CONTENT_RECORDED", "TOOL_CONTENT_RECORDED")
    ]
    assert len(content_events) >= 3, "request, response, and tool result must have local content"
    content_paths = set()
    for event in content_events:
        attr = event["attributes"]
        assert attr["content_available"] is True
        relative = Path(attr["content_ref"])
        assert not relative.is_absolute()
        path = (tmp_path / relative).resolve()
        assert path.is_relative_to(tmp_path.resolve())
        assert path.is_file()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == attr["content_sha256"]
        content_paths.add(path)
    assert len(content_paths) >= 3
    all_content = "\n".join(p.read_text(encoding="utf-8") for p in content_paths)
    for expected in ("SAFE_VISIBLE_PROMPT", "SAFE_VISIBLE_RESPONSE", "EXECWEAVE_PONG_OK"):
        assert expected in all_content


def test_sdk_default_filters_structured_credential_and_hidden_reasoning_fields(tmp_path, monkeypatch):
    _setup(monkeypatch, tmp_path)
    _capture()
    paths = [p for p in (tmp_path / "content").rglob("*") if p.is_file()]
    assert paths, "local content store must not silently be empty"
    all_artifacts = (tmp_path / "semantic.jsonl").read_text(encoding="utf-8")
    all_artifacts += "\n" + "\n".join(p.read_text(encoding="utf-8") for p in paths)
    for forbidden in (
        "DUMMY_API_KEY_VALUE", "DUMMY_AUTHORIZATION_VALUE",
        "DUMMY_COOKIE_VALUE", "DUMMY_TOKEN_VALUE", "DUMMY_PRIVATE_REASONING",
    ):
        assert forbidden not in all_artifacts


def test_sdk_explicit_metadata_only_keeps_lifecycle_without_content_files(tmp_path, monkeypatch):
    _setup(monkeypatch, tmp_path)
    processor = _capture("metadata_only")
    assert processor.capture_mode == "metadata_only"
    events = _events(tmp_path)
    kinds = {event["event_type"] for event in events}
    assert {"MODEL_REQUEST", "MODEL_RESPONSE", "TOOL_CALL", "TOOL_RESULT"} <= kinds
    assert not any("content_ref" in (event.get("attributes") or {}) for event in events)
    assert not (tmp_path / "content").exists()
    raw = (tmp_path / "semantic.jsonl").read_text(encoding="utf-8")
    assert "SAFE_VISIBLE_PROMPT" not in raw
    assert "SAFE_VISIBLE_RESPONSE" not in raw
    assert "EXECWEAVE_PONG_OK" not in raw
