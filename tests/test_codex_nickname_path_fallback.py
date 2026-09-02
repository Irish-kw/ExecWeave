"""When Codex omits agent_path, derive /root/<nickname> for child addressing."""

from __future__ import annotations

import json
from pathlib import Path

from execweave.agent_topology import PATH_EXECWEAVE_DERIVED, PATH_PROVIDER_DECLARED
from execweave.codex_conversation import codex_rollout_previews
from execweave.conversation_preview_codex import conversation_preview as wrap_codex_preview


def _rollout(path: Path, payload: dict[str, object], items: list[dict[str, object]]) -> Path:
    lines = [json.dumps({"type": "session_meta", "payload": payload}, ensure_ascii=False)]
    for index, item in enumerate(items, start=1):
        lines.append(
            json.dumps(
                {
                    "timestamp": f"2026-09-02T01:40:0{index}Z",
                    "type": "response_item",
                    "ordinal": index,
                    "payload": item,
                },
                ensure_ascii=False,
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_nickname_without_agent_path_becomes_root_nickname(tmp_path: Path) -> None:
    rollout = _rollout(
        tmp_path / "rollout-sartre.jsonl",
        {
            "id": "01a05fc7-1669-7043-aaf4-dd16258e273a",
            "agent_nickname": "Sartre",
            "parent_thread_id": "01a05fc6-1584-7132-9215-53d7a09c01f7",
        },
        [
            {
                "type": "message",
                "role": "user",
                "internal_chat_message_metadata_passthrough": {
                    "content_item_kinds": ["user.text"]
                },
                "content": [{"type": "input_text", "text": "誰最帥"}],
            },
            {
                "type": "message",
                "role": "assistant",
                "phase": "final_answer",
                "content": [{"type": "output_text", "text": "提問的人最帥"}],
            },
            {
                "type": "message",
                "role": "user",
                "internal_chat_message_metadata_passthrough": {
                    "content_item_kinds": ["user.text"]
                },
                "content": [{"type": "input_text", "text": "誰最美"}],
            },
            {
                "type": "message",
                "role": "assistant",
                "phase": "final_answer",
                "content": [{"type": "output_text", "text": "笑著看答案的人最美"}],
            },
        ],
    )
    preview = codex_rollout_previews(rollout)[0]
    assert preview["agent_path"] == "/root/Sartre"
    assert preview["agent_path_source"] == PATH_EXECWEAVE_DERIVED
    recipients = [message.get("recipient") for message in preview["messages"]]
    senders = [message.get("sender") for message in preview["messages"]]
    assert recipients[0] == "/root/Sartre"
    assert senders[1] == "/root/Sartre"
    assert recipients[2] == "/root/Sartre"
    wrapped = wrap_codex_preview(
        rollout,
        content_kind="codex.conversation_transcript.subagent",
        provider="codex",
        source={"id": "agent:codex:child", "name": "Sartre", "attributes": {"provider": "codex"}},
    )
    assert wrapped is not None
    assert wrapped["agent_path"] == "/root/Sartre"
    assert wrapped["is_root"] is False
    assert wrapped["agent_path_source"] == PATH_EXECWEAVE_DERIVED


def test_provider_declared_path_is_not_replaced_by_nickname(tmp_path: Path) -> None:
    rollout = _rollout(
        tmp_path / "rollout-take-one.jsonl",
        {
            "id": "child-thread",
            "agent_path": "/root/take_one",
            "agent_nickname": "Sartre",
            "parent_thread_id": "parent-thread",
        },
        [
            {
                "type": "message",
                "role": "user",
                "internal_chat_message_metadata_passthrough": {
                    "content_item_kinds": ["user.text"]
                },
                "content": [{"type": "input_text", "text": "hi"}],
            }
        ],
    )
    preview = codex_rollout_previews(rollout)[0]
    assert preview["agent_path"] == "/root/take_one"
    assert preview["agent_path_source"] == PATH_PROVIDER_DECLARED
    assert preview["messages"][0]["recipient"] == "/root/take_one"


def test_root_without_path_stays_root(tmp_path: Path) -> None:
    rollout = _rollout(
        tmp_path / "rollout-root.jsonl",
        {"id": "root-thread"},
        [
            {
                "type": "message",
                "role": "user",
                "internal_chat_message_metadata_passthrough": {
                    "content_item_kinds": ["user.text"]
                },
                "content": [{"type": "input_text", "text": "你是誰"}],
            }
        ],
    )
    preview = codex_rollout_previews(rollout)[0]
    assert preview["agent_path"] == "/root"
    assert preview["agent_path_source"] == PATH_EXECWEAVE_DERIVED
    assert preview["messages"][0]["recipient"] == "/root"
