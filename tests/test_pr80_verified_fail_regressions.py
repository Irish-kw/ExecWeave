"""PR80 verified-fail counterexamples (issue #42): inferred promotion + shared model + gates."""
from __future__ import annotations

import copy

import pytest

from execweave.dashboard_shell import render_static_dashboard_html
from test_execution_flow_integrity import _agent, _edge, _model, _project
from test_viewer_agent_isolation_e2e import _browser, _launch

pytestmark = pytest.mark.viewer_e2e


def _observed_spawn_edge(eid: str, src: str, tgt: str, seq: int, *, inferred: bool) -> dict:
    return {
        **_edge(eid, src, tgt, "SPAWNED_SUBAGENT", seq),
        "inferred": inferred,
        "causal": False,
        "event_types": ["semantic.claude.spawned_subagent"],
        "backends": ["semantic"],
        "attributions": ["claude_hook"],
        "attributes": {
            "provider": "claude",
            "evidence_source": "provider_hook",
            "inferred": inferred,
        },
    }


def test_r1_inferred_spawn_is_not_promoted_to_observed_action():
    raw = {
        "schema_version": "1.0",
        "session_id": "r1-inferred",
        "nodes": [
            _agent(
                "agent:rootA",
                "/root",
                agent_role="root",
                viewer_root=True,
                provider="claude",
            ),
            _agent("agent:child", "child", agent_role="subagent", provider="claude"),
            _model("model:shared", "shared", provider="claude"),
        ],
        "edges": [
            {
                **_edge("m", "agent:rootA", "model:shared", "USED_MODEL", 1),
                "attributes": {"provider": "claude", "evidence_source": "provider_hook"},
            },
            _observed_spawn_edge("s", "agent:rootA", "agent:child", 2, inferred=True),
        ],
    }
    display = _project(raw)
    actions = [
        n
        for n in display["nodes"]
        if n.get("attributes", {}).get("viewer_orchestration_action")
    ]
    assert actions == [], actions
    assert any(
        e.get("id") == "s" and e.get("inferred") is True for e in display["edges"]
    ), display["edges"]
    assert not any(
        e.get("viewer_only")
        and e.get("inferred") is False
        and e.get("relation") in {"SPAWNED_AGENT", "TARGETED_AGENT", "PERFORMED_ORCHESTRATION"}
        for e in display["edges"]
    )


def test_r1_positive_observed_spawn_still_projects():
    raw = {
        "schema_version": "1.0",
        "session_id": "r1-observed",
        "nodes": [
            _agent(
                "agent:rootA",
                "/root",
                agent_role="root",
                viewer_root=True,
                provider="claude",
            ),
            _agent("agent:child", "child", agent_role="subagent", provider="claude"),
            _model("model:shared", "shared", provider="claude"),
        ],
        "edges": [
            {
                **_edge("m", "agent:rootA", "model:shared", "USED_MODEL", 1),
                "attributes": {"provider": "claude", "evidence_source": "provider_hook"},
            },
            _observed_spawn_edge("s", "agent:rootA", "agent:child", 2, inferred=False),
        ],
    }
    display = _project(raw)
    actions = [
        n
        for n in display["nodes"]
        if n.get("attributes", {}).get("viewer_orchestration_action")
        and n.get("name") == "spawn_agent"
    ]
    assert len(actions) == 1
    assert not any(e.get("id") == "s" for e in display["edges"])


def test_r2_unrelated_owner_keeps_shared_model_usage():
    raw = {
        "schema_version": "1.0",
        "session_id": "r2-shared-model",
        "nodes": [
            _agent(
                "agent:rootA",
                "/root",
                agent_role="root",
                viewer_root=True,
                provider="claude",
            ),
            _agent("agent:rootB", "rootB", agent_role="root", provider="claude"),
            _agent("agent:child", "child", agent_role="subagent", provider="claude"),
            _model("model:shared", "shared", provider="claude"),
        ],
        "edges": [
            _edge("ma", "agent:rootA", "model:shared", "USED_MODEL", 1),
            _edge("mb", "agent:rootB", "model:shared", "USED_MODEL", 1),
            _observed_spawn_edge("s", "agent:rootA", "agent:child", 2, inferred=False),
        ],
    }
    display = _project(raw)
    visible = {n["id"] for n in display["nodes"]}
    assert "model:shared" in visible
    assert any(
        e["source"] == "agent:rootB" and e["target"] == "model:shared"
        for e in display["edges"]
    )
    assert any(
        n.get("attributes", {}).get("viewer_model_context")
        and n.get("attributes", {}).get("owner_agent_id") == "agent:rootA"
        for n in display["nodes"]
    )


def test_r2_shared_tool_survives_when_other_owner_has_direct_use():
    raw = {
        "schema_version": "1.0",
        "session_id": "r2-shared-tool",
        "nodes": [
            _agent(
                "agent:rootA",
                "/root",
                agent_role="root",
                viewer_root=True,
                provider="claude",
            ),
            _agent("agent:rootB", "rootB", agent_role="root", provider="claude"),
            _agent("agent:child", "child", agent_role="subagent", provider="claude"),
            {
                "id": "tool:shared",
                "type": "tool",
                "name": "run",
                "attributes": {"provider": "claude", "native_name": "run"},
            },
            {
                "id": "tool-call:a",
                "type": "tool_call",
                "name": "spawn_agent",
                "attributes": {"provider": "claude", "tool_name": "spawn_agent"},
            },
        ],
        "edges": [
            _edge("req", "agent:rootA", "tool-call:a", "REQUESTED_TOOL_CALL", 1),
            _edge("uses-call", "tool-call:a", "tool:shared", "USES_TOOL", 2),
            _observed_spawn_edge("s", "agent:rootA", "agent:child", 3, inferred=False),
            _edge("direct", "agent:rootB", "tool:shared", "USES_TOOL", 4),
        ],
    }
    display = _project(raw)
    assert "tool:shared" in {n["id"] for n in display["nodes"]}
    assert any(
        e["source"] == "agent:rootB" and e["target"] == "tool:shared"
        for e in display["edges"]
    )


def test_mutation_deleting_child_must_fail_positive_control():
    raw = {
        "schema_version": "1.0",
        "session_id": "mutation-child",
        "nodes": [
            _agent(
                "agent:rootA",
                "/root",
                agent_role="root",
                viewer_root=True,
                provider="claude",
            ),
            _model("model:shared", "shared", provider="claude"),
        ],
        "edges": [
            _edge("m", "agent:rootA", "model:shared", "USED_MODEL", 1),
            _observed_spawn_edge("s", "agent:rootA", "agent:missing", 2, inferred=False),
        ],
    }
    display = _project(raw)
    actions = [
        n
        for n in display["nodes"]
        if n.get("attributes", {}).get("viewer_orchestration_action")
        and n.get("name") == "spawn_agent"
        and n.get("attributes", {}).get("evidence_node_ids")
    ]
    # No real child agent => no successful targeted spawn_agent group.
    targeted = [
        a
        for a in actions
        if any(
            e["source"] == a["id"] and e["relation"] == "SPAWNED_AGENT"
            for e in display["edges"]
        )
    ]
    assert targeted == []


def test_r1_r2_chromium_initial_and_arrange_geometry():
    raw = {
        "schema_version": "1.0",
        "session_id": "r1r2-browser",
        "nodes": [
            _agent(
                "agent:rootA",
                "/root",
                agent_role="root",
                viewer_root=True,
                provider="claude",
            ),
            _agent("agent:rootB", "rootB", agent_role="root", provider="claude"),
            _agent("agent:child", "child", agent_role="subagent", provider="claude"),
            _model("model:shared", "shared", provider="claude"),
        ],
        "edges": [
            _edge("ma", "agent:rootA", "model:shared", "USED_MODEL", 1),
            _edge("mb", "agent:rootB", "model:shared", "USED_MODEL", 1),
            _observed_spawn_edge("s-inf", "agent:rootA", "agent:child", 2, inferred=True),
        ],
    }
    manager, executable = _browser()
    with manager as playwright:
        browser = _launch(playwright, executable)
        try:
            page = browser.new_page(viewport={"width": 1600, "height": 1000})
            errors: list[str] = []
            page.on("pageerror", lambda err: errors.append(str(err)))
            page.set_content(render_static_dashboard_html(copy.deepcopy(raw)))
            page.wait_for_selector("svg", timeout=15000)
            assert page.evaluate(
                "!!(window.__execweavePr70 && typeof window.__execweavePr70.metrics==='function')"
            )
            for _ in range(2):
                display = page.evaluate("window.__execweaveCore.getDisplayGraph()")
                metrics = page.evaluate("window.__execweavePr70.metrics()")
                assert isinstance(metrics.get("NODE_OVERLAPS"), (int, float))
                assert isinstance(metrics.get("EDGE_NODE_INTERSECTIONS"), (int, float))
                assert metrics["NODE_OVERLAPS"] == 0
                assert metrics["EDGE_NODE_INTERSECTIONS"] == 0
                visible = {n["id"] for n in display["nodes"]}
                for edge in display["edges"]:
                    assert edge["source"] in visible
                    assert edge["target"] in visible
                assert "model:shared" in visible
                assert any(
                    e["source"] == "agent:rootB" and e["target"] == "model:shared"
                    for e in display["edges"]
                )
                assert not any(
                    n.get("attributes", {}).get("viewer_orchestration_action")
                    for n in display["nodes"]
                )
                assert any(
                    e.get("inferred") is True and e.get("relation") == "SPAWNED_SUBAGENT"
                    for e in display["edges"]
                )
                page.locator("#arrange").click()
            assert not errors, errors
        finally:
            browser.close()
