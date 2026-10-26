from execweave.live_view import LIVE_HTML


def test_live_viewer_supports_persistent_dark_light_theme() -> None:
    assert 'id="theme-toggle"' in LIVE_HTML
    assert 'data-theme="light"' in LIVE_HTML
    assert "execweave-theme" in LIVE_HTML
    assert "localStorage.setItem" in LIVE_HTML
    assert "localStorage.getItem" in LIVE_HTML
    assert "Switch to light theme" in LIVE_HTML
    assert "Switch to dark theme" in LIVE_HTML
