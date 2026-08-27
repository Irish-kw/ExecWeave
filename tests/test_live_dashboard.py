from execweave.live_view import LIVE_HTML


def test_live_dashboard_combines_graph_inspector_and_activity_stream() -> None:
    assert 'id="graph-panel"' in LIVE_HTML
    assert 'id="inspector"' in LIVE_HTML
    assert 'id="activity-panel"' in LIVE_HTML
    assert 'id="activity-list"' in LIVE_HTML
    assert "selectActivityRow" in LIVE_HTML
    assert "selectNode" in LIVE_HTML
    assert "selectEdge" in LIVE_HTML


def test_live_dashboard_supports_three_camera_modes() -> None:
    assert 'data-camera="manual"' in LIVE_HTML
    assert 'data-camera="fit"' in LIVE_HTML
    assert 'data-camera="follow"' in LIVE_HTML
    assert "function fit(" in LIVE_HTML
    assert "function followLatest(" in LIVE_HTML
    assert "function scheduleCamera(" in LIVE_HTML
    assert "function userTookCamera(" in LIVE_HTML
    assert 'id="jump-latest"' in LIVE_HTML


def test_live_dashboard_marks_latest_execution_progress() -> None:
    assert "@keyframes latestNode" in LIVE_HTML
    assert ".node.latest rect" in LIVE_HTML
    assert "@keyframes latestEdge" in LIVE_HTML
    assert ".edge.latest-edge" in LIVE_HTML
    assert "function markLatest(" in LIVE_HTML
    assert "prefers-reduced-motion" in LIVE_HTML
