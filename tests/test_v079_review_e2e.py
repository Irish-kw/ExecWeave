from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import pytest

from multi_agent_run_fixture import CHILDREN, build_run
from test_viewer_agent_isolation_e2e import (
    _agent_id,
    _browser,
    _cards,
    _click_id,
    _launch,
    _wait_for_text,
)

pytestmark = pytest.mark.viewer_e2e

ENCRYPTED_NOTICE = "Observed — plaintext not exposed by provider."


def _entry(source_id: str, path: str, messages: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "provider": "codex",
        "source_id": source_id,
        "conversation_preview": {
            "agent_path": path,
            "messages": messages,
        },
    }


def test_root_uses_all_snapshots_and_child_keeps_evidence_states(tmp_path: Path) -> None:
    from execweave.dashboard_shell import render_static_dashboard_html
    from execweave.viewer_projection import project_viewer_graph

    graph = build_run(tmp_path)
    root_id = _agent_id(graph, "/root")
    child_path = CHILDREN[0][1]
    child_id = _agent_id(graph, child_path)
    entries = [
        # Real Codex runs can have an early Stop snapshot with the same source id and
        # no preview yet. The inspector must not stop at this first observation.
        {"provider": "codex", "source_id": root_id},
        _entry(
            root_id,
            "/root",
            [
                {
                    "timestamp": "2026-01-01T00:00:01Z",
                    "ordinal": 1,
                    "kind": "user_message",
                    "sender": "user",
                    "recipient": "/root",
                    "text": "MULTI-SNAPSHOT PROMPT",
                    "content_state": "plaintext",
                },
                {
                    "timestamp": "2026-01-01T00:00:02Z",
                    "ordinal": 2,
                    "kind": "assistant_final_response",
                    "phase": "final_answer",
                    "sender": "/root",
                    "text": "MULTI-SNAPSHOT FINAL",
                    "content_state": "plaintext",
                },
            ],
        ),
        _entry(
            child_id,
            child_path,
            [
                {
                    "kind": "task",
                    "phase": "assignment",
                    "sender": "/root",
                    "recipient": child_path,
                    "text": "SHARED-PREAMBLE-MUST-NOT-BECOME-TASK",
                    "content_state": "plaintext",
                    "content_role": "shared_injected_context",
                },
                {
                    "kind": "task",
                    "phase": "assignment",
                    "sender": "/root",
                    "recipient": child_path,
                    "text": None,
                    "content_state": "provider_encrypted",
                },
                {
                    "kind": "subagent_final_response",
                    "phase": "final_answer",
                    "sender": child_path,
                    "recipient": "/root",
                    "text": None,
                    "content_state": "provider_encrypted",
                },
            ],
        ),
    ]
    html = render_static_dashboard_html(
        project_viewer_graph(graph), conversation_entries=entries
    )
    viewer = tmp_path / "review-viewer.html"
    viewer.write_text(html, encoding="utf-8")

    manager, executable = _browser()
    with manager as playwright:
        browser = _launch(playwright, executable)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.goto(viewer.as_uri())
            page.wait_for_selector(".node", timeout=15000)

            _click_id(page, root_id)
            _wait_for_text(page, "MULTI-SNAPSHOT FINAL")
            labels, bodies = _cards(page)
            assert labels == ["Prompt", "Final response"]
            assert bodies == ["MULTI-SNAPSHOT PROMPT", "MULTI-SNAPSHOT FINAL"]

            _click_id(page, child_id)
            _wait_for_text(page, ENCRYPTED_NOTICE)
            labels, bodies = _cards(page)
            assert labels == ["Task", "Thinking", "Response"]
            assert bodies == [ENCRYPTED_NOTICE, "Not observed.", ENCRYPTED_NOTICE]
            assert "SHARED-PREAMBLE-MUST-NOT-BECOME-TASK" not in "\n".join(bodies)
        finally:
            browser.close()


def test_finished_live_page_keeps_the_same_document(tmp_path: Path) -> None:
    from execweave import live as live_module
    from execweave.viewer_projection import project_viewer_graph

    graph = build_run(tmp_path)
    projected = project_viewer_graph(graph)
    event_path = tmp_path / "events.jsonl"
    event_path.write_text("", encoding="utf-8")
    state = live_module._LiveState("finish-parity", event_path)
    state._projected_graph_locked = lambda: dict(projected)  # type: ignore[method-assign]
    state._viewer_projection_ever_active = True

    token = "finish-token"
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
                page = browser.new_page(viewport={"width": 1440, "height": 1000})
                page.goto(f"http://{host}:{port}/?t={token}")
                page.wait_for_selector(".node", timeout=15000)
                page.evaluate("document.body.dataset.execweaveDomIdentity='same-document'")

                state.finish(
                    graph,
                    final_html="<html><body id='replacement-document'>REPLACED FINAL</body></html>",
                )
                page.wait_for_function(
                    "()=>document.getElementById('status-label')?.textContent==='FINISHED'",
                    timeout=15000,
                )
                page.wait_for_timeout(750)

                assert page.locator("body").get_attribute("data-execweave-dom-identity") == (
                    "same-document"
                )
                assert not page.locator("#replacement-document").count()
                assert "REPLACED FINAL" not in page.locator("body").inner_text()
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
