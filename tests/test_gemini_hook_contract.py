from __future__ import annotations

import io
import json
from pathlib import Path

from execweave.gemini_hook_cli import gemini_hook_config, main as gemini_hook_main
from execweave.gemini_hook_contract import (
    GEMINI_HOOKS_REFERENCE,
    OFFICIAL_GEMINI_HOOK_EVENTS,
    gemini_official_hook_semantic_events,
)


def _base(event: str, timestamp: str = "2026-08-28T07:10:00Z") -> dict:
    return {
        "session_id": "gemini-session-1",
        "transcript_path": "/private/unstable-transcript.json",
        "cwd": "/repo",
        "hook_event_name": event,
        "timestamp": timestamp,
    }


def test_official_event_set_matches_current_gemini_reference_and_config() -> None:
    expected = {
        "SessionStart",
        "SessionEnd",
        "BeforeAgent",
        "AfterAgent",
        "BeforeModel",
        "AfterModel",
        "BeforeToolSelection",
        "BeforeTool",
        "AfterTool",
        "PreCompress",
        "Notification",
    }
    assert OFFICIAL_GEMINI_HOOK_EVENTS == expected
    hooks = gemini_hook_config("execweave-gemini-hook --strict")["hooks"]
    assert set(hooks) == expected
    assert hooks["BeforeTool"][0]["matcher"] == ".*"
    assert hooks["AfterTool"][0]["matcher"] == ".*"
    assert "matcher" not in hooks["BeforeAgent"][0]


def test_session_end_is_best_effort_provider_observation() -> None:
    event = gemini_official_hook_semantic_events(
        {**_base("SessionEnd"), "reason": "clear"}
    )[0]

    assert event["relation"] == "OBSERVED_PROVIDER_SESSION_END"
    assert event["target"]["id"] == "provider-session:gemini:gemini-session-1"
    assert event["attributes"]["gemini_session_end_reason"] == "clear"
    assert event["attributes"]["best_effort_hook"] is True
    assert event["attributes"]["flow_control_ignored_by_provider"] is True
    assert event["attributes"]["official_hook_reference"] == GEMINI_HOOKS_REFERENCE
    assert "transcript_path" not in event["attributes"]


def test_agent_boundaries_do_not_assert_pairing_or_accepted_final_response() -> None:
    before = gemini_official_hook_semantic_events(
        {**_base("BeforeAgent"), "prompt": "private prompt"}
    )[0]
    after = gemini_official_hook_semantic_events(
        {
            **_base("AfterAgent", "2026-08-28T07:10:03Z"),
            "prompt": "private prompt",
            "prompt_response": "candidate answer",
            "stop_hook_active": False,
        }
    )[0]

    assert before["relation"] == "OBSERVED_AGENT_TURN_START"
    assert before["attributes"]["boundary_semantics"] == (
        "after_user_prompt_before_agent_planning"
    )
    assert before["attributes"]["before_after_pairing_asserted"] is False
    assert after["relation"] == "OBSERVED_AGENT_TURN_END"
    assert after["attributes"]["response_can_be_rejected_and_retried_by_hook"] is True
    assert after["attributes"]["accepted_final_response_asserted"] is False
    rendered = json.dumps([before, after])
    assert "private prompt" not in rendered
    assert "candidate answer" not in rendered


def test_before_model_records_request_target_without_claiming_invocation() -> None:
    event = gemini_official_hook_semantic_events(
        {
            **_base("BeforeModel"),
            "llm_request": {
                "model": "gemini-3-pro",
                "messages": [{"role": "user", "content": "private"}],
                "config": {"temperature": 0.2},
                "toolConfig": {"mode": "AUTO", "allowedFunctionNames": ["read_file"]},
            },
        }
    )[0]

    assert event["relation"] == "OBSERVED_MODEL_REQUEST_TARGET"
    assert event["target"]["id"] == "model:gemini:gemini-3-pro"
    assert event["attributes"]["actual_model_invocation_asserted"] is False
    assert event["attributes"]["request_can_be_blocked_rewritten_or_replaced_by_hook"] is True
    assert event["attributes"]["generation_config_keys"] == ["temperature"]
    assert "private" not in json.dumps(event)


def test_before_tool_selection_records_policy_shape_without_tool_names() -> None:
    event = gemini_official_hook_semantic_events(
        {
            **_base("BeforeToolSelection"),
            "llm_request": {
                "model": "gemini-3-pro",
                "messages": [],
                "config": {},
                "toolConfig": {
                    "mode": "ANY",
                    "allowedFunctionNames": ["secret_tool_a", "secret_tool_b"],
                },
            },
        }
    )[0]

    assert event["relation"] == "OBSERVED_TOOL_SELECTION_MODEL_REQUEST"
    assert event["attributes"]["tool_selection_mode"] == "ANY"
    assert event["attributes"]["allowed_function_count"] == 2
    assert event["attributes"]["actual_model_invocation_asserted"] is False
    rendered = json.dumps(event)
    assert "secret_tool_a" not in rendered
    assert "secret_tool_b" not in rendered


def test_after_model_records_stream_chunk_metadata_without_response_body() -> None:
    event = gemini_official_hook_semantic_events(
        {
            **_base("AfterModel"),
            "llm_request": {
                "model": "gemini-3-pro",
                "messages": [{"role": "user", "content": "private request"}],
                "config": {},
            },
            "llm_response": {
                "candidates": [
                    {
                        "content": {"role": "model", "parts": ["private response chunk"]},
                        "finishReason": "STOP",
                    }
                ],
                "usageMetadata": {"totalTokenCount": 123},
            },
        }
    )[0]

    assert event["relation"] == "OBSERVED_MODEL_RESPONSE_CHUNK"
    assert event["source"]["id"] == "model:gemini:gemini-3-pro"
    assert event["attributes"]["streaming_chunk"] is True
    assert event["attributes"]["candidate_count"] == 1
    assert event["attributes"]["finish_reasons"] == ["STOP"]
    assert event["attributes"]["usage_total_token_count"] == 123
    assert event["attributes"]["response_chunk_can_be_replaced_or_denied_by_hook"] is True
    rendered = json.dumps(event)
    assert "private request" not in rendered
    assert "private response chunk" not in rendered


def test_notification_and_precompress_are_advisory_observations() -> None:
    notification = gemini_official_hook_semantic_events(
        {
            **_base("Notification"),
            "notification_type": "ToolPermission",
            "message": "private permission alert",
            "details": {"tool_name": "write_file", "file_path": "/secret"},
        }
    )[0]
    compression = gemini_official_hook_semantic_events(
        {**_base("PreCompress"), "trigger": "auto"}
    )[0]

    assert notification["relation"] == "OBSERVED_NOTIFICATION"
    assert notification["attributes"]["observability_only"] is True
    assert notification["attributes"]["notification_detail_keys"] == ["file_path", "tool_name"]
    assert "private permission alert" not in json.dumps(notification)
    assert "/secret" not in json.dumps(notification)
    assert compression["relation"] == "OBSERVED_PRE_COMPACTION"
    assert compression["attributes"]["advisory_only"] is True
    assert compression["attributes"]["async_hook"] is True
    assert compression["attributes"]["pre_post_pairing_asserted"] is False


def test_cli_persists_semantic_chunk_and_full_fidelity_response(
    monkeypatch, tmp_path: Path
) -> None:
    sidecar = tmp_path / "gemini.jsonl"
    payload = {
        **_base("AfterModel"),
        "cwd": str(tmp_path),
        "llm_request": {
            "model": "gemini-3-pro",
            "messages": [{"role": "user", "content": "prompt body"}],
            "config": {},
        },
        "llm_response": {
            "candidates": [
                {
                    "content": {"role": "model", "parts": ["response body"]},
                    "finishReason": "STOP",
                }
            ],
            "usageMetadata": {"totalTokenCount": 9},
        },
    }
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))

    assert gemini_hook_main(["--sidecar", str(sidecar)]) == 0

    records = [json.loads(line) for line in sidecar.read_text(encoding="utf-8").splitlines()]
    relations = {record["relation"] for record in records}
    assert "OBSERVED_MODEL_RESPONSE_CHUNK" in relations
    assert "RECEIVED_LLM_RESPONSE_CHUNK" in relations
    assert "OBSERVED_LLM_REQUEST_FOR_RESPONSE" in relations
    assert "prompt body" not in sidecar.read_text(encoding="utf-8")
    assert "response body" not in sidecar.read_text(encoding="utf-8")
    content_root = tmp_path / "content" / "sha256"
    assert content_root.is_dir()
    stored = b"\n".join(path.read_bytes() for path in content_root.iterdir())
    assert b"response body" in stored
