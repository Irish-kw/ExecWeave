"""Separate synthetic counter tests from actual File/crypto reading journeys."""

from __future__ import annotations

import copy
import json

import pytest

from execweave.dashboard_shell import render_static_dashboard_html
from test_content_browser import reference
from test_investigation_workspace import browser_page

__all__ = ["browser_page"]
pytestmark = pytest.mark.viewer_e2e


def fixture(data=b"captured body"):
    ref = reference(data)
    graph = {
        "run_id": "execution-A",
        "session_id": "one",
        "source_path": "/run/events.jsonl",
        "nodes": [
            {"id": "a", "type": "agent", "name": "Reader"},
            {"id": "content", "type": "observed_content", "attributes": ref},
        ],
        "edges": [],
    }
    record = {
        "key": "one",
        "kind": "tool",
        "native_id": "call",
        "owner_id": "a",
        "phases": ["response"],
        "references": [{"phase": "response", "state": "registered_not_read", "reference": ref}],
    }
    index = {
        "schema_version": "0.1",
        "scope": "recorded_event_investigation",
        "session_id": "one",
        "source_path": graph["source_path"],
        "inspection": {"state": "scanned_selected_streams"},
        "calls": [record],
        "messages": [],
        "artifacts": [],
        "agents": [],
    }
    ledger = {
        "schema_version": "1",
        "scope": json.dumps(["execution-A", "one", "/run/events.jsonl"], separators=(",", ":")),
        "records": [
            {**ref, "state": "verified", "readable": True, "hash_verified_bytes": len(data)}
        ],
        "evicted": 0,
    }
    return graph, index, ledger, ref


def evaluate(page, graph, index, ledger):
    page.set_content(render_static_dashboard_html(graph, investigation_index=index))
    return page.evaluate(
        "([i,l])=>window.__execweaveContentHealth.verifiedReads(i,l)", [index, ledger]
    )


def test_duplicate_references_count_bytes_once_not_invocations(browser_page):
    graph, index, ledger, _ = fixture("繁體中文".encode())
    index["calls"].append({**copy.deepcopy(index["calls"][0]), "key": "two"})
    result = evaluate(browser_page, graph, index, ledger)
    assert result["files"] == result["hash_verified_files"] == result["readable_files"] == 1
    assert result["hash_verified_bytes"] == result["declared_bytes"] == 12


def test_empty_body_is_a_verified_file_with_zero_bytes(browser_page):
    graph, index, ledger, _ = fixture(b"")
    result = evaluate(browser_page, graph, index, ledger)
    assert result["hash_verified_files"] == result["readable_files"] == 1
    assert result["hash_verified_bytes"] == 0


def test_binary_hash_and_readable_text_are_distinct(browser_page):
    graph, index, ledger, _ = fixture(b"\x00\xff")
    ledger["records"][0].update(state="binary_content", readable=False)
    result = evaluate(browser_page, graph, index, ledger)
    assert result["hash_verified_files"] == 1 and result["hash_verified_bytes"] == 2
    assert result["readable_files"] == result["readable_bytes"] == 0


@pytest.mark.parametrize(
    "state",
    [
        "hash_mismatch",
        "size_mismatch",
        "missing_blob",
        "unauthorized",
        "cancelled",
        "reading",
        "folder_required",
        "crypto_unavailable",
    ],
)
def test_non_verified_states_cannot_retain_success_counts(browser_page, state):
    graph, index, ledger, _ = fixture()
    ledger["records"][0]["state"] = state
    result = evaluate(browser_page, graph, index, ledger)
    assert result["hash_verified_files"] == result["readable_files"] == 0
    assert result["unverified_files"] == 1
    assert result["failed_reads"] == (
        1 if state in {"hash_mismatch", "size_mismatch", "missing_blob", "unauthorized"} else 0
    )


@pytest.mark.parametrize("field", ["run_id", "session_id", "source_path"])
def test_ledger_cannot_follow_another_execution(browser_page, field):
    graph, index, ledger, _ = fixture()
    graph[field] = "another"
    result = evaluate(browser_page, graph, index, ledger)
    assert result["hash_verified_files"] == 0


@pytest.mark.parametrize(
    "variant", ["graph-size", "index-size", "duplicate-ledger", "false-byte-count"]
)
def test_changed_or_ambiguous_declarations_reject_prior_reads(browser_page, variant):
    graph, index, ledger, ref = fixture()
    if variant == "graph-size":
        graph["nodes"][-1]["attributes"] = {**ref, "size_bytes": ref["size_bytes"] + 1}
    elif variant == "index-size":
        index["calls"][0]["references"].append(
            {
                "state": "registered_not_read",
                "reference": {**ref, "size_bytes": ref["size_bytes"] + 1},
            }
        )
    elif variant == "duplicate-ledger":
        ledger["records"].append(copy.deepcopy(ledger["records"][0]))
    else:
        ledger["records"][0]["hash_verified_bytes"] = True
    result = evaluate(browser_page, graph, index, ledger)
    assert result["hash_verified_files"] == 0


def test_eviction_and_unavailable_index_remain_partial(browser_page):
    graph, index, ledger, _ = fixture()
    ledger["evicted"] = 1
    assert evaluate(browser_page, graph, index, ledger)["partial"]
    assert browser_page.evaluate("window.__execweaveContentHealth.verifiedReads(null,null).partial")


def load_actual_reader(page, graph, index, ref):
    page.set_content(render_static_dashboard_html(graph, investigation_index=index))
    page.evaluate(
        'r=>window.__execweaveContentBrowser.attach(document.getElementById("details"),[r],"captured")',
        ref,
    )
    page.locator(".execweave-content-actions button").first.click()
    page.wait_for_function(
        "document.querySelector('#execweave-content-dialog').dataset.state==='folder_required'"
    )


def read_outcomes(page):
    return page.evaluate("window.__execweaveContentBrowser.getReadOutcomes()")


def test_real_failed_read_and_changed_folder_update_the_ledger(tmp_path, browser_page):
    graph, index, _, ref = fixture()
    original = copy.deepcopy(graph)
    folder = tmp_path / "run"
    path = folder / ref["path"]
    path.parent.mkdir(parents=True)
    path.write_bytes(b"short")
    load_actual_reader(browser_page, graph, index, ref)
    browser_page.locator("#execweave-content-folder").set_input_files(str(folder))
    browser_page.wait_for_function(
        "document.querySelector('#execweave-content-dialog').dataset.state==='size_mismatch'"
    )
    result = read_outcomes(browser_page)
    assert result["records"][0]["state"] == "size_mismatch"
    assert result["records"][0]["hash_verified_bytes"] is None
    # Returned copies cannot mutate the private ledger.
    browser_page.evaluate(
        "window.__execweaveContentBrowser.getReadOutcomes().records[0].state='verified'"
    )
    assert read_outcomes(browser_page)["records"][0]["state"] == "size_mismatch"
    browser_page.keyboard.press("Escape")
    browser_page.get_by_role("button", name="Content health", exact=True).click()
    summary = browser_page.locator("#execweave-health-verified-reads").inner_text()
    assert "0/1 indexed files hash-verified" in summary and "1 latest read failures" in summary
    assert browser_page.evaluate("window.__execweaveCore.getGraph()") == original


@pytest.mark.parametrize("action", ["scope", "pagehide", "different-folder"])
def test_actual_outcomes_are_revoked_with_folder_capability(tmp_path, browser_page, action):
    graph, index, _, ref = fixture()
    folder = tmp_path / "run"
    p = folder / ref["path"]
    p.parent.mkdir(parents=True)
    p.write_bytes(b"short")
    load_actual_reader(browser_page, graph, index, ref)
    browser_page.locator("#execweave-content-folder").set_input_files(str(folder))
    browser_page.wait_for_function(
        "document.querySelector('#execweave-content-dialog').dataset.state==='size_mismatch'"
    )
    if action == "scope":
        browser_page.evaluate("window.__execweaveCore.getGraph().run_id='other'")
    elif action == "pagehide":
        browser_page.evaluate("window.dispatchEvent(new Event('pagehide'))")
    else:
        different = tmp_path / "different"
        different.mkdir()
        (different / "note.txt").write_text("not a capture")
        browser_page.locator("#execweave-content-folder").set_input_files(str(different))
    assert read_outcomes(browser_page)["records"] == []


@pytest.mark.parametrize(
    "variant,state,verified,readable",
    [
        ("intact", "verified", 1, 1),
        ("binary", "binary_content", 1, 0),
        ("tamper", "hash_mismatch", 0, 0),
        ("missing", "missing_blob", 0, 0),
    ],
)
def test_native_file_reader_supplies_actual_verification_counts(
    tmp_path, browser_page, variant, state, verified, readable
):
    """Native File input and crypto; no mocked hash, fetch, or file methods."""
    data = b"\x00\xff" if variant == "binary" else b"actual captured text"
    graph, index, _, ref = fixture(data)
    folder = tmp_path / "export"
    folder.mkdir()
    path = folder / ref["path"]
    path.parent.mkdir(parents=True)
    path.write_bytes(b"x" * len(data) if variant == "tamper" else data)
    if variant == "missing":
        path.unlink()
        (path.parent / ("f" * 64 + ".txt")).write_text("unrelated")
    document = folder / "viewer.html"
    document.write_text(
        render_static_dashboard_html(graph, investigation_index=index), encoding="utf-8"
    )
    page = browser_page
    page.goto(document.as_uri())
    page.evaluate(
        'r=>window.__execweaveContentBrowser.attach(document.getElementById("details"),[r],"captured")',
        ref,
    )
    page.locator(".execweave-content-actions button").first.click()
    page.locator("#execweave-content-folder").set_input_files(str(folder))
    page.wait_for_function(
        's=>document.querySelector("#execweave-content-dialog").dataset.state===s', arg=state
    )
    outcomes = read_outcomes(page)
    assert len(outcomes["records"]) == 1 and outcomes["records"][0]["state"] == state
    page.keyboard.press("Escape")
    page.get_by_role("button", name="Content health", exact=True).click()
    report = page.evaluate(
        "([i,l])=>window.__execweaveContentHealth.verifiedReads(i,l)", [index, outcomes]
    )
    assert report["hash_verified_files"] == verified and report["readable_files"] == readable
    assert report["hash_verified_bytes"] == (len(data) if verified else 0)
    assert page.locator("#execweave-health-verified-reads").is_visible()
