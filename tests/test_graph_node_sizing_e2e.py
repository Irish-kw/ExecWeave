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
                    lines: Number(g.dataset.labelLines || 1),
                    height: rect ? Number(rect.getAttribute('height')) : 0,
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
    # The base renderer cuts at 28 characters regardless of width. Widening the node
    # without re-applying the label buys nothing, and still ends in an ellipsis, so
    # the ellipsis alone cannot tell the two apart. The width has to be spent.
    assert len(tool["text"]) > 28, (
        f"the extra width is not being used; still the 28-character cut: {tool['text']!r}"
    )


def test_a_short_label_keeps_the_minimum_width(tmp_path: Path) -> None:
    """Growth is driven by the label, so an ordinary name must not move anything."""
    drawn = _drawn(tmp_path, _graph_with("read"))
    tool = next(node for node in drawn if node["id"] == "tool:codex:x")
    assert tool["width"] == 160, f"a short label must not widen its node: {tool}"


def _graph_with_wide_node_upstream(label: str) -> dict[str, Any]:
    """A wide node in the first lane, with populated lanes to its right.

    The wide node has to sit upstream of something, or nothing is ever at risk of
    being reached into and the derivation is never exercised. It also cannot be an
    agent: the projection labels an agent by its path, so a long ``name`` on one is
    discarded before it reaches the page.
    """
    graph = _graph_with("read")
    graph["nodes"].append({"id": "process:1", "type": "process", "name": label, "attributes": {}})
    graph["nodes"].append({"id": "model:m", "type": "model", "name": "gpt", "attributes": {}})
    graph["edges"].append(
        {"id": "e3", "source": "process:1", "target": "agent:/root",
         "relation": "STARTED_AGENT", "attributes": {}}
    )
    graph["edges"].append(
        {"id": "e4", "source": "agent:/root", "target": "model:m",
         "relation": "USED_MODEL", "attributes": {}}
    )
    return graph


def test_a_wide_node_never_reaches_into_the_next_lane(tmp_path: Path) -> None:
    """The lane a node sits in must start clear of the widest node before it."""
    drawn = _drawn(tmp_path, _graph_with_wide_node_upstream(LONG_LABEL))
    widest = max(node["width"] for node in drawn)
    assert widest > 160, "the fixture must actually contain a widened node"
    ordered = sorted(drawn, key=lambda node: node["x"])
    for left, right in zip(ordered, ordered[1:]):
        if left["x"] == right["x"]:
            continue
        assert left["x"] + left["width"] <= right["x"], (
            f"{left['id']} ends at {left['x'] + left['width']} but "
            f"{right['id']} starts at {right['x']}"
        )


def test_lanes_keep_their_established_positions_when_nothing_is_wide(tmp_path: Path) -> None:
    """Deriving lane x must reproduce the table it replaced, or every run shifts.

    Every lane has to be occupied for that comparison to mean anything: an empty lane
    reserves no column, so a fixture missing one would not be measuring the derivation
    against the old table at all.
    """
    graph = _graph_with("read")
    graph["nodes"] += [
        {"id": "process:p", "type": "process", "name": "sh", "attributes": {}},
        {"id": "agent:/root/a", "type": "agent", "name": "a",
         "attributes": {"agent_role": "child", "agent_path": "/root/a"}},
        {"id": "model:m", "type": "model", "name": "gpt", "attributes": {}},
        {"id": "file:f", "type": "file", "name": "a.md", "attributes": {}},
        {"id": "endpoint:e", "type": "network_endpoint", "name": "1.1.1.1:443", "attributes": {}},
    ]
    graph["edges"] += [
        {"id": "l1", "source": "process:p", "target": "agent:/root", "relation": "STARTED", "attributes": {}},
        {"id": "l2", "source": "agent:/root", "target": "agent:/root/a", "relation": "SPAWNED_AGENT", "attributes": {}},
        {"id": "l3", "source": "agent:/root/a", "target": "model:m", "relation": "USED_MODEL", "attributes": {}},
        {"id": "l4", "source": "agent:/root/a", "target": "file:f", "relation": "WROTE_FILE", "attributes": {}},
        {"id": "l5", "source": "agent:/root/a", "target": "endpoint:e", "relation": "REACHED", "attributes": {}},
    ]
    by_lane = {node["lane"]: node["x"] for node in _drawn(tmp_path, graph)}
    assert by_lane.get("runtime") == 0, by_lane
    assert by_lane.get("root") == 270, by_lane
    assert by_lane.get("agent") == 540, by_lane
    assert by_lane.get("model") == 820, by_lane
    assert by_lane.get("tool") == 1100, by_lane
    # file took the column endpoint used to hold; endpoint follows it.
    assert by_lane.get("file") == 1380, by_lane
    assert by_lane.get("endpoint") == 1660, by_lane


def test_an_empty_lane_reserves_no_column(tmp_path: Path) -> None:
    """A lane holding nothing used to cost a column, and every edge crossing it paid.

    With the model and tool lanes empty, an agent writing a file was separated from it
    by two columns of nothing.
    """
    graph = _graph_with("read")
    graph["nodes"] = [node for node in graph["nodes"] if node["type"] != "tool"]
    graph["edges"] = []
    graph["nodes"].append({"id": "file:f", "type": "file", "name": "a.md", "attributes": {}})
    graph["edges"].append({"id": "l1", "source": "agent:/root", "target": "file:f",
                           "relation": "WROTE_FILE", "attributes": {}})

    by_lane = {node["lane"]: node["x"] for node in _drawn(tmp_path, graph)}
    # runtime, model and tool all hold nothing here, so root starts the graph and file
    # follows it directly rather than sitting four columns away.
    assert by_lane.get("root") == 0, by_lane
    assert by_lane.get("file") == 270, (
        f"empty lanes are still reserving columns: {by_lane}"
    )


def test_no_edge_leaves_a_wide_node_at_the_old_constant(tmp_path: Path) -> None:
    """Routing anchored on the old 160 would start inside a widened node."""
    viewer = _render(tmp_path, _graph_with_wide_node_upstream(LONG_LABEL))
    manager, executable = _browser()
    with manager as playwright:
        browser = _launch(playwright, executable)
        try:
            page = browser.new_page(viewport={"width": 1600, "height": 900})
            page.goto(viewer.as_uri())
            drawn = _nodes(page)
            paths = json.loads(
                page.evaluate(
                    "() => JSON.stringify([...document.querySelectorAll('.edge')]"
                    ".map(el => el.getAttribute('d')))"
                )
            )
        finally:
            browser.close()

    wide = next(node for node in drawn if node["id"] == "process:1")
    assert wide["width"] > 160, "the fixture must contain a widened edge source"
    starts = [float(d.split()[1]) for d in paths if d]
    assert any(start == pytest.approx(wide["x"] + wide["width"], abs=1) for start in starts), (
        f"no edge leaves {wide['id']} at its right edge {wide['x'] + wide['width']}: {starts}"
    )
    assert not any(start == pytest.approx(wide["x"] + 160, abs=1) for start in starts), (
        f"an edge still starts at the old fixed width, inside the node: {starts}"
    )


WRAPPABLE = "src/execweave/very/deeply/nested/module_with_a_long_name.py"


def test_a_label_past_the_ceiling_wraps_to_two_lines(tmp_path: Path) -> None:
    """At the width ceiling the label runs out of room; it wraps before it truncates."""
    graph = _graph_with("read")
    graph["nodes"].append(
        {"id": "file:1", "type": "file", "name": WRAPPABLE, "attributes": {}}
    )
    graph["edges"].append(
        {"id": "e5", "source": "agent:/root", "target": "file:1",
         "relation": "WROTE_FILE", "attributes": {}}
    )
    drawn = _drawn(tmp_path, graph)
    wrapped = next(node for node in drawn if node["id"] == "file:1")

    assert wrapped["width"] == 320, f"a label this long must reach the ceiling: {wrapped}"
    assert wrapped["lines"] == 2, f"it must wrap rather than truncate at one line: {wrapped}"
    assert wrapped["height"] > 50, f"a wrapped node must be taller: {wrapped}"
    assert wrapped["full"] == WRAPPABLE
    # Split where a reader would split it, not mid-token.
    assert wrapped["text"].startswith("src/execweave/"), wrapped["text"]


def test_a_single_line_node_keeps_the_geometry_it_always_had(tmp_path: Path) -> None:
    """Height became per-node; a one-line node must not move by a pixel."""
    drawn = _drawn(tmp_path, _graph_with("read"))
    for node in drawn:
        assert node["lines"] == 1, node
        assert node["height"] == 50, f"an unwrapped node changed height: {node}"


def test_a_wrapped_node_does_not_overlap_the_row_below(tmp_path: Path) -> None:
    """Taller nodes need more vertical room than the fixed gap allowed."""
    graph = _graph_with("read")
    for index in range(4):
        graph["nodes"].append(
            {"id": f"file:{index}", "type": "file",
             "name": f"{WRAPPABLE}.{index}", "attributes": {}}
        )
        graph["edges"].append(
            {"id": f"ef{index}", "source": "agent:/root", "target": f"file:{index}",
             "relation": "WROTE_FILE", "attributes": {}}
        )
    drawn = sorted(_drawn(tmp_path, graph), key=lambda node: (node["x"], node["y"]))
    for upper, lower in zip(drawn, drawn[1:]):
        if upper["x"] != lower["x"]:
            continue
        assert upper["y"] + upper["height"] <= lower["y"], (
            f"{upper['id']} ends at {upper['y'] + upper['height']} but "
            f"{lower['id']} starts at {lower['y']}"
        )
