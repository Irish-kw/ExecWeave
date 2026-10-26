"""Signed checks UI; component crypto bridge is not native browser acceptance.

Native file-origin cases below contain no bridge and remain enabled in CI.
Python/Node native signature interoperability is separately checked in core tests.
"""

from __future__ import annotations

import hashlib
import json

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from execweave import controlled_checks as cc
from execweave.dashboard_shell import render_static_dashboard_html
from execweave.run_assessment import build_run_assessment
from test_controlled_checks import setup_case, signed
from test_investigation_workspace import browser_page

__all__ = ["browser_page"]
pytestmark = pytest.mark.viewer_e2e


def bridge(page):
    """UI only: real Python crypto calls over a deliberately injected bridge."""

    def verify(public, signature, raw):
        try:
            Ed25519PublicKey.from_public_bytes(bytes(public)).verify(bytes(signature), bytes(raw))
            return True
        except InvalidSignature:
            return False

    page.expose_function("componentVerifyEd25519", verify)
    page.expose_function("componentDigest", lambda raw: list(hashlib.sha256(bytes(raw)).digest()))
    page.evaluate("""()=>Object.defineProperty(globalThis,'crypto',{configurable:true,value:{subtle:{
      importKey:async(_fmt,key)=>({raw:Array.from(new Uint8Array(key))}),
      verify:async(_alg,key,sig,data)=>{if(window.deferSignature)await new Promise(r=>window.releaseSignature=r);return window.componentVerifyEd25519(key.raw,Array.from(new Uint8Array(sig)),Array.from(new Uint8Array(data)))},
      digest:async(_alg,data)=>new Uint8Array(await window.componentDigest(Array.from(new Uint8Array(data)))).buffer
    }}})""")


def load(page, tmp_path, *, native=False):
    values = setup_case(tmp_path)
    document = render_static_dashboard_html(values[0])
    if native:
        viewer = tmp_path / "viewer.html"
        viewer.write_text(document, encoding="utf-8")
        page.goto(viewer.as_uri())
        assert page.evaluate("isSecureContext && !!crypto.subtle")
    else:
        page.set_content(document)
        bridge(page)
    page.evaluate("window.__execweaveCore.selectNode('agent:1')")
    page.get_by_role("button", name="Review signed fixed checks", exact=True).click()
    return values


def select_json(page, selector, value, name="record.json"):
    page.locator(selector).set_input_files(
        {"name": name, "mimeType": "application/json", "buffer": cc.encoded(value)}
    )


def trust(page, profile):
    select_json(page, "#execweave-controlled-profile", profile)
    page.wait_for_function(
        "document.querySelector('#execweave-controlled-status').textContent.startsWith('Profile loaded')"
    )
    assert page.locator(".execweave-controlled-result").count() == 0
    page.get_by_label("I independently trust this verifier key", exact=False).check()


def import_receipt(page, envelope):
    select_json(page, "#execweave-controlled-receipt", envelope)
    page.wait_for_function(
        "/^Signed execution (accepted|not accepted)/.test(document.querySelector('#execweave-controlled-status').textContent)"
    )


def test_actual_signed_execution_requires_separate_confirmed_trust(browser_page, tmp_path):
    data, artifact, policy, raw, key, profile, envelope = load(browser_page, tmp_path)
    import_receipt(browser_page, envelope)
    assert (
        "independently selected"
        in browser_page.locator("#execweave-controlled-status").inner_text()
    )
    select_json(browser_page, "#execweave-controlled-profile", profile)
    browser_page.wait_for_function(
        "document.querySelector('#execweave-controlled-status').textContent.startsWith('Profile loaded')"
    )
    import_receipt(browser_page, envelope)
    assert browser_page.locator(".execweave-controlled-result").count() == 0
    browser_page.get_by_label("I independently trust this verifier key", exact=False).check()
    import_receipt(browser_page, envelope)
    assert (
        browser_page.locator(".execweave-controlled-result").get_attribute("data-state")
        == "checks_passed"
    )
    assert "3 passed" in browser_page.locator(".execweave-controlled-result").inner_text()
    assert browser_page.locator('[data-axis="task"]').get_attribute("data-state") == "unverified"
    browser_page.keyboard.press("Escape")
    assert browser_page.get_by_role(
        "button", name="Review signed fixed checks", exact=True
    ).evaluate("e=>e===document.activeElement")
    assert browser_page.locator("#nodes .node.selected").get_attribute("data-id") == "agent:1"
    assert browser_page.evaluate("window.__execweaveCore.getGraph()") == data


@pytest.mark.parametrize(
    "change",
    ["bad-signature", "wrong-policy", "wrong-task", "wrong-run", "forged-results", "extra-field"],
)
def test_signed_invalid_or_foreign_receipts_never_show_as_accepted(browser_page, tmp_path, change):
    data, artifact, policy, raw, key, profile, envelope = load(browser_page, tmp_path)
    if change == "wrong-policy":
        profile["policy_sha256"] = "f" * 64
    trust(browser_page, profile)
    if change == "bad-signature":
        envelope["signature_b64"] = cc._b64(bytes(64))
    else:
        payload = json.loads(envelope["payload"])
        if change == "wrong-task":
            payload["subject"]["task_id"] = "task:other"
        elif change == "wrong-run":
            payload["scope"]["run_id"] = "other"
        elif change == "forged-results":
            payload["results"].pop()
        elif change == "extra-field":
            payload["summary"] = {"passed": 999}
        envelope = signed(key, payload)
    import_receipt(browser_page, envelope)
    assert "not accepted" in browser_page.locator("#execweave-controlled-status").inner_text()
    assert browser_page.locator(".execweave-controlled-result").count() == 0


def test_failed_checks_are_signed_and_not_overwritten_by_passing_report(browser_page, tmp_path):
    data, artifact, policy, raw, key, profile, envelope = load(browser_page, tmp_path)
    trust(browser_page, profile)
    import_receipt(browser_page, envelope)
    import_receipt(browser_page, envelope)
    assert browser_page.locator(".execweave-controlled-result").count() == 1
    artifact.write_bytes(b"{}")
    failed = cc.execute_checks(data, "task:1", raw, ["result.json=" + str(artifact)], key)
    import_receipt(browser_page, failed)
    assert browser_page.locator(".execweave-controlled-result").count() == 2
    assert (
        browser_page.locator('.execweave-controlled-result[data-state="checks_failed"]').count()
        == 1
    )
    assert browser_page.locator('[data-axis="task"]').get_attribute("data-state") == "unverified"


@pytest.mark.parametrize(
    "change", ["run", "task", "protected", "pagehide", "untrust", "new-profile"]
)
def test_accepted_checks_revoked_on_trust_or_task_change(browser_page, tmp_path, change):
    data, artifact, policy, raw, key, profile, envelope = load(browser_page, tmp_path)
    trust(browser_page, profile)
    import_receipt(browser_page, envelope)
    if change == "pagehide":
        browser_page.evaluate("window.dispatchEvent(new Event('pagehide'))")
    elif change == "untrust":
        browser_page.get_by_label("I independently trust this verifier key", exact=False).uncheck()
    elif change == "new-profile":
        select_json(browser_page, "#execweave-controlled-profile", profile)
    else:
        if change == "run":
            data["run_id"] = "other"
        elif change == "task":
            data["nodes"][0]["name"] = "a different requested result"
        else:
            data["live_payload_compact"] = True
        assessment = build_run_assessment(data)
        browser_page.evaluate(
            "([g,a])=>{Object.assign(window.__execweaveCore.getGraph(),g);window.__execweaveDashboard.onPayload({run_assessment:a})}",
            [data, assessment],
        )
    assert browser_page.locator(".execweave-controlled-result").count() == 0


def test_pending_signature_does_not_reappear_after_close_and_reopen(browser_page, tmp_path):
    data, artifact, policy, raw, key, profile, envelope = load(browser_page, tmp_path)
    trust(browser_page, profile)
    browser_page.evaluate("window.deferSignature=true")
    select_json(browser_page, "#execweave-controlled-receipt", envelope)
    browser_page.wait_for_function("typeof window.releaseSignature==='function'")
    browser_page.get_by_role("button", name="Close signed checks", exact=True).click()
    browser_page.get_by_role("button", name="Review signed fixed checks", exact=True).click()
    browser_page.evaluate("window.releaseSignature()")
    browser_page.wait_for_timeout(30)
    assert browser_page.locator(".execweave-controlled-result").count() == 0
    assert (
        browser_page.locator("#execweave-controlled-status")
        .inner_text()
        .startswith("Select a signed")
    )


def test_policy_code_and_markup_never_execute_in_viewer(browser_page, tmp_path):
    data, artifact, policy, raw, key, profile, envelope = load(browser_page, tmp_path)
    profile["label"] = '<img src=x onerror="window.XSS=1">'
    trust(browser_page, profile)
    import_receipt(browser_page, envelope)
    assert browser_page.locator("#execweave-controlled-dialog img").count() == 0
    assert browser_page.evaluate("window.XSS") is None
    assert browser_page.locator(".execweave-controlled-result").count() == 1


def test_real_selected_folder_comparison_and_close_revoke_component(browser_page, tmp_path):
    data, artifact, policy, raw, key, profile, envelope = load(browser_page, tmp_path)
    trust(browser_page, profile)
    import_receipt(browser_page, envelope)
    folder = tmp_path / "delivery"
    folder.mkdir()
    item = folder / "result.json"
    item.write_bytes(artifact.read_bytes())
    (folder / "unlisted.txt").write_text("not part of checks")
    browser_page.locator(".execweave-controlled-folder").set_input_files(folder)
    browser_page.wait_for_function(
        "document.querySelector('.execweave-controlled-comparison').dataset.state==='match'"
    )
    item.write_bytes(b"X" * item.stat().st_size)
    browser_page.locator(".execweave-controlled-folder").set_input_files(folder)
    browser_page.wait_for_function(
        "document.querySelector('.execweave-controlled-comparison').dataset.state==='mismatch'"
    )
    assert "hash_mismatch" in browser_page.locator(".execweave-controlled-comparison").inner_text()
    browser_page.keyboard.press("Escape")
    browser_page.get_by_role("button", name="Review signed fixed checks", exact=True).click()
    assert (
        browser_page.locator(".execweave-controlled-comparison").get_attribute("data-state")
        == "not_compared"
    )


def test_unavailable_crypto_cannot_authorize_a_profile(browser_page, tmp_path):
    data, artifact, policy, raw, key, profile, envelope = load(browser_page, tmp_path)
    browser_page.evaluate("Object.defineProperty(globalThis,'crypto',{configurable:true,value:{}})")
    select_json(browser_page, "#execweave-controlled-profile", profile)
    browser_page.wait_for_function(
        "document.querySelector('#execweave-controlled-status').textContent.startsWith('Profile not accepted')"
    )
    assert (
        "cryptography unavailable"
        in browser_page.locator("#execweave-controlled-status").inner_text()
    )
    assert browser_page.locator(".execweave-controlled-result").count() == 0


@pytest.mark.parametrize(
    "state", ["pass", "failed-check", "tampered-signature", "tampered-artifact"]
)
def test_native_file_ed25519_trust_and_artifact_journey(browser_page, tmp_path, state):
    data, artifact, policy, raw, key, profile, envelope = load(browser_page, tmp_path, native=True)
    trust(browser_page, profile)
    if state == "failed-check":
        artifact.write_bytes(b"{}")
        envelope = cc.execute_checks(data, "task:1", raw, ["result.json=" + str(artifact)], key)
    if state == "tampered-signature":
        envelope["signature_b64"] = cc._b64(bytes(64))
    import_receipt(browser_page, envelope)
    if state == "tampered-signature":
        assert browser_page.locator(".execweave-controlled-result").count() == 0
        return
    expected = "checks_failed" if state == "failed-check" else "checks_passed"
    assert (
        browser_page.locator(".execweave-controlled-result").get_attribute("data-state") == expected
    )
    folder = tmp_path / "delivered"
    folder.mkdir()
    item = folder / "result.json"
    item.write_bytes(artifact.read_bytes())
    if state == "tampered-artifact":
        item.write_bytes(b"X" * item.stat().st_size)
    browser_page.locator(".execweave-controlled-folder").set_input_files(folder)
    compare = "mismatch" if state == "tampered-artifact" else "match"
    browser_page.wait_for_function(
        "s=>document.querySelector('.execweave-controlled-comparison').dataset.state===s",
        arg=compare,
    )
    assert browser_page.locator('[data-axis="task"]').get_attribute("data-state") == "unverified"
