"""Node width is measured from the label, and lanes move out of its way.

Every node used to be 160px wide with its label cut at 28 characters, so a name like
``collaborationspawn_agent`` was unreadable no matter how much empty canvas sat beside
it. Widening alone is not enough: lane x positions were constants 270-280 apart, so a
node wider than that would reach into the lane on its right. These checks drive a real
page because a layout defect is only visible once something is drawn.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from test_viewer_agent_isolation_e2e import _browser, _launch

LONG_LABEL = "collaborationspawn_agent_with_a_very_long_provider_supplied_name"


def _graph_with(label: str) -> dict[str, Any]:
    """A minimal graph whose tool node carries the label under test."""
    return {
        "schema_version": "1.0",
        "nodes": [
            {"id": "agent:/root", "type": "agent", "name": "/root",
             "attributes": {"agent_role": "root", "agent_path": "/root"}},
            {"id": "tool:codex:x", "type": "tool", "name": label, "attributes": {}},
        ],
        "edges": [
            {"id": "e1", "source": "agent:/root", "target": "tool:codex:x",
             "relation": "USES_TOOL", "attributes": {}},
        ],
    }


def _render(tmp_path: Path, graph: dict[str, Any]) -> Path:
    from execweave.viewer_projection import write_graph_html

    viewer = tmp_path / "viewer.html"
    write_graph_html(graph, viewer)
    return viewer


def _nodes(page: Any) -> list[dict[str, Any]]:
    """Read each drawn node's box and label straight off the page."""
    page.wait_for_selector(".node", timeout=15000)
    return json.loads(
        page.evaluate(
            """() => JSON.stringify([...document.querySelectorAll('.node')].map(g => {
                const rect = g.querySelector('rect');
                const label = g.querySelector('.name-label');
                const t = (g.getAttribute('transform') || '').match(/translate\\(([-0-9.]+) ([-0-9.]+)\\)/);
                return {
                    id: g.dataset.id,
                    lane: g.dataset.layoutLane || '',
                    width: rect ? Number(rect.getAttribute('width')) : 0,
                    x: t ? Number(t[1]) : 0,
                    y: t ? Number(t[2]) : 0,
                    text: label ? label.textContent : '',
                    full: g.dataset.fullLabel || '',
                    title: g.querySelector('title')?.textContent || '',
                };
            }))"""
        )
    )


def _drawn(tmp_path: Path, graph: dict[str, Any]) -> list[dict[str, Any]]:
    viewer = _render(tmp_path, graph)
    manager, executable = _browser()
    with manager as playwright:
        browser = _launch(playwright, executable)
        try:
            page = browser.new_page(viewport={"width": 1600, "height": 900})
            page.goto(viewer.as_uri())
            return _nodes(page)
        finally:
            browser.close()


def test_a_long_label_widens_its_node_instead_of_being_cut(tmp_path: Path) -> None:
    drawn = _drawn(tmp_path, _graph_with(LONG_LABEL))
    tool = next(node for node in drawn if node["id"] == "tool:codex:x")

    assert tool["width"] > 160, f"the node stayed at the old fixed width: {tool}"
    assert tool["width"] <= 320, f"the node grew past the ceiling: {tool}"
    assert tool["full"] == LONG_LABEL, "the full label must survive on the element"
    assert tool["title"] == LONG_LABEL, "hover must offer the whole label"
    assert "…" in tool["text"] or tool["text"] == LONG_LABEL, (
        f"a label that does not fit must end in an ellipsis, not a hard cut: {tool['text']!r}"
    )
    assert not tool["text"].startswith(LONG_LABEL[:28] + "x"), "still cut at 28 characters"


def test_a_short_label_keeps_the_minimum_width(tmp_path: Path) -> None:
    """Growth is driven by the label, so an ordinary name must not move anything."""
    drawn = _drawn(tmp_path, _graph_with("read"))
    tool = next(node for node in drawn if node["id"] == "tool:codex:x")
    assert tool["width"] == 160, f"a short label must not widen its node: {tool}"


def test_a_wide_node_never_reaches_into_the_next_lane(tmp_path: Path) -> None:
    """The lane a node sits in must start clear of the widest node before it."""
    drawn = _drawn(tmp_path, _graph_with(LONG_LABEL))
    ordered = sorted(drawn, key=lambda node: node["x"])
    for left, right in zip(ordered, ordered[1:]):
        if left["x"] == right["x"]:
            continue
        assert left["x"] + left["width"] <= right["x"], (
            f"{left['id']} ends at {left['x'] + left['width']} but "
            f"{right['id']} starts at {right['x']}"
        )


def test_lanes_keep_their_established_positions_when_nothing_is_wide(tmp_path: Path) -> None:
    """Deriving lane x must reproduce the table it replaced, or every run shifts."""
    graph = _graph_with("read")
    graph["nodes"].append(
        {"id": "agent:/root/a", "type": "agent", "name": "a",
         "attributes": {"agent_role": "child", "agent_path": "/root/a"}}
    )
    graph["edges"].append(
        {"id": "e2", "source": "agent:/root", "target": "agent:/root/a",
         "relation": "SPAWNED_AGENT", "attributes": {}}
    )
    by_lane = {node["lane"]: node["x"] for node in _drawn(tmp_path, graph)}
    assert by_lane.get("root") == 270, by_lane
    assert by_lane.get("agent") == 540, by_lane
    assert by_lane.get("tool") == 1100, by_lane


def test_the_edge_leaves_the_wide_node_at_its_own_right_edge(tmp_path: Path) -> None:
    """Routing anchored on the old constant would start inside a widened node."""
    viewer = _render(tmp_path, _graph_with(LONG_LABEL))
    manager, executable = _browser()
    with manager as playwright:
        browser = _launch(playwright, executable)
        try:
            page = browser.new_page(viewport={"width": 1600, "height": 900})
            page.goto(viewer.as_uri())
            drawn = _nodes(page)
            path = page.eval_on_selector(".edge", "el => el.getAttribute('d')")
        finally:
            browser.close()

    root = next(node for node in drawn if node["id"] == "agent:/root")
    start_x = float(path.split()[1])
    assert start_x == pytest.approx(root["x"] + root["width"], abs=1), (
        f"edge starts at {start_x}, root node spans {root['x']}..{root['x'] + root['width']}"
    )
