from __future__ import annotations

import pytest

from execweave.dashboard_shell import render_static_dashboard_html
from test_viewer_agent_isolation_e2e import _browser, _launch

pytestmark = pytest.mark.viewer_e2e


def _production_edge(
    edge_id: str,
    source: str,
    target: str,
    relation: str,
    sequence: int,
    event_type: str,
    *,
    count: int = 1,
    backend: str = "semantic",
    attribution: str = "antigravity_hook",
    identity_exact: bool | None = None,
):
    timestamp = f"2026-09-09T06:50:{sequence:02d}.000000Z"
    payload = {
        "id": edge_id,
        "source": source,
        "target": target,
        "relation": relation,
        "count": count,
        "evidence_event_count": count,
        "first_seen": timestamp,
        "last_seen": timestamp,
        "first_sequence": sequence,
        "last_sequence": sequence,
        "event_ids": [f"event:{edge_id}:{index}" for index in range(count)],
        "event_types": [event_type],
        "backends": [backend],
        "attributions": [attribution],
        "causal": False,
        "inferred": False,
        "inference_methods": [],
        "identity_methods": [],
        "identity_hashes": [],
        "confidence_min": None,
        "confidence_max": None,
        "confidence_semantics": [],
        "supporting_event_ids": [],
    }
    if identity_exact is not None:
        payload["identity_exact"] = identity_exact
        if identity_exact:
            payload["identity_methods"] = ["validated_transcript_record_order_and_provider_ids"]
    return payload


def _agy_graph():
    root_id = "agent:antigravity:conversation:root-conversation"
    session_id = "provider-session:antigravity:root-conversation"
    model_id = "model:antigravity:gemini-3.8-flash-low"
    root = {
        "id": root_id,
        "type": "agent",
        "name": "/root",
        "attributes": {
            "provider": "antigravity",
            "agent_role": "root",
            "agent_path": "/root",
            "conversation_id": "root-conversation",
        },
    }
    session = {
        "id": session_id,
        "type": "provider_session",
        "name": "root-conversation",
        "attributes": {"provider": "antigravity"},
    }
    model = {
        "id": model_id,
        "type": "model",
        "name": "gemini-3.8-flash-low",
        "attributes": {"provider": "antigravity", "model_name": "gemini-3.8-flash-low"},
    }
    child_specs = [
        ("tech", "Tech Hype Judge"),
        ("strategy", "Strategic Analyst"),
        ("cosmic", "Cosmic Philosopher"),
    ]
    children = [
        {
            "id": f"agent:antigravity:conversation:{suffix}",
            "type": "agent",
            "name": name,
            "attributes": {
                "provider": "antigravity",
                "conversation_id": suffix,
                "agent_type": name,
                "agent_nickname": name,
                "agent_role": "subagent",
                "parent_scope_id": "root-conversation",
            },
        }
        for suffix, name in child_specs
    ]
    subtasks = [
        {
            "id": f"subtask:antigravity:root-conversation:7:{index}",
            "type": "subtask",
            "name": child["name"],
            "attributes": {
                "provider": "antigravity",
                "conversation_id": "root-conversation",
                "step_index": 7,
                "subagent_index": index,
                "role": child["name"],
            },
        }
        for index, child in enumerate(children)
    ]
    edges = [
        _production_edge(
            "session",
            root_id,
            session_id,
            "OBSERVED_PROVIDER_SESSION",
            1,
            "semantic.antigravity.session.observed",
        ),
        _production_edge(
            "model",
            session_id,
            model_id,
            "INVOKES_MODEL",
            2,
            "semantic.antigravity.model.invocation.requested",
        ),
    ]
    for index, (subtask, child) in enumerate(zip(subtasks, children, strict=True)):
        sequence = 10 + index * 3
        edges.extend(
            [
                _production_edge(
                    f"request-{index}",
                    root_id,
                    subtask["id"],
                    "REQUESTED_SUBTASK",
                    sequence,
                    "semantic.antigravity.subtask.requested",
                    identity_exact=True,
                ),
                _production_edge(
                    f"assign-{index}",
                    subtask["id"],
                    child["id"],
                    "ASSIGNED_AGENT_TASK",
                    sequence + 1,
                    "semantic.antigravity.subtask.assigned",
                    identity_exact=True,
                ),
                _production_edge(
                    f"child-session-{index}",
                    root_id,
                    child["id"],
                    "HAS_CHILD_AGENT_SESSION",
                    sequence + 2,
                    "semantic.antigravity.agent_session.child",
                    count=11,
                    identity_exact=True,
                ),
            ]
        )

    agy_process = {
        "id": "process:agy",
        "type": "process",
        "name": "agy.EXE ×3",
        "attributes": {"provider": "antigravity"},
    }
    conhost = {
        "id": "process:conhost",
        "type": "process",
        "name": "conhost.exe",
        "attributes": {},
    }
    node = {
        "id": "process:node",
        "type": "process",
        "name": "node.exe",
        "attributes": {},
    }
    external = {
        "id": "endpoint:external",
        "type": "network_endpoint",
        "name": "External",
        "attributes": {},
    }
    edges.extend(
        [
            _production_edge(
                "launch-agy",
                session_id,
                agy_process["id"],
                "LAUNCHED",
                40,
                "process.started",
                backend="portable",
                attribution="direct",
            ),
            _production_edge(
                "spawn-conhost",
                agy_process["id"],
                conhost["id"],
                "SPAWNED",
                41,
                "process.spawned",
                backend="portable",
                attribution="observed",
            ),
            _production_edge(
                "spawn-node",
                agy_process["id"],
                node["id"],
                "SPAWNED",
                42,
                "process.spawned",
                backend="portable",
                attribution="observed",
            ),
            _production_edge(
                "network",
                agy_process["id"],
                external["id"],
                "CONNECTED_TO",
                43,
                "network.connected",
                backend="portable",
                attribution="direct",
            ),
        ]
    )
    nodes = [root, session, model, *children, *subtasks, agy_process, conhost, node, external]
    return {
        "schema_version": "0.2",
        "session_id": "antigravity-real-shape",
        "nodes": nodes,
        "edges": edges,
        "node_count": len(nodes),
        "edge_count": len(edges),
    }, root_id, model_id, [child["id"] for child in children], [subtask["id"] for subtask in subtasks]


def _snapshot(page):
    display = page.evaluate("window.__execweaveCore.getDisplayGraph()")
    raw = page.evaluate("window.__execweaveCore.getGraph()")
    positions = page.evaluate(
        """() => Object.fromEntries([...document.querySelectorAll('.node')].map(g => {
            const m=(g.getAttribute('transform')||'').match(/translate\\(([-0-9.]+) ([-0-9.]+)\\)/);
            return [g.dataset.id, {x:m?Number(m[1]):0,y:m?Number(m[2]):0}];
        }))"""
    )
    metrics = page.evaluate("window.__execweavePr70.metrics()")
    return display, raw, positions, metrics


def _assert_closed_display_graph(display):
    visible_ids = {node["id"] for node in display["nodes"]}
    assert all(
        edge["source"] in visible_ids and edge["target"] in visible_ids
        for edge in display["edges"]
    )


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_real_antigravity_subtasks_flow_through_model_and_keep_hard_geometry_gates(theme):
    graph, root_id, raw_model_id, child_ids, subtask_ids = _agy_graph()
    manager, executable = _browser()
    with manager as playwright:
        browser = _launch(playwright, executable)
        try:
            page = browser.new_page(viewport={"width": 1800, "height": 1100})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
            page.set_content(render_static_dashboard_html(graph))
            page.wait_for_selector(".node")
            if page.locator("html").get_attribute("data-theme") != theme:
                page.locator("#theme-toggle").click()
            display, raw, positions, metrics = _snapshot(page)
            _assert_closed_display_graph(display)

            contexts = [
                node
                for node in display["nodes"]
                if node.get("attributes", {}).get("viewer_model_context")
            ]
            assert len(contexts) == 1
            assert contexts[0]["name"] == "gemini-3.8-flash-low"
            assert contexts[0]["attributes"]["model_resource_id"] == raw_model_id

            actions = [
                node
                for node in display["nodes"]
                if node.get("attributes", {}).get("viewer_orchestration_action")
                and node["name"] == "assign_agent_task"
            ]
            assert len(actions) == 1
            action = actions[0]
            assert action["attributes"]["viewer_occurrence_count"] == 3

            assert not any(node["id"] in set(subtask_ids) for node in display["nodes"])
            assert len([node for node in display["nodes"] if node["type"] == "agent"]) == 4
            assert not any(
                edge["relation"] in {"REQUESTED_SUBTASK", "ASSIGNED_AGENT_TASK", "HAS_CHILD_AGENT_SESSION"}
                and (
                    edge["source"] == root_id
                    or edge["target"] in set(child_ids)
                    or edge["source"] in set(subtask_ids)
                )
                for edge in display["edges"]
            )

            context = contexts[0]
            targets = {
                edge["target"]
                for edge in display["edges"]
                if edge["source"] == action["id"] and edge["relation"] == "TARGETED_AGENT"
            }
            assert targets == set(child_ids)
            assert any(
                edge["source"] == root_id
                and edge["target"] == context["id"]
                and edge["relation"] == "MODEL_CONTEXT"
                for edge in display["edges"]
            )
            assert any(
                edge["source"] == context["id"]
                and edge["target"] == action["id"]
                and edge["relation"] == "PERFORMED_ORCHESTRATION"
                for edge in display["edges"]
            )

            assert positions[root_id]["x"] < positions[context["id"]]["x"]
            assert positions[context["id"]]["x"] < positions[action["id"]]["x"]
            for child_id in child_ids:
                assert positions[action["id"]]["x"] < positions[child_id]["x"]

            assert metrics["NODE_OVERLAPS"] == 0
            assert metrics["EDGE_NODE_INTERSECTIONS"] == 0

            child_session = [
                edge for edge in raw["edges"] if edge["relation"] == "HAS_CHILD_AGENT_SESSION"
            ]
            assert len(child_session) == 3
            assert {edge["count"] for edge in child_session} == {11}

            page.locator("#arrange").click()
            arranged_display, _, arranged_positions, arranged_metrics = _snapshot(page)
            _assert_closed_display_graph(arranged_display)
            assert arranged_metrics["NODE_OVERLAPS"] == 0
            assert arranged_metrics["EDGE_NODE_INTERSECTIONS"] == 0
            assert arranged_positions[root_id]["x"] < arranged_positions[context["id"]]["x"]
            assert arranged_positions[context["id"]]["x"] < arranged_positions[action["id"]]["x"]
            for child_id in child_ids:
                assert arranged_positions[action["id"]]["x"] < arranged_positions[child_id]["x"]
            assert not errors, errors
        finally:
            browser.close()


def test_ambiguous_antigravity_assignment_chain_fails_closed():
    graph, _, _, child_ids, subtask_ids = _agy_graph()
    subtask_id = subtask_ids[0]
    extra_child = {
        "id": "agent:antigravity:conversation:ambiguous",
        "type": "agent",
        "name": "Ambiguous candidate",
        "attributes": {"provider": "antigravity", "conversation_id": "ambiguous"},
    }
    graph["nodes"].append(extra_child)
    graph["node_count"] += 1
    graph["edges"].append(
        _production_edge(
            "assign-ambiguous",
            subtask_id,
            extra_child["id"],
            "ASSIGNED_AGENT_TASK",
            30,
            "semantic.antigravity.subtask.assigned",
            identity_exact=True,
        )
    )
    graph["edge_count"] += 1

    manager, executable = _browser()
    with manager as playwright:
        browser = _launch(playwright, executable)
        try:
            page = browser.new_page(viewport={"width": 1800, "height": 1100})
            page.set_content(render_static_dashboard_html(graph))
            page.wait_for_selector(".node")
            display = page.evaluate("window.__execweaveCore.getDisplayGraph()")
        finally:
            browser.close()

    # The ambiguous subtask stays raw; no viewer-only assignment action may claim a child.
    assert subtask_id in {node["id"] for node in display["nodes"]}
    assert not any(
        node.get("attributes", {}).get("viewer_orchestration_action")
        and node["name"] == "assign_agent_task"
        and child_ids[0] in {
            edge["target"] for edge in display["edges"] if edge["source"] == node["id"]
        }
        for node in display["nodes"]
    )
