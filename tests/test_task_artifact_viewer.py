"""Artifact comparison: File inputs, explicit component digests, native cases.

Component tests reuse the named hashlib bridge solely for UI/race contracts.
The separate native cases navigate a real file origin and never replace crypto.
"""

from __future__ import annotations

import hashlib

import pytest

from execweave.dashboard_shell import render_static_dashboard_html
from execweave.task_artifacts import bind_artifacts, manifest_bytes
from test_investigation_workspace import browser_page
from test_task_validation_reports import graph, receipt
from test_task_validation_viewer import component_digest_bridge, load, open_dialog, select

__all__ = ["browser_page"]
pytestmark = pytest.mark.viewer_e2e


def artifacts(tmp_path, content=b"original bytes", name="output/result.txt"):
    source = tmp_path / "source"
    source.write_bytes(content)
    return bind_artifacts(receipt(), [f"{name}={source}"])


def start(page, value):
    load(page)
    component_digest_bridge(page)
    open_dialog(page)
    select(page, value)


def choose(page, folder):
    page.locator(".execweave-task-artifact-folder").set_input_files(str(folder))
    page.wait_for_function(
        "!document.querySelector('.execweave-task-artifacts') || document.querySelector('.execweave-task-artifacts').dataset.state!=='checking'"
    )


def folder(tmp_path, content=b"original bytes", name="output/result.txt", base="selected"):
    root = tmp_path / base
    target = root / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    return root


@pytest.mark.parametrize(
    "outcome,expected",
    [
        ("intact", "match"),
        ("same-size", "mismatch"),
        ("missing", "mismatch"),
        ("size", "mismatch"),
        ("binary", "match"),
        ("empty", "match"),
    ],
)
def test_component_selected_file_comparison_and_task_nonpromotion(
    tmp_path, browser_page, outcome, expected
):
    body = b"\x00\xff" if outcome == "binary" else b"" if outcome == "empty" else b"original bytes"
    value = artifacts(tmp_path, body)
    root = folder(tmp_path, body)
    if outcome == "same-size":
        (root / "output/result.txt").write_bytes(b"x" * len(body))
    elif outcome == "missing":
        (root / "output/result.txt").unlink()
        (root / "unrelated").write_text("not the artifact")
    elif outcome == "size":
        (root / "output/result.txt").write_bytes(b"truncated")
    start(browser_page, value)
    before = browser_page.evaluate("window.__execweaveCore.getGraph()")
    assert (
        browser_page.locator(".execweave-task-artifacts").get_attribute("data-state")
        == "not_checked"
    )
    choose(browser_page, root)
    box = browser_page.locator(".execweave-task-artifacts")
    assert box.get_attribute("data-state") == expected
    assert "not proof of test execution" in box.inner_text()
    assert browser_page.locator('[data-axis="task"]').get_attribute("data-state") == "unverified"
    assert browser_page.evaluate("window.__execweaveCore.getGraph()") == before


def test_v1_without_versions_stays_readable(tmp_path, browser_page):
    start(browser_page, receipt())
    assert (
        browser_page.locator(".execweave-task-artifacts").get_attribute("data-state")
        == "not_supplied"
    )
    assert not browser_page.locator(".execweave-task-artifact-folder").count()


def test_manifest_change_is_rejected_without_hash_update(tmp_path, browser_page):
    value = artifacts(tmp_path)
    value["artifacts"]["entries"][0]["size_bytes"] += 1
    start(browser_page, value)
    assert (
        "manifest hash mismatch"
        in browser_page.locator("#execweave-task-report-status").inner_text()
    )
    assert not browser_page.locator(".execweave-task-report").count()


@pytest.mark.parametrize(
    "mutate", ["duplicate", "case-collision", "parent", "bool", "newline-hash"]
)
def test_rehashed_but_invalid_manifest_cannot_be_accepted(tmp_path, browser_page, mutate):
    value = artifacts(tmp_path)
    m = value["artifacts"]
    entry = m["entries"][0]
    if mutate == "duplicate":
        m["entries"].append(dict(entry))
    elif mutate == "case-collision":
        m["entries"].append({**entry, "path": entry["path"].upper()})
    elif mutate == "parent":
        entry["path"] = "../private"
    elif mutate == "bool":
        entry["size_bytes"] = True
    else:
        entry["sha256"] += "\n"
    m["manifest_sha256"] = hashlib.sha256(manifest_bytes(m["entries"])).hexdigest()
    start(browser_page, value)
    assert "not accepted" in browser_page.locator("#execweave-task-report-status").inner_text()
    assert not browser_page.locator(".execweave-task-report").count()


def test_different_file_versions_do_not_deduplicate_same_report(tmp_path, browser_page):
    one = artifacts(tmp_path, b"AAAA")
    two = artifacts(tmp_path, b"BBBB")
    start(browser_page, one)
    select(browser_page, one)
    select(browser_page, two)
    assert browser_page.locator(".execweave-task-report").count() == 2
    text = browser_page.locator("#execweave-task-report-results").inner_text()
    assert (
        one["artifacts"]["manifest_sha256"] in text and two["artifacts"]["manifest_sha256"] in text
    )


def test_extra_files_are_not_read_or_included_in_version_claim(tmp_path, browser_page):
    value = artifacts(tmp_path)
    root = folder(tmp_path)
    (root / "secret").write_text("PRIVATE_NOT_ASSOCIATED")
    start(browser_page, value)
    browser_page.evaluate(
        """()=>{const read=File.prototype.arrayBuffer;File.prototype.arrayBuffer=function(){if(this.name==='secret')throw new Error('unrelated body opened');return read.call(this)}}"""
    )
    choose(browser_page, root)
    assert browser_page.locator(".execweave-task-artifacts").get_attribute("data-state") == "match"
    assert (
        "1 other selected files were not read"
        in browser_page.locator(".execweave-task-artifacts").inner_text()
    )
    assert (
        "PRIVATE_NOT_ASSOCIATED"
        not in browser_page.locator("#execweave-task-report-results").inner_text()
    )


def defer_first_digest(page):
    page.evaluate("""()=>{const prior=crypto.subtle.digest;let first=true;crypto.subtle.digest=(...a)=>{
        if(!first)return prior(...a);first=false;
        return new Promise(resolve=>{window.finishArtifactDigest=async()=>resolve(await prior(...a))});
    }}""")


def test_changed_folder_revokes_match_and_rejects_stale_result(tmp_path, browser_page):
    value = artifacts(tmp_path)
    one = folder(tmp_path)
    two = folder(tmp_path, b"x" * 14, base="other")
    start(browser_page, value)
    choose(browser_page, one)
    defer_first_digest(browser_page)
    browser_page.locator(".execweave-task-artifact-folder").set_input_files(str(one))
    browser_page.wait_for_function('typeof window.finishArtifactDigest==="function"')
    assert (
        browser_page.locator(".execweave-task-artifacts").get_attribute("data-state") == "checking"
    )
    choose(browser_page, two)
    browser_page.evaluate("window.finishArtifactDigest()")
    assert (
        browser_page.locator(".execweave-task-artifacts").get_attribute("data-state") == "mismatch"
    )


def test_close_pending_read_retains_no_success_and_preserves_selection(tmp_path, browser_page):
    value = artifacts(tmp_path)
    root = folder(tmp_path)
    load(browser_page)
    component_digest_bridge(browser_page)
    browser_page.evaluate("window.__execweaveCore.selectNode('agent:1')")
    open_dialog(browser_page)
    select(browser_page, value)
    defer_first_digest(browser_page)
    browser_page.locator(".execweave-task-artifact-folder").set_input_files(str(root))
    browser_page.wait_for_function('typeof window.finishArtifactDigest==="function"')
    browser_page.keyboard.press("Escape")
    open_dialog(browser_page)
    browser_page.evaluate("window.finishArtifactDigest()")
    assert (
        browser_page.locator(".execweave-task-artifacts").get_attribute("data-state") == "cancelled"
    )
    assert browser_page.locator("#nodes .node.selected").get_attribute("data-id") == "agent:1"


def test_scope_change_discards_pending_comparison(tmp_path, browser_page):
    value = artifacts(tmp_path)
    root = folder(tmp_path)
    start(browser_page, value)
    defer_first_digest(browser_page)
    browser_page.locator(".execweave-task-artifact-folder").set_input_files(str(root))
    browser_page.wait_for_function('typeof window.finishArtifactDigest==="function"')
    browser_page.evaluate(
        "()=>{window.__execweaveCore.getGraph().run_id='changed';window.__execweaveDashboard.onPayload({})}"
    )
    browser_page.evaluate("window.finishArtifactDigest()")
    assert not browser_page.locator(".execweave-task-report").count()


def test_unicode_relative_path_is_not_replaced_by_basename(tmp_path, browser_page):
    value = artifacts(tmp_path, b"content", "成果/報告.txt")
    root = folder(tmp_path, b"content", "成果/報告.txt")
    start(browser_page, value)
    choose(browser_page, root)
    assert browser_page.locator(".execweave-task-artifacts").get_attribute("data-state") == "match"
    wrong = folder(tmp_path, b"content", "報告.txt", base="wrong")
    choose(browser_page, wrong)
    assert (
        browser_page.locator(".execweave-task-artifacts").get_attribute("data-state") == "mismatch"
    )


@pytest.mark.parametrize("outcome", ["intact", "tampered", "missing", "empty"])
def test_native_receipt_artifact_folder_comparison(tmp_path, browser_page, outcome):
    """Actual file origin, FileList and WebCrypto; no digest bridge."""
    content = b"" if outcome == "empty" else b"original bytes"
    value = artifacts(tmp_path, content)
    root = folder(tmp_path, content)
    if outcome == "tampered":
        (root / "output/result.txt").write_bytes(b"x" * len(content))
    elif outcome == "missing":
        (root / "output/result.txt").unlink()
        (root / "other").write_text("unrelated")
    view = tmp_path / "viewer.html"
    view.write_text(render_static_dashboard_html(graph()), encoding="utf-8")
    browser_page.goto(view.as_uri())
    open_dialog(browser_page)
    select(browser_page, value)
    choose(browser_page, root)
    assert browser_page.locator(".execweave-task-artifacts").get_attribute("data-state") == (
        "match" if outcome in ("intact", "empty") else "mismatch"
    )
    assert browser_page.locator('[data-axis="task"]').get_attribute("data-state") == "unverified"
