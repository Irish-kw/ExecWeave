from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "execweave"
PANEL = SRC / "viewer_agent_panel.py"
FOCUS = SRC / "viewer_dashboard_focus.py"


def test_positive_child_topology_overrides_stale_root_attributes_in_panel() -> None:
    source = PANEL.read_text(encoding="utf-8")
    assert (
        "const nodeHasChildAuthority=node=>!!String(attrs(node).parent_agent_path||'').trim();"
        in source
    )
    assert "const nodeHasRootAuthority=node=>!nodeHasChildAuthority(node)&&(" in source


def test_positive_child_topology_overrides_stale_root_attributes_in_node_label() -> None:
    source = FOCUS.read_text(encoding="utf-8")
    assert "const explicitChild=!!String(attrs.parent_agent_path||'').trim();" in source
    assert "const explicitRoot=!explicitChild&&(" in source
