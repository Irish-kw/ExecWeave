from __future__ import annotations

import json
import os
from pathlib import Path

from execweave.content_evidence import content_observation_event, filter_transport_credentials
from execweave.content_store import FullFidelityContentStore


def test_content_store_preserves_complete_text_and_deduplicates(tmp_path: Path) -> None:
    store = FullFidelityContentStore(tmp_path)
    text = "system prompt\nuser secret-in-prompt=keep-me\n" * 200

    first = store.put_text(text, content_kind="prompt")
    second = store.put_text(text, content_kind="prompt")

    assert first == second
    assert first.size_bytes == len(text.encode("utf-8"))
    assert first.complete_from_source is True
    assert (tmp_path / first.path).read_text(encoding="utf-8") == text
    if os.name != "nt":
        assert (tmp_path / first.path).stat().st_mode & 0o077 == 0


def test_json_store_preserves_nested_tool_input_and_output(tmp_path: Path) -> None:
    store = FullFidelityContentStore(tmp_path)
    payload = {
        "tool": "Write",
        "input": {"file_path": "/tmp/a", "content": "full content"},
        "output": {"status": "ok", "bytes": 12},
    }

    reference = store.put_json(payload, content_kind="tool_exchange")

    assert json.loads((tmp_path / reference.path).read_text(encoding="utf-8")) == payload
    assert reference.representation == "parsed_json_canonical"


def test_transport_filter_drops_credentials_but_keeps_noncredential_metadata() -> None:
    metadata = {
        "request_id": "req-1",
        "headers": {
            "Authorization": "Bearer never-store",
            "X-Request-ID": "req-1",
            "Cookie": "session=never-store",
        },
        "routing": {"provider": "anthropic", "model": "claude"},
    }

    filtered, removed = filter_transport_credentials(metadata)

    assert filtered == {
        "request_id": "req-1",
        "headers": {"X-Request-ID": "req-1"},
        "routing": {"provider": "anthropic", "model": "claude"},
    }
    assert removed == ["headers.Authorization", "headers.Cookie"]


def test_transport_filter_is_not_for_prompt_or_tool_content(tmp_path: Path) -> None:
    store = FullFidelityContentStore(tmp_path)
    tool_input = {"api_key": "literal-value-the-agent-wrote", "path": "config.json"}

    reference = store.put_json(tool_input, content_kind="tool_input")

    stored = json.loads((tmp_path / reference.path).read_text(encoding="utf-8"))
    assert stored["api_key"] == "literal-value-the-agent-wrote"


def test_content_event_keeps_evidence_boundary_explicit(tmp_path: Path) -> None:
    store = FullFidelityContentStore(tmp_path)
    reference = store.put_text("hello", content_kind="assistant_response")
    source = {"type": "inference_request", "id": "inference-request:req-1"}

    event = content_observation_event(
        timestamp="2026-08-26T00:00:00Z",
        provider="openrouter",
        source=source,
        reference=reference,
        relation="OBSERVED_RESPONSE_CONTENT",
        observed_field="response.body",
        evidence_source="gateway_response",
        attribution="gateway_api",
    )

    assert event["relation"] == "OBSERVED_RESPONSE_CONTENT"
    assert event["attributes"]["content_complete_from_source"] is True
    assert event["attributes"]["causal"] is False
    assert event["attributes"]["inferred"] is False
    assert event["target"]["attributes"]["sha256"] == reference.sha256
