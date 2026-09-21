"""Shipped receipt UI: synthetic component tests and separate native File tests.

The explicitly named component fixture delegates digest computation to Python's
hashlib. It validates UI/identity/races, not browser cryptography. Native file
journeys below use unchanged WebCrypto, real input files and no request shim.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from execweave.dashboard_shell import render_static_dashboard_html
from execweave.run_assessment import build_run_assessment
from execweave.task_validation import report_summary
from test_task_validation_reports import graph, receipt, xml, INVALID
from test_investigation_workspace import browser_page

__all__ = ["browser_page"]
pytestmark = pytest.mark.viewer_e2e


def load(page):
    data = graph()
    page.set_content(render_static_dashboard_html(data))
    return data


def component_digest_bridge(page):
    page.expose_function(
        "testReportDigest", lambda data: list(hashlib.sha256(bytes(data)).digest())
    )
    page.evaluate("""()=>Object.defineProperty(globalThis,'crypto',{configurable:true,value:{subtle:{
      digest:async (_algorithm, data)=>new Uint8Array(await window.testReportDigest(Array.from(new Uint8Array(data)))).buffer
    }}})""")


def select(page, value):
    page.locator("#execweave-task-report-file").set_input_files(
        {
            "name": "operator-report.json",
            "mimeType": "application/json",
            "buffer": json.dumps(value, ensure_ascii=False).encode(),
        }
    )
    page.wait_for_function(
        "/Report (accepted|not accepted)/.test(document.querySelector('#execweave-task-report-status').textContent)"
    )


def open_dialog(page):
    page.get_by_role("button", name="Review external task reports", exact=True).click()


@pytest.mark.parametrize(
    "outcomes,state",
    [
        ([], "checks_passed"),
        (["failure"], "checks_failed"),
        (["error"], "checks_failed"),
        (["skipped"], "partial"),
    ],
)
def test_component_receipt_is_recounted_and_original_claim_unchanged(browser_page, outcomes, state):
    data = load(browser_page)
    component_digest_bridge(browser_page)
    before = browser_page.evaluate("window.__execweaveCore.getGraph()")
    open_dialog(browser_page)
    value = receipt(data, xml(outcomes))
    value["summary"] = {"state": "all tasks succeeded", "counts": {"passed": 999}}
    select(browser_page, value)
    assert browser_page.locator(".execweave-task-report").get_attribute("data-state") == state
    assert "not authenticated" in browser_page.locator(".execweave-task-report").inner_text()
    assert "999" not in browser_page.locator(".execweave-task-report").inner_text()
    assert browser_page.locator('[data-axis="task"]').get_attribute("data-state") == "unverified"
    assert browser_page.evaluate("window.__execweaveCore.getGraph()") == before


@pytest.mark.parametrize(
    "change", ["session", "run", "path", "task", "snapshot", "hash", "authority"]
)
def test_component_mismatch_is_rejected_not_cross_bound(browser_page, change):
    data = load(browser_page)
    component_digest_bridge(browser_page)
    open_dialog(browser_page)
    value = receipt(data)
    if change in ("session", "run", "path"):
        value["scope"][
            {"session": "session_id", "run": "run_id", "path": "source_path"}[change]
        ] = "foreign"
    elif change == "task":
        value["subject"]["task_id"] = "agent:1"
    elif change == "snapshot":
        value["subject"]["task_snapshot_sha256"] = "f" * 64
    elif change == "hash":
        value["report"]["sha256"] = "f" * 64
    else:
        value["authority"] = "independent_authenticated"
    select(browser_page, value)
    assert "not accepted" in browser_page.locator("#execweave-task-report-status").inner_text()
    assert browser_page.locator(".execweave-task-report").count() == 0


def test_component_conflicting_reports_retained_and_duplicates_not_multiplied(browser_page):
    data = load(browser_page)
    component_digest_bridge(browser_page)
    open_dialog(browser_page)
    good = receipt(data)
    bad = receipt(data, xml(["failure"]))
    select(browser_page, good)
    select(browser_page, good)
    select(browser_page, bad)
    assert browser_page.locator(".execweave-task-report").count() == 2
    assert browser_page.locator('.execweave-task-report[data-state="checks_failed"]').count() == 1
    browser_page.keyboard.press("Escape")
    assert browser_page.get_by_role(
        "button", name="Review external task reports", exact=True
    ).evaluate("e=>e===document.activeElement")
    open_dialog(browser_page)
    assert browser_page.locator(".execweave-task-report").count() == 2


@pytest.mark.parametrize("changed", ["run", "task", "protected", "pagehide"])
def test_component_imported_results_revoked_when_scope_changes(browser_page, changed):
    data = load(browser_page)
    component_digest_bridge(browser_page)
    open_dialog(browser_page)
    select(browser_page, receipt(data))
    browser_page.keyboard.press("Escape")
    if changed == "pagehide":
        browser_page.evaluate("window.dispatchEvent(new Event('pagehide'))")
    else:
        if changed == "run":
            data["run_id"] = "other"
        elif changed == "task":
            data["nodes"][0]["name"] = "changed goal"
        else:
            data["live_payload_compact"] = True
        assessment = build_run_assessment(data)
        browser_page.evaluate(
            "([g,a])=>{Object.assign(window.__execweaveCore.getGraph(),g);window.__execweaveDashboard.onPayload({run_assessment:a})}",
            [data, assessment],
        )
    open_dialog(browser_page)
    assert browser_page.locator(".execweave-task-report").count() == 0


def test_browser_python_parser_parity_including_rejected_shapes(browser_page):
    load(browser_page)
    valid = [
        xml(),
        xml(["failure"]),
        xml(["error"]),
        xml(["skipped"]),
        "<testsuite/>",
        '<testsuite><testcase name="空白"><skipped/></testcase></testsuite>',
    ]
    for document in valid:
        assert browser_page.evaluate(
            "x=>window.__execweaveTaskReports.inspectXML(x)", document
        ) == report_summary(document)
    for document in INVALID:
        assert browser_page.evaluate(
            "x=>{try{window.__execweaveTaskReports.inspectXML(x);return false}catch{return true}}",
            document,
        )


def test_component_no_crypto_and_hostile_labels_do_not_promote_success(browser_page):
    data = load(browser_page)
    open_dialog(browser_page)
    browser_page.evaluate("Object.defineProperty(globalThis,'crypto',{configurable:true,value:{}})")
    select(browser_page, receipt(data))
    assert (
        "Native SHA-256 unavailable"
        in browser_page.locator("#execweave-task-report-status").inner_text()
    )
    component_digest_bridge(browser_page)
    value = receipt(data)
    value["validator"] = "<img src=https://example.invalid onerror=evil()>"
    select(browser_page, value)
    assert (
        browser_page.locator(
            "#execweave-task-reports-dialog img,#execweave-task-reports-dialog a"
        ).count()
        == 0
    )
    assert "<img" in browser_page.locator(".execweave-task-report").inner_text()


def test_component_duplicate_json_field_rejected(browser_page):
    load(browser_page)
    component_digest_bridge(browser_page)
    open_dialog(browser_page)
    browser_page.locator("#execweave-task-report-file").set_input_files(
        {"name": "x.json", "mimeType": "application/json", "buffer": b'{"format":"a","format":"b"}'}
    )
    browser_page.wait_for_function(
        "document.querySelector('#execweave-task-report-status').textContent.includes('duplicate_json_key')"
    )
    assert browser_page.locator(".execweave-task-report").count() == 0


def test_component_cancelled_digest_cannot_fill_reopened_dialog(browser_page):
    data = load(browser_page)
    open_dialog(browser_page)
    browser_page.evaluate("""()=>Object.defineProperty(globalThis,'crypto',{configurable:true,value:{subtle:{
      digest:()=>new Promise(r=>window.finishTestDigest=r)
    }}})""")
    value = receipt(data)
    browser_page.locator("#execweave-task-report-file").set_input_files(
        {"name": "x.json", "mimeType": "application/json", "buffer": json.dumps(value).encode()}
    )
    browser_page.wait_for_function('typeof window.finishTestDigest==="function"')
    browser_page.keyboard.press("Escape")
    open_dialog(browser_page)
    browser_page.evaluate(
        "x=>window.finishTestDigest(new Uint8Array(x).buffer)",
        list(bytes.fromhex(value["report"]["sha256"])),
    )
    assert browser_page.locator(".execweave-task-report").count() == 0


@pytest.mark.parametrize("outcome", ["pass", "fail", "empty", "tampered"])
def test_native_operator_receipt_file_and_crypto(tmp_path, browser_page, outcome):
    """No digest bridge: true file navigation, input bytes and native WebCrypto."""
    data = graph()
    pagefile = tmp_path / "viewer.html"
    pagefile.write_text(render_static_dashboard_html(data), encoding="utf-8")
    value = receipt(
        data,
        "<testsuite/>" if outcome == "empty" else xml(["failure"]) if outcome == "fail" else xml(),
    )
    if outcome == "tampered":
        value["report"]["xml"] = xml(["failure"])
    file = tmp_path / "report.json"
    file.write_text(json.dumps(value), encoding="utf-8")
    browser_page.goto(pagefile.as_uri())
    open_dialog(browser_page)
    browser_page.locator("#execweave-task-report-file").set_input_files(str(file))
    browser_page.wait_for_function(
        "/Report (accepted|not accepted)/.test(document.querySelector('#execweave-task-report-status').textContent)"
    )
    if outcome == "tampered":
        assert "hash mismatch" in browser_page.locator("#execweave-task-report-status").inner_text()
        assert browser_page.locator(".execweave-task-report").count() == 0
    else:
        assert (
            browser_page.locator(".execweave-task-report").get_attribute("data-state")
            == {"pass": "checks_passed", "fail": "checks_failed", "empty": "no_executed_checks"}[
                outcome
            ]
        )
    assert browser_page.locator('[data-axis="task"]').get_attribute("data-state") == "unverified"
    assert browser_page.evaluate("window.__execweaveCore.getGraph()") == data
