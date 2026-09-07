from __future__ import annotations

from execweave.dashboard_shell import DASHBOARD_HTML
from execweave.viewer_dashboard_clean import _DASHBOARD_JS


def test_dashboard_exposes_file_activity_filter_with_changed_default() -> None:
    assert 'id="file-graph-filter"' in DASHBOARD_HTML
    assert '<option value="changed" selected>Changed only</option>' in DASHBOARD_HTML
    assert '<option value="all">All observed</option>' in DASHBOARD_HTML
    assert '<option value="hide">Hidden</option>' in DASHBOARD_HTML
    assert "__execweaveFileDisplayMode" in DASHBOARD_HTML


def test_dashboard_file_projection_distinguishes_changes_from_scans() -> None:
    assert "fileMutationEvents=new Set(['filesystem.created','filesystem.modified','filesystem.moved','filesystem.deleted'])" in _DASHBOARD_JS
    assert "fileDisplayMode==='hide'" in _DASHBOARD_JS
    assert "fileDisplayMode==='all'" in _DASHBOARD_JS
    assert "relatedEventTypes=related.flatMap" in _DASHBOARD_JS
    assert "return activity!=='observed'" in _DASHBOARD_JS
    assert "return'unknown'" in _DASHBOARD_JS
    assert "hidden_file_observation_node_count" in _DASHBOARD_JS


def test_file_and_directory_nodes_share_one_fold_group() -> None:
    assert "type==='file'||type==='directory'?'filesystem':type" in _DASHBOARD_JS
    assert "viewer:folded:${type}" in _DASHBOARD_JS
    assert "earlier files / directories" in _DASHBOARD_JS
    assert "foldedType=type==='filesystem'?'file_cluster':type" in _DASHBOARD_JS
