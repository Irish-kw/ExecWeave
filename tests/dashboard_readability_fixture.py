"""Sanitized seven-agent topology used by dashboard readability browser regressions."""

from __future__ import annotations

from typing import Any


ROOT_ID = "agent:root"
CHILD_IDS = tuple(f"agent:child:{index}" for index in range(1, 7))
SHARED_TOOL_IDS = (
    "tool:read",
    "tool:search",
    "tool:shell",
    "tool:fetch",
)
COLLAB_TOOL_IDS = (
    "tool:spawn_agent",
    "tool:send_input",
    "tool:wait_agent",
)
MODEL_ID = "model:gpt"
RUNTIME_ID = "session:runtime"
ENDPOINT_ID = "endpoint:example"


def _stamp(second: int) -> str:
    return f"2026-08-31T03:40:{second:02d}Z"


def build_dashboard_readability_graph() -> dict[str, Any]:
    nodes: list[dict[str, Any]] = [
        {
            "id": ROOT_ID,
            "type": "agent",
            "name": "root",
            "first_seen": _stamp(0),
            "attributes": {
                "provider": "fixture",
                "agent_role": "root",
                "root_agent_path": "/root",
            },
        },
        {
            "id": RUNTIME_ID,
            "type": "session",
            "name": "ExecWeave runtime",
            "first_seen": _stamp(0),
            "attributes": {"backend": "fixture"},
        },
        {
            "id": MODEL_ID,
            "type": "model",
            "name": "fixture-model",
            "first_seen": _stamp(1),
            "attributes": {"provider": "fixture"},
        },
        {
            "id": ENDPOINT_ID,
            "type": "network_endpoint",
            "name": "example.invalid:443",
            "first_seen": _stamp(2),
            "attributes": {"port": 443},
        },
    ]
    edges: list[dict[str, Any]] = [
        {
            "id": "runtime-root",
            "source": RUNTIME_ID,
            "target": ROOT_ID,
            "relation": "OWNS_AGENT",
            "first_sequence": 1,
            "first_seen": _stamp(0),
        },
        {
            "id": "root-model",
            "source": ROOT_ID,
            "target": MODEL_ID,
            "relation": "USED_MODEL",
            "first_sequence": 2,
            "first_seen": _stamp(1),
        },
        {
            "id": "fetch-endpoint",
            "source": "tool:fetch",
            "target": ENDPOINT_ID,
            "relation": "REACHED_ENDPOINT",
            "first_sequence": 90,
            "first_seen": _stamp(48),
        },
    ]

    for index, child_id in enumerate(CHILD_IDS, start=1):
        path = f"/root/worker_{index}"
        nodes.append(
            {
                "id": child_id,
                "type": "agent",
                "name": f"worker-{index}",
                "first_seen": _stamp(2 + index),
                "attributes": {
                    "provider": "fixture",
                    "agent_role": "subagent",
                    "child_agent_path": path,
                    "parent_agent_path": "/root",
                },
            }
        )
        edges.append(
            {
                "id": f"spawn-{index}",
                "source": ROOT_ID,
                "target": child_id,
                "relation": "SPAWNED_AGENT",
                "first_sequence": 10 + index,
                "last_sequence": 10 + index,
                "first_seen": _stamp(2 + index),
                "last_seen": _stamp(2 + index),
                "count": 1,
            }
        )
        edges.append(
            {
                "id": f"stop-{index}",
                "source": child_id,
                "target": ROOT_ID,
                "relation": "SUBAGENT_STOPPED",
                "first_sequence": 70 + index,
                "last_sequence": 70 + index,
                "first_seen": _stamp(38 + index),
                "last_seen": _stamp(38 + index),
                "count": 1,
            }
        )

    for tool_id in (*SHARED_TOOL_IDS, *COLLAB_TOOL_IDS):
        nodes.append(
            {
                "id": tool_id,
                "type": "tool",
                "name": tool_id.removeprefix("tool:"),
                "first_seen": _stamp(5),
                "attributes": {
                    "provider": "fixture",
                    "tool_name": tool_id.removeprefix("tool:"),
                },
            }
        )

    sequence = 20
    for child_index, child_id in enumerate(CHILD_IDS, start=1):
        for tool_index, tool_id in enumerate(SHARED_TOOL_IDS, start=1):
            call_id = f"tool_call:child:{child_index}:{tool_index}"
            nodes.append(
                {
                    "id": call_id,
                    "type": "tool_call",
                    "name": f"call-{child_index}-{tool_index}",
                    "first_seen": _stamp(min(59, 6 + child_index + tool_index)),
                    "attributes": {
                        "provider": "fixture",
                        "tool_name": tool_id.removeprefix("tool:"),
                        "tool_use_id": call_id,
                    },
                }
            )
            edges.extend(
                [
                    {
                        "id": f"owner-{call_id}",
                        "source": child_id,
                        "target": call_id,
                        "relation": "ISSUED_TOOL_CALL",
                        "first_sequence": sequence,
                        "first_seen": _stamp(min(59, 6 + child_index + tool_index)),
                    },
                    {
                        "id": f"tool-{call_id}",
                        "source": call_id,
                        "target": tool_id,
                        "relation": "RESOLVED_TOOL",
                        "first_sequence": sequence + 1,
                        "first_seen": _stamp(min(59, 7 + child_index + tool_index)),
                    },
                ]
            )
            sequence += 2

    for index, tool_id in enumerate(COLLAB_TOOL_IDS, start=1):
        call_id = f"tool_call:root:collab:{index}"
        nodes.append(
            {
                "id": call_id,
                "type": "tool_call",
                "name": f"root-collab-{index}",
                "first_seen": _stamp(8 + index),
                "attributes": {
                    "provider": "fixture",
                    "tool_name": tool_id.removeprefix("tool:"),
                    "tool_use_id": call_id,
                },
            }
        )
        edges.extend(
            [
                {
                    "id": f"owner-{call_id}",
                    "source": ROOT_ID,
                    "target": call_id,
                    "relation": "ISSUED_TOOL_CALL",
                    "first_sequence": sequence,
                    "first_seen": _stamp(8 + index),
                },
                {
                    "id": f"tool-{call_id}",
                    "source": call_id,
                    "target": tool_id,
                    "relation": "RESOLVED_TOOL",
                    "first_sequence": sequence + 1,
                    "first_seen": _stamp(9 + index),
                },
            ]
        )
        sequence += 2

    return {
        "session_id": "dashboard-readability-fixture",
        "event_count": 96,
        "nodes": nodes,
        "edges": edges,
        "node_count": len(nodes),
        "edge_count": len(edges),
    }
