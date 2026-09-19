"""Process results never stand in for task validation or archive completeness."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import subprocess
import sys

import pytest

from execweave.run_assessment import build_run_assessment


def graph_fixture():
    digest = hashlib.sha256(b"recorded").hexdigest()
    return {
        "graph_schema_version": "0.2", "session_id": "assessment-run", "source_path": "/example/events.jsonl",
        "session_outcome": {"state": "succeeded", "return_code": 0, "recorder_finished": True,
                            "event_id": "terminal-1", "interrupted": False, "collector_failed": False},
        "nodes": [
            {"id": "a", "type": "agent", "name": "agent"},
            {"id": "t", "type": "task", "name": "task"},
            {"id": "c", "type": "observed_content", "attributes": {
                "sha256": digest, "path": f"content/sha256/{digest}.txt", "size_bytes": 8,
                "complete_from_source": False}},
        ],
        "edges": [{"id": "done", "source": "a", "target": "t", "relation": "TASK_COMPLETED"}],
    }


def test_successful_process_with_native_completion_and_source_gaps():
    report = build_run_assessment(graph_fixture())
    assert report["execution"]["state"] == "succeeded"
    assert report["task_validation"]["state"] == "unverified"
    assert report["task_validation"]["reported_completed"] == 1
    assert report["content"]["source_partial"] == 1
    assert report["content"]["bytes_verified"] is None
    assert report["content"]["archive_state"] == "not_checked_in_this_view"


@pytest.mark.parametrize("code,state", [(0, "succeeded"), (3, "failed"), (-9, "failed"), (130, "failed")])
def test_numeric_exit_alone_does_not_imply_interrupt(code, state):
    graph = graph_fixture()
    graph["session_outcome"].update(return_code=code, state=state)
    assert build_run_assessment(graph)["execution"]["state"] == state


@pytest.mark.parametrize("code", [None, False, True, "0", 0.0, [], {}])
def test_invalid_exit_codes_do_not_become_success(code):
    graph = graph_fixture()
    graph["session_outcome"].update(return_code=code, state="unknown")
    assert build_run_assessment(graph)["execution"]["state"] == "unknown"


@pytest.mark.parametrize("patch,state", [
    ({"interrupted": True, "state": "interrupted"}, "interrupted"),
    ({"collector_failed": True, "interrupted": True, "state": "collector_failed"}, "collector_failed"),
    ({"interrupted": "false"}, "unknown"),
    ({"collector_failed": "false"}, "unknown"),
    ({"state": "failed"}, "unknown"),
    ({"event_id": None}, "unknown"),
    ({"recorder_finished": False}, "unknown"),
])
def test_terminal_precedence_and_invalid_metadata(patch, state):
    graph = graph_fixture()
    graph["session_outcome"].update(patch)
    assert build_run_assessment(graph)["execution"]["state"] == state


def test_finished_view_and_agent_text_do_not_create_success():
    graph = {"session_id": "old", "nodes": [], "edges": [], "live_finished": True,
             "status": "SUCCESS", "response": "TERMINATE; 100% passed", "tests_passed": 20}
    report = build_run_assessment(graph)
    assert report["execution"]["state"] == "unknown"
    assert report["task_validation"]["state"] == "unverified"
    assert report["content"]["bytes_verified"] is None


def test_conflicting_task_reports_are_preserved_not_last_writer_wins():
    graph = graph_fixture()
    graph["edges"].extend([dict(graph["edges"][0]),
                           {"id": "failed", "source": "t", "target": "t", "relation": "TASK_FAILED"}])
    report = build_run_assessment(graph)["task_validation"]
    assert report["reported_completed"] == report["reported_failed"] == report["both_reported"] == 1
    assert report["state"] == "unverified"


@pytest.mark.parametrize("patch", [
    {"inferred": True}, {"viewer_only": True}, {"attributes": {"viewer_only": True}},
    {"inferred": "false"}, {"source": "missing"}, {"target": "c"}, {"relation": []},
])
def test_non_native_or_invalid_task_edges_do_not_count(patch):
    graph = graph_fixture()
    graph["edges"][0].update(patch)
    assert build_run_assessment(graph)["task_validation"]["reported_completed"] == 0


def test_payload_paths_and_fake_validation_objects_are_never_walked(tmp_path):
    graph = graph_fixture()
    private = tmp_path / "private.txt"
    private.write_text("not a content reference")
    graph["nodes"][0]["attributes"] = {"body": {"path": str(private), "tests_passed": 100,
                                               "relation": "TASK_FAILED"}}
    result = build_run_assessment(graph)
    assert result["content"]["declared"] == 1
    assert result["task_validation"]["state"] == "unverified"
    assert result["task_validation"]["reported_failed"] == 0
    assert "private.txt" not in json.dumps(result)


@pytest.mark.parametrize("attributes,key", [
    ({"path": "../outside.txt"}, "invalid_references"),
    ({"sha256": "incorrect"}, "invalid_references"),
    ({"size_bytes": False}, "invalid_references"),
    ({"representation": "opaque_encrypted"}, "opaque"),
    ({"representation": "redacted"}, "redacted"),
    ({"complete_from_source": "true"}, "source_completeness_unknown"),
])
def test_content_metadata_categories(attributes, key):
    graph = graph_fixture()
    graph["nodes"][2]["attributes"].update(attributes)
    content = build_run_assessment(graph)["content"]
    assert content[key] == 1
    assert content["bytes_verified"] is None


def test_malformed_representation_is_unknown_not_exception():
    graph = graph_fixture()
    graph["nodes"][2]["attributes"]["representation"] = {"invalid": []}
    assert build_run_assessment(graph)["content"]["opaque"] == 0


def test_shared_hash_is_not_two_verified_bodies_or_merged_source_identity():
    graph = graph_fixture()
    graph["nodes"].append({**graph["nodes"][2], "id": "c2"})
    content = build_run_assessment(graph)["content"]
    assert content["declared"] == 2 and content["unique_declared_files"] == 1
    assert content["bytes_verified"] is None


def test_expansion_content_not_silently_lost_and_duplicates_not_double_counted():
    graph = graph_fixture()
    graph["expansion"] = {"clusters": {"folded": {"nodes": [copy.deepcopy(graph["nodes"][2])], "edges": []}}}
    assert build_run_assessment(graph)["content"]["declared"] == 1
    graph["nodes"].pop()
    assert build_run_assessment(graph)["content"]["declared"] == 1


def test_conflicting_duplicate_ids_are_withheld_and_visible():
    graph = graph_fixture()
    graph["nodes"].append({"id": "c", "type": "task"})
    report = build_run_assessment(graph)
    assert report["content"]["declared"] == 0
    assert report["inspection"]["ambiguous_node_ids"] == 1
    assert report["inspection"]["state"] == "partial"


@pytest.mark.parametrize("limit", [0, 1, 3])
def test_budget_never_claims_empty_or_partial_scan_is_complete(limit):
    report = build_run_assessment(graph_fixture(), max_records=limit)
    assert report["inspection"]["limit_reached"] is True
    assert report["inspection"]["inspected_records"] <= limit
    assert report["inspection"]["state"] == "partial"


def test_compact_and_projected_inputs_are_not_full_inventory():
    for key in ("live_payload_compact", "viewer_projection"):
        graph = graph_fixture()
        graph[key] = True
        assert build_run_assessment(graph)["inspection"]["state"] == "partial"


def test_assessment_does_not_mutate_evidence():
    graph = graph_fixture()
    original = copy.deepcopy(graph)
    build_run_assessment(graph)
    assert graph == original


def test_projection_preserves_assessment_before_task_folding():
    from execweave.viewer_projection import project_viewer_graph
    graph = graph_fixture()
    original = copy.deepcopy(graph)
    projected = project_viewer_graph(graph)
    assert projected["run_assessment"] == build_run_assessment(graph)
    assert graph == original


@pytest.mark.parametrize("exit_code", [0, 7])
def test_native_collector_to_graph_to_assessment(tmp_path, exit_code):
    from execweave.collector import RuntimeCollector
    from execweave.sink import JsonlSink
    from execweave.graph import build_execution_graph
    # Real process and recorder, without a paid model or synthetic exit metadata.
    event_path = tmp_path / "events.jsonl"
    collector = RuntimeCollector(session_id="native", sink=JsonlSink(event_path), watch_root=tmp_path,
                                  poll_interval=0.05, collect_filesystem=False, collect_network=False)
    assert collector.run([sys.executable, "-c", f"raise SystemExit({exit_code})"]) == exit_code
    graph = build_execution_graph(event_path).to_dict()
    result = build_run_assessment(graph)
    assert result["execution"]["state"] == ("succeeded" if exit_code == 0 else "failed")
    assert result["execution"]["return_code"] == exit_code
    assert result["task_validation"]["state"] == "unverified"


def test_live_metadata_is_cached_but_terminal_updates_and_compact_payloads_keep_it(tmp_path, monkeypatch):
    from execweave import live_core
    graph = graph_fixture()
    state = live_core._LiveState("assessment-run", tmp_path / "events.jsonl")
    first = state.live_update(None)["run_assessment"]
    second = state.live_update(state._update_sequence)["run_assessment"]
    assert first is second
    state.finish(graph, final_html="<html></html>")
    terminal = state.live_update(state._update_sequence)
    assert terminal["run_assessment"]["execution"]["state"] == "succeeded"
    assert terminal["run_assessment"] is not first
    packed = live_core._compact_live_graph({**graph, "run_assessment": terminal["run_assessment"]})
    assert packed["run_assessment"] == terminal["run_assessment"]


def test_shell_scripts_remain_valid_and_singleton(tmp_path):
    from execweave.dashboard_shell import DASHBOARD_HTML, render_static_dashboard_html
    from execweave.viewer_projection import render_graph_html
    from execweave.viewer_run_assessment import inject_run_assessment
    for i, html in enumerate((DASHBOARD_HTML, render_static_dashboard_html(graph_fixture()), render_graph_html(graph_fixture()))):
        assert html.count('id="execweave-run-assessment-script"') == 1
        assert inject_run_assessment(html) == html
        for j, script in enumerate(re.findall(r"<script[^>]*>(.*?)</script>", html, re.S)):
            path = tmp_path / f"{i}-{j}.js"
            path.write_text(script, encoding="utf-8")
            subprocess.run(["node", "--check", str(path)], check=True, capture_output=True)


@pytest.fixture
def browser_page():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as playwright:
        executable = os.environ.get("EXECWEAVE_E2E_CHROMIUM")
        browser = playwright.chromium.launch(**({"executable_path": executable} if executable else {}))
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        yield page
        assert errors == []
        browser.close()


def load_assessment(page, graph):
    from execweave.viewer_run_assessment import inject_run_assessment
    payload = json.dumps(graph).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    page.set_content(inject_run_assessment('<html><body><aside id="inspector"><section id="existing">Existing selection</section></aside>'
        '<script>window.g=' + payload + ';window.__execweaveCore={getGraph:()=>window.g};'
        'window.calls=0;window.__execweaveDashboard={onPayload(){window.calls++},onFinished(){window.calls++}};</script></body></html>'))


@pytest.mark.viewer_e2e
def test_browser_shows_independent_axes_and_retains_other_inspector(browser_page):
    graph = graph_fixture()
    graph["run_assessment"] = build_run_assessment(graph)
    load_assessment(browser_page, graph)
    assert browser_page.locator('[data-axis="execution"]').get_attribute("data-state") == "succeeded"
    assert "Not independently verified" in browser_page.locator('[data-axis="task"]').inner_text()
    assert "source-incomplete" in browser_page.locator('[data-axis="content"]').inner_text()
    assert browser_page.locator("#existing").inner_text() == "Existing selection"


@pytest.mark.viewer_e2e
def test_live_update_changes_result_without_collapsing_details(browser_page):
    graph = graph_fixture()
    graph["run_assessment"] = build_run_assessment(graph)
    load_assessment(browser_page, graph)
    browser_page.get_by_text("Evidence scope and limitations", exact=True).click()
    changed = copy.deepcopy(graph)
    changed["session_outcome"].update(state="failed", return_code=2)
    report = build_run_assessment(changed)
    browser_page.evaluate("r=>window.__execweaveDashboard.onPayload({run_assessment:r})", report)
    assert browser_page.locator('[data-axis="execution"]').get_attribute("data-state") == "failed"
    assert browser_page.locator("#execweave-run-assessment details").evaluate("n=>n.open")
    assert browser_page.evaluate("window.calls") == 1
    browser_page.evaluate("window.__execweaveDashboard.onFinished()")
    assert browser_page.evaluate("window.calls") == 2
    assert browser_page.locator('[data-axis="execution"]').get_attribute("data-state") == "failed"


@pytest.mark.viewer_e2e
def test_run_change_and_stale_packet_cannot_reuse_success(browser_page):
    graph = graph_fixture()
    report = build_run_assessment(graph)
    graph["run_assessment"] = report
    load_assessment(browser_page, graph)
    browser_page.evaluate("()=>{window.g={session_id:'other',nodes:[],edges:[]};window.__execweaveRunAssessment.refresh()}")
    assert browser_page.locator('[data-axis="execution"]').get_attribute("data-state") == "unknown"
    browser_page.evaluate("r=>window.__execweaveDashboard.onPayload({run_assessment:r})", report)
    assert browser_page.locator('[data-axis="execution"]').get_attribute("data-state") == "unknown"


@pytest.mark.viewer_e2e
def test_plain_text_provenance_cannot_inject_html(browser_page):
    graph = graph_fixture()
    graph["session_outcome"]["event_id"] = '<img src=x onerror="window.unsafe=true">'
    graph["run_assessment"] = build_run_assessment(graph)
    load_assessment(browser_page, graph)
    assert "<img" in browser_page.locator("#execweave-run-assessment").text_content()
    assert browser_page.locator("#execweave-run-assessment img").count() == 0
    assert browser_page.evaluate("window.unsafe||false") is False


@pytest.mark.viewer_e2e
def test_full_static_dashboard_exposes_metadata_assessment(browser_page):
    from execweave.viewer_projection import render_graph_html
    browser_page.set_content(render_graph_html(graph_fixture()))
    assert browser_page.locator("#execweave-run-assessment").count() == 1
    assert browser_page.locator("#execweave-run-assessment").is_visible()
    assert not browser_page.locator("#current-title").is_visible()
    assert browser_page.locator('[data-axis="execution"]').get_attribute("data-state") == "succeeded"
    assert browser_page.locator('[data-axis="task"]').get_attribute("data-state") == "unverified"


@pytest.mark.parametrize("mode", ["snapshot", "noop", "delta", "resync"])
def test_assessment_is_published_in_every_live_envelope(tmp_path, mode):
    from execweave.live import _BaseLiveState
    state = _BaseLiveState("assessment-run", tmp_path / "events.jsonl")
    initial_sequence = state._update_sequence
    state.finish(graph_fixture(), final_html="<html></html>")
    after = {"snapshot": None, "noop": state._update_sequence,
             "delta": initial_sequence, "resync": state._update_sequence + 50}[mode]
    payload = state.live_update(after)
    assert payload["kind"] == ("snapshot" if mode == "resync" else mode)
    assert payload["run_assessment"]["execution"]["state"] == "succeeded"
    assert payload["run_assessment"]["task_validation"]["state"] == "unverified"
    assert payload["live_finished"] is True


def test_authentication_guards_live_assessment_without_extra_endpoint(tmp_path):
    import http.client
    import threading
    from http.server import ThreadingHTTPServer
    from execweave.live import _LiveState, _handler_factory
    state = _LiveState("assessment-run", tmp_path / "events.jsonl")
    state.finish(graph_fixture(), final_html="<html></html>")
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler_factory(state, "test-secret"))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        for token, status in [(None, 401), ("wrong", 401), ("test-secret", 200)]:
            connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
            try:
                connection.request("GET", "/live.json", headers={"X-ExecWeave-Token": token} if token else {})
                response = connection.getresponse()
                body = response.read()
                assert response.status == status
                if status == 200:
                    assert json.loads(body)["run_assessment"]["execution"]["state"] == "succeeded"
                    assert "no-store" in response.getheader("Cache-Control", "")
            finally:
                connection.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_real_live_failure_export_retains_independent_axes(tmp_path):
    from execweave.live import run_live
    result = run_live([sys.executable, "-c", "raise SystemExit(3)"], watch_root=tmp_path,
                      output_dir=tmp_path / "run", collect_filesystem=False, collect_network=False,
                      port=0, open_browser=False, linger_seconds=0)
    assert result.return_code == 3
    raw = json.loads((tmp_path / "run" / "graph.json").read_text(encoding="utf-8"))
    assert "run_assessment" not in raw  # Derived presentation does not rewrite the raw graph.
    html = (tmp_path / "run" / "viewer.html").read_text(encoding="utf-8")
    embedded = json.loads(re.search(r"window.__execweaveStaticGraph=(.*?);window.__execweaveStaticConversations=", html).group(1))
    assert embedded["run_assessment"]["execution"]["state"] == "failed"
    assert embedded["run_assessment"]["task_validation"]["state"] == "unverified"
    assert json.loads((tmp_path / "run" / "finalization.json").read_text())["state"] == "complete"


@pytest.mark.viewer_e2e
def test_recorded_history_expansion_survives_run_status_update(browser_page):
    from execweave.dashboard_shell import render_static_dashboard_html
    graph = graph_fixture()
    graph["nodes"][0]["attributes"] = {"agent_role": "root"}
    records = [{"source_id": "a", "source_type": "agent", "provider": "ollama", "conversation_preview": {
        "is_root": True, "provider": "ollama", "agent_path": "/root", "messages": [
            {"sender": "user", "recipient": "/root", "kind": "user_message", "text": "do this", "ordinal": 1},
            {"sender": "/root", "recipient": "user", "kind": "assistant_message", "text": "recorded answer", "ordinal": 2}
        ]}}]
    browser_page.set_content(render_static_dashboard_html(graph, conversation_entries=records))
    browser_page.evaluate("()=>window.__execweaveAgentPanel.render(window.__execweaveCore.getDisplayGraph().nodes.find(n=>n.id==='a'))")
    details = browser_page.locator('#details details').first
    details.evaluate("n=>n.open=true")
    before = details.inner_text()
    graph["session_outcome"].update(return_code=2, state="failed")
    browser_page.evaluate("r=>window.__execweaveRunAssessment.refresh({run_assessment:r})", build_run_assessment(graph))
    assert details.evaluate("n=>n.open")
    assert details.inner_text() == before
    assert browser_page.locator('[data-axis="execution"]').get_attribute('data-state') == 'failed'


@pytest.mark.viewer_e2e
@pytest.mark.parametrize("theme", ["dark", "light"])
def test_warning_uses_warning_color_not_success_or_node_color(browser_page, theme):
    from execweave.viewer_projection import render_graph_html
    browser_page.set_content(render_graph_html(graph_fixture()))
    browser_page.evaluate("theme=>document.documentElement.dataset.theme=theme", theme)
    colors = browser_page.locator('[data-axis="content"]').evaluate("""n=>({
        warning:getComputedStyle(n).borderLeftColor,
        node:getComputedStyle(document.documentElement).getPropertyValue('--node-file').trim()
    })""")
    expected = browser_page.evaluate("""()=>{
        const n=document.createElement('i');n.style.color='var(--noncausal)';document.body.append(n);
        const color=getComputedStyle(n).color;n.remove();return color;
    }""")
    assert colors["warning"] == expected


def test_reference_metadata_inspection_never_reads_files(tmp_path, monkeypatch):
    import builtins
    graph = graph_fixture()

    def unexpected(*args, **kwargs):
        raise AssertionError("metadata assessment must not open files")

    monkeypatch.setattr(builtins, "open", unexpected)
    monkeypatch.setattr(os, "open", unexpected)
    result = build_run_assessment(graph)
    assert result["content"]["valid_references"] == 1
    assert result["content"]["bytes_verified"] is None


def test_empty_inventory_does_not_mean_capture_disabled_or_complete():
    report = build_run_assessment({"session_id": "empty", "nodes": [], "edges": []})
    assert report["content"]["declared"] == 0
    assert report["content"]["state"] == "not_verified"
    assert report["content"]["archive_state"] == "not_checked_in_this_view"
    assert "capture_failed" not in json.dumps(report)
