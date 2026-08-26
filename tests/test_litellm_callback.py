from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from execweave.litellm_callback import (
    ExecWeaveLiteLLMCallback,
    standard_logging_to_events,
)
from execweave.litellm_callback_cli import callback_path, config_fragment, main as callback_cli_main
from execweave.live import run_live


def _standard_payload() -> dict[str, object]:
    return {
        "id": "call-123",
        "status": "success",
        "call_type": "acompletion",
        "model_group": "assistant",
        "model": "azure/gpt-5",
        "model_id": "deployment-west",
        "prompt_tokens": 12,
        "completion_tokens": 8,
        "total_tokens": 20,
        "response_cost": 0.0042,
        "response_time": 0.75,
        "cache_hit": True,
        "api_base": "https://user:secret@private-provider.example/v1?token=SECRET",
        "messages": [{"role": "user", "content": "PRIVATE_PROMPT"}],
        "response": {"choices": [{"message": {"content": "PRIVATE_RESPONSE"}}]},
        "metadata": {
            "user_api_key_hash": "PRIVATE_KEY_HASH",
            "requester_custom_headers": {"x-secret": "PRIVATE_HEADER"},
        },
        "model_parameters": {"system": "PRIVATE_SYSTEM_PROMPT"},
    }


def test_litellm_standard_logging_extracts_only_whitelisted_routing_metadata() -> None:
    events = standard_logging_to_events(
        _standard_payload(),
        endpoint="http://localhost:4000",
        timestamp="2026-08-26T00:00:00Z",
    )
    rendered = json.dumps(events, sort_keys=True)
    relations = {event["relation"] for event in events}

    assert relations == {
        "SERVED_INFERENCE",
        "REQUESTED_MODEL",
        "ROUTED_TO_MODEL",
        "ROUTED_TO_DEPLOYMENT",
    }
    assert "assistant" in rendered
    assert "azure/gpt-5" in rendered
    assert "deployment-west" in rendered
    assert "PRIVATE_PROMPT" not in rendered
    assert "PRIVATE_RESPONSE" not in rendered
    assert "PRIVATE_KEY_HASH" not in rendered
    assert "PRIVATE_HEADER" not in rendered
    assert "PRIVATE_SYSTEM_PROMPT" not in rendered
    assert "private-provider.example" not in rendered
    assert "SECRET" not in rendered
    assert "ROUTED_TO_PROVIDER" not in relations

    request = next(event["target"] for event in events if event["relation"] == "SERVED_INFERENCE")
    attrs = request["attributes"]
    assert attrs["requested_model"] == "assistant"
    assert attrs["resolved_model"] == "azure/gpt-5"
    assert attrs["deployment_id"] == "deployment-west"
    assert attrs["prompt_tokens"] == 12
    assert attrs["completion_tokens"] == 8
    assert attrs["total_tokens"] == 20
    assert attrs["cost_usd"] == 0.0042
    assert attrs["cache_hit"] is True
    assert attrs["response_time_seconds"] == 0.75
    assert attrs["call_type"] == "acompletion"


def test_litellm_callback_is_noop_without_live_sidecar(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("EXECWEAVE_SEMANTIC_SIDECAR", raising=False)
    sidecar = tmp_path / "semantic.jsonl"
    callback = ExecWeaveLiteLLMCallback()
    callback.log_success_event(
        {"standard_logging_object": _standard_payload()},
        {"private": "PRIVATE_RESPONSE"},
        None,
        datetime.now(timezone.utc),
    )
    assert not sidecar.exists()


def test_litellm_callback_writes_live_sidecar_without_content(monkeypatch, tmp_path: Path) -> None:
    sidecar = tmp_path / "semantic.jsonl"
    monkeypatch.setenv("EXECWEAVE_SEMANTIC_SIDECAR", str(sidecar))
    monkeypatch.setenv("EXECWEAVE_LITELLM_ENDPOINT", "http://localhost:4555")
    callback = ExecWeaveLiteLLMCallback()

    callback.log_success_event(
        {"standard_logging_object": _standard_payload()},
        {"private": "PRIVATE_RESPONSE_OBJECT"},
        None,
        datetime.now(timezone.utc),
    )

    records = [json.loads(line) for line in sidecar.read_text(encoding="utf-8").splitlines()]
    rendered = json.dumps(records, sort_keys=True)
    assert records
    assert all(record["attributes"]["gateway"] == "litellm" for record in records)
    assert "http://localhost:4555" in rendered
    assert "PRIVATE_RESPONSE_OBJECT" not in rendered
    assert "PRIVATE_PROMPT" not in rendered


def test_litellm_callback_fail_open_on_invalid_payload(monkeypatch, tmp_path: Path) -> None:
    sidecar = tmp_path / "semantic.jsonl"
    monkeypatch.setenv("EXECWEAVE_SEMANTIC_SIDECAR", str(sidecar))
    callback = ExecWeaveLiteLLMCallback()
    callback.log_success_event(
        {"standard_logging_object": {"messages": ["PRIVATE_PROMPT"]}},
        None,
        None,
        None,
    )
    assert not sidecar.exists()


def test_run_live_materializes_configured_litellm_callback(tmp_path: Path) -> None:
    code = r'''
from datetime import datetime, timezone
from execweave.litellm_callback import execweave_litellm_callback

execweave_litellm_callback.log_success_event(
    {
        "standard_logging_object": {
            "id": "live-call-1",
            "call_type": "acompletion",
            "model_group": "assistant",
            "model": "openai/gpt-5",
            "model_id": "deployment-live",
            "prompt_tokens": 4,
            "completion_tokens": 2,
            "total_tokens": 6,
            "response_cost": 0.001,
            "messages": [{"role": "user", "content": "SHOULD_NOT_APPEAR"}],
            "response": {"content": "SHOULD_NOT_APPEAR_EITHER"},
        }
    },
    None,
    None,
    datetime.now(timezone.utc),
)
'''
    result = run_live(
        [sys.executable, "-c", code],
        watch_root=tmp_path,
        output_dir=tmp_path / "litellm-live",
        poll_interval=0.03,
        collect_filesystem=False,
        collect_network=False,
        port=0,
        open_browser=False,
        linger_seconds=0,
    )

    assert result.return_code == 0
    assert result.semantic_sidecar.exists()
    assert result.materialized_event_stream.name == "events.semantic.jsonl"
    graph = json.loads(result.graph.read_text(encoding="utf-8"))
    relations = {edge["relation"] for edge in graph["edges"]}
    rendered = json.dumps(graph, sort_keys=True)
    assert "SERVED_INFERENCE" in relations
    assert "REQUESTED_MODEL" in relations
    assert "ROUTED_TO_MODEL" in relations
    assert "ROUTED_TO_DEPLOYMENT" in relations
    assert "SHOULD_NOT_APPEAR" not in rendered
    assert "SHOULD_NOT_APPEAR_EITHER" not in rendered


def test_litellm_callback_setup_cli(capsys) -> None:
    assert callback_path() == "execweave.litellm_callback.execweave_litellm_callback"
    assert callback_path() in config_fragment()
    assert callback_cli_main(["--print-config"]) == 0
    assert callback_path() in capsys.readouterr().out
    assert callback_cli_main(["--print-callback"]) == 0
    assert capsys.readouterr().out.strip() == callback_path()
