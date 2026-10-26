"""Exact indexed call navigation, not agent-wide attribution or provider capture."""

from __future__ import annotations

import copy

import pytest

from execweave.dashboard_shell import render_static_dashboard_html
from test_investigation_workspace import browser_page
from test_runtime_evidence_browser import graph

__all__ = ["browser_page"]
pytestmark = pytest.mark.viewer_e2e


def fixture():
    g = graph()
    rows = [
        {
            "key": "row-" + x,
            "kind": "tool",
            "native_id": "call-" + x,
            "owner_id": x,
            "target_id": "shared-tool",
            "source_name": x,
            "target_name": "shell",
            "phases": ["request", "response"],
            "identity_bound": True,
            "references": [],
            "observations": [],
        }
        for x in ["a", "b"]
    ]
    index = {
        "schema_version": "0.1",
        "scope": "recorded_event_investigation",
        "session_id": g["session_id"],
        "source_path": g["source_path"],
        "agents": [],
        "calls": rows,
        "messages": [],
        "artifacts": [],
        "inspection": {"state": "scanned_selected_streams"},
    }
    return g, index


def show(page, g, index):
    page.set_content(render_static_dashboard_html(g, investigation_index=index))
    page.get_by_role("button", name="Browse calls", exact=True).click()
    page.locator(".investigation-row").first.locator("summary").click()
    page.get_by_role("button", name="Runtime evidence for this invocation", exact=True).wait_for()


def test_actual_call_button_opens_exact_neighborhood_and_returns(browser_page):
    g, index = fixture()
    show(browser_page, g, index)
    browser_page.get_by_role(
        "button", name="Runtime evidence for this invocation", exact=True
    ).click()
    ids = browser_page.locator(".execweave-runtime-row").evaluate_all(
        "rows=>rows.map(r=>r.dataset.runtimeId)"
    )
    assert set(ids) == {"pa", "f", "net"}
    browser_page.keyboard.press("Escape")
    assert browser_page.locator("#execweave-investigation-dialog").is_visible()
    assert browser_page.locator(".investigation-row[open]").count() == 1
    assert browser_page.get_by_role(
        "button", name="Runtime evidence for this invocation", exact=True
    ).evaluate("n=>n===document.activeElement")
    assert browser_page.evaluate("window.__execweaveCore.getGraph()") == g


@pytest.mark.parametrize(
    "variant",
    [
        "missing",
        "name-only",
        "wrong-type",
        "duplicate",
        "owner-conflict",
        "resource-conflict",
        "inferred",
    ],
)
def test_missing_or_conflicting_call_never_falls_back_to_agent(browser_page, variant):
    g, index = fixture()
    row = index["calls"][0]
    if variant == "missing":
        row["native_id"] = "unknown"
    elif variant == "name-only":
        row["native_id"] = "A call"
    elif variant == "wrong-type":
        row["native_id"] = "a"
    elif variant == "duplicate":
        g["nodes"].append(copy.deepcopy(g["nodes"][2]))
    elif variant == "owner-conflict":
        row["owner_id"] = "b"
    elif variant == "resource-conflict":
        row["target_id"] = "other-tool"
    else:
        g["nodes"][2]["inferred"] = True
    show(browser_page, g, index)
    browser_page.get_by_role(
        "button", name="Runtime evidence for this invocation", exact=True
    ).click()
    assert not browser_page.locator("#execweave-runtime-dialog").count()
    assert (
        "not substituted" in browser_page.locator("#execweave-investigation-updates").inner_text()
    )


def test_same_process_cannot_bridge_to_another_invocation(browser_page):
    g, index = fixture()
    g["edges"].append(
        {
            "id": "shared-process",
            "source": "call-b",
            "target": "pa",
            "relation": "CORRELATED_WITH_PROCESS",
            "inferred": True,
        }
    )
    show(browser_page, g, index)
    browser_page.get_by_role(
        "button", name="Runtime evidence for this invocation", exact=True
    ).click()
    assert "pb" not in browser_page.locator(".execweave-runtime-row").evaluate_all(
        "rows=>rows.map(r=>r.dataset.runtimeId)"
    )


def test_stale_pinned_index_does_not_open_new_call_identity(browser_page):
    g, index = fixture()
    show(browser_page, g, index)
    changed = copy.deepcopy(index)
    changed["calls"][0]["native_id"] = "call-b"
    browser_page.evaluate("i=>window.__execweaveInvestigation.setIndex(i)", changed)
    browser_page.get_by_role(
        "button", name="Runtime evidence for this invocation", exact=True
    ).click()
    assert (
        "changed or is ambiguous"
        in browser_page.locator("#execweave-investigation-updates").inner_text()
    )
    assert not browser_page.locator("#execweave-runtime-dialog").count()


def test_model_invocation_uses_its_exact_model_call_node(browser_page):
    g, index = fixture()
    g["nodes"][2]["type"] = "model_call"
    g["nodes"][4]["type"] = "model"
    g["edges"][0]["relation"] = "REQUESTS_MODEL_CALL"
    g["edges"][2]["relation"] = "USED_MODEL"
    index["calls"][0]["kind"] = "model"
    show(browser_page, g, index)
    browser_page.get_by_role(
        "button", name="Runtime evidence for this invocation", exact=True
    ).click()
    assert browser_page.locator("#execweave-runtime-dialog").is_visible()
    assert "call-a" in browser_page.locator("#execweave-runtime-status").inner_text()


def test_no_runtime_path_is_disclosed_without_owner_fallback(browser_page):
    g, index = fixture()
    g["edges"] = [e for e in g["edges"] if e["id"] != "a-process"]
    show(browser_page, g, index)
    browser_page.get_by_role(
        "button", name="Runtime evidence for this invocation", exact=True
    ).click()
    assert browser_page.locator(".execweave-runtime-row").count() == 0
    assert (
        "does not prove no runtime activity"
        in browser_page.locator("#execweave-runtime-rows").inner_text()
    )


def test_protected_canvas_cannot_supply_a_retained_invocation(browser_page):
    from test_dashboard_camera_scheduler_e2e import _CORE_SEAM, _CORE_TEST_SEAM

    g, index = fixture()
    html = render_static_dashboard_html(g, investigation_index=index)
    browser_page.set_content(html.replace(_CORE_SEAM, _CORE_TEST_SEAM, 1))
    browser_page.evaluate(
        "window.__execweaveCore.setSnapshot({live_payload_compact:true,nodes:[],edges:[],node_count:100000,edge_count:200000})"
    )
    resolved = browser_page.evaluate(
        "r=>window.__execweaveRuntimeEvidence.invocationTarget(r)", index["calls"][0]
    )
    assert resolved == {"state": "partial", "id": None}
