"""Selecting an agent must scope what the conversation panel shows.

`conversations.json` already isolates each agent correctly, but the viewer rendered
every thread as one tree no matter which node was selected: `selectedNodeId` never
reached the conversation panel, whose render function only ever took `(panel, entries)`.
Clicking `/root` and clicking `/root/ci_agent` therefore produced identical output,
which made the per-agent isolation invisible to the person reading it.

The Markdown index had the matching problem: every section was headed
`provider · nickname`, and a Codex nickname is unrelated to the task the agent was
given, so six agents read as six variants of "OpenAI Codex · <a scientist>".
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from execweave.agent_trace import cursor_subagent
from execweave.content_evidence import content_observation_event
from execweave.content_store import FullFidelityContentStore
from execweave.conversation_records import write_conversation_records

SRC = Path(__file__).resolve().parents[1] / "src" / "execweave"
VIEWER = SRC / "viewer.py"
TREE = SRC / "viewer_conversation_tree.py"
LIVE_SCRIPT = SRC / "live_view_script_a.py"


# ── the viewer must route selection into the conversation panel ───────────────


def test_static_viewer_node_click_focuses_that_agent() -> None:
    source = VIEWER.read_text(encoding="utf-8")
    assert "showDetails('Node',node);if(typeof execweaveFocusConversationAgent==='function')" in source, (
        "clicking a graph node must scope the conversation panel to that agent"
    )
    assert "execweaveClearConversationFocus()" in source, (
        "clicking the background must restore the full conversation tree"
    )


def test_live_dashboard_selection_focuses_that_agent() -> None:
    source = LIVE_SCRIPT.read_text(encoding="utf-8")
    assert "window.__execweaveFocusConversationAgent?.(node)" in source
    # An edge is not an agent, so selecting one drops the agent scope.
    assert "window.__execweaveClearConversationFocus?.()" in source


def test_both_viewer_variants_carry_the_focus_implementation() -> None:
    tree = TREE.read_text(encoding="utf-8")
    for symbol in (
        "execweaveConversationFocusRecord",
        "execweaveRenderFocusedConversation",
        "conversationFocusRecord",
        "renderFocusedConversation",
    ):
        assert symbol in tree, f"{symbol} missing; static and live must both scope"
    # The live panel is inside an IIFE, so the graph script reaches it through window.
    assert "window.__execweaveFocusConversationAgent=focusConversationAgent" in tree
    assert "window.__execweaveClearConversationFocus=clearConversationFocus" in tree
    # Records must carry the graph node id, which is how a click is matched to a thread.
    assert tree.count("nodeId:String(entry?.source_id||'')") == 2
    assert tree.count("nodeId:String(node.id)") == 2


def test_focused_render_runs_before_the_whole_tree_is_built() -> None:
    """The focus branch has to short-circuit, or the full tree is drawn underneath."""
    tree = TREE.read_text(encoding="utf-8")
    assert (
        "if(focused){execweaveRenderFocusedConversation(panel,focused);return true}"
        in tree
    )
    assert "if(focused){renderFocusedConversation(panel,focused);return true}" in tree


# ── execute the shipped JavaScript, not just grep it ─────────────────────────


def _shipped_focus_helpers(viewer_html: str) -> str:
    start = viewer_html.index("let execweaveConversationFocusNodeId=null;")
    end = viewer_html.index("function execweaveRenderFocusedConversation")
    return viewer_html[start:end]


@pytest.mark.skipif(shutil.which("node") is None, reason="node is unavailable")
def test_focus_selects_exactly_one_agent_thread(tmp_path: Path) -> None:
    """Drive the real functions from a generated viewer through every selection state."""
    from execweave.viewer_projection import write_graph_html

    graph = _two_agent_graph(tmp_path)
    html_path = tmp_path / "viewer.html"
    write_graph_html(graph, html_path)
    helpers = _shipped_focus_helpers(html_path.read_text(encoding="utf-8"))

    script = tmp_path / "focus.js"
    script.write_text(
        helpers
        + """
let renders=0;
function execweaveRenderConversationRecords(){renders++}
const records=[
 {key:'a',path:'/root',          nodeId:'agent:OpenAI Codex',        entry:{},isRoot:true},
 {key:'b',path:'/root/child_one',nodeId:'agent:codex:S:subagent:ONE',entry:{},isRoot:false},
 {key:'c',path:'/root/child_two',nodeId:'agent:codex:S:subagent:TWO',entry:{},isRoot:false},
];
const pick=()=>{const r=execweaveConversationFocusRecord(records);return r?r.path:null};
const out={};
out.unfocused=pick();
execweaveFocusConversationAgent({type:'agent',id:'agent:codex:S:subagent:ONE'});
out.child=pick();
execweaveFocusConversationAgent({type:'agent',id:'agent:OpenAI Codex'});
out.root=pick();
execweaveFocusConversationAgent({type:'process',id:'process:1'});
out.nonAgent=pick();
execweaveFocusConversationAgent({type:'agent',id:'agent:codex:S:subagent:TWO'});
execweaveClearConversationFocus();
out.cleared=pick();
out.renders=renders;
console.log(JSON.stringify(out));
""",
        encoding="utf-8",
    )
    result = subprocess.run(
        [shutil.which("node"), str(script)], capture_output=True, text=True, check=True
    )
    payload = json.loads(result.stdout)

    assert payload["unfocused"] is None, "no selection must keep the full tree"
    assert payload["child"] == "/root/child_one", "selecting a child must scope to it"
    assert payload["root"] == "/root", "selecting root must scope to root alone"
    assert payload["nonAgent"] is None, "a non-agent node carries no conversation scope"
    assert payload["cleared"] is None
    assert payload["renders"] >= 4, "each scope change must repaint the panel"


# ── Markdown headings must identify the agent ────────────────────────────────


def _two_agent_graph(run_root: Path) -> dict[str, Any]:
    store = FullFidelityContentStore(run_root)
    root = {
        "id": "agent:OpenAI Codex",
        "type": "agent",
        "name": "OpenAI Codex",
        "attributes": {"provider": "codex", "session_id": "S", "agent_role": "root",
                       "root_agent_path": "/root",
                       "root_topology_evidence": "provider_rollout_session_meta"},
    }
    child = cursor_subagent(
        {"session_id": "S", "subagent_id": "child-1", "subagent_type": "Explore"}
    )
    assert child is not None
    child["attributes"]["agent_nickname"] = "Avicenna"

    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    for index, (source, kind, value) in enumerate(
        [
            (root, "codex.assistant_final_response", "root answer"),
            (child, "cursor.subagent_summary", "child answer"),
        ]
    ):
        reference = store.put_text(value, content_kind=kind)
        event = content_observation_event(
            timestamp=f"2026-08-29T00:0{index}:00Z",
            provider=str((source.get("attributes") or {}).get("provider") or "codex"),
            source=source,
            reference=reference,
            relation="PRODUCED_ASSISTANT_RESPONSE",
            observed_field="text",
            evidence_source="provider_hook",
            attribution="provider_hook",
        )
        nodes.setdefault(event["source"]["id"], event["source"])
        nodes.setdefault(event["target"]["id"], event["target"])
        edges.append(
            {
                "source": event["source"]["id"],
                "target": event["target"]["id"],
                "relation": event["relation"],
                "first_sequence": index,
                "last_sequence": index,
                "first_seen": event["timestamp"],
                "last_seen": event["timestamp"],
            }
        )
    return {"nodes": list(nodes.values()), "edges": edges}


def test_markdown_headings_lead_with_the_agent_path(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    graph = _two_agent_graph(run_root)
    write_conversation_records(graph, run_root)
    headings = [
        line
        for line in (run_root / "conversations.md").read_text(encoding="utf-8").splitlines()
        if line.startswith("### ")
    ]
    assert headings, "no agent sections were rendered"
    for heading in headings:
        identity = heading[4:].split(" · ", 1)[0]
        assert identity.startswith("/root"), (
            f"heading must identify the agent, got {heading!r}"
        )
    assert len({h[4:].split(" · ", 1)[0] for h in headings}) == len(headings), (
        "every section heading must name a distinct agent"
    )


def test_markdown_heading_does_not_repeat_the_provider_as_an_annotation(
    tmp_path: Path,
) -> None:
    """Root's label is the provider name; printing it twice reads as noise."""
    run_root = tmp_path / "run"
    write_conversation_records(_two_agent_graph(run_root), run_root)
    text = (run_root / "conversations.md").read_text(encoding="utf-8")
    root_heading = next(
        line for line in text.splitlines() if line.startswith("### /root ·")
    )
    assert not re.search(r"\(OpenAI Codex\)", root_heading), root_heading
    # A genuine nickname is still kept, because it is how the provider named the agent.
    assert "(Avicenna)" in text
