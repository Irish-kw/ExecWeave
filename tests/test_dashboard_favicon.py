from execweave.live import _AUTHENTICATED_LIVE_HTML
from execweave.live_view import LIVE_HTML


def test_shared_dashboard_declares_inline_favicon() -> None:
    favicon = '<link rel="icon" href="data:,">'
    assert favicon in LIVE_HTML
    assert favicon in _AUTHENTICATED_LIVE_HTML
