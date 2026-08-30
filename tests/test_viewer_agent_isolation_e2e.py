"""Open the shipped viewers in a real browser and read what each agent shows.

Every agent-isolation defect this project has shipped survived a green test suite
and was found by a person opening the page. The unit tests assert over source
text and over the projected index; neither notices when a render path stops
consulting that index. The live dashboard did exactly that — it only fetched the
conversation index once the run had finished, so for the whole run it fell back
to a flat list of every stored record, and every agent showed every other
agent's conversation.

So these tests drive the pages themselves: build one run, render it through both
shipped viewers, and read the sections a person would read.
"""

from __future__ import annotations

import json
import os
import shutil
import threading
from pathlib import Path
from typing import Any

import pytest

from multi_agent_run_fixture import CHILDREN, build_run

MARKERS = {path: marker for _, path, _, marker in CHILDREN}
ALL_MARKERS = set(MARKERS.values())

pytestmark = pytest.mark.viewer_e2e


def _chromium_path() -> str | None:
    explicit = os.environ.get("EXECWEAVE_E2E_CHROMIUM")
    if explicit and Path(explicit).exists():
        return explicit
    base = Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH", ""))
    if base.is_dir():
        for candidate in sorted(base.glob("chromium*/chrome-linux/chrome")):
            return str(candidate)
        for candidate in sorted(base.glob("chromium*/chrome-mac/Chromium.app/Contents/MacOS/Chromium")):
            return str(candidate)
    return shutil.which("chromium") or shutil.which("chromium-browser")


def _required() -> bool:
    """CI sets this. A viewer check that skips itself is worse than no check."""
    return os.environ.get("EXECWEAVE_E2E_REQUIRED", "").strip() not in {"", "0", "false"}


def _unavailable(reason: str) -> None:
    if _required():
        pytest.fail(f"the viewer end-to-end check is required here but {reason}")
    pytest.skip(reason)


def _browser():
    try:
        from playwright import sync_api
    except ImportError:
        _unavailable("playwright is not installed")
    # An explicit binary wins; otherwise let playwright resolve the one it
    # installed, which is what a CI runner has.
    return sync_api.sync_playwright(), _chromium_path()


def _launch(playwright: Any, executable: str | None) -> Any:
    try:
        return playwright.chromium.launch(**({"executable_path": executable} if executable else {}))
    except Exception as error:  # noqa: BLE001 - the reason is reported verbatim
        _unavailable(f"chromium would not launch: {error}")
        raise


def _sections(page: Any, panel_selector: str) -> dict[str, str]:
    """Read the conversation panel the way a person reads it: one block per agent."""
    page.wait_for_selector(f"{panel_selector} .execweave-conversation-agent-section", timeout=15000)
    return page.eval_on_selector_all(
        f"{panel_selector} .execweave-conversation-agent-section",
        """sections=>Object.fromEntries(sections.map(section=>[
            (section.querySelector('.execweave-conversation-agent-scope')?.textContent||'')
                .split(' \\u00b7 ')[0].trim(),
            section.innerText,
        ]))""",
    )


def _assert_each_agent_sees_only_itself(sections: dict[str, str]) -> None:
    for path, marker in MARKERS.items():
        assert path in sections, f"{path} has no section of its own: {sorted(sections)}"
        text = sections[path]
        assert marker in text, f"{path} does not show its own answer"
        leaked = sorted(other for other in ALL_MARKERS - {marker} if other in text)
        assert not leaked, f"{path} shows another agent's conversation: {leaked}"
    root = sections.get("/root")
    assert root is not None, f"the root agent has no section: {sorted(sections)}"
    assert ALL_MARKERS <= {marker for marker in ALL_MARKERS if marker in root}, (
        "the root agent must still see the answers addressed to it, or this check proves nothing"
    )


# ── the finalized viewer ──────────────────────────────────────────────────────


def test_the_recorded_viewer_shows_each_agent_only_its_own_conversation(tmp_path: Path) -> None:
    from execweave.viewer_projection import write_graph_html

    graph = build_run(tmp_path)
    viewer = tmp_path / "viewer.html"
    write_graph_html(graph, viewer)

    manager, executable = _browser()
    with manager as playwright:
        browser = _launch(playwright, executable)
        try:
            page = browser.new_page()
            page.goto(viewer.as_uri())
            _assert_each_agent_sees_only_itself(_sections(page, "#execweave-conversation-panel"))
        finally:
            browser.close()


# ── the live dashboard, while the run is still open ───────────────────────────


def test_the_live_dashboard_isolates_agents_before_the_run_finishes(tmp_path: Path) -> None:
    """The run is deliberately never finished: that is when the leak happened."""
    from execweave import live as live_module

    graph = build_run(tmp_path)
    event_path = tmp_path / "events.jsonl"
    event_path.write_text("", encoding="utf-8")

    state = live_module._LiveState("e2e", event_path)
    state._projected_graph_locked = lambda: dict(graph)  # type: ignore[method-assign]
    token = "e2e-token"
    server = live_module._LocalThreadingHTTPServer(
        ("127.0.0.1", 0), live_module._handler_factory(state, token)
    )
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]

    manager, executable = _browser()
    try:
        with manager as playwright:
            browser = _launch(playwright, executable)
            try:
                page = browser.new_page()
                page.goto(f"http://{host}:{port}/?t={token}")
                assert not state._finished, "this test only means something mid-run"
                _assert_each_agent_sees_only_itself(_sections(page, "#conversation-records"))
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_the_live_server_serves_the_same_index_the_file_would_carry(tmp_path: Path) -> None:
    """A separate projection for the live run is how the two viewers drifted apart."""
    from urllib.request import urlopen

    from execweave.conversation_records import conversation_index_payload
    from execweave import live as live_module

    graph = build_run(tmp_path)
    event_path = tmp_path / "events.jsonl"
    event_path.write_text("", encoding="utf-8")
    state = live_module._LiveState("e2e", event_path)
    state._projected_graph_locked = lambda: dict(graph)  # type: ignore[method-assign]
    token = "e2e-token"
    server = live_module._LocalThreadingHTTPServer(
        ("127.0.0.1", 0), live_module._handler_factory(state, token)
    )
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    try:
        assert not (tmp_path / "conversations.json").exists()
        with urlopen(f"http://{host}:{port}/conversations.json?t={token}", timeout=5) as response:
            served = json.loads(response.read().decode("utf-8"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert served == conversation_index_payload(graph, tmp_path)
    assert served["entry_count"] == 5
