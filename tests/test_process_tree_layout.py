from pathlib import Path

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
