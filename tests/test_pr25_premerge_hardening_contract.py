from __future__ import annotations

from pathlib import Path


def test_shared_dashboard_contains_premerge_hardening() -> None:
    from execweave.live_view import LIVE_HTML
    from execweave.dashboard_shell import DASHBOARD_HTML

    for html in (LIVE_HTML, DASHBOARD_HTML):
        assert "execweaveMeasureCache=new Map()" in html
        assert "agentOrder=new Map(childOrder)" in html
        assert "geometryChanged=laneShifted||dimensionsChanged" in html
        assert "group.setAttribute('transform',`translate(${p.x} ${p.y})`)" in html
        assert "function execweaveCameraWidth(id)" in html
        assert "function execweaveCameraHeight(id)" in html
        assert "rawNodeById=new Map()" in html
        assert "TOOL_CALL_OWNERSHIP_RELATIONS=['REQUESTED_TOOL_CALL','OBSERVED_TOOL_CALL','OWNED_TOOL_CALL']" in html

        assert "maxX:maxX+160" not in html
        assert "maxY:maxY+50" not in html
        assert "p.x+80" not in html
        assert "p.y+25" not in html
        assert "const stamps=ordered.map(call=>String(call?.first_seen||'').filter(Boolean));" not in html


def test_pr25_integrity_allowance_is_exact_branch_scoped() -> None:
    workflow = Path(".github/workflows/provider-capability-stage-integrity.yml").read_text(
        encoding="utf-8"
    )

    assert (
        '[[ "$HEAD_REF" == "release/0.8.3-graph-ergonomics" '
        '&& -n "$conversation_focus_changed" ]]' in workflow
    )
    assert (
        'tests/test_conversation_agent_focus.py=PR #25 only:' in workflow
    )
    assert (
        'if git diff --name-only "$BASELINE_REF...HEAD"' in workflow
    )
