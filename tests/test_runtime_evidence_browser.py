"""Real Chromium interactions over labeled synthetic graph evidence."""
from __future__ import annotations

import copy

import pytest

from execweave.dashboard_shell import render_static_dashboard_html
from test_investigation_workspace import browser_page

__all__ = ["browser_page"]
pytestmark = pytest.mark.viewer_e2e


def graph():
    nodes = [
        {"id": "a", "type": "agent", "name": "Same name", "attributes": {"agent_role": "root"}},
        {"id": "b", "type": "agent", "name": "Same name"},
        {"id": "call-a", "type": "tool_call", "name": "A call"},
        {"id": "call-b", "type": "tool_call", "name": "B call"},
        {"id": "shared-tool", "type": "tool", "name": "Shared shell"},
        {"id": "pa", "type": "process", "name": "Producer process", "attributes": {"pid": 12}},
        {"id": "pb", "type": "process", "name": "Reviewer process", "attributes": {"pid": 13}},
        {"id": "f", "type": "file", "name": "Historical file", "attributes": {"path": "/recorded/result.txt"}},
        {"id": "net", "type": "network_endpoint", "name": "Remote service", "attributes": {"host": "example.invalid", "port": 443}},
        {"id": "orphan", "type": "process", "name": "Unlinked process"},
    ]
    edges = [
        {"id": "a-call", "source": "a", "target": "call-a", "relation": "REQUESTED_TOOL_CALL"},
        {"id": "b-call", "source": "b", "target": "call-b", "relation": "REQUESTED_TOOL_CALL"},
        {"id": "a-tool", "source": "call-a", "target": "shared-tool", "relation": "USES_TOOL"},
        {"id": "b-tool", "source": "call-b", "target": "shared-tool", "relation": "USES_TOOL"},
        {"id": "a-process", "source": "call-a", "target": "pa", "relation": "CORRELATED_WITH_PROCESS", "inferred": True, "causal": False},
        {"id": "b-process", "source": "call-b", "target": "pb", "relation": "CORRELATED_WITH_PROCESS", "inferred": True},
        {"id": "file-read", "source": "pa", "target": "f", "relation": "READ", "causal": True, "first_seen": "2026-01-01T00:00:01Z"},
        {"id": "connect", "source": "pa", "target": "net", "relation": "CONNECTED_TO", "causal": True},
    ]
    return {"session_id": "runtime-navigation", "source_path": "/run/events.jsonl", "nodes": nodes, "edges": edges}


def load(page, data=None):
    data = data or graph()
    page.set_content(render_static_dashboard_html(data))
    return data


def index(page, data, anchors=None):
    return page.evaluate("([g,ids])=>window.__execweaveRuntimeEvidence.buildIndex(g,ids)", [data, anchors or []])


def test_navigation_keeps_correlation_and_does_not_cross_shared_tool(browser_page):
    g = load(browser_page)
    result = index(browser_page, g, ["a"])
    reached = {r["id"]: r for r in result["rows"] if r["path"] is not None}
    assert set(reached) == {"pa", "f", "net"}
    assert reached["f"]["path"][1]["inferred"] is True
    assert reached["f"]["path"][1]["causal"] is False
    assert reached["f"]["path"][-1]["id"] == "file-read"
    assert {r["id"] for r in result["rows"]} >= {"pb", "orphan"}
    assert browser_page.evaluate("window.__execweaveCore.getGraph()") == g


def test_selected_shared_tool_exposes_separate_recorded_call_paths(browser_page):
    g = load(browser_page)
    result = index(browser_page, g, ["shared-tool"])
    assert {r["id"] for r in result["rows"] if r["path"] is not None} == {"pa", "pb", "f", "net"}
    for row in result["rows"]:
        if row["id"] == "pa":
            assert row["path"][0]["source"] == "call-a"
        if row["id"] == "pb":
            assert row["path"][0]["source"] == "call-b"


def test_process_parent_and_file_do_not_bridge_other_owners(browser_page):
    g = graph()
    g["nodes"].append({"id": "parent", "type": "process"})
    g["edges"] += [
        {"id": "parent-a", "source": "parent", "target": "pa", "relation": "SPAWNED"},
        {"id": "parent-b", "source": "parent", "target": "pb", "relation": "SPAWNED"},
        {"id": "shared-file", "source": "pb", "target": "f", "relation": "READ"},
    ]
    load(browser_page, g)
    reached = {r["id"] for r in index(browser_page, g, ["a"])["rows"] if r["path"] is not None}
    assert reached == {"pa", "f", "net"}


def test_ambiguous_node_identity_is_not_last_writer_wins(browser_page):
    g = graph()
    g["nodes"].append({"id": "pa", "type": "process", "name": "conflicting process"})
    load(browser_page, g)
    result = index(browser_page, g, ["a"])
    assert result["ambiguous_ids"] == 1 and result["partial"]
    assert "pa" not in {r["id"] for r in result["rows"]}
    assert not any(r["path"] is not None for r in result["rows"])


def test_ambiguous_edge_identity_is_withheld(browser_page):
    g = graph()
    g["edges"].append({**g["edges"][4], "target": "pb"})
    load(browser_page, g)
    result = index(browser_page, g, ["a"])
    assert result["ambiguous_edge_ids"] == 1 and result["partial"]
    assert not any(r["path"] is not None for r in result["rows"])


def test_exact_node_and_edge_replay_do_not_multiply_inventory(browser_page):
    g = graph()
    g["nodes"].extend(copy.deepcopy(g["nodes"]))
    g["edges"].extend(copy.deepcopy(g["edges"]))
    load(browser_page)
    result = index(browser_page, g)
    assert len(result["rows"]) == 5
    assert not result["partial"]
    assert next(r for r in result["rows"] if r["id"] == "pa")["relation_count"] == 3


def test_expansion_and_unlinked_records_remain_discoverable(browser_page):
    g = graph()
    g["expansion"] = {"clusters": {"one": {"nodes": [{"id": "expanded", "type": "file"}], "edges": []}}}
    load(browser_page, g)
    result = index(browser_page, g)
    assert {r["id"] for r in result["rows"]} >= {"orphan", "expanded"}
    browser_page.get_by_role("button", name="Runtime evidence", exact=True).click()
    browser_page.get_by_label("Search runtime evidence", exact=True).fill("Unlinked")
    browser_page.get_by_role("button", name="Search runtime", exact=True).click()
    assert browser_page.locator(".execweave-runtime-row").count() == 1
    browser_page.locator(".execweave-runtime-row summary").click()
    browser_page.wait_for_function("document.querySelector('#execweave-runtime-rows').innerText.includes('No direct agent/call edge')")


def test_node_and_edge_view_only_records_are_not_runtime_evidence(browser_page):
    g = graph()
    g["nodes"].append({"id": "display-only", "type": "process", "viewer_only": True})
    g["edges"][4]["viewer_only"] = True
    load(browser_page, g)
    result = index(browser_page, g, ["a"])
    assert "display-only" not in {r["id"] for r in result["rows"]}
    assert not any(r["path"] is not None for r in result["rows"])


def test_output_budget_and_navigation_boundary_are_visible(browser_page):
    load(browser_page)
    g = {"session_id": "large", "nodes": [{"id": f"p{i}", "type": "process"} for i in range(10005)], "edges": []}
    result = index(browser_page, g)
    assert len(result["rows"]) == 10000 and result["omitted"] == 5 and result["partial"]


def test_one_step_selection_action_keeps_exact_agent_isolation(browser_page):
    load(browser_page)
    browser_page.evaluate("window.__execweaveCore.selectNode('a')")
    browser_page.get_by_role("button", name="Runtime evidence for selection", exact=True).click()
    rows = browser_page.locator(".execweave-runtime-row")
    assert set(rows.evaluate_all("nodes=>nodes.map(n=>n.dataset.runtimeId)")) == {"pa", "f", "net"}
    rows.filter(has_text="Producer process").locator("summary").click()
    browser_page.wait_for_function("document.querySelector('#execweave-runtime-rows').innerText.includes('INFERRED / CORRELATED')")
    browser_page.get_by_role("button", name="Show all runtime evidence", exact=True).click()
    assert browser_page.locator('.execweave-runtime-row[data-runtime-id="orphan"]').count() == 1


def test_updates_pin_rows_and_run_changes_clear_them(browser_page):
    load(browser_page)
    browser_page.get_by_role("button", name="Runtime evidence", exact=True).click()
    row = browser_page.locator('.execweave-runtime-row[data-runtime-id="pa"]')
    row.locator("summary").click()
    browser_page.evaluate("()=>{window.__execweaveCore.getGraph().nodes.push({id:'new',type:'process'});window.__execweaveDashboard.onPayload({})}")
    assert browser_page.locator('.execweave-runtime-row[data-runtime-id="new"]').count() == 0
    assert row.evaluate("n=>n.open")
    assert "pinned" in browser_page.locator("#execweave-runtime-updates").inner_text()
    browser_page.get_by_role("button", name="Refresh runtime snapshot", exact=True).click()
    assert browser_page.locator('.execweave-runtime-row[data-runtime-id="new"]').count() == 1
    assert browser_page.locator('.execweave-runtime-row[data-runtime-id="pa"]').evaluate("n=>n.open")
    browser_page.evaluate("()=>{window.__execweaveCore.getGraph().session_id='other';window.__execweaveDashboard.onPayload({})}")
    assert not browser_page.locator("#execweave-runtime-dialog").is_visible()
    assert browser_page.locator(".execweave-runtime-row").count() == 0


def test_pagination_is_bounded_and_escape_restores_focus(browser_page):
    g = graph()
    g["nodes"] += [{"id": f"extra{i}", "type": "process"} for i in range(60)]
    load(browser_page, g)
    browser_page.get_by_role("button", name="Runtime evidence", exact=True).click()
    assert browser_page.locator(".execweave-runtime-row").count() == 25
    browser_page.get_by_role("button", name="Next runtime records", exact=True).click()
    assert browser_page.locator(".execweave-runtime-row").count() == 25
    assert "Page 2/3" in browser_page.locator("#execweave-runtime-status").inner_text()
    browser_page.keyboard.press("Escape")
    assert browser_page.locator("#execweave-runtime-launcher").evaluate("n=>n===document.activeElement")


def test_hostile_labels_are_plain_text_and_never_navigated(browser_page):
    g = graph()
    g["nodes"][5]["name"] = '<img src="https://example.invalid/exfil" onerror="window.exfil=true">'
    load(browser_page, g)
    requests = []
    browser_page.on("request", lambda request: requests.append(request.url))
    browser_page.get_by_role("button", name="Runtime evidence", exact=True).click()
    browser_page.locator('.execweave-runtime-row[data-runtime-id="pa"] summary').click()
    assert browser_page.locator("#execweave-runtime-dialog img, #execweave-runtime-dialog a").count() == 0
    assert browser_page.evaluate("window.exfil===undefined")
    assert not requests


def test_missing_anchor_is_not_replaced_with_same_named_agent(browser_page):
    load(browser_page)
    browser_page.evaluate("window.__execweaveRuntimeEvidence.open('missing-agent')")
    assert browser_page.locator(".execweave-runtime-row").count() == 0
    assert "missing or ambiguous" in browser_page.locator("#execweave-runtime-status").inner_text()


def test_conflicting_causal_metadata_does_not_promote_relationship(browser_page):
    g = graph()
    g["edges"][0]["causal"] = True
    g["edges"][0]["attributes"] = {"causal": False}
    load(browser_page, g)
    result = index(browser_page, g, ["a"])
    row = next(r for r in result["rows"] if r["id"] == "pa")
    assert row["path"][0]["causal"] is False


def test_missing_edge_endpoint_is_visible_as_partial_inventory(browser_page):
    g = graph()
    g["edges"].append({"id": "unresolved", "source": "missing", "target": "pa", "relation": "SPAWNED"})
    load(browser_page, g)
    result = index(browser_page, g)
    assert result["dangling_edges"] == 1 and result["partial"]
    browser_page.get_by_role("button", name="Runtime evidence", exact=True).click()
    assert "1 unresolved edges" in browser_page.locator("#execweave-runtime-status").inner_text()
