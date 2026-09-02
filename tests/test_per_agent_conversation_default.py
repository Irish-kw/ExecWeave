"""Per-agent isolation is enforced by the unified compact inspector in v0.7.9.

The old default multi-agent conversation tree was removed. These regressions retain
their historical test identities but now pin the replacement behavior: namespaced
agent paths are resolved correctly, only a selected agent gets a conversation view,
and sibling traffic is not eligible for that agent's Task/Thinking/Response cards.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from execweave.dashboard_shell import render_static_dashboard_html
from execweave.viewer_agent_panel import inject_agent_panel

SRC = Path(__file__).resolve().parents[1] / "src" / "execweave"
PANEL = SRC / "viewer_agent_panel.py"
PANEL_DEFAULT = SRC / "viewer_agent_panel_default.py"


def _graph() -> dict[str, Any]:
    return {
        "nodes": [
            {
                "id": "agent:OpenAI Codex",
                "type": "agent",
                "name": "OpenAI Codex",
                "attributes": {
                    "provider": "codex",
                    "agent_role": "root",
                    "root_agent_path": "/root",
                },
            },
            {
                "id": "agent:codex:S:subagent:one",
                "type": "agent",
                "name": "default",
                "attributes": {
                    "provider": "codex",
                    "agent_role": "subagent",
                    "child_agent_path": "/root/alpha",
                    "parent_agent_path": "/root",
                },
            },
            {
                "id": "agent:codex:S:subagent:two",
                "type": "agent",
                "name": "default",
                "attributes": {
                    "provider": "codex",
                    "agent_role": "subagent",
                    "child_agent_path": "/root/beta",
                    "parent_agent_path": "/root",
                },
            },
        ],
        "edges": [],
    }


def _entry(
    path: str,
    source_id: str,
    thread: str,
    messages: list[dict[str, Any]],
    is_root: bool,
) -> dict[str, Any]:
    return {
        "provider": "codex",
        "source_id": source_id,
        "source_name": path,
        "conversation_preview": {
            "agent_path": path,
            "thread_id": thread,
            "is_root": is_root,
            "parent_thread_id": None if is_root else "S",
            "messages": messages,
        },
    }


def test_panel_reads_the_namespaced_agent_path_attributes() -> None:
    source = PANEL.read_text(encoding="utf-8")
    assert "attrs(node).agent_path||attrs(node).child_agent_path||attrs(node).root_agent_path" in source
    assert "node?.name||''" in source


def test_default_render_lists_one_isolated_section_per_agent() -> None:
    html = render_static_dashboard_html(_graph(), conversation_entries=[])
    assert "execweave-agent-view" in html
    assert "execweave-conversation-agent-section" not in html
    assert "execweaveRenderRichConversationRecords" not in html
    assert "selectedNode=null" in html


def test_a_message_authored_by_another_agent_is_not_shown_as_ones_own() -> None:
    source = PANEL.read_text(encoding="utf-8")
    policy = PANEL_DEFAULT.read_text(encoding="utf-8")
    assert "const own=(message,path)=>!message?.sender||String(message.sender)===path" in source
    assert "String(message?.recipient||'')===path" in policy
    assert "own(message,path)" in source
    assert "sender!==path" in policy


def test_no_phantom_agents_from_unread_topology_paths(tmp_path: Path) -> None:
    del tmp_path
    source = PANEL.read_text(encoding="utf-8")
    assert "attrs(node).child_agent_path" in source
    assert "/root/<subagent_id>" not in source
    assert "subagent_id" not in source


def test_an_entry_without_messages_does_not_become_a_second_agent(tmp_path: Path) -> None:
    del tmp_path
    node_id = "agent:codex:S:subagent:one"
    entries = [
        _entry(
            "/root/alpha",
            node_id,
            "T1",
            [{"sender": "/root/alpha", "text": "ANSWER"}],
            False,
        ),
        {"provider": "codex", "source_id": node_id, "conversation_preview": {}},
    ]
    html = render_static_dashboard_html(_graph(), conversation_entries=entries)
    assert html.count('"source_id":"agent:codex:S:subagent:one"') == 2
    assert "function recordFor(node)" in html
    assert "return aggregate(entries.filter(" in html
    assert "messages:ordered.map(item=>item.message)" in html
    assert "entries.find(entry=>String(entry?.source_id||'')" not in html
    assert "execweave-conversation-agent-section" not in html


def test_each_agent_section_carries_only_messages_it_authored(tmp_path: Path) -> None:
    del tmp_path
    shared = [
        {"sender": "user", "recipient": "/root", "text": "ROOT PROMPT"},
        {"sender": "/root", "recipient": "/root/alpha", "text": "ALPHA TASK"},
        {"sender": "/root/alpha", "recipient": "/root", "text": "ALPHA ANSWER"},
        {"sender": "/root/beta", "recipient": "/root", "text": "BETA ANSWER"},
    ]
    entries = [
        _entry("/root", "agent:OpenAI Codex", "S", list(shared), True),
        _entry("/root/alpha", "agent:codex:S:subagent:one", "T1", list(shared), False),
        _entry("/root/beta", "agent:codex:S:subagent:two", "T2", list(shared), False),
    ]
    html = render_static_dashboard_html(_graph(), conversation_entries=entries)
    assert "ROOT PROMPT" in html
    assert "ALPHA TASK" in html
    assert "ALPHA ANSWER" in html
    assert "BETA ANSWER" in html
    assert "function childRounds(messages,path)" in html
    assert "const isTask=message=>{const sender" in html
    assert "let responses=inside.filter" in html
    assert inject_agent_panel(html) == html
