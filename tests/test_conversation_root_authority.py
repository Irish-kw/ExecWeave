from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "execweave"
PANEL = SRC / "viewer_agent_panel.py"
SHELL = SRC / "dashboard_shell.py"


def test_viewer_root_selection_is_exact_identity_first_and_path_compat_is_safe() -> None:
    source = PANEL.read_text(encoding="utf-8")
    assert "records[0]" not in source
    assert "entries.find(" not in source
    assert "function aggregate(matches)" in source
    assert (
        "const exact=nodeId?entries.filter(entry=>String(entry?.source_id||'')===nodeId):[];"
        in source
    )
    assert "if(exact.length)return aggregate(exact);" in source
    assert "recordForPath('/root')" in source
    assert "if(String(path)==='/root')return canonicalRootRecord();" in source
    assert "const roots=entries.filter(entryHasRootAuthority);" in source
    assert "if(sourceIds.length!==1)return null;" in source
    assert "String(preview.topology_state||'')==='derived'" in source
    assert "const agentKey=node=>String(node?.id||'')||nodePath(node);" in source


def test_derived_root_can_render_locally_but_has_no_canonical_root_authority() -> None:
    source = PANEL.read_text(encoding="utf-8")
    shell = SHELL.read_text(encoding="utf-8")
    assert "preview.is_root===true&&String(preview.topology_state||'')!=='derived'" in source
    assert (
        "const previewUsesRootRenderer=preview=>!!preview&&preview.is_root===true&&"
        "String(preview.agent_path||'')==='/root';"
        in source
    )
    assert "const isRoot=nodeHasRootAuthority(node)||previewUsesRootRenderer(preview);" in source
    assert "const entryHasRootAuthority=entry=>" in source
    assert "preview.is_root===true||path==='/root'" not in shell
    assert "return html" in shell
