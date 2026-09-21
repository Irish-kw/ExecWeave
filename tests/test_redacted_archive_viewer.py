"""Offline verification understands redacted derivative lineage without source bytes."""

from __future__ import annotations

import json
import os

import pytest
from execweave.redacted_archive import create_redacted_archive
from test_delivery_status import files_from, node_verify
from test_redacted_archive import policy, source_archive


@pytest.fixture
def browser_page():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        executable = os.environ.get("EXECWEAVE_E2E_CHROMIUM")
        browser = playwright.chromium.launch(
            **({"executable_path": executable} if executable else {})
        )
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        yield page
        assert errors == []
        browser.close()


def derivative(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    source_archive(source)
    policy_path = tmp_path / "policy.json"
    policy(policy_path)
    derived = tmp_path / "derived"
    create_redacted_archive(source, derived, policy_path)
    graph = json.loads((derived / "graph.json").read_text())
    return source, derived, graph


def test_js_archive_verifier_checks_derivative_lineage_with_native_webcrypto(tmp_path):
    _source, derived, graph = derivative(tmp_path)
    result = node_verify(tmp_path, files_from(derived), graph)
    assert result["state"] == "verified_now"
    assert result["derivation"]["state"] == "verified_now"
    assert result["derivation"]["mapping_count"] == 3
    assert result["derivation"]["source_state"] == "declared_not_rechecked"
    assert result["derivation"]["policy_sha256"] == graph["redacted_derivative"]["policy_sha256"]


def test_js_archive_verifier_rejects_changed_lineage(tmp_path):
    _source, derived, graph = derivative(tmp_path)
    files = files_from(derived)
    lineage = json.loads((derived / "lineage.json").read_text())
    lineage["derived"]["content_file_count"] += 1
    from test_delivery_status import replace_file

    replace_file(files, "lineage.json", json.dumps(lineage), repin=False)
    result = node_verify(tmp_path, files, graph)
    assert result["state"] == "not_verified"
    assert result["code"] in {"hash_mismatch", "size_mismatch", "lineage_mismatch"}


def test_delivery_panel_discloses_verified_derivative_lineage_component(tmp_path, browser_page):
    _source, derived, graph = derivative(tmp_path)
    browser_page.set_content((derived / "viewer.html").read_text(encoding="utf-8"))
    policy_sha = graph["redacted_derivative"]["policy_sha256"]
    # UI-only bridge: native File/WebCrypto verification is covered by the Node
    # verifier above and a separate CI/Grok native journey.
    browser_page.evaluate(
        """sha=>{
      window.__execweaveArchiveVerifier.filesFromSelection=()=>new Map();
      window.__execweaveArchiveVerifier.verifyArchive=async()=>({
        state:'verified_now',reference_count:3,verified_file_count:3,primary_file_count:3,
        checked_bytes:123,checked_at:'synthetic-component',recorded_state:'complete',
        session_id:window.__execweaveCore.getGraph().session_id,
        source_path:window.__execweaveCore.getGraph().source_path||null,
        derivation:{state:'verified_now',mapping_count:3,policy_sha256:sha,
          source_finalization_sha256:'0'.repeat(64),source_state:'declared_not_rechecked'}
      });
    }""",
        policy_sha,
    )
    browser_page.locator("#execweave-delivery-summary").click()
    browser_page.evaluate(
        "()=>window.__execweaveDeliveryStatus.verifySelected([new File(['x'],'placeholder')])"
    )
    browser_page.wait_for_function(
        "document.querySelector('[data-axis=archive]')?.dataset.state==='verified_now'",
        timeout=5000,
    )
    text = browser_page.locator("[data-axis=archive]").inner_text()
    assert "Redacted derivative lineage verified" in text
    assert "source archive itself was declared by fingerprint and was not rechecked" in text
    assert browser_page.locator("[data-axis=task]").get_attribute("data-state") == "unverified"
