from pathlib import Path

from execweave.live_view import LIVE_HTML
from execweave.live_view_process_layout import LIVE_PROCESS_LAYOUT_SCRIPT


def test_live_html_includes_process_tree_layout_and_arrange_without_trailing_fit() -> None:
    assert "execweaveLayoutProcessTree" in LIVE_HTML
    assert "execweaveArrangePositions" in LIVE_HTML
    assert "PROCESS_COL_GAP" in LIVE_PROCESS_LAYOUT_SCRIPT
    assert "arrangeButton.onclick=()=>execweaveArrangePositions()" in LIVE_HTML


def test_process_layout_module_is_loaded_after_readability() -> None:
    source = Path("src/execweave/live_view.py").read_text(encoding="utf-8")
    seam = (
        "{LIVE_SCRIPT_A}{LIVE_READABILITY_SCRIPT}"
        "{LIVE_PROCESS_LAYOUT_SCRIPT}{LIVE_SCRIPT_B}"
    )
    assert seam in source
