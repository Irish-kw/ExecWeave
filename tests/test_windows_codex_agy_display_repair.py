"""Lock the Windows Codex empty-canvas hole and Agy fold copies.

Codex run 5c214cd13aaf41589af542b1ba2dcd85 compact-snapshots to nodes=[]
while keeping event_count. Agy run 9f836c8f1b494cd3b995477d0743e7d5
duplicated child assignments and pasted child replies onto /root.
"""

from __future__ import annotations

from execweave.agy_preview_sanitize import sanitize_antigravity_preview_messages
from execweave.live import _LIVE_HTML
from execweave.viewer_dashboard_clean import _LIVE_SET_SNAPSHOT_CLEAN


def test_live_set_snapshot_enters_protective_mode_on_compact_payload() -> None:
    assert "if(data.live_payload_compact)" in _LIVE_SET_SNAPSHOT_CLEAN
    assert "enterProtectiveMode(data)" in _LIVE_SET_SNAPSHOT_CLEAN
    start = _LIVE_HTML.find("function setSnapshot(data){")
    assert start >= 0
    chunk = _LIVE_HTML[start : start + 220]
    assert "if(data.live_payload_compact)" in chunk
    assert "enterProtectiveMode(data)" in chunk


def test_agy_drops_duplicate_child_assignment_user_message() -> None:
    assignment = "請扮演「理性客觀、以數據與邏輯為依據的極客 AI 評判官（Agent Alpha。"
    reply = "經多維神經網路特徵提取與張量分析，使用者帥度指標高達 99.87%。"
    entries = [
        {
            "provider": "antigravity",
            "conversation_preview": {
                "is_root": False,
                "agent_path": "/root/12845f85-5101-46a0-bbd6-970fbf7f8d91",
                "messages": [
                    {
                        "kind": "task",
                        "sender": "/root",
                        "recipient": "/root/12845f85-5101-46a0-bbd6-970fbf7f8d91",
                        "text": assignment,
                    },
                    {
                        "kind": "user_message",
                        "sender": "user",
                        "recipient": "/root/12845f85-5101-46a0-bbd6-970fbf7f8d91",
                        "text": assignment,
                    },
                    {
                        "kind": "assistant_message",
                        "sender": "/root/12845f85-5101-46a0-bbd6-970fbf7f8d91",
                        "text": reply,
                    },
                ],
            },
        }
    ]
    sanitize_antigravity_preview_messages(entries)
    kinds = [message["kind"] for message in entries[0]["conversation_preview"]["messages"]]
    assert kinds == ["task", "assistant_message"]


def test_agy_root_does_not_keep_child_replies_as_subagent_tasks() -> None:
    reply = "天啊！請容許我先扶一下眼鏡——"
    entries = [
        {
            "provider": "antigravity",
            "conversation_preview": {
                "is_root": True,
                "agent_path": "/root",
                "messages": [
                    {"kind": "user_message", "sender": "user", "recipient": "/root", "text": "開兩個agent討論我帥不帥"},
                    {"kind": "assistant_message", "sender": "/root", "text": "兩位專屬 Agent 已經上線"},
                    {
                        "kind": "subagent_task",
                        "phase": "assignment",
                        "sender": "user",
                        "recipient": "/root",
                        "text": reply,
                    },
                    {"kind": "assistant_message", "sender": "/root", "text": "討論實況轉播來了"},
                ],
            },
        },
        {
            "provider": "antigravity",
            "conversation_preview": {
                "is_root": False,
                "agent_path": "/root/bc64ee5c-2e3c-47f4-b1ef-d8b4207f03fb",
                "messages": [
                    {
                        "kind": "assistant_message",
                        "sender": "/root/bc64ee5c-2e3c-47f4-b1ef-d8b4207f03fb",
                        "text": reply,
                    }
                ],
            },
        },
    ]
    sanitize_antigravity_preview_messages(entries)
    root = entries[0]["conversation_preview"]["messages"]
    assert [message["kind"] for message in root] == ["user_message", "assistant_message", "assistant_message"]
    assert all(message.get("kind") != "subagent_task" for message in root)
    assert reply not in [message.get("text") for message in root]
