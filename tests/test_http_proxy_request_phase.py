from __future__ import annotations

import json
from pathlib import Path

import pytest

from execweave.http_proxy import ProxyConfig, record_exchange_fail_open

pytestmark = pytest.mark.viewer_e2e


@pytest.mark.parametrize(
    ("mode", "provider_name", "config_relation"),
    [
        ("openai-compatible", "local-openai", "OBSERVED_PROVIDER_REQUEST_CONFIG"),
        ("ollama", "ollama", "OBSERVED_INFERENCE_REQUEST_CONFIG"),
    ],
)
def test_two_phase_proxy_capture_leaves_no_orphan_content_and_no_request_duplicates(
    tmp_path: Path,
    mode: str,
    provider_name: str,
    config_relation: str,
) -> None:
    sidecar = tmp_path / "events.jsonl"
    config = ProxyConfig(
        upstream="http://127.0.0.1:11434/v1" if mode != "ollama" else "http://127.0.0.1:11434",
        sidecar=sidecar,
        mode=mode,
        provider_name=provider_name,
    )
    request = {
        "model": "demo",
        "stream": False,
        "messages": [{"role": "user", "content": "ping"}],
        "tools": [{"type": "function", "function": {"name": "echo"}}],
        "options": {"temperature": 0.2},
    }
    request_body = json.dumps(request, separators=(",", ":")).encode()

    assert record_exchange_fail_open(
        config,
        exchange_id="exchange-1",
        request_body=request_body,
        request_content_type="application/json",
        response_body=b"",
        response_content_type=None,
        method="POST",
        request_path="/chat/completions",
        status=None,
        request_only=True,
    )
    request_events = [json.loads(line) for line in sidecar.read_text().splitlines() if line.strip()]
    request_relations = [event["relation"] for event in request_events]
    assert "OBSERVED_INFERENCE_REQUEST" in request_relations
    assert "OBSERVED_INFERENCE_REQUEST_RAW" in request_relations
    assert config_relation in request_relations
    assert request_relations.count("REQUESTED_MODEL") == 1
    requested_model = next(event for event in request_events if event["relation"] == "REQUESTED_MODEL")
    assert requested_model["source"]["type"] in {"inference_request", "provider_request"}
    assert requested_model["target"]["type"] == "model"
    assert requested_model["target"]["name"] == "demo"
    assert requested_model["attributes"]["inferred"] is False
    assert not any("RESPONSE" in relation for relation in request_relations)
    assert "OBSERVED_PROVIDER_METADATA" not in request_relations
    _assert_all_content_is_referenced(tmp_path, request_events)

    response = (
        {"model": "demo", "message": {"role": "assistant", "content": "ok"}}
        if mode == "ollama"
        else {
            "id": "chatcmpl-1",
            "model": "demo",
            "choices": [{"message": {"role": "assistant", "content": "ok"}}],
        }
    )
    response_body = json.dumps(response, separators=(",", ":")).encode()
    assert record_exchange_fail_open(
        config,
        exchange_id="exchange-1",
        request_body=request_body,
        request_content_type="application/json",
        response_body=response_body,
        response_content_type="application/json",
        method="POST",
        request_path="/chat/completions",
        status=200,
        request_recorded=True,
    )
    events = [json.loads(line) for line in sidecar.read_text().splitlines() if line.strip()]
    relations = [event["relation"] for event in events]
    assert relations.count("OBSERVED_INFERENCE_REQUEST") == 1
    assert relations.count("OBSERVED_INFERENCE_REQUEST_RAW") == 1
    assert relations.count(config_relation) == 1
    assert relations.count("REQUESTED_MODEL") == 1
    assert relations.count("OBSERVED_INFERENCE_RESPONSE") == 1
    assert relations.count("OBSERVED_INFERENCE_RESPONSE_RAW") == 1
    _assert_all_content_is_referenced(tmp_path, events)


def _assert_all_content_is_referenced(root: Path, events: list[dict]) -> None:
    referenced = {
        Path(event["attributes"]["content_path"]).as_posix()
        for event in events
        if isinstance(event.get("attributes"), dict) and event["attributes"].get("content_path")
    }
    content_root = root / "content"
    actual = (
        {
            path.relative_to(root).as_posix()
            for path in content_root.rglob("*")
            if path.is_file()
        }
        if content_root.exists()
        else set()
    )
    assert actual == referenced, {
        "orphaned": sorted(actual - referenced),
        "missing": sorted(referenced - actual),
    }
