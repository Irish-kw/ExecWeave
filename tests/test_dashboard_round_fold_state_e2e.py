"""Browser regressions for persistent conversation round fold state."""

from __future__ import annotations

import copy
import os
import shutil
import threading
from pathlib import Path
from typing import Any

import pytest

from multi_agent_run_fixture import CHILDREN, build_run

pytestmark = pytest.mark.viewer_e2e


def _chromium_path() -> str | None:
    explicit = os.environ.get("EXECWEAVE_E2E_CHROMIUM")
    if explicit and Path(explicit).exists():
        return explicit
    base = Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH", ""))
    if base.is_dir():
        for candidate in sorted(base.glob("chromium*/chrome-linux/chrome")):
            return str(candidate)
        for candidate in sorted(
            base.glob("chromium*/chrome-mac/Chromium.app/Contents/MacOS/Chromium")
        ):
            return str(candidate)
    return shutil.which("chromium") or shutil.which("chromium-browser")


def _required() -> bool:
    return os.environ.get("EXECWEAVE_E2E_REQUIRED", "").strip().lower() not in {
        "",
        "0",
        "false",
    }


def _browser():
    try:
        from playwright import sync_api
    except ImportError:
        if _required():
            pytest.fail("the viewer end-to-end check is required here but playwright is not installed")
        pytest.skip("playwright is not installed")
    return sync_api.sync_playwright(), _chromium_path()


def _launch(playwright: Any, executable: str | None) -> Any:
    try:
        return playwright.chromium.launch(**({"executable_path": executable} if executable else {}))
    except Exception as error:  # noqa: BLE001 - surface browser failures verbatim
        if _required():
            pytest.fail(f"the viewer end-to-end check is required here but Chromium failed: {error}")
        pytest.skip(f"Chromium failed: {error}")


def _agent_id(graph: dict[str, Any], path: str) -> str:
    for node in graph.get("nodes", []):
        if not isinstance(node, dict) or node.get("type") != "agent":
            continue
        attrs = node.get("attributes") if isinstance(node.get("attributes"), dict) else {}
        candidate = attrs.get("agent_path") or attrs.get("child_agent_path") or attrs.get(
            "root_agent_path"
        )
        if candidate == path or (path == "/root" and attrs.get("agent_role") == "root"):
            return str(node["id"])
    raise AssertionError(f"no graph agent for {path}")


def _click_id(page: Any, node_id: str) -> None:
    found = page.eval_on_selector_all(
        ".node",
        """(nodes,id)=>{const node=nodes.find(item=>item.dataset.id===id);if(!node)return false;
        node.dispatchEvent(new MouseEvent('click',{bubbles:true}));return true}""",
        node_id,
    )
    assert found, f"graph did not render node {node_id}"
    page.wait_for_timeout(200)


def _old_fold(page: Any) -> Any:
    fold = page.locator("#details .execweave-agent-older").filter(has_text="spawn four agents")
    assert fold.count() == 1, "the original older root round must have one stable fold"
    return fold.first


def _with_inserted_historical_round(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    changed = copy.deepcopy(entries)
    roots = [
        entry
        for entry in changed
        if (entry.get("conversation_preview") or {}).get("agent_path") == "/root"
    ]
    assert roots, "fixture did not produce a root conversation entry"
    target = max(
        roots,
        key=lambda entry: len((entry.get("conversation_preview") or {}).get("messages") or []),
    )
    messages = target["conversation_preview"]["messages"]
    messages.extend(
        [
            {
                "timestamp": "2025-12-31T23:59:58Z",
                "ordinal": -2,
                "sender": "user",
                "recipient": "/root",
                "kind": "user_message",
                "text": "inserted historical round",
            },
            {
                "timestamp": "2025-12-31T23:59:59Z",
                "ordinal": -1,
                "sender": "/root",
                "recipient": "user",
                "kind": "assistant_message",
                "phase": "final_answer",
                "text": "historical answer",
            },
        ]
    )
    return changed


def _exercise_state_contract(
    page: Any,
    graph: dict[str, Any],
    entries: list[dict[str, Any]],
    *,
    polling: bool,
) -> None:
    root_id = _agent_id(graph, "/root")
    child_id = _agent_id(graph, CHILDREN[0][1])
    _click_id(page, root_id)
    page.wait_for_function(
        "()=>(document.getElementById('details')?.innerText||'').includes('spawn four agents')"
    )

    old = _old_fold(page)
    assert not old.evaluate("node=>node.open")
    old.locator("summary").click()
    assert old.evaluate("node=>node.open"), "one click must keep the older round open"

    if polling:
        page.wait_for_timeout(1900)
        assert _old_fold(page).evaluate("node=>node.open"), (
            "two live polling intervals closed a round the user opened"
        )

    page.evaluate(
        "()=>{window.__execweaveFoldSentinel=document.querySelector('#details .execweave-agent-older')}"
    )
    page.evaluate("payload=>window.__execweaveAgentPanel.setEntries(payload)", entries)
    assert page.evaluate(
        "()=>window.__execweaveFoldSentinel===document.querySelector('#details .execweave-agent-older')"
    ), "an identical conversation payload rebuilt the inspector"
    assert _old_fold(page).evaluate("node=>node.open")

    changed = _with_inserted_historical_round(entries)
    changed_snapshot = page.evaluate(
        """payload=>{
        const sentinel=window.__execweaveFoldSentinel;
        window.__execweaveAgentPanel.setEntries(payload);
        const folds=[...document.querySelectorAll('#details .execweave-agent-older')];
        const old=folds.find(node=>node.innerText.includes('spawn four agents'));
        const inserted=folds.filter(node=>node.innerText.includes('inserted historical round'));
        return {
          rebuilt:sentinel!==document.querySelector('#details .execweave-agent-older'),
          oldOpen:Boolean(old?.open),
          insertedCount:inserted.length,
          insertedOpen:inserted.length===1?Boolean(inserted[0].open):null,
        };
        }""",
        changed,
    )
    assert changed_snapshot["rebuilt"], "a changed conversation payload did not redraw the inspector"
    assert changed_snapshot["oldOpen"], (
        "redrawing for new conversation evidence cleared the user's open choice"
    )
    assert changed_snapshot["insertedCount"] == 1, (
        "the newly discovered historical round must have one fold"
    )
    assert changed_snapshot["insertedOpen"] is False, (
        "a newly discovered historical round must default to closed"
    )

    if polling:
        # The server still serves the original payload. The next poll therefore redraws
        # once more; the original round must remain open across that redraw too.
        page.wait_for_timeout(1000)
        assert _old_fold(page).evaluate("node=>node.open")

    _old_fold(page).locator("summary").click()
    assert not _old_fold(page).evaluate("node=>node.open")

    if polling:
        page.wait_for_timeout(1900)
        assert not _old_fold(page).evaluate("node=>node.open"), (
            "live polling reopened a round the user explicitly closed"
        )

    _click_id(page, child_id)
    _click_id(page, root_id)
    assert not _old_fold(page).evaluate("node=>node.open"), (
        "switching agents lost that agent's fold state"
    )


def test_round_fold_state_survives_live_polling_payload_changes_and_agent_switches(
    tmp_path: Path,
) -> None:
    from execweave import live as live_module
    from execweave.conversation_records import conversation_index_payload
    from execweave.viewer_projection import project_viewer_graph, write_graph_html

    graph = build_run(tmp_path, rounds=2)
    entries = conversation_index_payload(graph, tmp_path)["entries"]
    viewer = tmp_path / "viewer.html"
    write_graph_html(graph, viewer)

    event_path = tmp_path / "events.jsonl"
    event_path.write_text("", encoding="utf-8")
    state = live_module._LiveState("fold-state", event_path)
    projected = project_viewer_graph(graph)
    state._projected_graph_locked = lambda: dict(projected)  # type: ignore[method-assign]
    state._viewer_projection_ever_active = True
    token = "fold-state-token"
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
                static_page = browser.new_page(viewport={"width": 1440, "height": 1000})
                static_page.goto(viewer.as_uri())
                static_page.wait_for_selector(".node", timeout=15000)
                _exercise_state_contract(static_page, graph, entries, polling=False)

                live_page = browser.new_page(viewport={"width": 1440, "height": 1000})
                live_page.goto(f"http://{host}:{port}/?t={token}")
                live_page.wait_for_selector(".node", timeout=15000)
                _exercise_state_contract(live_page, graph, entries, polling=True)
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
