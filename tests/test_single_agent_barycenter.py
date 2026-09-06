from __future__ import annotations

import json
import subprocess
from pathlib import Path
import tempfile
from typing import Any

import pytest

from execweave.dashboard_shell import DASHBOARD_HTML
from execweave.live_view import LIVE_HTML
from execweave.live_view_readability import LIVE_READABILITY_SCRIPT


def _build_topology_in_node(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> dict[str, Any]:
    """Execute execweaveBuildTopology in Node.js with simulated environment."""
    script = f"""
    const nodes = {json.dumps(nodes)};
    const edges = {json.dumps(edges)};
    global.nodeById = new Map(nodes.map(n => [n.id, n]));
    global.edgeById = new Map(edges.map(e => [e.id || `${{e.source}}:${{e.relation || ''}}:${{e.target}}`, e]));
    global.edgeId = e => e.id || `${{e.source}}:${{e.relation || ''}}:${{e.target}}`;
    global.svg = {{ classList: {{ toggle: () => {{}} }} }};
    global.window = {{}};
    global.updateNodeElement = () => {{}};
    global.updateEdgeElement = () => {{}};
    global.createEdgeElement = () => {{}};
    global.createNodeElement = () => {{}};
    global.clearSelection = () => {{}};
    global.selectNode = () => {{}};
    global.selectEdge = () => {{}};
    global.show = () => {{}};
    global.nodeElements = new Map();
    global.edgeElements = new Map();
    global.document = {{
        createElementNS: () => ({{ setAttribute: () => {{}}, appendChild: () => {{}} }}),
        getElementById: () => null
    }};
    {LIVE_READABILITY_SCRIPT}
    const topo = execweaveBuildTopology();
    const specObj = {{}};
    for (const [id, s] of topo.spec.entries()) {{
        specObj[id] = {{ lane: s.lane, rank: s.rank, order: s.order, x: s.x, y: s.y }};
    }}
    const sourceBary = {{}};
    const agentBary = {{}};
    for (const node of nodes) {{
        if (topo.sourceBarycentre) sourceBary[node.id] = topo.sourceBarycentre(node);
        if (topo.agentBarycenter) agentBary[node.id] = topo.agentBarycenter(node);
    }}
    process.stdout.write(JSON.stringify({{
        spec: specObj,
        sourceBarycentre: sourceBary,
        agentBarycenter: agentBary
    }}));
    """
    with tempfile.NamedTemporaryFile(mode="w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(script)
        temp_path = f.name
    try:
        proc = subprocess.run(
            ["node", temp_path],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if proc.returncode != 0:
            raise RuntimeError(f"Node execution failed with code {proc.returncode}:\nSTDERR:\n{proc.stderr}\nSTDOUT:\n{proc.stdout}")
        return json.loads(proc.stdout)
    finally:
        Path(temp_path).unlink(missing_ok=True)


def test_single_agent_barycenter_fallback_reduces_edge_crossings() -> None:
    """R2: Single-agent setups calculate proper root fallback barycenters instead of MAX_SAFE_INTEGER."""
    # Root agent accesses files in order: zeta.py (seq 1), alpha.py (seq 2), mid.py (seq 3)
    nodes = [
        {"id": "agent:/root", "type": "agent", "name": "/root",
         "attributes": {"agent_role": "root", "agent_path": "/root"}},
        {"id": "file:zeta.py", "type": "file", "name": "zeta.py", "attributes": {}},
        {"id": "file:alpha.py", "type": "file", "name": "alpha.py", "attributes": {}},
        {"id": "file:mid.py", "type": "file", "name": "mid.py", "attributes": {}},
    ]
    edges = [
        {"id": "e1", "source": "agent:/root", "target": "file:zeta.py", "relation": "WROTE_FILE",
         "first_sequence": 1},
        {"id": "e2", "source": "agent:/root", "target": "file:alpha.py", "relation": "WROTE_FILE",
         "first_sequence": 2},
        {"id": "e3", "source": "agent:/root", "target": "file:mid.py", "relation": "WROTE_FILE",
         "first_sequence": 3},
    ]

    result = _build_topology_in_node(nodes, edges)
    spec = result["spec"]
    bary = result["sourceBarycentre"]

    # Verify barycenter values are finite and non-MAX_SAFE_INTEGER
    assert bary["file:zeta.py"] == 0
    assert bary["file:alpha.py"] == 1
    assert bary["file:mid.py"] == 2

    # Under alphabetical sorting, alpha.py would be 0, mid.py 1, zeta.py 2.
    # Under root fallback, zeta.py (first) is placed first (order 0, lowest y),
    # alpha.py (second) is placed second, mid.py (third) is placed third.
    assert spec["file:zeta.py"]["order"] == 0
    assert spec["file:alpha.py"]["order"] == 1
    assert spec["file:mid.py"]["order"] == 2

    assert spec["file:zeta.py"]["y"] < spec["file:alpha.py"]["y"]
    assert spec["file:alpha.py"]["y"] < spec["file:mid.py"]["y"]


def test_single_agent_tool_barycenter_root_fallback() -> None:
    """R2: Tool ordering in single-agent setups follows root connection sequence."""
    nodes = [
        {"id": "agent:/root", "type": "agent", "name": "/root",
         "attributes": {"agent_role": "root", "agent_path": "/root"}},
        {"id": "tool:write", "type": "tool", "name": "write", "attributes": {}},
        {"id": "tool:read", "type": "tool", "name": "read", "attributes": {}},
        {"id": "tool:execute", "type": "tool", "name": "execute", "attributes": {}},
    ]
    edges = [
        {"id": "e1", "source": "agent:/root", "target": "tool:write", "relation": "USES_TOOL",
         "first_sequence": 10},
        {"id": "e2", "source": "agent:/root", "target": "tool:read", "relation": "USES_TOOL",
         "first_sequence": 20},
        {"id": "e3", "source": "agent:/root", "target": "tool:execute", "relation": "USES_TOOL",
         "first_sequence": 30},
    ]

    result = _build_topology_in_node(nodes, edges)
    spec = result["spec"]

    assert spec["tool:write"]["order"] < spec["tool:read"]["order"]
    assert spec["tool:read"]["order"] < spec["tool:execute"]["order"]
    assert spec["tool:write"]["y"] < spec["tool:read"]["y"] < spec["tool:execute"]["y"]


def test_multi_agent_child_order_strictly_preserved() -> None:
    """R2: When child agents exist, childOrder governs barycenters and multi-agent layout is preserved."""
    nodes = [
        {"id": "agent:/root", "type": "agent", "name": "/root",
         "attributes": {"agent_role": "root", "agent_path": "/root"}},
        {"id": "agent:/root/c0", "type": "agent", "name": "c0",
         "attributes": {"agent_role": "child", "agent_path": "/root/c0"}},
        {"id": "agent:/root/c1", "type": "agent", "name": "c1",
         "attributes": {"agent_role": "child", "agent_path": "/root/c1"}},
        {"id": "file:zeta.py", "type": "file", "name": "zeta.py", "attributes": {}},
        {"id": "file:alpha.py", "type": "file", "name": "alpha.py", "attributes": {}},
    ]
    edges = [
        {"id": "s0", "source": "agent:/root", "target": "agent:/root/c0", "relation": "SPAWNED_AGENT",
         "first_sequence": 1},
        {"id": "s1", "source": "agent:/root", "target": "agent:/root/c1", "relation": "SPAWNED_AGENT",
         "first_sequence": 2},
        # c0 (order 0) writes zeta.py; c1 (order 1) writes alpha.py
        {"id": "w0", "source": "agent:/root/c0", "target": "file:zeta.py", "relation": "WROTE_FILE",
         "first_sequence": 3},
        {"id": "w1", "source": "agent:/root/c1", "target": "file:alpha.py", "relation": "WROTE_FILE",
         "first_sequence": 4},
    ]

    result = _build_topology_in_node(nodes, edges)
    spec = result["spec"]
    bary = result["sourceBarycentre"]

    # c0 is childOrder 0, so zeta.py gets barycenter 0
    # c1 is childOrder 1, so alpha.py gets barycenter 1
    assert bary["file:zeta.py"] == 0.0
    assert bary["file:alpha.py"] == 1.0
    assert spec["file:zeta.py"]["order"] == 0
    assert spec["file:alpha.py"]["order"] == 1
    assert spec["file:zeta.py"]["y"] < spec["file:alpha.py"]["y"]


def test_multiple_root_agents_fallback() -> None:
    """R2: Multiple root agents order targets by root index."""
    nodes = [
        {"id": "agent:/root1", "type": "agent", "name": "root1",
         "attributes": {"agent_role": "root", "agent_path": "/root1", "viewer_root": True}},
        {"id": "agent:/root2", "type": "agent", "name": "root2",
         "attributes": {"agent_role": "root", "agent_path": "/root2", "viewer_root": True}},
        {"id": "file:f1", "type": "file", "name": "z_file1", "attributes": {}},
        {"id": "file:f2", "type": "file", "name": "a_file2", "attributes": {}},
    ]
    edges = [
        {"id": "e1", "source": "agent:/root1", "target": "file:f1", "relation": "WROTE_FILE"},
        {"id": "e2", "source": "agent:/root2", "target": "file:f2", "relation": "WROTE_FILE"},
    ]

    result = _build_topology_in_node(nodes, edges)
    spec = result["spec"]

    # root1 (index 0) target comes before root2 (index 1) target
    assert spec["file:f1"]["order"] < spec["file:f2"]["order"]
    assert spec["file:f1"]["y"] < spec["file:f2"]["y"]


def test_orphan_unconnected_evidence_fallback() -> None:
    """Orphan evidence with no agent connection sorts to the bottom."""
    nodes = [
        {"id": "agent:/root", "type": "agent", "name": "/root",
         "attributes": {"agent_role": "root", "agent_path": "/root"}},
        {"id": "file:connected", "type": "file", "name": "z_connected", "attributes": {}},
        {"id": "file:orphan", "type": "file", "name": "a_orphan", "attributes": {}},
    ]
    edges = [
        {"id": "e1", "source": "agent:/root", "target": "file:connected", "relation": "WROTE_FILE",
         "first_sequence": 1},
    ]

    result = _build_topology_in_node(nodes, edges)
    spec = result["spec"]

    # connected file is ordered before orphan file
    assert spec["file:connected"]["order"] < spec["file:orphan"]["order"]
    assert spec["file:connected"]["y"] < spec["file:orphan"]["y"]


def test_secondary_component_2d_packing_wraps_rows() -> None:
    """R1: Secondary component packing wraps horizontally in 2D rows rather than stacking in 1D vertical tower."""
    # Create spine component
    nodes = [
        {"id": "agent:/root", "type": "agent", "name": "/root",
         "attributes": {"agent_role": "root", "agent_path": "/root"}},
        {"id": "tool:spine_tool", "type": "tool", "name": "spine_tool", "attributes": {}},
    ]
    edges = [
        {"id": "e0", "source": "agent:/root", "target": "tool:spine_tool", "relation": "USES_TOOL"},
    ]

    # Create 6 orphan secondary components (each has an isolated file-process pair)
    # Each node is ~160px wide, so component width is >= 160px.
    # Spine width is Math.max(600, spineRight - spineLeft) = 600..800px.
    # 6 components across ~160px + 170px gap will wrap after 2-3 components per row.
    for i in range(6):
        nodes.append({"id": f"file:orphan_{i}", "type": "file", "name": f"orphan_{i}", "attributes": {}})
        nodes.append({"id": f"file:sec_{i}", "type": "file", "name": f"sec_{i}", "attributes": {}})
        edges.append({"id": f"sec_edge_{i}", "source": f"file:orphan_{i}", "target": f"file:sec_{i}",
                      "relation": "CONNECTED_TO"})

    result = _build_topology_in_node(nodes, edges)
    spec = result["spec"]

    # Collect Y positions of the secondary component files
    y_positions = {spec[f"file:orphan_{i}"]["y"] for i in range(6)}
    x_positions = {spec[f"file:orphan_{i}"]["x"] for i in range(6)}

    # If it were a 1D vertical stack, there would be 6 distinct Y levels and only 1 X level.
    # In 2D grid packing, there are multiple items per row (multiple X values sharing a Y level)
    # and fewer than 6 distinct Y levels!
    assert len(x_positions) > 1, f"Expected 2D horizontal distribution, got X positions: {x_positions}"
    assert len(y_positions) < 6, f"Expected row wrapping in 2D grid, got 6 vertical levels: {y_positions}"


def test_live_html_and_dashboard_html_compatibility() -> None:
    """Premerge hardening contracts and seams remain intact in LIVE_HTML and DASHBOARD_HTML."""
    for html in (LIVE_HTML, DASHBOARD_HTML):
        assert "agentOrder=new Map(childOrder)" in html
        assert "rootFallbackBarycenter" in html
        assert "effectiveBarycentre" in html
        assert "cursorX+box.w>spineLeft+spineWidth" in html
