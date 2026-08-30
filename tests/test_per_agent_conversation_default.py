"""Every agent shows only its own conversation, before anyone clicks anything.

v0.7.4 scoped the conversation panel to a selected agent, but the default view was
still one merged tree carrying every agent's messages. Opening a run therefore looked
exactly as it did before the fix: root's section replayed each child's answer, and the
isolation only appeared once the reader happened to click a node.

Two defects made the default worse than it looked. The panel read ``agent_path`` from
graph nodes, but topology attributes were namespaced apart, so a subagent carries
``child_agent_path``; the panel invented ``/root/<subagent_id>`` paths and published
them as extra agents beside the real ones. Conversation entries that materialized no
messages also became their own agent records, so a four-agent run reported seven.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from execweave.viewer_projection import write_graph_html

SRC = Path(__file__).resolve().parents[1] / "src" / "execweave"
TREE = SRC / "viewer_conversation_tree.py"


def _graph() -> dict[str, Any]:
    """A root that dispatched two children, shaped like a real Codex run."""
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


# ── the namespaced topology attributes must be read ──────────────────────────


def test_panel_reads_the_namespaced_agent_path_attributes() -> None:
    """A subagent carries child_agent_path, not agent_path."""
    tree = TREE.read_text(encoding="utf-8")
    assert tree.count("attrs.agent_path||attrs.child_agent_path||attrs.root_agent_path") == 2, (
        "both viewer variants must resolve the namespaced topology paths"
    )
    assert "attrs.agent_path||'').trim()" not in tree, (
        "reading agent_path alone invents /root/<id> paths for every subagent"
    )


# ── the default view, not a click, must isolate each agent ───────────────────


def test_default_render_lists_one_isolated_section_per_agent() -> None:
    tree = TREE.read_text(encoding="utf-8")
    for symbol in (
        "execweaveConversationAgentSection",
        "conversationAgentSection",
        "execweaveOrderedConversationRecords",
        "orderedConversationRecords",
    ):
        assert symbol in tree, f"{symbol} missing; the default view must scope per agent"
    assert tree.count("each agent shows only its own conversation") == 2
    # The merged root-plus-descendants tree must no longer be the default shape.
    assert "execweaveAppendConversationBranch(children,record" not in tree.split(
        "_STATIC_RENDER"
    )[1].split('""".strip()')[0]


def test_a_message_authored_by_another_agent_is_not_shown_as_ones_own() -> None:
    tree = TREE.read_text(encoding="utf-8")
    for symbol in ("execweaveOwnConversationMessage", "ownConversationMessage"):
        assert symbol in tree
    # A sender that is another agent path is excluded; 'user' and own turns stay.
    # An agent-authored message belongs to its sender; anything else follows its
    # recipient, so a user prompt addressed to root never reaches a child.
    assert tree.count("if(sender.startsWith('/'))return sender===own") == 2
    assert tree.count("if(recipient.startsWith('/'))return recipient===own") == 2


# ── execute the shipped page, not just grep it ───────────────────────────────


def _run_render(nodes: list[dict[str, Any]], entries: list[dict[str, Any]], tmp_path: Path):
    """Drive the shipped helpers from a generated page against supplied evidence."""
    html_path = tmp_path / "viewer.html"
    if not html_path.exists():
        write_graph_html({"nodes": nodes, "edges": []}, html_path)
    html = html_path.read_text(encoding="utf-8")
    helpers = html[
        html.index("const execweaveConversationRootIds") : html.index(
            "function execweaveRenderRichConversationRecords"
        )
    ]
    script = tmp_path / "sections.js"
    script.write_text(
        "const possibleNodes=JSON.parse(process.argv[2]);\n"
        + helpers
        + """
const entries=JSON.parse(process.argv[3]);
const records=execweaveOrderedConversationRecords(execweaveConversationAgentRecords(entries));
console.log(JSON.stringify(records.map(record=>({
  path:record.path,
  count:execweaveConversationMessageCount(record),
  texts:(execweaveOwnConversationEntry(record)?.conversation_preview?.messages||[])
          .map(message=>String(message.text||''))
}))));
""",
        encoding="utf-8",
    )
    result = subprocess.run(
        [shutil.which("node"), str(script), json.dumps(nodes), json.dumps(entries)],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def _entry(path: str, source_id: str, thread: str, messages: list[dict[str, Any]], is_root: bool):
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


@pytest.mark.skipif(shutil.which("node") is None, reason="node is unavailable")
def test_no_phantom_agents_from_unread_topology_paths(tmp_path: Path) -> None:
    """A subagent's path lives in child_agent_path; reading agent_path invents one."""
    sections = _run_render(_graph()["nodes"], [], tmp_path)
    paths = [section["path"] for section in sections]
    assert paths == ["/root", "/root/alpha", "/root/beta"], paths
    assert not any("subagent" in path for path in paths), "a fabricated id path appeared"


@pytest.mark.skipif(shutil.which("node") is None, reason="node is unavailable")
def test_an_entry_without_messages_does_not_become_a_second_agent(tmp_path: Path) -> None:
    node_id = "agent:codex:S:subagent:one"
    entries = [
        _entry("/root/alpha", node_id, "T1", [{"sender": "/root/alpha", "text": "ANSWER"}], False),
        {"provider": "codex", "source_id": node_id, "conversation_preview": {}},
    ]
    sections = _run_render([], entries, tmp_path)
    assert len(sections) == 1, [section["path"] for section in sections]
    assert sections[0]["texts"] == ["ANSWER"]


@pytest.mark.skipif(shutil.which("node") is None, reason="node is unavailable")
def test_each_agent_section_carries_only_messages_it_authored(tmp_path: Path) -> None:
    """Root must not replay a child's answer, and a child must not carry a sibling's."""
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
    by_path = {s["path"]: s for s in _run_render([], entries, tmp_path)}

    root = by_path["/root"]["texts"]
    assert "ROOT PROMPT" in root
    assert "ALPHA TASK" in root, "root authored the assignment, so it stays with root"
    assert "ALPHA ANSWER" not in root, "root must not replay a child's answer"
    assert "BETA ANSWER" not in root

    alpha = by_path["/root/alpha"]["texts"]
    assert alpha == ["ALPHA ANSWER"], alpha
