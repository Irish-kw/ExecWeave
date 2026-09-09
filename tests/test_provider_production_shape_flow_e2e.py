from __future__ import annotations

import pytest

from execweave.dashboard_shell import render_static_dashboard_html
from test_provider_execution_flow_e2e import PROVIDERS
from test_viewer_agent_isolation_e2e import _browser, _launch

pytestmark = pytest.mark.viewer_e2e

AGENT_PROVIDERS = {"claude", "codex", "antigravity", "cursor", "opencode"}
ROOT_ONLY_MODEL_PROVIDERS = {
    "ollama",
    "llamacpp",
    "vllm",
    "lmstudio",
    "anthropic",
    "openrouter",
    "litellm",
    "openai-compatible",
}


def _edge(
    edge_id: str,
    source: str,
    target: str,
    relation: str,
    sequence: int,
    provider: str,
    *,
    identity_exact: bool | None = None,
    event_type: str | None = None,
) -> dict[str, object]:
    timestamp = f"2026-09-09T07:00:{sequence:02d}.000000Z"
    payload: dict[str, object] = {
        "id": edge_id,
        "source": source,
        "target": target,
        "relation": relation,
        "count": 1,
        "evidence_event_count": 1,
        "first_seen": timestamp,
        "last_seen": timestamp,
        "first_sequence": sequence,
        "last_sequence": sequence,
        "event_ids": [f"event:{edge_id}"],
        "event_types": [event_type or f"semantic.{provider}.{relation.lower()}"],
        "backends": ["semantic"],
        "attributions": [f"{provider}_integration"],
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
            payload["identity_methods"] = [f"{provider}_provider_exact_identity"]
    return payload


def _observed_content(node_id: str, content_kind: str) -> dict[str, object]:
    return {
        "id": node_id,
        "type": "observed_content",
        "name": content_kind,
        "attributes": {
            "content_kind": content_kind,
            "media_type": "text/plain; charset=utf-8",
            "representation": "raw_utf8",
            "complete_from_source": True,
        },
    }


def _positions(page) -> dict[str, dict[str, float]]:
    return page.evaluate(
        """() => Object.fromEntries([...document.querySelectorAll('.node')].map(g => {
            const m=(g.getAttribute('transform')||'').match(/translate\\(([-0-9.]+) ([-0-9.]+)\\)/);
            return [g.dataset.id, {x:m?Number(m[1]):0,y:m?Number(m[2]):0}];
        }))"""
    )


def _snapshot(page):
    return (
        page.evaluate("window.__execweaveCore.getDisplayGraph()"),
        page.evaluate("window.__execweaveCore.getGraph()"),
        _positions(page),
        page.evaluate("window.__execweavePr70.metrics()"),
    )


def _assert_hard_geometry(metrics: dict[str, object]) -> None:
    assert metrics["NODE_OVERLAPS"] == 0
    assert metrics["EDGE_NODE_INTERSECTIONS"] == 0


def _assert_closed_display_graph(display: dict[str, object]) -> None:
    visible_ids = {node["id"] for node in display["nodes"]}
    assert all(
        edge["source"] in visible_ids and edge["target"] in visible_ids
        for edge in display["edges"]
    )


def test_provider_shape_matrix_covers_every_supported_dashboard_provider() -> None:
    assert AGENT_PROVIDERS | ROOT_ONLY_MODEL_PROVIDERS == set(PROVIDERS)
    assert not (AGENT_PROVIDERS & ROOT_ONLY_MODEL_PROVIDERS)


def test_cursor_dual_spawn_and_subtask_evidence_becomes_one_model_spawn_child_flow() -> None:
    provider = "cursor"
    root_id = "agent:Cursor"
    child_id = "agent:cursor:subagent:child-1"
    model_id = "model:cursor:cursor-model"
    subtask_id = "subtask:cursor:session-1:subagent:child-1"
    prompt_id = "observed-content:cursor-prompt"
    description_id = "observed-content:cursor-description"
    graph = {
        "schema_version": "0.2",
        "session_id": "cursor-production-exact-delegation",
        "nodes": [
            {
                "id": root_id,
                "type": "agent",
                "name": "/root",
                "attributes": {
                    "provider": provider,
                    "agent_role": "root",
                    "agent_path": "/root",
                },
            },
            {
                "id": child_id,
                "type": "agent",
                "name": "Cursor subagent child-1",
                "attributes": {
                    "provider": provider,
                    "subagent_id": "child-1",
                    "parent_agent_path": "/root",
                },
            },
            {
                "id": model_id,
                "type": "model",
                "name": "cursor-model",
                "attributes": {"provider": provider, "model_name": "cursor-model"},
            },
            {
                "id": subtask_id,
                "type": "subtask",
                "name": "Inspect parser",
                "attributes": {
                    "provider": provider,
                    "subagent_id": "child-1",
                    "exact_child_agent_linkage": True,
                },
            },
            _observed_content(prompt_id, "cursor.subtask_prompt"),
            _observed_content(description_id, "cursor.subtask_description"),
        ],
        "edges": [
            _edge("model", root_id, model_id, "USED_MODEL", 1, provider),
            _edge(
                "spawn",
                root_id,
                child_id,
                "SPAWNED_SUBAGENT",
                2,
                provider,
                identity_exact=True,
                event_type="semantic.cursor.subagent.started",
            ),
            _edge(
                "request",
                root_id,
                subtask_id,
                "REQUESTED_SUBTASK",
                3,
                provider,
                identity_exact=True,
            ),
            _edge(
                "assign",
                subtask_id,
                child_id,
                "ASSIGNED_AGENT_TASK",
                4,
                provider,
                identity_exact=True,
            ),
            _edge(
                "prompt",
                subtask_id,
                prompt_id,
                "HAS_SUBTASK_PROMPT",
                5,
                provider,
            ),
            _edge(
                "description",
                subtask_id,
                description_id,
                "HAS_SUBTASK_DESCRIPTION",
                6,
                provider,
            ),
        ],
    }
    graph["node_count"] = len(graph["nodes"])
    graph["edge_count"] = len(graph["edges"])

    manager, executable = _browser()
    with manager as playwright:
        browser = _launch(playwright, executable)
        try:
            page = browser.new_page(viewport={"width": 1800, "height": 1000})
            errors: list[str] = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.set_content(render_static_dashboard_html(graph))
            page.wait_for_selector(".node")
            display, raw, positions, metrics = _snapshot(page)
            _assert_hard_geometry(metrics)
            _assert_closed_display_graph(display)
            page.locator("#arrange").click()
            arranged_display, _, _, arranged_metrics = _snapshot(page)
            _assert_hard_geometry(arranged_metrics)
            _assert_closed_display_graph(arranged_display)
            assert not errors, errors
        finally:
            browser.close()

    contexts = [
        node for node in display["nodes"]
        if node.get("attributes", {}).get("viewer_model_context")
    ]
    actions = [
        node for node in display["nodes"]
        if node.get("attributes", {}).get("viewer_orchestration_action")
    ]
    assert len(contexts) == 1 and contexts[0]["name"] == "cursor-model"
    assert len(actions) == 1 and actions[0]["name"] == "spawn_agent"
    action = actions[0]
    assert subtask_id in action["attributes"]["evidence_node_ids"]
    assert {"spawn", "request", "assign"} <= set(action["attributes"]["evidence_edge_ids"])
    assert [node["id"] for node in display["nodes"] if node["type"] == "agent"].count(child_id) == 1
    visible_ids = {node["id"] for node in display["nodes"]}
    assert subtask_id not in visible_ids
    assert {prompt_id, description_id} <= visible_ids
    assert any(edge["relation"] == "SPAWNED_SUBAGENT" for edge in raw["edges"])
    assert any(edge["relation"] == "ASSIGNED_AGENT_TASK" for edge in raw["edges"])
    assert any(
        edge["source"] == action["id"]
        and edge["target"] == child_id
        and edge["relation"] == "SPAWNED_AGENT"
        for edge in display["edges"]
    )
    assert any(
        edge["source"] == action["id"]
        and edge["target"] == prompt_id
        and edge["relation"] == "HAS_SUBTASK_PROMPT"
        for edge in display["edges"]
    )
    assert any(
        edge["source"] == action["id"]
        and edge["target"] == description_id
        and edge["relation"] == "HAS_SUBTASK_DESCRIPTION"
        for edge in display["edges"]
    )
    assert positions[root_id]["x"] < positions[contexts[0]["id"]]["x"]
    assert positions[contexts[0]["id"]]["x"] < positions[action["id"]]["x"]
    assert positions[action["id"]]["x"] < positions[child_id]["x"]


def test_opencode_exact_task_session_assignment_projects_without_duplicate_task_tool() -> None:
    provider = "opencode"
    root_id = "agent:opencode:session:parent"
    child_id = "agent:opencode:session:child"
    model_id = "model:opencode:model-a"
    call_id = "tool-call:opencode:parent:call-task"
    tool_id = "tool:opencode:task"
    graph = {
        "schema_version": "0.2",
        "session_id": "opencode-production-task-session",
        "nodes": [
            {
                "id": root_id,
                "type": "agent",
                "name": "/root",
                "attributes": {
                    "provider": provider,
                    "session_id": "parent",
                    "agent_role": "root",
                    "agent_path": "/root",
                },
            },
            {
                "id": child_id,
                "type": "agent",
                "name": "explore",
                "attributes": {
                    "provider": provider,
                    "session_id": "child",
                    "parent_scope_id": "parent",
                    "agent_role": "subagent",
                },
            },
            {
                "id": model_id,
                "type": "model",
                "name": "model-a",
                "attributes": {"provider": provider, "model_name": "model-a"},
            },
            {
                "id": call_id,
                "type": "tool_call",
                "name": "task",
                "attributes": {
                    "provider": provider,
                    "session_id": "parent",
                    "call_id": "call-task",
                    "tool_name": "task",
                },
            },
            {
                "id": tool_id,
                "type": "tool",
                "name": "task",
                "attributes": {"provider": provider, "native_name": "task"},
            },
        ],
        "edges": [
            _edge("model", root_id, model_id, "USED_MODEL", 1, provider),
            _edge("request-task", root_id, call_id, "REQUESTED_TOOL_CALL", 2, provider),
            _edge("uses-task", call_id, tool_id, "USES_TOOL", 3, provider),
            _edge(
                "assign-child",
                call_id,
                child_id,
                "ASSIGNED_AGENT_TASK",
                4,
                provider,
                identity_exact=True,
                event_type="semantic.opencode.task_session.assigned",
            ),
        ],
    }
    graph["node_count"] = len(graph["nodes"])
    graph["edge_count"] = len(graph["edges"])

    manager, executable = _browser()
    with manager as playwright:
        browser = _launch(playwright, executable)
        try:
            page = browser.new_page(viewport={"width": 1600, "height": 900})
            errors: list[str] = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.set_content(render_static_dashboard_html(graph))
            page.wait_for_selector(".node")
            display, raw, positions, metrics = _snapshot(page)
            _assert_hard_geometry(metrics)
            _assert_closed_display_graph(display)
            page.locator("#arrange").click()
            arranged_display, _, _, arranged_metrics = _snapshot(page)
            _assert_hard_geometry(arranged_metrics)
            _assert_closed_display_graph(arranged_display)
            assert not errors, errors
        finally:
            browser.close()

    contexts = [
        node for node in display["nodes"]
        if node.get("attributes", {}).get("viewer_model_context")
    ]
    actions = [
        node for node in display["nodes"]
        if node.get("attributes", {}).get("viewer_orchestration_action")
        and node["name"] == "assign_agent_task"
    ]
    visible_ids = {node["id"] for node in display["nodes"]}
    assert len(contexts) == 1 and contexts[0]["name"] == "model-a"
    assert len(actions) == 1
    assert call_id not in visible_ids
    assert tool_id not in visible_ids
    assert [node["id"] for node in display["nodes"] if node["type"] == "agent"].count(child_id) == 1
    assert any(
        edge["relation"] == "ASSIGNED_AGENT_TASK" and edge.get("identity_exact") is True
        for edge in raw["edges"]
    )
    assert any(
        edge["source"] == actions[0]["id"]
        and edge["target"] == child_id
        and edge["relation"] == "TARGETED_AGENT"
        for edge in display["edges"]
    )
    assert positions[root_id]["x"] < positions[contexts[0]["id"]]["x"]
    assert positions[contexts[0]["id"]]["x"] < positions[actions[0]["id"]]["x"]
    assert positions[actions[0]["id"]]["x"] < positions[child_id]["x"]


def test_root_only_model_provider_shapes_do_not_invent_agent_orchestration() -> None:
    manager, executable = _browser()
    with manager as playwright:
        browser = _launch(playwright, executable)
        try:
            page = browser.new_page(viewport={"width": 1400, "height": 800})
            errors: list[str] = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            for provider in sorted(ROOT_ONLY_MODEL_PROVIDERS):
                errors.clear()
                root_id = f"agent:{provider}:root"
                model_id = f"model:{provider}:model-a"
                graph = {
                    "schema_version": "0.2",
                    "session_id": f"{provider}-production-root-only",
                    "nodes": [
                        {
                            "id": root_id,
                            "type": "agent",
                            "name": "/root",
                            "attributes": {
                                "provider": provider,
                                "agent_role": "root",
                                "agent_path": "/root",
                            },
                        },
                        {
                            "id": model_id,
                            "type": "model",
                            "name": "model-a",
                            "attributes": {"provider": provider, "model_name": "model-a"},
                        },
                    ],
                    "edges": [
                        _edge("model", root_id, model_id, "USED_MODEL", 1, provider),
                    ],
                    "node_count": 2,
                    "edge_count": 1,
                }
                page.set_content(render_static_dashboard_html(graph))
                page.wait_for_selector(".node")
                display, raw, _, metrics = _snapshot(page)
                _assert_hard_geometry(metrics)
                _assert_closed_display_graph(display)
                assert not errors, (provider, errors)
                assert not any(
                    node.get("attributes", {}).get("viewer_orchestration_action")
                    for node in display["nodes"]
                ), provider
                assert not any(
                    node.get("attributes", {}).get("viewer_model_context")
                    for node in display["nodes"]
                ), provider
                assert {node["id"] for node in display["nodes"]} == {root_id, model_id}, provider
                assert any(
                    edge["source"] == root_id
                    and edge["target"] == model_id
                    and edge["relation"] == "USED_MODEL"
                    for edge in display["edges"]
                ), provider
                assert len(raw["nodes"]) == 2 and len(raw["edges"]) == 1
        finally:
            browser.close()
