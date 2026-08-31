"""Chromium regressions for the PR #25 pre-merge hardening set."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from test_graph_node_sizing_e2e import LONG_LABEL, _browser, _launch, _nodes, _render

pytestmark = pytest.mark.viewer_e2e

_CORE_SEAM = (
    "window.__execweaveCore={getActivities:()=>activities.slice(),getGraph:()=>graph,"
    "getPositions:()=>new Map(positions),selectEdge,selectNode,focusNode,markLatest,"
    "setCameraMode};"
)
_CORE_TEST_SEAM = (
    "window.__execweaveCore={getActivities:()=>activities.slice(),getGraph:()=>graph,"
    "getPositions:()=>new Map(positions),selectEdge,selectNode,focusNode,markLatest,"
    "setCameraMode,applyDelta,graphBounds,execweaveMeasure};"
)


def _instrumented_viewer(tmp_path: Path, graph: dict[str, Any]) -> Path:
    """Expose closed-over renderer functions only in this test artifact."""
    from execweave.dashboard_shell import render_static_dashboard_html

    html = render_static_dashboard_html(graph)
    assert _CORE_SEAM in html, "dashboard core seam changed; update this test deliberately"
    html = html.replace(_CORE_SEAM, _CORE_TEST_SEAM, 1)
    viewer = tmp_path / "instrumented-viewer.html"
    viewer.write_text(html, encoding="utf-8")
    return viewer


def _by_id(page: Any) -> dict[str, dict[str, Any]]:
    return {row["id"]: row for row in _nodes(page)}


def _root() -> dict[str, Any]:
    return {
        "id": "agent:/root",
        "type": "agent",
        "name": "/root",
        "attributes": {"agent_role": "root", "agent_path": "/root"},
    }


def _edge(ident: str, source: str, target: str, relation: str, **extra: Any) -> dict[str, Any]:
    return {
        "id": ident,
        "source": source,
        "target": target,
        "relation": relation,
        "attributes": {},
        **extra,
    }


def _layout_shift_graph() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "node_count": 2,
        "edge_count": 1,
        "event_count": 1,
        "nodes": [_root(), {"id": "file:f", "type": "file", "name": "a.md", "attributes": {}}],
        "edges": [_edge("e-file", "agent:/root", "file:f", "WROTE_FILE")],
    }


def test_live_delta_moves_existing_nodes_when_a_new_wide_upstream_lane_appears(
    tmp_path: Path,
) -> None:
    viewer = _instrumented_viewer(tmp_path, _layout_shift_graph())
    manager, executable = _browser()
    with manager as playwright:
        browser = _launch(playwright, executable)
        try:
            page = browser.new_page(viewport={"width": 1500, "height": 900})
            page.goto(viewer.as_uri())
            page.wait_for_selector(".node", timeout=15000)
            before = _by_id(page)
            before_paths = page.eval_on_selector_all(
                ".edge", "nodes => nodes.map(node => node.getAttribute('d'))"
            )
            update = {
                "event_count": 2,
                "node_count": 3,
                "edge_count": 2,
                "nodes_added": [
                    {
                        "id": "process:wide",
                        "type": "process",
                        "name": LONG_LABEL,
                        "attributes": {},
                    }
                ],
                "nodes_updated": [],
                "edges_added": [
                    _edge("e-start", "process:wide", "agent:/root", "STARTED_AGENT")
                ],
                "edges_updated": [],
            }
            page.evaluate("update => window.__execweaveCore.applyDelta(update)", update)
            page.wait_for_timeout(80)
            after = _by_id(page)
            after_paths = page.eval_on_selector_all(
                ".edge", "nodes => nodes.map(node => node.getAttribute('d'))"
            )
        finally:
            browser.close()

    assert after["process:wide"]["width"] > 160, after["process:wide"]
    assert after["agent:/root"]["x"] > before["agent:/root"]["x"] + 100
    assert after["file:f"]["x"] > before["file:f"]["x"] + 100
    assert after["agent:/root"]["y"] == pytest.approx(before["agent:/root"]["y"], abs=1)
    assert after["file:f"]["y"] == pytest.approx(before["file:f"]["y"], abs=1)
    assert before_paths != after_paths, "existing edges were not rerouted with moved nodes"


def _wide_camera_graph() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "nodes": [
            _root(),
            {"id": "process:wide", "type": "process", "name": LONG_LABEL, "attributes": {}},
            {
                "id": "file:wrapped",
                "type": "file",
                "name": "src/execweave/very/deeply/nested/module_with_a_long_name.py",
                "attributes": {},
            },
        ],
        "edges": [
            _edge("e1", "process:wide", "agent:/root", "STARTED_AGENT"),
            _edge("e2", "agent:/root", "file:wrapped", "WROTE_FILE"),
        ],
    }


def test_bounds_and_focus_use_actual_node_dimensions(tmp_path: Path) -> None:
    viewer = _instrumented_viewer(tmp_path, _wide_camera_graph())
    manager, executable = _browser()
    with manager as playwright:
        browser = _launch(playwright, executable)
        try:
            page = browser.new_page(viewport={"width": 1200, "height": 760})
            page.goto(viewer.as_uri())
            page.wait_for_selector('.node[data-id="process:wide"]', timeout=15000)
            bounds = page.evaluate(
                """() => {
                const positions=window.__execweaveCore.getPositions();
                const rows=[...document.querySelectorAll('.node')].map(group=>{
                  const p=positions.get(group.dataset.id),rect=group.querySelector('rect');
                  return {x:p.x,y:p.y,w:Number(rect.getAttribute('width')),
                          h:Number(rect.getAttribute('height'))};
                });
                return {actual:window.__execweaveCore.graphBounds(),expected:{
                  minX:Math.min(...rows.map(r=>r.x)),
                  maxX:Math.max(...rows.map(r=>r.x+r.w)),
                  minY:Math.min(...rows.map(r=>r.y)),
                  maxY:Math.max(...rows.map(r=>r.y+r.h))}};
                }"""
            )
            page.evaluate("() => window.__execweaveCore.focusNode('process:wide')")
            page.wait_for_timeout(300)
            centered = page.evaluate(
                """() => {
                const node=document.querySelector('.node[data-id="process:wide"] rect')
                  .getBoundingClientRect();
                const svg=document.getElementById('svg').getBoundingClientRect();
                return {dx:(node.left+node.width/2)-(svg.left+svg.width/2),
                        dy:(node.top+node.height/2)-(svg.top+svg.height/2),width:node.width};
                }"""
            )
        finally:
            browser.close()

    for key in ("minX", "maxX", "minY", "maxY"):
        assert bounds["actual"][key] == pytest.approx(bounds["expected"][key], abs=1), bounds
    assert centered["width"] > 160, centered
    assert abs(centered["dx"]) <= 3, centered
    assert abs(centered["dy"]) <= 3, centered


def _root_barycentre_graph() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "nodes": [
            _root(),
            {
                "id": "agent:/root/a",
                "type": "agent",
                "name": "a",
                "attributes": {"agent_role": "child", "agent_path": "/root/a"},
            },
            {
                "id": "agent:/root/b",
                "type": "agent",
                "name": "b",
                "attributes": {"agent_role": "child", "agent_path": "/root/b"},
            },
            {"id": "file:z-child0", "type": "file", "name": "z-child0", "attributes": {}},
            {"id": "file:a-root", "type": "file", "name": "a-root", "attributes": {}},
            {"id": "file:b-child1", "type": "file", "name": "b-child1", "attributes": {}},
        ],
        "edges": [
            _edge(
                "spawn-a", "agent:/root", "agent:/root/a", "SPAWNED_AGENT", first_sequence=1
            ),
            _edge(
                "spawn-b", "agent:/root", "agent:/root/b", "SPAWNED_AGENT", first_sequence=2
            ),
            _edge("f0", "agent:/root/a", "file:z-child0", "WROTE_FILE"),
            _edge("fr", "agent:/root", "file:a-root", "WROTE_FILE"),
            _edge("f1", "agent:/root/b", "file:b-child1", "WROTE_FILE"),
        ],
    }


def test_root_owned_evidence_participates_in_barycentre_order(tmp_path: Path) -> None:
    viewer = _render(tmp_path, _root_barycentre_graph())
    manager, executable = _browser()
    with manager as playwright:
        browser = _launch(playwright, executable)
        try:
            page = browser.new_page(viewport={"width": 1500, "height": 900})
            page.goto(viewer.as_uri())
            page.wait_for_selector(".node", timeout=15000)
            rows = _by_id(page)
        finally:
            browser.close()

    assert (
        rows["file:z-child0"]["y"]
        < rows["file:a-root"]["y"]
        < rows["file:b-child1"]["y"]
    ), rows


def _observed_tool_graph() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "nodes": [
            _root() | {"id": "agent:OpenCode"},
            {
                "id": "tool-call:opencode:s:c1",
                "type": "tool_call",
                "name": "Read",
                "first_seen": "2026-08-31T08:00:00Z",
                "attributes": {"tool_name": "Read"},
            },
            {"id": "tool:opencode:Read", "type": "tool", "name": "Read", "attributes": {}},
            {
                "id": "tool-call-observation:antigravity:c:2",
                "type": "tool_call_observation",
                "name": "completed tool (identity unavailable)",
                "first_seen": "2026-08-31T08:01:00Z",
                "attributes": {"conversation_id": "c", "step_index": 2},
            },
        ],
        "edges": [
            _edge("o1", "agent:OpenCode", "tool-call:opencode:s:c1", "OBSERVED_TOOL_CALL"),
            _edge("o1b", "agent:OpenCode", "tool-call:opencode:s:c1", "OWNED_TOOL_CALL"),
            _edge("u1", "tool-call:opencode:s:c1", "tool:opencode:Read", "USES_TOOL"),
            _edge(
                "o2",
                "agent:OpenCode",
                "tool-call-observation:antigravity:c:2",
                "OBSERVED_TOOL_CALL",
            ),
        ],
    }


def _cards(page: Any, node_id: str) -> dict[str, str]:
    found = page.eval_on_selector_all(
        ".node",
        """(nodes,id)=>{const node=nodes.find(item=>item.dataset.id===id);if(!node)return false;
        node.dispatchEvent(new MouseEvent('click',{bubbles:true}));return true}""",
        node_id,
    )
    assert found, node_id
    page.wait_for_timeout(200)
    pairs = page.evaluate(
        """() => [...document.querySelectorAll('.execweave-agent-card')].map(c => [
        c.querySelector('.execweave-agent-label')?.textContent,
        c.querySelector('.execweave-agent-body')?.textContent])"""
    )
    return {label: body for label, body in pairs if label}


def test_tool_panel_accepts_observed_and_owned_relations_without_duplicates(tmp_path: Path) -> None:
    viewer = _render(tmp_path, _observed_tool_graph())
    manager, executable = _browser()
    with manager as playwright:
        browser = _launch(playwright, executable)
        try:
            page = browser.new_page(viewport={"width": 1400, "height": 900})
            page.goto(viewer.as_uri())
            page.wait_for_selector(".node", timeout=15000)
            tools = _cards(page, "agent:OpenCode").get("Tools", "")
        finally:
            browser.close()

    assert "Read" in tools, tools
    assert tools.count("Read") == 1, f"the same logical call was double-counted: {tools!r}"
    assert "completed tool (identity unavailable)" in tools, tools


def test_repeated_text_measurement_hits_the_browser_once(tmp_path: Path) -> None:
    viewer = _instrumented_viewer(tmp_path, _layout_shift_graph())
    manager, executable = _browser()
    with manager as playwright:
        browser = _launch(playwright, executable)
        try:
            page = browser.new_page(viewport={"width": 1200, "height": 760})
            page.goto(viewer.as_uri())
            page.wait_for_selector(".node", timeout=15000)
            calls = page.evaluate(
                """() => {
                const proto=SVGTextElement.prototype,original=proto.getComputedTextLength;
                let count=0;
                proto.getComputedTextLength=function(){count++;return original.call(this)};
                try{
                  for(let i=0;i<30;i++)
                    window.__execweaveCore.execweaveMeasure('__execweave_cache_probe__');
                }finally{proto.getComputedTextLength=original}
                return count;
                }"""
            )
        finally:
            browser.close()

    assert calls == 1, f"the same string caused {calls} synchronous SVG measurements"


def _dense_raw_graph(call_count: int = 40, junk_count: int = 400) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = [_root()]
    edges: list[dict[str, Any]] = []
    for index in range(call_count):
        call_id = f"tool-call:test:{index}"
        nodes.append(
            {
                "id": call_id,
                "type": "tool_call",
                "name": f"tool-{index}",
                "first_seen": f"2026-08-31T08:00:{index % 60:02d}Z",
                "attributes": {},
            }
        )
        edges.append(_edge(f"call-{index}", "agent:/root", call_id, "OBSERVED_TOOL_CALL"))
    for index in range(junk_count):
        nodes.append(
            {
                "id": f"observed-content:junk:{index}",
                "type": "observed_content",
                "name": "junk",
                "attributes": {},
            }
        )
    return {"schema_version": "1.0", "nodes": nodes, "edges": edges}


def test_dense_tool_panel_does_not_linearly_find_each_raw_node(tmp_path: Path) -> None:
    viewer = _render(tmp_path, _dense_raw_graph())
    manager, executable = _browser()
    with manager as playwright:
        browser = _launch(playwright, executable)
        try:
            page = browser.new_page(viewport={"width": 1400, "height": 900})
            page.goto(viewer.as_uri())
            page.wait_for_selector(".node", timeout=15000)
            page.evaluate(
                """() => {
                const original=Array.prototype.find;
                window.__execweaveRawFindCount=0;window.__execweaveOriginalFind=original;
                Array.prototype.find=function(...args){
                  let raw=false;
                  for(let i=0;i<Math.min(this.length,64);i++){
                    if(String(this[i]?.id||'').startsWith('tool-call:')){raw=true;break}
                  }
                  if(raw)window.__execweaveRawFindCount++;
                  return original.apply(this,args);
                };
                }"""
            )
            try:
                _cards(page, "agent:/root")
                count = page.evaluate("() => window.__execweaveRawFindCount")
            finally:
                page.evaluate("() => {Array.prototype.find=window.__execweaveOriginalFind}")
        finally:
            browser.close()

    assert count == 0, f"tool rendering performed {count} linear raw-node searches"
