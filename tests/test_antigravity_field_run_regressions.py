from __future__ import annotations

from pathlib import Path

from execweave.graph import GraphAccumulator
from execweave.viewer_projection import project_viewer_graph


def _apply(accumulator: GraphAccumulator, event: dict, index: int) -> None:
    accumulator.apply(
        {
            "schema_version": "0.2",
            "session_id": "agy-field-shape",
            "event_id": f"field-{index}",
            "timestamp": f"2026-09-04T05:{index // 60:02d}:{index % 60:02d}Z",
            "sequence": index,
            **event,
        }
    )


def test_field_shape_keeps_34_model_calls_but_folds_52_transcript_replays() -> None:
    accumulator = GraphAccumulator(
        session_id="agy-field-shape",
        source_path=Path("events.semantic.jsonl"),
    )
    session = {
        "id": "provider-session:antigravity:root",
        "type": "provider_session",
    }
    model = {"id": "model:antigravity:flash", "type": "model"}
    for index in range(34):
        _apply(
            accumulator,
            {
                "event_type": "semantic.antigravity.model.invocation.requested",
                "relation": "INVOKES_MODEL",
                "source": session,
                "target": model,
                "attributes": {
                    "backend": "semantic",
                    "provider": "antigravity",
                    "antigravity_initial_num_steps": index * 3 + 1,
                    "antigravity_invocation_number": index % 3,
                },
            },
            index + 1,
        )

    tool_call = {
        "id": "tool-call:antigravity:child:stable-write-call",
        "type": "tool_call",
        "name": "write_to_file",
        "attributes": {
            "provider": "antigravity",
            "conversation_id": "child",
            "step_index": 1,
        },
    }
    file_node = {
        "id": "file:C:/workspace/report.md",
        "type": "file",
        "name": "report.md",
    }
    for replay in range(52):
        _apply(
            accumulator,
            {
                "event_type": "semantic.antigravity.child.file.declared",
                "relation": "DECLARED_TARGET",
                "source": tool_call,
                "target": file_node,
                "attributes": {
                    "backend": "semantic",
                    "provider": "antigravity",
                    "antigravity_initial_num_steps": replay + 4,
                    "antigravity_invocation_number": replay % 4,
                },
            },
            replay + 35,
        )

    graph = accumulator.to_dict()
    model_edge = next(edge for edge in graph["edges"] if edge["relation"] == "INVOKES_MODEL")
    file_edge = next(edge for edge in graph["edges"] if edge["relation"] == "DECLARED_TARGET")
    assert model_edge["count"] == 34
    assert model_edge["evidence_event_count"] == 34
    assert file_edge["count"] == 1
    assert file_edge["evidence_event_count"] == 52


def test_field_shape_projects_one_result_node_and_one_continuing_role_agent() -> None:
    root = {
        "id": "agent:antigravity:conversation:root",
        "type": "agent",
        "name": "Antigravity",
        "attributes": {"provider": "antigravity", "agent_role": "root"},
    }
    tool = {
        "id": "tool:antigravity:write_to_file",
        "type": "tool",
        "name": "write_to_file",
        "attributes": {"provider": "antigravity"},
    }
    nodes = [root, tool]
    edges = []
    for index in range(4):
        result_id = f"tool-result:antigravity:{index}"
        nodes.append(
            {
                "id": result_id,
                "type": "tool_result",
                "name": "write_to_file result",
                "first_seen": f"2026-09-04T05:00:0{index}Z",
                "last_seen": f"2026-09-04T05:00:0{index}Z",
                "attributes": {"provider": "antigravity"},
            }
        )
        edges.append(
            {
                "id": f"result-edge-{index}",
                "source": tool["id"],
                "target": result_id,
                "relation": "TOOL_RESULT_RETURNED",
                "count": 1,
            }
        )

    for index, child in enumerate(("child-original", "child-followup")):
        subtask_id = f"subtask:antigravity:root:{index}:0"
        child_id = f"agent:antigravity:conversation:{child}"
        nodes.extend(
            [
                {
                    "id": subtask_id,
                    "type": "subtask",
                    "name": "geologist discussion",
                    "attributes": {"provider": "antigravity"},
                },
                {
                    "id": child_id,
                    "type": "agent",
                    "name": "geologist",
                    "first_seen": f"2026-09-04T05:01:0{index}Z",
                    "last_seen": f"2026-09-04T05:01:3{index}Z",
                    "attributes": {
                        "provider": "antigravity",
                        "conversation_id": child,
                        "agent_role": "subagent",
                        "parent_scope_id": "root",
                        "parent_agent_path": "/root",
                        "child_agent_path": "/root/geologist",
                        "provider_role_path": "/root/geologist",
                        "parent_relation_source": "provider_validated_child_transcript",
                        "provider_role_slot": 0,
                        "provider_role_type": "research",
                        "provider_role_workspace": "inherit",
                    },
                },
            ]
        )
        edges.extend(
            [
                {
                    "id": f"request-{index}",
                    "source": root["id"],
                    "target": subtask_id,
                    "relation": "REQUESTED_SUBTASK",
                    "count": 1,
                },
                {
                    "id": f"assign-{index}",
                    "source": subtask_id,
                    "target": child_id,
                    "relation": "ASSIGNED_AGENT_TASK",
                    "count": 1,
                },
            ]
        )

    projected = project_viewer_graph(
        {
            "graph_schema_version": "0.2",
            "session_id": "agy-field-shape",
            "event_count": 10,
            "node_count": len(nodes),
            "edge_count": len(edges),
            "nodes": nodes,
            "edges": edges,
        }
    )
    results = [node for node in projected["nodes"] if node.get("type") == "tool_result"]
    agents = [
        node
        for node in projected["nodes"]
        if (node.get("attributes") or {}).get("child_agent_path") == "/root/geologist"
    ]
    assert len(results) == 1
    assert results[0]["attributes"]["viewer_occurrence_count"] == 4
    assert len(agents) == 1
    assert set(agents[0]["attributes"]["provider_conversation_ids"]) == {
        "child-original",
        "child-followup",
    }
    requested_subtasks = {
        edge["target"]
        for edge in projected["edges"]
        if edge.get("source") == root["id"] and edge.get("relation") == "REQUESTED_SUBTASK"
    }
    assigned_subtasks = {
        edge["source"]
        for edge in projected["edges"]
        if edge.get("target") == agents[0]["id"]
        and edge.get("relation") == "ASSIGNED_AGENT_TASK"
    }
    assert requested_subtasks == assigned_subtasks


def test_result_aggregation_never_crosses_provider_or_outcome_identity() -> None:
    nodes = []
    for provider, failed in (("claude", False), ("codex", False), ("claude", True)):
        nodes.append(
            {
                "id": f"tool-result:{provider}:{'failed' if failed else 'ok'}",
                "type": "tool_result",
                "name": "write result",
                "attributes": {
                    "provider": provider,
                    "provider_reported_error": failed,
                },
            }
        )
    projected = project_viewer_graph(
        {
            "graph_schema_version": "0.2",
            "session_id": "provider-boundaries",
            "event_count": 0,
            "node_count": len(nodes),
            "edge_count": 0,
            "nodes": nodes,
            "edges": [],
        }
    )
    assert len([node for node in projected["nodes"] if node["type"] == "tool_result"]) == 3


def test_agy_role_continuity_never_merges_parallel_equal_role_slots() -> None:
    nodes = []
    for slot in (0, 1):
        nodes.append(
            {
                "id": f"agent:antigravity:conversation:parallel-{slot}",
                "type": "agent",
                "name": "reviewer",
                "attributes": {
                    "provider": "antigravity",
                    "agent_role": "subagent",
                    "parent_scope_id": "root",
                    "parent_agent_path": "/root",
                    "child_agent_path": "/root/reviewer",
                    "provider_role_path": "/root/reviewer",
                    "parent_relation_source": "provider_validated_child_transcript",
                    "provider_role_slot": slot,
                    "provider_role_type": "research",
                    "provider_role_workspace": "inherit",
                },
            }
        )
    projected = project_viewer_graph(
        {
            "graph_schema_version": "0.2",
            "session_id": "parallel-role-slots",
            "event_count": 0,
            "node_count": 2,
            "edge_count": 0,
            "nodes": nodes,
            "edges": [],
        }
    )
    assert len(projected["nodes"]) == 2
