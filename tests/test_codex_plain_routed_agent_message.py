from __future__ import annotations

import json
from pathlib import Path

from execweave.codex_conversation import codex_rollout_previews


def _line(ordinal: int, payload: dict[str, object]) -> str:
    return json.dumps(
        {
            "type": "response_item",
            "timestamp": f"2026-01-01T00:00:{ordinal:02d}Z",
            "ordinal": ordinal,
            "payload": payload,
        }
    )


def _write_parent_rollout(tmp_path: Path, returned_text: str) -> Path:
    path = tmp_path / "rollout-parent.jsonl"
    lines = [
        json.dumps(
            {
                "type": "session_meta",
                "payload": {"id": "parent-thread", "agent_path": "/root"},
            }
        ),
        _line(
            1,
            {
                "type": "function_call",
                "name": "spawn_agent",
                "call_id": "call-child",
                "arguments": json.dumps({"message": "answer the child question"}),
            },
        ),
        _line(
            2,
            {
                "type": "function_call_output",
                "call_id": "call-child",
                "output": json.dumps(
                    {"task_name": "/root/child", "thread_id": "child-thread"}
                ),
            },
        ),
        _line(
            3,
            {
                "type": "agent_message",
                "author": "/root/child",
                "recipient": "/root",
                "content": [{"type": "output_text", "text": returned_text}],
            },
        ),
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_plain_routed_agent_message_keeps_its_provider_plaintext(tmp_path: Path) -> None:
    previews = codex_rollout_previews(
        _write_parent_rollout(tmp_path, "MARKER-PLAIN done")
    )

    child = next(preview for preview in previews if preview.get("agent_path") == "/root/child")
    messages = child["messages"]
    assert [message.get("kind") for message in messages] == ["task", "agent_message"]
    assert messages[0]["text"] == "answer the child question"
    assert messages[1]["sender"] == "/root/child"
    assert messages[1]["recipient"] == "/root"
    assert messages[1]["text"] == "MARKER-PLAIN done"


def test_protocol_header_without_payload_is_not_rendered_as_response_text(tmp_path: Path) -> None:
    previews = codex_rollout_previews(
        _write_parent_rollout(
            tmp_path,
            "Message type: notify\nTask name: /root/child\nSender: /root/child",
        )
    )

    child = next(preview for preview in previews if preview.get("agent_path") == "/root/child")
    response = child["messages"][-1]
    assert response["kind"] == "notify"
    assert response["text"] is None
