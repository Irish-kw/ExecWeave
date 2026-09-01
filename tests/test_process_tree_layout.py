from pathlib import Path
import json
import subprocess

from execweave.live_view import LIVE_HTML
from execweave.live_view_process_layout import LIVE_PROCESS_LAYOUT_SCRIPT
from execweave.live_view_readability import LIVE_READABILITY_SCRIPT

SRC = Path(__file__).resolve().parents[1] / "src" / "execweave"


def _arrange_positions_source() -> str:
    start = LIVE_PROCESS_LAYOUT_SCRIPT.index("function execweaveArrangePositions()")
    end = LIVE_PROCESS_LAYOUT_SCRIPT.index("execweaveArrangeGraph=execweaveArrangePositions")
    return LIVE_PROCESS_LAYOUT_SCRIPT[start:end]


def test_live_html_includes_process_tree_layout_and_arrange_without_trailing_fit() -> None:
    assert "execweaveLayoutProcessTree" in LIVE_HTML
    assert "execweaveArrangePositions" in LIVE_HTML
    assert "PROCESS_COL_GAP" in LIVE_PROCESS_LAYOUT_SCRIPT
    assert "arrangeButton.onclick=()=>execweaveArrangePositions()" in LIVE_HTML


def test_arrange_recomputes_all_visible_nodes_and_edges_without_fit() -> None:
    source = _arrange_positions_source()
    assert "fit(true)" not in source
    assert "fit(" not in source
    assert "execweaveBuildTopology()" in source
    assert "for(const id of ordered)next.set(id,execweavePlaceStable(id,execweaveDesiredPosition(id),next,id))" in source
    assert "for(const edge of edgeById.values())updateEdgeElement(edge)" in source
    assert "execweaveLayoutRelated" in LIVE_HTML
    assert "execweaveLayoutProcessTree" in LIVE_HTML


def test_readability_arrange_no_longer_zooms_the_camera() -> None:
    start = LIVE_READABILITY_SCRIPT.index("function execweaveArrangeGraph()")
    end = LIVE_READABILITY_SCRIPT.index("window.__execweaveArrangeGraph=execweaveArrangeGraph")
    source = LIVE_READABILITY_SCRIPT[start:end]
    assert "fit(true)" not in source
    assert "fit(" not in source


def test_process_parent_child_are_not_stacked_in_one_runtime_column() -> None:
    assert "walk(child,level+1)" in LIVE_PROCESS_LAYOUT_SCRIPT
    assert "spec.processDepth=depth.get(id)||0" in LIVE_PROCESS_LAYOUT_SCRIPT
    assert "spec.x=colX.get(depth.get(id)||0)||spec.x" in LIVE_PROCESS_LAYOUT_SCRIPT
    assert "colX.set(level,x)" in LIVE_PROCESS_LAYOUT_SCRIPT
    assert "x+=(colWidth.get(level)||EXECWEAVE_NODE_W)+PROCESS_COL_GAP" in LIVE_PROCESS_LAYOUT_SCRIPT


def test_related_nodes_are_pulled_toward_neighbors() -> None:
    assert "execweavePullBesideNeighbors" in LIVE_PROCESS_LAYOUT_SCRIPT
    assert "execweaveAlignRelatedY" in LIVE_PROCESS_LAYOUT_SCRIPT
    assert "execweaveIsEndpointNode" in LIVE_PROCESS_LAYOUT_SCRIPT
    assert "type.includes('tool')" in LIVE_PROCESS_LAYOUT_SCRIPT
    assert "sameColumn" in LIVE_PROCESS_LAYOUT_SCRIPT
    assert "kind:'column'" in LIVE_PROCESS_LAYOUT_SCRIPT


def test_process_layout_module_is_loaded_after_readability() -> None:
    source = (SRC / "live_view.py").read_text(encoding="utf-8")
    seam = (
        "{LIVE_SCRIPT_A}{LIVE_READABILITY_SCRIPT}"
        "{LIVE_PROCESS_LAYOUT_SCRIPT}{LIVE_SCRIPT_B}"
    )
    assert seam in source


def test_live_html_embeds_dagre_directed_graph_layout() -> None:
    assert "execweaveLayoutDirectedGraph" in LIVE_HTML
    assert "dagre.layout" in LIVE_HTML
    source = _arrange_positions_source()
    assert "fit(" not in source
    assert "execweaveLayoutDirectedGraph(execweaveTopology)" in source


def test_two_fixed_size_nodes_do_not_overlap_after_dagre_layout() -> None:
    start = LIVE_PROCESS_LAYOUT_SCRIPT.index("const EXECWEAVE_DAG_GAP=24;")
    end = LIVE_PROCESS_LAYOUT_SCRIPT.index("const execweaveBuildTopologyBase=execweaveBuildTopology;")
    layout_js = LIVE_PROCESS_LAYOUT_SCRIPT[start:end]
    vendor = SRC / "vendor" / "dagre.min.js"
    script = (
        "global.dagre=require(process.argv[1]);\n"
        "global.nodeById=new Map([['a',{id:'a'}],['b',{id:'b'}]]);\n"
        "global.edgeById=new Map([['e',{id:'e',source:'a',target:'b'}]]);\n"
        "global.execweaveWidthOf=id=>id==='a'?160:220;\n"
        "global.execweaveHeightOf=id=>id==='a'?50:64;\n"
        "global.execweaveSeparateLane=()=>{};\n"
        + layout_js
        + """
const topo={spec:new Map([['a',{x:0,y:0}],['b',{x:0,y:0}]])};
execweaveLayoutDirectedGraph(topo);
const boxes=['a','b'].map(id=>({id,x:topo.spec.get(id).x,y:topo.spec.get(id).y,w:execweaveWidthOf(id),h:execweaveHeightOf(id)}));
const A=boxes[0],B=boxes[1];
const ix=Math.max(0,Math.min(A.x+A.w,B.x+B.w)-Math.max(A.x,B.x));
const iy=Math.max(0,Math.min(A.y+A.h,B.y+B.h)-Math.max(A.y,B.y));
process.stdout.write(JSON.stringify({area:ix*iy,boxes}));
"""
    )
    completed = subprocess.run(
        ["node", "-e", script, str(vendor)],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)
    assert payload["area"] == 0, payload
