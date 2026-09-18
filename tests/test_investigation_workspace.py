"""Exact occurrence inspection without changing raw graph or provider behavior."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from execweave.framework_adapters import AdapterContext, CAMELAdapter, ContentCapturePolicy, ToolCallRecord
from execweave.graph import GraphAccumulator
from execweave.investigation_index import InvestigationCache, build_investigation_index


def scenario(tmp_path, *, mode="prompt_and_response", total=1):
    context = AdapterContext(framework="camel", run_id="one", session_id="one",
                             sidecar=tmp_path / "semantic.jsonl", content_root=tmp_path,
                             capture_policy=ContentCapturePolicy(mode))
    adapter = CAMELAdapter(context)
    a = adapter.agent_created("a", name="same name", role="producer")
    b = adapter.agent_created("b", name="same name", role="reviewer")
    c = adapter.agent_created("c", name="other recipient")
    for i in range(total):
        adapter.message(f"m{i}", a, b, content="identical text")
        if i % 2 == 0:
            adapter.message(f"m{i}", a, b, content="identical text", received=True)
    # The same message addressed elsewhere is not delivered to that recipient.
    adapter.message("m0", a, c, content="identical text")
    tool = adapter.tool("shared")
    call = adapter.entity("tool_call", "call")
    context.record_tool_call(ToolCallRecord(call, a, tool, arguments={"x": 1}))
    context.record_tool_call(ToolCallRecord(call, a, tool, result="done", status="result"))
    events = [json.loads(x) for x in (tmp_path / "semantic.jsonl").read_text().splitlines()]
    accumulator = GraphAccumulator(session_id="one", source_path=tmp_path / "events.jsonl")
    for i, event in enumerate(events):
        accumulator.apply({**event, "session_id": "one", "sequence": i})
    return accumulator.to_dict(), events, a, b, c


def overwrite(tmp_path, events):
    (tmp_path / "semantic.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")


def test_native_framework_send_receive_and_shared_tool(tmp_path):
    graph, events, a, b, c = scenario(tmp_path)
    before = copy.deepcopy(graph)
    report = build_investigation_index(graph, tmp_path)
    assert graph == before
    assert report["inspection"]["state"] == "scanned_selected_streams"
    rows = report["messages"]
    assert len(rows) == 2
    delivered = next(r for r in rows if r["target_id"] == b.id)
    addressed = next(r for r in rows if r["target_id"] == c.id)
    assert delivered["phases"] == ["sent", "received"]
    assert addressed["phases"] == ["sent"]
    assert delivered["owner_id"] == a.id
    assert "consumed" not in delivered["phases"]
    assert all(r["state"] == "registered_not_read" for r in delivered["references"])
    call = report["calls"][0]
    assert call["phases"] == ["request", "response"]
    assert call["owner_id"] == a.id
    assert call["observations"][0]["event_id"] in {e["event_id"] for e in events}
    assert len(report["agents"]) == 3


def test_equal_text_occurrences_remain_separate(tmp_path):
    graph, _, _, _, _ = scenario(tmp_path, total=100)
    index = build_investigation_index(graph, tmp_path)
    assert len(index["messages"]) == 101
    assert len({row["key"] for row in index["messages"]}) == 101


def test_metadata_only_does_not_claim_capture_failure_or_fabricate_content(tmp_path):
    graph, _, _, _, _ = scenario(tmp_path, mode="metadata_only")
    report = build_investigation_index(graph, tmp_path)
    assert len(report["messages"]) == 2
    assert report["calls"][0]["phases"] == ["request", "response"]
    assert all(x["state"] == "not_recorded" and x["reference"] is None
               for r in report["messages"] + report["calls"] for x in r["references"])
    assert report["inspection"]["state"] == "scanned_selected_streams"


@pytest.mark.parametrize("which,value", [("session_id", "foreign"), ("session_id", None), ("session_id", 7)])
def test_foreign_or_malformed_session_cannot_join(tmp_path, which, value):
    graph, events, _, _, _ = scenario(tmp_path)
    for event in events:
        event["attributes"][which] = value
    overwrite(tmp_path, events)
    report = build_investigation_index(graph, tmp_path)
    assert report["messages"] == [] and report["calls"] == []
    assert report["inspection"]["scope_rejected"] > 0


def test_top_level_and_attribute_scope_must_agree(tmp_path):
    graph, events, _, _, _ = scenario(tmp_path)
    for e in events:
        e["session_id"] = "foreign"
    overwrite(tmp_path, events)
    report = build_investigation_index(graph, tmp_path)
    assert not report["messages"]


@pytest.mark.parametrize("flag,value", [("inferred", True), ("viewer_only", True), ("inferred", "false"), ("viewer_only", 0)])
def test_inferred_or_malformed_flags_do_not_become_evidence(tmp_path, flag, value):
    graph, events, _, _, _ = scenario(tmp_path)
    for e in events:
        e["attributes"][flag] = value
    overwrite(tmp_path, events)
    assert build_investigation_index(graph, tmp_path)["messages"] == []


def test_conflicting_participants_not_silently_resolved(tmp_path):
    graph, events, a, b, _ = scenario(tmp_path)
    for event in events:
        if event["event_type"] == "MESSAGE_SENT":
            event["attributes"]["recipient_agent_id"] = a.id
    overwrite(tmp_path, events)
    index = build_investigation_index(graph, tmp_path)
    assert index["inspection"]["invalid_records"] > 0
    assert all("sent" not in r["phases"] for r in index["messages"])


def test_duplicate_event_id_is_deduped_only_when_compatible(tmp_path):
    graph, events, _, _, _ = scenario(tmp_path)
    selected = next(e for e in events if e["event_type"] == "TOOL_RESULT")
    overwrite(tmp_path, events + [copy.deepcopy(selected)])
    assert len(build_investigation_index(graph, tmp_path)["calls"][0]["observations"]) == 2
    conflict = copy.deepcopy(selected)
    conflict["attributes"]["content_sha256"] = "f" * 64
    overwrite(tmp_path, events + [conflict])
    index = build_investigation_index(graph, tmp_path)
    assert index["calls"][0]["phases"] == ["request"]
    assert index["inspection"]["conflicting_event_ids"] == 1


@pytest.mark.parametrize("value", [None, "", "x" * 2049, {}, []])
def test_missing_native_identity_is_not_guessed(tmp_path, value):
    graph, events, _, _, _ = scenario(tmp_path)
    for event in events:
        if event["event_type"] in {"MESSAGE_SENT", "MESSAGE_RECEIVED"}:
            event["attributes"]["message_id"] = value
    overwrite(tmp_path, events)
    report = build_investigation_index(graph, tmp_path)
    assert len(report["messages"]) == 3
    assert all(not x["identity_bound"] and len(x["phases"]) == 1 for x in report["messages"])


@pytest.mark.parametrize("path", ["../secret", "/etc/passwd", "https://example.test/raw", "content/sha256/" + "f" * 64 + ".txt"])
def test_payload_paths_are_not_capabilities(tmp_path, path):
    graph, events, _, _, _ = scenario(tmp_path)
    for event in events:
        if event["event_type"] == "TOOL_RESULT":
            event["attributes"]["content_ref"] = path
    overwrite(tmp_path, events)
    report = build_investigation_index(graph, tmp_path)
    row = report["calls"][0]["references"][-1]
    assert row["reference"] is None and row["state"] == "invalid_reference"


def test_unregistered_well_formed_ref_is_not_an_archive_claim(tmp_path):
    graph, _, _, _, _ = scenario(tmp_path)
    graph["nodes"] = [n for n in graph["nodes"] if n["type"] != "observed_content"]
    index = build_investigation_index(graph, tmp_path)
    assert all(ref["state"] == "not_in_graph_inventory" and ref["reference"] is None
               for row in index["messages"] + index["calls"] for ref in row["references"])


def test_inspection_does_not_open_content_or_workspace(tmp_path, monkeypatch):
    graph, _, _, _, _ = scenario(tmp_path)
    original = os.open
    opened = []

    def guarded(path, *args, **kwargs):
        opened.append(Path(path))
        assert Path(path).name == "semantic.jsonl"
        return original(path, *args, **kwargs)

    monkeypatch.setattr(os, "open", guarded)
    assert build_investigation_index(graph, tmp_path)["calls"]
    assert opened


@pytest.mark.parametrize("limit", ["max_events", "max_bytes", "max_observations"])
def test_exhausted_budget_never_looks_like_full_inventory(tmp_path, limit):
    graph, _, _, _, _ = scenario(tmp_path)
    index = build_investigation_index(graph, tmp_path, **{limit: 0})
    assert index["inspection"]["limit_reached"]
    assert index["inspection"]["state"] != "scanned_selected_streams"


@pytest.mark.parametrize("limit", [-1, True, 1.5, "100"])
def test_bad_budget_is_rejected(tmp_path, limit):
    with pytest.raises(ValueError):
        build_investigation_index({}, tmp_path, max_events=limit)


def test_malformed_duplicate_keys_and_nonfinite_lines_are_explicit(tmp_path):
    graph, _, _, _, _ = scenario(tmp_path)
    with (tmp_path / "semantic.jsonl").open("a") as f:
        f.write('{"a":1,"a":2}\nNaN\n[]\n{bad\n')
    report = build_investigation_index(graph, tmp_path)
    assert report["inspection"]["invalid_records"] == 4
    assert report["inspection"]["state"] == "partial"


def test_symlink_stream_rejected(tmp_path):
    graph, _, _, _, _ = scenario(tmp_path)
    outside = tmp_path.parent / (tmp_path.name + "-outside")
    stream = tmp_path / "semantic.jsonl"
    stream.rename(outside)
    stream.symlink_to(outside)
    report = build_investigation_index(graph, tmp_path)
    assert report["messages"] == [] and report["inspection"]["state"] == "unavailable"


def test_cached_scan_is_invalidated_by_appended_events_and_scope(tmp_path, monkeypatch):
    from execweave import investigation_index as module
    graph, events, _, _, _ = scenario(tmp_path)
    cache = InvestigationCache()
    original = module._scan
    calls = []

    def counted(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(module, "_scan", counted)
    first = build_investigation_index(graph, tmp_path, cache=cache)
    build_investigation_index(graph, tmp_path, cache=cache)
    assert len(calls) == 1
    event = copy.deepcopy(next(e for e in events if e["event_type"] == "MESSAGE_SENT"))
    event["event_id"] = "fresh"
    event["attributes"]["message_id"] = "another"
    overwrite(tmp_path, events + [event])
    assert len(build_investigation_index(graph, tmp_path, cache=cache)["messages"]) == len(first["messages"]) + 1
    graph["session_id"] = "foreign"
    assert not build_investigation_index(graph, tmp_path, cache=cache)["messages"]
    assert len(calls) == 3


def test_file_observation_is_not_a_snapshot_or_consumption(tmp_path):
    graph, _, a, _, _ = scenario(tmp_path)
    graph["nodes"].append({"id": "f", "type": "file", "name": "DESIGN.md"})
    graph["edges"].append({"id": "file-edge", "source": a.id, "target": "f", "relation": "READ"})
    index = build_investigation_index(graph, tmp_path)
    assert index["artifacts"][0]["snapshots"] == []
    assert index["artifacts"][0]["relations"][0]["relation"] == "READ"


def test_file_snapshot_keeps_exact_ref_relation_and_version(tmp_path):
    graph, _, _, _, _ = scenario(tmp_path)
    content = next(n for n in graph["nodes"] if n["type"] == "observed_content")
    graph["nodes"].append({"id": "f", "type": "file", "name": "DESIGN.md"})
    graph["edges"].append({"id": "snapshot-edge", "source": "f", "target": content["id"], "relation": "OBSERVED_FILE_CONTENT_BEFORE_READ"})
    item = build_investigation_index(graph, tmp_path)["artifacts"][0]
    assert item["snapshot_count"] == 1
    assert item["snapshots"][0]["reference"]["sha256"] == content["attributes"]["sha256"]
    assert item["snapshots"][0]["relation"] == "OBSERVED_FILE_CONTENT_BEFORE_READ"


def test_index_published_with_existing_conversation_payload(tmp_path):
    from execweave.conversation_records import conversation_index_payload
    graph, _, _, _, _ = scenario(tmp_path)
    payload = conversation_index_payload(graph, tmp_path)
    assert len(payload["investigation"]["messages"]) == 2
    assert payload["entries"]


def test_static_output_embeds_same_index_without_altering_raw_graph(tmp_path):
    from execweave.viewer_projection import write_graph_html
    graph, _, _, _, _ = scenario(tmp_path)
    before = copy.deepcopy(graph)
    output = write_graph_html(graph, tmp_path / "viewer.html")
    payload = json.loads((tmp_path / "conversations.json").read_text())
    assert graph == before
    assert 'window.__execweaveStaticInvestigation=' in output.read_text()
    assert payload["investigation"]["calls"][0]["phases"] == ["request", "response"]


@pytest.fixture
def browser_page():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        chromium = os.environ.get("EXECWEAVE_E2E_CHROMIUM") or shutil.which("chromium")
        browser = p.chromium.launch(executable_path=chromium, headless=True, args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        yield page
        assert errors == []
        browser.close()


def show(page, graph, index):
    from execweave.dashboard_shell import render_static_dashboard_html
    page.set_content(render_static_dashboard_html(graph, investigation_index=index))
    page.get_by_role("button", name="Explore run", exact=True).click()


@pytest.mark.viewer_e2e
def test_full_shell_agents_search_without_canvas_and_handoffs(tmp_path, browser_page):
    graph, _, a, b, _ = scenario(tmp_path)
    index = build_investigation_index(graph, tmp_path)
    page = browser_page
    show(page, graph, index)
    assert page.locator(".investigation-row").count() == 3
    page.get_by_label("Search investigation", exact=True).fill("reviewer")
    page.get_by_role("button", name="Search records", exact=True).click()
    assert page.locator(".investigation-row").count() == 1
    page.locator(".investigation-row summary").click()
    page.get_by_role("button", name="Show agent handoffs", exact=True).click()
    page.get_by_label("Search investigation", exact=True).fill("")
    page.get_by_role("button", name="Search records", exact=True).click()
    assert page.locator(".investigation-row").count() == 1
    page.locator(".investigation-row summary").click()
    page.get_by_text("Consumption: not observed", exact=False).wait_for()
    assert "Consumption: not observed" in page.locator("#execweave-investigation-rows").inner_text()
    assert page.evaluate("window.__execweaveCore.getGraph()") == graph


@pytest.mark.viewer_e2e
def test_same_message_other_recipient_stays_unreceived(tmp_path, browser_page):
    graph, _, _, _, _ = scenario(tmp_path)
    page = browser_page
    show(page, graph, build_investigation_index(graph, tmp_path))
    page.get_by_role("button", name="Handoffs", exact=True).click()
    page.get_by_label("Investigation filter", exact=True).select_option("attention")
    assert page.locator(".investigation-row").count() == 1
    assert "other recipient" in page.locator(".investigation-row").inner_text()
    assert "Receipt not observed" in page.locator(".investigation-row").inner_text()


@pytest.mark.viewer_e2e
def test_reader_receives_exact_registered_reference(tmp_path, browser_page):
    graph, _, _, _, _ = scenario(tmp_path)
    page = browser_page
    show(page, graph, build_investigation_index(graph, tmp_path))
    page.get_by_role("button", name="Model / tool calls", exact=True).click()
    page.locator(".investigation-row summary").click()
    page.locator(".investigation-row .execweave-content-actions button").first.click()
    assert page.locator("#execweave-content-dialog").is_visible()
    assert page.locator("#execweave-content-dialog").get_attribute("data-state") == "folder_required"


@pytest.mark.viewer_e2e
def test_no_snapshot_does_not_read_current_workspace(tmp_path, browser_page):
    graph, _, _, _, _ = scenario(tmp_path)
    (tmp_path / "DESIGN.md").write_text("current content must not be read")
    graph["nodes"].append({"id": "f", "type": "file", "name": "DESIGN.md"})
    page = browser_page
    show(page, graph, build_investigation_index(graph, tmp_path))
    page.get_by_role("button", name="Files / artifacts", exact=True).click()
    page.locator(".investigation-row summary").click()
    page.get_by_text("Only a file/path observation", exact=False).wait_for()
    assert "not read" in page.locator(".investigation-row").inner_text()
    assert "current content must not" not in page.locator(".investigation-row").inner_text()


@pytest.mark.viewer_e2e
def test_open_page_is_pinned_on_index_update(tmp_path, browser_page):
    graph, _, _, _, _ = scenario(tmp_path, total=60)
    index = build_investigation_index(graph, tmp_path)
    page = browser_page
    show(page, graph, index)
    page.get_by_role("button", name="Handoffs", exact=True).click()
    assert page.locator(".investigation-row").count() == 25
    page.get_by_role("button", name="Next page", exact=True).click()
    page.locator(".investigation-row summary").first.click()
    page.locator(".investigation-row[open]").get_by_text("Native occurrence:", exact=False).wait_for()
    before = page.locator("#execweave-investigation-rows").inner_text()
    smaller = copy.deepcopy(index)
    smaller["messages"] = []
    page.evaluate("x=>window.__execweaveInvestigation.setIndex(x)", smaller)
    assert page.locator("#execweave-investigation-rows").inner_text() == before
    assert page.locator(".investigation-row[open]").count() == 1
    page.get_by_role("button", name="Refresh index", exact=True).click()
    assert page.locator(".investigation-row").count() == 0


@pytest.mark.viewer_e2e
def test_foreign_index_does_not_replace_current_run(tmp_path, browser_page):
    graph, _, _, _, _ = scenario(tmp_path)
    index = build_investigation_index(graph, tmp_path)
    page = browser_page
    show(page, graph, index)
    page.evaluate("x=>window.__execweaveInvestigation.setIndex(x)", {**index, "session_id": "foreign", "agents": []})
    page.get_by_role("button", name="Refresh index", exact=True).click()
    assert page.locator(".investigation-row").count() == 3


@pytest.mark.viewer_e2e
def test_labels_render_literally_in_complete_page(tmp_path, browser_page):
    graph, _, _, _, _ = scenario(tmp_path)
    index = build_investigation_index(graph, tmp_path)
    index["agents"][0]["name"] = '<img src=x onerror="window.infected=true">'
    page = browser_page
    show(page, graph, index)
    assert page.locator("#execweave-investigation-rows img").count() == 0
    assert "<img" in page.locator("#execweave-investigation-rows").inner_text()
    assert page.evaluate("window.infected||false") is False


def test_assembled_shell_js_syntax(tmp_path):
    import re
    from execweave.dashboard_shell import DASHBOARD_HTML, render_static_dashboard_html
    from execweave.viewer_investigation import inject_investigation
    graph, _, _, _, _ = scenario(tmp_path)
    for i, html in enumerate([DASHBOARD_HTML, render_static_dashboard_html(graph, investigation_index=build_investigation_index(graph, tmp_path))]):
        assert html.count('id="execweave-investigation-script"') == 1
        assert inject_investigation(html) == html
        js = tmp_path / f"bundle-{i}.js"
        js.write_text("\n".join(re.findall(r"<script[^>]*>(.*?)</script>", html, re.S)), encoding="utf-8")
        subprocess.run(["node", "--check", str(js)], check=True, capture_output=True, timeout=20)
