"""Lock the Windows Codex empty-canvas hole and Agy fold copies.

Codex run 5c214cd13aaf41589af542b1ba2dcd85 compact-snapshots to nodes=[]
while keeping event_count. Agy run 9f836c8f1b494cd3b995477d0743e7d5
duplicated child assignments and pasted child replies onto /root. Windows Agy
run eed7e42ef1c242fe9e913b73ce106463 additionally exposed follow-up
send_message payloads as root assistant messages.
"""

from __future__ import annotations

from execweave.agy_preview_sanitize import sanitize_antigravity_preview_messages
from execweave.live import _LIVE_HTML


def test_live_set_snapshot_enters_protective_mode_on_compact_payload() -> None:
    start = _LIVE_HTML.find("function setSnapshot(data){")
    assert start >= 0
    chunk = _LIVE_HTML[start : start + 280]
    assert "if(data.live_payload_compact)" in chunk
    assert "enterProtectiveMode(data)" in chunk


def test_agy_drops_duplicate_child_assignment_user_message() -> None:
    assignment = "Act as an objective reviewer who relies on data and logic (Reviewer Alpha)."
    reply = "After feature analysis, the proposal scores 99.87%."
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
    reply = "Allow me to adjust my glasses first."
    entries = [
        {
            "provider": "antigravity",
            "conversation_preview": {
                "is_root": True,
                "agent_path": "/root",
                "messages": [
                    {"kind": "user_message", "sender": "user", "recipient": "/root", "text": "Start two agents to discuss the proposal"},
                    {"kind": "assistant_message", "sender": "/root", "text": "Two dedicated agents are online"},
                    {
                        "kind": "subagent_task",
                        "phase": "assignment",
                        "sender": "user",
                        "recipient": "/root",
                        "text": reply,
                    },
                    {"kind": "assistant_message", "sender": "/root", "text": "Here is the live discussion"},
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


def test_agy_followup_dispatch_belongs_to_child_not_root() -> None:
    child_path = "/root/16fbb4a2-dffe-442f-8373-9b4fde9f199a"
    followup = "Follow-up question: is the revised proposal clearer? Answer in one short sentence."
    entries = [
        {
            "provider": "antigravity",
            "conversation_preview": {
                "is_root": True,
                "agent_path": "/root",
                "messages": [
                    {"kind": "user_message", "sender": "user", "recipient": "/root", "text": "Ask them whether the revised proposal is clearer; short answer"},
                    {
                        "kind": "assistant_message",
                        "phase": "planner_response",
                        "sender": "/root",
                        "recipient": None,
                        "text": followup,
                    },
                    {
                        "kind": "assistant_message",
                        "phase": "planner_response",
                        "sender": "/root",
                        "recipient": None,
                        "text": "Fetching the other reviewer's short answer...",
                    },
                ],
            },
        },
        {
            "provider": "antigravity",
            "conversation_preview": {
                "is_root": False,
                "agent_path": child_path,
                "messages": [
                    {
                        "kind": "subagent_task",
                        "phase": "assignment",
                        "sender": "user",
                        "recipient": child_path,
                        "text": followup,
                    },
                    {
                        "kind": "user_message",
                        "sender": "user",
                        "recipient": child_path,
                        "text": followup,
                    },
                    {
                        "kind": "assistant_message",
                        "sender": child_path,
                        "text": "The clarity score is off the charts.",
                    },
                ],
            },
        },
    ]

    sanitize_antigravity_preview_messages(entries)

    root = entries[0]["conversation_preview"]["messages"]
    assert followup not in [message.get("text") for message in root]
    assert [message.get("text") for message in root] == [
        "Ask them whether the revised proposal is clearer; short answer",
        "Fetching the other reviewer's short answer...",
    ]

    child = entries[1]["conversation_preview"]["messages"]
    assert [message["kind"] for message in child] == ["task", "assistant_message"]
    task = child[0]
    assert task["sender"] == "/root"
    assert task["recipient"] == child_path
    assert task["phase"] == "assignment"
    assert task["content_role"] == "antigravity_addressed_task"


def test_agy_does_not_invent_child_round_without_addressed_task() -> None:
    child_path = "/root/90be5fc1-bf98-4e78-9eae-7fc4c0601c46"
    weather = "Have them look up the weather in Tokyo and Beijing online and write it to a .md file; short answer"
    entries = [
        {
            "provider": "antigravity",
            "conversation_preview": {
                "is_root": True,
                "agent_path": "/root",
                "messages": [
                    {"kind": "user_message", "sender": "user", "recipient": "/root", "text": weather},
                    {"kind": "assistant_message", "sender": "/root", "text": "Online lookup completed and written to weather.md"},
                ],
            },
        },
        {
            "provider": "antigravity",
            "conversation_preview": {
                "is_root": False,
                "agent_path": child_path,
                "messages": [
                    {
                        "kind": "task",
                        "sender": "/root",
                        "recipient": child_path,
                        "text": "The user asked whether the proposal is sound",
                    },
                    {
                        "kind": "assistant_message",
                        "sender": child_path,
                        "text": "Sound.",
                    },
                ],
            },
        },
    ]

    sanitize_antigravity_preview_messages(entries)

    child = entries[1]["conversation_preview"]["messages"]
    assert len(child) == 2
    assert all(weather not in str(message.get("text") or "") for message in child)
