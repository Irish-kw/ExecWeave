"""Default role navigation must not alter graph, ownership, or camera geometry."""

from __future__ import annotations

import copy

import pytest

from execweave.dashboard_shell import render_static_dashboard_html
from execweave.viewer_run_guide import inject_run_guide
from test_investigation_workspace import browser_page
from test_runtime_evidence_browser import graph

__all__ = ["browser_page"]
pytestmark = pytest.mark.viewer_e2e


def show(page, g=None):
    g = graph() if g is None else g
    page.set_content(render_static_dashboard_html(g))
    return g


def test_default_guide_retains_full_graph_and_not_response_content(browser_page):
    g = show(browser_page)
    assert browser_page.locator("#execweave-run-guide").evaluate("n=>n.open")
    assert browser_page.locator("#execweave-run-guide-roles button").count() == 2
    assert browser_page.evaluate("window.__execweaveWorkflow.status().mode") == "all"
    assert "pa" in browser_page.evaluate(
        "window.__execweaveCore.getDisplayGraph().nodes.map(n=>n.id)"
    )
    assert not browser_page.locator("#details #execweave-run-guide").count()
    assert browser_page.evaluate("window.__execweaveCore.getGraph()") == g


def test_same_names_select_exact_agent_without_taking_camera(browser_page):
    g = show(browser_page)
    browser_page.locator("#zoom-in").click()
    browser_page.wait_for_timeout(300)
    before = browser_page.locator("#viewport").get_attribute("transform")
    browser_page.locator('#execweave-run-guide-roles button[data-agent-id="b"]').click()
    assert browser_page.locator("#nodes .node.selected").get_attribute("data-id") == "b"
    assert browser_page.locator("#viewport").get_attribute("transform") == before
    assert browser_page.evaluate("window.__execweaveCore.getGraph()") == g


def test_guide_filters_then_limits_large_role_list(browser_page):
    g = graph()
    g["nodes"] += [{"id": f"role-{i}", "type": "agent", "name": f"Unique {i}"} for i in range(60)]
    show(browser_page, g)
    assert browser_page.locator("#execweave-run-guide-roles button").count() == 6
    browser_page.get_by_label("Find role in run guide").fill("Unique")
    assert browser_page.locator("#execweave-run-guide-roles button").count() == 25
    browser_page.get_by_label("Find role in run guide").fill("role-59")
    assert browser_page.locator("#execweave-run-guide-roles button").count() == 1


@pytest.mark.parametrize("variant", ["duplicate-agent", "type-conflict", "malformed"])
def test_ambiguous_role_ids_are_withheld_not_resolved_by_name(browser_page, variant):
    g = graph()
    if variant == "duplicate-agent":
        g["nodes"].append(copy.deepcopy(g["nodes"][0]))
    elif variant == "type-conflict":
        g["nodes"].append({"id": "a", "type": "process", "name": "Same name"})
    else:
        g["nodes"].append({"id": None, "type": "agent"})
    show(browser_page, g)
    if variant != "malformed":
        assert not browser_page.locator('#execweave-run-guide-roles [data-agent-id="a"]').count()
    assert "Partial" in browser_page.locator("#execweave-run-guide-status").inner_text()


def test_updates_pin_role_buttons_and_preserve_typed_search(browser_page):
    show(browser_page)
    browser_page.get_by_label("Find role in run guide").fill("Same")
    browser_page.evaluate(
        "()=>{window.__execweaveCore.getGraph().nodes.push({id:'new-role',type:'agent',name:'Same new'});window.__execweaveDashboard.onPayload({})}"
    )
    assert browser_page.locator("#execweave-run-guide-roles button").count() == 2
    assert (
        "Updated roles are available"
        in browser_page.locator("#execweave-run-guide-status").inner_text()
    )
    browser_page.get_by_role("button", name="Refresh role list", exact=True).click()
    assert browser_page.locator("#execweave-run-guide-roles button").count() == 3
    assert browser_page.get_by_label("Find role in run guide").input_value() == "Same"


def test_removed_role_does_not_select_a_same_named_peer(browser_page):
    show(browser_page)
    browser_page.evaluate(
        "window.__execweaveCore.getGraph().nodes=window.__execweaveCore.getGraph().nodes.filter(n=>n.id!=='a')"
    )
    browser_page.locator('#execweave-run-guide-roles [data-agent-id="a"]').click()
    assert "no longer unique" in browser_page.locator("#execweave-run-guide-status").inner_text()
    assert browser_page.locator("#nodes .node.selected").count() == 0


@pytest.mark.parametrize(
    "label,tab",
    [
        ("All roles", "agents"),
        ("Browse calls", "calls"),
        ("Browse handoffs", "messages"),
        ("Browse artifacts", "artifacts"),
    ],
)
def test_default_actions_choose_the_requested_investigation_tab(browser_page, label, tab):
    show(browser_page)
    browser_page.get_by_role("button", name=label, exact=True).click()
    assert (
        browser_page.locator(f'#execweave-investigation-dialog [data-tab="{tab}"]').get_attribute(
            "aria-pressed"
        )
        == "true"
    )


def test_execution_change_clears_search_and_old_role_inventory(browser_page):
    show(browser_page)
    browser_page.get_by_label("Find role in run guide").fill("a")
    browser_page.evaluate(
        "()=>{window.__execweaveCore.getGraph().session_id='new';window.__execweaveCore.getGraph().nodes=[];window.__execweaveDashboard.onPayload({})}"
    )
    assert browser_page.get_by_label("Find role in run guide").input_value() == ""
    assert not browser_page.locator("#execweave-run-guide-roles button").count()


def test_role_labels_are_text_not_executable_markup(browser_page):
    g = graph()
    g["nodes"][0]["name"] = '<img src=x onerror="window.injected=true">'
    show(browser_page, g)
    assert browser_page.locator("#execweave-run-guide img").count() == 0
    assert browser_page.evaluate("window.injected===undefined")


def test_guide_injection_is_additive_and_idempotent():
    html = render_static_dashboard_html(graph())
    assert html.count('id="execweave-run-guide-script"') == 1
    assert inject_run_guide(html) == html
    with pytest.raises(RuntimeError):
        inject_run_guide("no body")


def test_actual_compact_transition_does_not_reuse_retained_role_snapshot(browser_page):
    from test_dashboard_camera_scheduler_e2e import _CORE_SEAM, _CORE_TEST_SEAM

    html = render_static_dashboard_html(graph())
    assert _CORE_SEAM in html
    browser_page.set_content(html.replace(_CORE_SEAM, _CORE_TEST_SEAM, 1))
    assert browser_page.locator("#execweave-run-guide-roles button").count() == 2
    browser_page.evaluate("""()=>{
      const compact={session_id:'other',live_payload_compact:true,node_count:100000,edge_count:100000,nodes:[],edges:[]};
      window.__execweaveCore.setSnapshot(compact);window.__execweaveDashboard.onPayload({graph:compact});
    }""")
    assert browser_page.locator("#protective").is_visible()
    assert not browser_page.locator("#execweave-run-guide-roles button").count()
    assert browser_page.get_by_label("Find role in run guide").is_disabled()
    assert browser_page.get_by_role("button", name="Browse calls", exact=True).is_disabled()
    browser_page.evaluate(
        "g=>{window.__execweaveCore.setSnapshot(g);window.__execweaveDashboard.onPayload({graph:g})}",
        graph(),
    )
    assert browser_page.locator("#execweave-run-guide-roles button").count() == 2
    assert browser_page.get_by_label("Find role in run guide").is_enabled()
