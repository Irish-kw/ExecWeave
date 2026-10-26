from __future__ import annotations

import json
from pathlib import Path

from execweave.codex_conversation import codex_rollout_preview


def _write_rollout(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )


def _message(role: str, text: str, *, phase: str | None = None, user_text: bool = False) -> dict:
    payload: dict = {
        "type": "message",
        "role": role,
        "content": [{"type": "input_text" if role == "user" else "output_text", "text": text}],
    }
    if phase is not None:
        payload["phase"] = phase
    if user_text:
        payload["internal_chat_message_metadata_passthrough"] = {
            "content_item_kinds": ["user.text"]
        }
    return {"timestamp": "2026-08-29T00:00:00Z", "type": "response_item", "payload": payload}


def _child_records(thread_id: str, agent_path: str, task: str, private_reply: str) -> list[dict]:
    return [
        {
            "timestamp": "2026-08-29T00:00:00Z",
            "type": "session_meta",
            "payload": {
                "id": thread_id,
                "parent_thread_id": "root-thread",
                "agent_path": agent_path,
                "subagent_history_start_ordinal": 3,
            },
        },
        _message("user", "ROOT PRIVATE PROMPT", user_text=True),
        _message("assistant", "ROOT PRIVATE ANSWER", phase="commentary"),
        _message("user", task),
        _message("assistant", private_reply, phase="commentary"),
        _message("assistant", f"FINAL {private_reply}", phase="final_answer"),
    ]


def test_codex_subagent_preview_excludes_inherited_parent_history_without_inline_ordinals(
    tmp_path: Path,
) -> None:
    agent1 = tmp_path / "rollout-agent-1.jsonl"
    agent2 = tmp_path / "rollout-agent-2.jsonl"
    _write_rollout(
        agent1,
        _child_records("agent-1", "/root/agent1", "TASK FOR AGENT 1", "AGENT 1 PRIVATE"),
    )
    _write_rollout(
        agent2,
        _child_records("agent-2", "/root/agent2", "TASK FOR AGENT 2", "AGENT 2 PRIVATE"),
    )

    preview1 = codex_rollout_preview(agent1)
    preview2 = codex_rollout_preview(agent2)
    assert preview1 is not None
    assert preview2 is not None

    text1 = [message.get("text") for message in preview1["messages"]]
    text2 = [message.get("text") for message in preview2["messages"]]

    assert "ROOT PRIVATE PROMPT" not in text1
    assert "ROOT PRIVATE ANSWER" not in text1
    assert "ROOT PRIVATE PROMPT" not in text2
    assert "ROOT PRIVATE ANSWER" not in text2

    assert "TASK FOR AGENT 1" in text1
    assert "AGENT 1 PRIVATE" in text1
    assert "AGENT 2 PRIVATE" not in text1

    assert "TASK FOR AGENT 2" in text2
    assert "AGENT 2 PRIVATE" in text2
    assert "AGENT 1 PRIVATE" not in text2

    assert all(
        message.get("sender") in {"/root", "/root/agent1"}
        for message in preview1["messages"]
    )
    assert all(
        message.get("sender") in {"/root", "/root/agent2"}
        for message in preview2["messages"]
    )
