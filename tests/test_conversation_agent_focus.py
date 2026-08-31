"""Agent selection is owned by the unified compact inspector in v0.7.9.

The old standalone conversation tree is gone. These regressions keep the same test
identities while asserting the replacement contract: one selected agent maps to one
run-local preview, non-agent selection has no conversation scope, and Markdown still
names each archived agent unambiguously.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from execweave.agent_trace import cursor_subagent
from execweave.content_evidence import content_observation_event
from execweave.content_store import FullFidelityContentStore
from execweave.conversation_records import write_conversation_records
from execweave.dashboard_shell import DASHBOARD_HTML
from execweave.live import _LIVE_HTML
from execweave.viewer_agent_panel import inject_agent_panel
from execweave.viewer_projection import write_graph_html

SRC = Path(__file__).resolve().parents[1] / "src" / "execweave"
PANEL = SRC / "viewer_agent_panel.py"


def test_static_viewer_node_click_focuses_that_agent() -> None:
    source = PANEL.read_text(encoding="utf-8")
    assert "document.addEventListener('click'" in source
    assert "event.target.closest?.('.node')" in source
    assert "syncSelection();refresh()" in source
    assert "const node=graphNode(selected.dataset.id);if(node)render(node)" in source


def test_live_dashboard_selection_focuses_that_agent() -> None:
    assert "window.__execweaveAgentPanel" in _LIVE_HTML
    assert "function syncSelection()" in _LIVE_HTML
    assert "const node=graphNode(selected.dataset.id);if(node)render(node)" in _LIVE_HTML


def test_both_viewer_variants_carry_the_focus_implementation() -> None:
    assert "window.__execweaveAgentPanel" in _LIVE_HTML
    assert "window.__execweaveAgentPanel" in DASHBOARD_HTML
    assert _LIVE_HTML.count("window.__execweaveAgentPanel") == 1
    assert DASHBOARD_HTML.count("window.__execweaveAgentPanel") == 1
    assert inject_agent_panel(DASHBOARD_HTML) == DASHBOARD_HTML


def test_focused_render_runs_before_the_whole_tree_is_built() -> None:
    source = PANEL.read_text(encoding="utf-8")
    assert "details.replaceChildren();" in source
    assert "details.appendChild(list);return true" in source
    assert "execweaveRenderRichConversationRecords" not in DASHBOARD_HTML
    assert "execweaveRenderFocusedConversation" not in DASHBOARD_HTML


def test_focus_selects_exactly_one_agent_thread(tmp_path: Path) -> None:
    graph = _two_agent_graph(tmp_path)
    viewer = tmp_path / "viewer.html"
    write_graph_html(graph, viewer)
    html = viewer.read_text(encoding="utf-8")

    source = PANEL.read_text(encoding="utf-8")
    assert "return aggregate(entries.filter(" in source
    assert "String(entry?.source_id||'')===nodeId" in source
    assert "String(entry?.conversation_preview?.agent_path||'')===path" in source
    assert "messages:ordered.map(item=>item.message)" in source
    assert "selectedNode=node" in source
    assert "else selectedNode=null" in source
    assert "window.__execweaveStaticConversations=" in html
    assert "execweaveConversationFocusNodeId" not in html


def _two_agent_graph(run_root: Path) -> dict[str, Any]:
    store = FullFidelityContentStore(run_root)
    root = {
        "id": "agent:OpenAI Codex",
        "type": "agent",
        "name": "OpenAI Codex",
        "attributes": {
            "provider": "codex",
            "session_id": "S",
            "agent_role": "root",
            "root_agent_path": "/root",
            "root_topology_evidence": "provider_rollout_session_meta",
        },
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
        assert identity.startswith("/root"), f"heading must identify the agent, got {heading!r}"
    assert len({h[4:].split(" · ", 1)[0] for h in headings}) == len(headings), (
        "every section heading must name a distinct agent"
    )


def test_markdown_heading_does_not_repeat_the_provider_as_an_annotation(
    tmp_path: Path,
) -> None:
    run_root = tmp_path / "run"
    write_conversation_records(_two_agent_graph(run_root), run_root)
    text = (run_root / "conversations.md").read_text(encoding="utf-8")
    root_heading = next(line for line in text.splitlines() if line.startswith("### /root ·"))
    assert not re.search(r"\(OpenAI Codex\)", root_heading), root_heading
    assert "(Avicenna)" in text
