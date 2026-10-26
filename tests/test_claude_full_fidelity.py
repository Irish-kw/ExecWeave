from __future__ import annotations

import json
from pathlib import Path

from execweave.claude_full_fidelity import claude_hook_to_content_events
from execweave.content_store import FullFidelityContentStore


def _store(tmp_path: Path) -> FullFidelityContentStore:
    return FullFidelityContentStore(tmp_path)


def _payload(event: str) -> dict:
    return {
        "session_id": "session-1",
        "transcript_path": "/tmp/transcript.jsonl",
        "cwd": "/repo",
        "permission_mode": "default",
        "hook_event_name": event,
    }


def _load_reference(tmp_path: Path, event: dict) -> bytes:
    return (tmp_path / event["attributes"]["content_path"]).read_bytes()


def test_user_prompt_is_stored_complete_without_sidecar_inline_copy(tmp_path: Path) -> None:
    prompt = "prompt-start\x00" + ("P" * 12000) + "prompt-end"
    events = claude_hook_to_content_events(
        {**_payload("UserPromptSubmit"), "prompt": prompt},
        store=_store(tmp_path),
        timestamp="2026-08-26T12:00:00Z",
    )

    prompt_event = next(event for event in events if event["relation"] == "RECEIVED_USER_PROMPT")
    assert _load_reference(tmp_path, prompt_event).decode("utf-8") == prompt
    assert prompt_event["attributes"]["content_complete_from_source"] is True
    assert prompt_event["attributes"]["causal"] is False
    assert prompt_event["attributes"]["inferred"] is False
    assert prompt not in json.dumps(events)


def test_tool_input_keeps_content_credentials_but_filters_metadata_credentials(tmp_path: Path) -> None:
    payload = {
        **_payload("PreToolUse"),
        "authorization": "Bearer transport-secret",
        "tool_name": "Write",
        "tool_use_id": "toolu_1",
        "tool_input": {
            "file_path": "/repo/config.json",
            "api_key": "content-secret-must-remain",
            "content": "full file body",
        },
    }
    events = claude_hook_to_content_events(
        payload,
        store=_store(tmp_path),
        timestamp="2026-08-26T12:00:00Z",
    )

    metadata_event = next(
        event for event in events if event["relation"] == "OBSERVED_PROVIDER_METADATA"
    )
    metadata = json.loads(_load_reference(tmp_path, metadata_event))
    assert "authorization" not in metadata
    assert metadata_event["attributes"]["transport_credentials_excluded"] == ["authorization"]

    input_event = next(event for event in events if event["relation"] == "HAS_TOOL_INPUT")
    stored_input = json.loads(_load_reference(tmp_path, input_event))
    assert stored_input["api_key"] == "content-secret-must-remain"
    assert stored_input["content"] == "full file body"


def test_posttooluse_keeps_structured_output_separate_from_model_visible_result(
    tmp_path: Path,
) -> None:
    post_events = claude_hook_to_content_events(
        {
            **_payload("PostToolUse"),
            "tool_name": "Read",
            "tool_use_id": "toolu_read",
            "tool_input": {"file_path": "/repo/a.py"},
            "tool_response": {"filePath": "/repo/a.py", "success": True},
        },
        store=_store(tmp_path),
        timestamp="2026-08-26T12:00:01Z",
    )
    structured = next(event for event in post_events if event["relation"] == "HAS_TOOL_OUTPUT")
    assert structured["attributes"]["model_visible_serialization"] is False

    batch_events = claude_hook_to_content_events(
        {
            **_payload("PostToolBatch"),
            "tool_calls": [
                {
                    "tool_name": "Read",
                    "tool_use_id": "toolu_read",
                    "tool_input": {"file_path": "/repo/a.py"},
                    "tool_response": "     1\tprint('model-visible')\n",
                }
            ],
        },
        store=_store(tmp_path),
        timestamp="2026-08-26T12:00:02Z",
    )
    model_visible = next(
        event for event in batch_events if event["relation"] == "MODEL_RECEIVED_TOOL_RESULT"
    )
    assert model_visible["attributes"]["model_visible_serialization"] is True
    assert _load_reference(tmp_path, model_visible).decode("utf-8") == (
        "     1\tprint('model-visible')\n"
    )


def test_message_display_preserves_order_metadata_and_delta(tmp_path: Path) -> None:
    events = claude_hook_to_content_events(
        {
            **_payload("MessageDisplay"),
            "turn_id": "turn-1",
            "message_id": "message-1",
            "index": 3,
            "final": True,
            "delta": "final lines\n",
        },
        store=_store(tmp_path),
        timestamp="2026-08-26T12:00:03Z",
    )
    display = next(event for event in events if event["relation"] == "DISPLAYED_ASSISTANT_TEXT")
    assert display["attributes"]["turn_id"] == "turn-1"
    assert display["attributes"]["message_id"] == "message-1"
    assert display["attributes"]["index"] == 3
    assert display["attributes"]["final"] is True
    assert _load_reference(tmp_path, display).decode("utf-8") == "final lines\n"


def test_stop_and_subagent_stop_capture_final_responses(tmp_path: Path) -> None:
    main_events = claude_hook_to_content_events(
        {**_payload("Stop"), "last_assistant_message": "main final"},
        store=_store(tmp_path),
        timestamp="2026-08-26T12:00:04Z",
    )
    main_final = next(
        event for event in main_events if event["relation"] == "PRODUCED_ASSISTANT_RESPONSE"
    )
    assert main_final["source"]["id"] == "agent:Claude Code"
    assert _load_reference(tmp_path, main_final).decode("utf-8") == "main final"

    sub_events = claude_hook_to_content_events(
        {
            **_payload("SubagentStop"),
            "agent_id": "agent-7",
            "agent_type": "Explore",
            "last_assistant_message": "subagent final",
        },
        store=_store(tmp_path),
        timestamp="2026-08-26T12:00:05Z",
    )
    sub_final = next(
        event for event in sub_events if event["relation"] == "PRODUCED_ASSISTANT_RESPONSE"
    )
    assert sub_final["source"]["id"] == "agent:claude:session-1:subagent:agent-7"
    assert _load_reference(tmp_path, sub_final).decode("utf-8") == "subagent final"
