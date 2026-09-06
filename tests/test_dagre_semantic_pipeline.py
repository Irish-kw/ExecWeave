from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
from typing import Any

import pytest

from execweave.dashboard_shell import DASHBOARD_HTML
from execweave.live_view import LIVE_HTML
from execweave.live_view_process_layout import LIVE_PROCESS_LAYOUT_SCRIPT
from execweave.live_view_readability import LIVE_READABILITY_SCRIPT
import execweave._dashboard_shell_base as shell_base

VENDOR_DAGRE = Path(__file__).resolve().parents[1] / "src" / "execweave" / "vendor" / "dagre.min.js"


def _run_node_pipeline(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> dict[str, Any]:
    """Execute complete layout pipeline in Node.js and return stages and metrics."""
    vendor_dagre_posix = VENDOR_DAGRE.resolve().as_posix()
    script = f"""
    const nodes = {json.dumps(nodes)};
    const edges = {json.dumps(edges)};
    global.nodeById = new Map(nodes.map(n => [n.id, n]));
    global.edgeById = new Map(edges.map(e => [e.id || `${{e.source}}:${{e.relation || ''}}:${{e.target}}`, e]));
    global.edgeId = e => e.id || `${{e.source}}:${{e.relation || ''}}:${{e.target}}`;
    global.svg = {{
        classList: {{ toggle: () => {{}}, add: () => {{}}, remove: () => {{}}, contains: () => false }},
        appendChild: () => {{}}
    }};
    global.window = global;
    global.updateNodeElement = () => {{}};
    global.updateEdgeElement = () => {{}};
    global.createNodeElement = () => {{}};
    global.createEdgeElement = () => {{}};
    global.clearSelection = () => {{}};
    global.selectNode = () => {{}};
    global.selectEdge = () => {{}};
    global.show = () => {{}};
    global.nodeElements = new Map();
    global.edgeElements = new Map();
    global.positions = new Map();
    global.document = {{
        createElementNS: () => ({{
            setAttribute: () => {{}},
            appendChild: () => {{}},
            classList: {{ add: () => {{}}, remove: () => {{}}, contains: () => false }},
            textContent: '',
            getComputedTextLength: () => 0
        }}),
        getElementById: () => null
    }};
    const vendorDagre = (typeof process !== 'undefined' && process.argv && (process.argv[2] || process.argv[1])) || '{vendor_dagre_posix}';
    if (typeof dagre === 'undefined' && typeof require === 'function') {{
        try {{ global.dagre = require(vendorDagre); }} catch (_) {{
            try {{ global.dagre = require('{vendor_dagre_posix}'); }} catch (_) {{}}
        }}
    }}
    {LIVE_READABILITY_SCRIPT}
    {LIVE_PROCESS_LAYOUT_SCRIPT}
    const topo = execweaveBuildTopology();
    const spec = {{}};
    for (const [id, s] of topo.spec.entries()) {{
        spec[id] = {{ lane: s.lane, rank: s.rank, order: s.order, x: s.x, y: s.y }};
    }}
    const pipeline = topo.dagrePipeline || {{}};
    const stages = pipeline.stages || {{}};
    const serializeStage = m => {{
        if (!m) return {{}};
        const out = {{}};
        for (const [k, v] of (m.entries ? m.entries() : Object.entries(m))) {{
            out[k] = {{ x: v.x, y: v.y, lane: v.lane }};
        }}
        return out;
    }};
    process.stdout.write(JSON.stringify({{
        spec,
        metrics: pipeline.metrics || {{}},
        stages: {{
            PRE_DAGRE: serializeStage(stages.PRE_DAGRE),
            POST_DAGRE: serializeStage(stages.POST_DAGRE),
            POST_FINAL_CONSTRAINT: serializeStage(stages.POST_FINAL_CONSTRAINT),
        }}
    }}));
    """
    with tempfile.NamedTemporaryFile(mode="w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(script)
        temp_path = Path(f.name)

    try:
        proc = subprocess.run(
            ["node", str(temp_path), str(VENDOR_DAGRE)],
            capture_output=True,
            text=True,
            check=True,
            encoding="utf-8",
        )
        return json.loads(proc.stdout)
    finally:
        temp_path.unlink(missing_ok=True)


def _multi_lane_graph() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Graph spanning runtime, root, agent, model, tool, file, endpoint lanes."""
    nodes = [
        {"id": "process:main", "type": "process", "name": "daemon", "attributes": {}},
        {"id": "agent:/root", "type": "agent", "name": "/root", "attributes": {"agent_role": "root", "agent_path": "/root"}},
        {"id": "agent:/root/w1", "type": "agent", "name": "worker1", "attributes": {"agent_role": "child", "agent_path": "/root/w1"}},
        {"id": "model:llm", "type": "model", "name": "gemma", "attributes": {}},
        {"id": "tool:search", "type": "tool", "name": "search", "attributes": {}},
        {"id": "tool:bash", "type": "tool", "name": "bash", "attributes": {}},
        {"id": "file:output.txt", "type": "file", "name": "output.txt", "attributes": {}},
        {"id": "file:input.json", "type": "file", "name": "input.json", "attributes": {}},
        {"id": "endpoint:api", "type": "endpoint", "name": "api.remote", "attributes": {}},
    ]
    edges = [
        {"id": "e0", "source": "process:main", "target": "agent:/root", "relation": "LAUNCHED"},
        {"id": "e1", "source": "agent:/root", "target": "agent:/root/w1", "relation": "SPAWNED_AGENT"},
        {"id": "e2", "source": "agent:/root/w1", "target": "model:llm", "relation": "USED_MODEL"},
        {"id": "e3", "source": "agent:/root/w1", "target": "tool:search", "relation": "USES_TOOL"},
        {"id": "e4", "source": "agent:/root/w1", "target": "tool:bash", "relation": "USES_TOOL"},
        {"id": "e5", "source": "agent:/root/w1", "target": "file:output.txt", "relation": "WROTE_FILE"},
        {"id": "e6", "source": "agent:/root", "target": "file:input.json", "relation": "READ_FILE"},
        {"id": "e7", "source": "process:main", "target": "endpoint:api", "relation": "NETWORK_CONNECT"},
    ]
    return nodes, edges


def test_dagre_pipeline_executes_three_validation_stages() -> None:
    """R3: 3-stage validation pipeline PRE_DAGRE, POST_DAGRE, POST_FINAL_CONSTRAINT executes."""
    nodes, edges = _multi_lane_graph()
    result = _run_node_pipeline(nodes, edges)

    stages = result["stages"]
    assert "PRE_DAGRE" in stages
    assert "POST_DAGRE" in stages
    assert "POST_FINAL_CONSTRAINT" in stages

    pre = stages["PRE_DAGRE"]
    post_dagre = stages["POST_DAGRE"]
    post_final = stages["POST_FINAL_CONSTRAINT"]

    # All nodes must be tracked in each stage
    for n in nodes:
        nid = n["id"]
        assert nid in pre, f"{nid} missing in PRE_DAGRE"
        assert nid in post_dagre, f"{nid} missing in POST_DAGRE"
        assert nid in post_final, f"{nid} missing in POST_FINAL_CONSTRAINT"

    # Verify stage progression
    assert len(pre) == len(nodes)
    assert len(post_dagre) == len(nodes)
    assert len(post_final) == len(nodes)


def test_dagre_retention_rates_are_healthy_and_positive() -> None:
    """R3: DAGRE_X_RETENTION_RATE > 0% and DAGRE_Y_RETENTION_RATE > 0%."""
    nodes, edges = _multi_lane_graph()
    result = _run_node_pipeline(nodes, edges)
    metrics = result["metrics"]

    assert metrics.get("DAGRE_SEMANTIC_CONSTRAINT_PIPELINE") == "PASS"
    x_rate = metrics.get("DAGRE_X_RETENTION_RATE", 0.0)
    y_rate = metrics.get("DAGRE_Y_RETENTION_RATE", 0.0)

    assert x_rate > 0.0, f"Expected DAGRE_X_RETENTION_RATE > 0%, got {x_rate}%"
    assert y_rate > 0.0, f"Expected DAGRE_Y_RETENTION_RATE > 0%, got {y_rate}%"
    assert metrics["xRetained"] > 0
    assert metrics["yRetained"] > 0


def test_semantic_lane_corridor_bounds_are_respected() -> None:
    """R3: Dagre optimizes within semantic lane corridors without invading neighboring lanes."""
    nodes, edges = _multi_lane_graph()
    result = _run_node_pipeline(nodes, edges)
    spec = result["spec"]

    # Non-process nodes must follow semantic lane order horizontally:
    # root < agent < model, tool < file < endpoint
    assert spec["agent:/root"]["x"] < spec["agent:/root/w1"]["x"]
    assert spec["agent:/root/w1"]["x"] < spec["model:llm"]["x"]
    assert spec["agent:/root/w1"]["x"] < spec["tool:search"]["x"]
    assert spec["tool:search"]["x"] <= spec["file:output.txt"]["x"]
    assert spec["file:output.txt"]["x"] <= spec["endpoint:api"]["x"]


def test_arrange_button_single_authority_and_visibility_scoping() -> None:
    """R4: Arrange executes semantic-constrained relayout scoped to visible nodes/edges without camera fit."""
    assert "function execweaveArrangePositions()" in LIVE_PROCESS_LAYOUT_SCRIPT
    assert "execweaveIsNodeVisible" in LIVE_PROCESS_LAYOUT_SCRIPT
    assert "execweaveIsEdgeVisible" in LIVE_PROCESS_LAYOUT_SCRIPT
    assert "arrangeButton.onclick=()=>execweaveArrangePositions()" in LIVE_PROCESS_LAYOUT_SCRIPT

    # Assert Arrange does NOT touch camera state (no auto-fit)
    start = LIVE_PROCESS_LAYOUT_SCRIPT.index("function execweaveArrangePositions()")
    end = LIVE_PROCESS_LAYOUT_SCRIPT.index("execweaveArrangeGraph=execweaveArrangePositions")
    arrange_body = LIVE_PROCESS_LAYOUT_SCRIPT[start:end]
    assert "fit(" not in arrange_body
    assert "scheduleCamera(" not in arrange_body
    assert "transform.scale" not in arrange_body


def test_arrange_is_deterministic() -> None:
    """R4: Arrange produces identical coordinates when executed repeatedly on the same graph."""
    nodes, edges = _multi_lane_graph()
    run1 = _run_node_pipeline(nodes, edges)
    run2 = _run_node_pipeline(nodes, edges)
    assert run1["spec"] == run2["spec"]


def test_hardcoded_seam_internalization_and_consistency() -> None:
    """R9: Seams #2, #3, #4 in _dashboard_shell_base.py are internalized and consistent."""
    # The helper functions in _dashboard_shell_base.py now cleanly pass through
    sample_html = "<html><body><script>const x = 1;</script></body></html>"
    assert shell_base._preserve_semantic_layout_constraints(sample_html) == sample_html
    assert shell_base._preserve_semantic_arrange(sample_html) == sample_html
    assert shell_base._route_ordinary_edges_from_final_positions(sample_html) == sample_html

    # Legacy 1D vertical shift loop must be absent from both LIVE_HTML and DASHBOARD_HTML
    legacy_needle = "const shift=floor+EXECWEAVE_BAND_GAP-top;"
    assert legacy_needle not in LIVE_HTML
    assert legacy_needle not in DASHBOARD_HTML

    # Both HTML distributions include the internalized pipeline and arrange
    for html in (LIVE_HTML, DASHBOARD_HTML):
        assert "execweaveRestoreSemanticLayoutConstraints" in html
        assert "execweaveRetargetRoutePoints" in html
        assert "window.__execweaveDagrePipeline" in html
        assert "DAGRE_SEMANTIC_CONSTRAINT_PIPELINE" in html


def test_secondary_component_2d_grid_packing_preserved() -> None:
    """R1/R9: Claude's 2D grid packing is preserved and not overridden by legacy 1D shifts."""
    nodes = [
        {"id": "agent:/root", "type": "agent", "name": "/root", "attributes": {"agent_role": "root", "agent_path": "/root"}},
        {"id": "tool:root_tool", "type": "tool", "name": "tool", "attributes": {}},
    ]
    edges = [
        {"id": "e0", "source": "agent:/root", "target": "tool:root_tool", "relation": "USES_TOOL"},
    ]
    # Add 6 secondary isolated components
    for i in range(6):
        nodes.append({"id": f"file:sec_{i}", "type": "file", "name": f"sec_{i}.txt", "attributes": {}})
        nodes.append({"id": f"endpoint:sec_{i}", "type": "endpoint", "name": f"endpoint_{i}", "attributes": {}})
        edges.append({"id": f"sec_edge_{i}", "source": f"file:sec_{i}", "target": f"endpoint:sec_{i}", "relation": "CONNECTS"})

    result = _run_node_pipeline(nodes, edges)
    spec = result["spec"]

    # In 2D grid packing, secondary components wrap horizontally across multiple columns
    y_vals = {spec[f"file:sec_{i}"]["y"] for i in range(6)}
    x_vals = {spec[f"file:sec_{i}"]["x"] for i in range(6)}
    assert len(x_vals) > 1, f"Expected multi-column 2D packing, got X values: {x_vals}"
    assert len(y_vals) < 6, f"Expected row wrapping in 2D grid, got 6 vertical levels: {y_vals}"
