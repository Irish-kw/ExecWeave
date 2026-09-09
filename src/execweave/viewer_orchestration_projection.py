from __future__ import annotations

import hashlib
import json
from collections import defaultdict, deque
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

from .conversation_records import conversation_record_entries
from .viewer_semantic_projection import project_provider_neutral_viewer_graph

_ORCHESTRATION_SUFFIXES = {
    "spawn_agent": "spawn_agent",
    "send_input": "send_input",
    "wait_agent": "wait_agent",
    "resume_agent": "resume_agent",
    "close_agent": "close_agent",
    "assign_agent_task": "assign_agent_task",
    "send_message": "send_input",
}
_ACTION_RELATIONS = {
    "spawn_agent": "SPAWNED_AGENT",
    "send_input": "SENT_INPUT_TO",
    "wait_agent": "WAITED_FOR",
    "resume_agent": "RESUMED_AGENT",
    "close_agent": "CLOSED_AGENT",
    "assign_agent_task": "ASSIGNED_AGENT_TASK",
}
_TARGET_KEYS = ("target", "targets", "id", "agent_id", "recipient", "recipients")
_MODEL_RELATIONS = {"USED_MODEL", "INVOKED_MODEL", "REQUESTED_MODEL", "INFERRED"}
_MAX_INPUT_BYTES = 64 * 1024
_MAX_ORCHESTRATION_CALLS = 256


def _attrs(node: dict[str, Any]) -> dict[str, Any]:
    value = node.get("attributes")
    return value if isinstance(value, dict) else {}


def _normalize_action(value: object) -> str | None:
    text = str(value or "").strip().lower().replace("-", "_")
    if not text:
        return None
    for suffix, action in _ORCHESTRATION_SUFFIXES.items():
        if text == suffix or text.endswith(suffix):
            return action
    return None


def _edge_order(edge: dict[str, Any]) -> tuple[int, str, str]:
    sequence = edge.get("first_sequence")
    return (
        sequence if isinstance(sequence, int) and not isinstance(sequence, bool) else 2**63 - 1,
        str(edge.get("first_seen") or ""),
        str(edge.get("id") or ""),
    )


def _moment(node: dict[str, Any], evidence: list[dict[str, Any]]) -> tuple[int, str]:
    sequences = [
        value
        for edge in evidence
        for value in (edge.get("first_sequence"), edge.get("last_sequence"))
        if isinstance(value, int) and not isinstance(value, bool)
    ]
    times = [
        str(value)
        for value in (
            node.get("first_seen"),
            node.get("last_seen"),
            *(edge.get("first_seen") for edge in evidence),
            *(edge.get("last_seen") for edge in evidence),
        )
        if value
    ]
    return (min(sequences) if sequences else 2**63 - 1, min(times, default=""))


def _latest_moment(node: dict[str, Any], evidence: list[dict[str, Any]]) -> tuple[int, str]:
    sequences = [
        value
        for edge in evidence
        for value in (edge.get("first_sequence"), edge.get("last_sequence"))
        if isinstance(value, int) and not isinstance(value, bool)
    ]
    times = [
        str(value)
        for value in (
            node.get("first_seen"),
            node.get("last_seen"),
            *(edge.get("first_seen") for edge in evidence),
            *(edge.get("last_seen") for edge in evidence),
        )
        if value
    ]
    return (max(sequences) if sequences else -1, max(times, default=""))


def _viewer_id(kind: str, *parts: str) -> str:
    raw = "\0".join(parts).encode("utf-8", errors="replace")
    digest = hashlib.sha256(raw).hexdigest()[:24]
    return f"viewer:{kind}:{digest}"


def _run_root(graph: dict[str, Any]) -> Path | None:
    source = graph.get("source_path")
    if not isinstance(source, str) or not source:
        return None
    try:
        return Path(source).expanduser().resolve(strict=False).parent
    except (OSError, RuntimeError, ValueError):
        return None


def _read_target_selectors(
    call_id: str,
    *,
    run_root: Path | None,
    node_by_id: dict[str, dict[str, Any]],
    outgoing: dict[str, list[dict[str, Any]]],
) -> tuple[list[str], list[str]]:
    """Read routing selectors only from exact provider tool-input evidence."""

    if run_root is None:
        return [], []
    root = run_root.resolve(strict=False)
    selectors: list[str] = []
    support_ids: list[str] = []
    for edge in outgoing.get(call_id, []):
        if edge.get("relation") != "HAS_TOOL_INPUT":
            continue
        content = node_by_id.get(str(edge.get("target") or ""))
        if not content or content.get("type") != "observed_content":
            continue
        relative = _attrs(content).get("path")
        if not isinstance(relative, str) or not relative:
            continue
        try:
            path = (root / relative).resolve(strict=False)
            path.relative_to(root)
        except (OSError, RuntimeError, ValueError):
            continue
        try:
            if not path.is_file() or path.stat().st_size > _MAX_INPUT_BYTES:
                continue
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        support_ids.append(str(edge.get("id") or content.get("id") or ""))
        for key in _TARGET_KEYS:
            value = payload.get(key)
            values = value if isinstance(value, list) else [value]
            for item in values:
                if isinstance(item, str) and item.strip():
                    selectors.append(item.strip())
    return list(dict.fromkeys(selectors)), [value for value in support_ids if value]


def _agent_aliases(node: dict[str, Any]) -> set[str]:
    attrs = _attrs(node)
    values = {
        node.get("id"),
        node.get("name"),
        attrs.get("agent_id"),
        attrs.get("thread_id"),
        attrs.get("agent_path"),
        attrs.get("root_agent_path"),
        attrs.get("child_agent_path"),
        attrs.get("agent_nickname"),
        attrs.get("nickname"),
    }
    aliases: set[str] = set()
    for value in values:
        if not isinstance(value, str) or not value.strip():
            continue
        text = value.strip()
        aliases.add(text)
        aliases.add(text.casefold())
        aliases.add(text.rsplit("/", 1)[-1].casefold())
        aliases.add(text.rsplit(":", 1)[-1].casefold())
    return aliases


def _agent_lookup(nodes: list[dict[str, Any]]) -> tuple[dict[str, str], set[str]]:
    candidates: dict[str, set[str]] = defaultdict(set)
    agent_ids: set[str] = set()
    for node in nodes:
        node_id = node.get("id")
        if node.get("type") != "agent" or not isinstance(node_id, str):
            continue
        agent_ids.add(node_id)
        for alias in _agent_aliases(node):
            candidates[alias].add(node_id)
    exact = {alias: next(iter(ids)) for alias, ids in candidates.items() if len(ids) == 1}
    return exact, agent_ids


def _resolve_agent(selector: str, aliases: dict[str, str]) -> str | None:
    candidates = (
        selector,
        selector.casefold(),
        selector.rsplit("/", 1)[-1].casefold(),
        selector.rsplit(":", 1)[-1].casefold(),
    )
    for key in candidates:
        target = aliases.get(key)
        if target:
            return target
    return None


def _root_ids(nodes: list[dict[str, Any]]) -> set[str]:
    roots: set[str] = set()
    for node in nodes:
        if node.get("type") != "agent" or not isinstance(node.get("id"), str):
            continue
        attrs = _attrs(node)
        if attrs.get("agent_role") == "root" or "/root" in {
            str(node.get("name") or ""),
            str(attrs.get("agent_path") or ""),
            str(attrs.get("root_agent_path") or ""),
        }:
            roots.add(str(node["id"]))
    return roots


def _agent_depths(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> dict[str, int]:
    _, agent_ids = _agent_lookup(nodes)
    children: dict[str, set[str]] = defaultdict(set)
    incoming_children: set[str] = set()
    for edge in edges:
        if edge.get("relation") != "SPAWNED_AGENT":
            continue
        source, target = edge.get("source"), edge.get("target")
        if source in agent_ids and target in agent_ids and source != target:
            children[str(source)].add(str(target))
            incoming_children.add(str(target))
    roots = _root_ids(nodes) or (agent_ids - incoming_children)
    depth: dict[str, int] = {}
    queue: deque[tuple[str, int]] = deque((node_id, 0) for node_id in sorted(roots))
    while queue:
        node_id, level = queue.popleft()
        previous = depth.get(node_id)
        if previous is not None and previous <= level:
            continue
        depth[node_id] = level
        for child in sorted(children.get(node_id, ())):
            queue.append((child, level + 1))
    for node_id in agent_ids:
        depth.setdefault(node_id, 0)
    return depth


def _owner_for_call(
    call_id: str,
    *,
    node_by_id: dict[str, dict[str, Any]],
    incoming: dict[str, list[dict[str, Any]]],
) -> str | None:
    direct: list[tuple[int, str]] = []
    for edge in incoming.get(call_id, []):
        source = node_by_id.get(str(edge.get("source") or ""))
        if source and source.get("type") == "agent":
            priority = 0 if edge.get("relation") in {"REQUESTED_TOOL_CALL", "EXECUTED_TOOL_CALL"} else 1
            direct.append((priority, str(source["id"])))
    if direct:
        return min(direct)[1]
    for edge in incoming.get(call_id, []):
        parent_id = str(edge.get("source") or "")
        parent = node_by_id.get(parent_id)
        if not parent or parent.get("type") not in {"agent_turn", "agent_execution"}:
            continue
        for grand in incoming.get(parent_id, []):
            source = node_by_id.get(str(grand.get("source") or ""))
            if source and source.get("type") == "agent":
                return str(source["id"])
    return None


def _tool_for_call(
    call_id: str,
    *,
    node_by_id: dict[str, dict[str, Any]],
    outgoing: dict[str, list[dict[str, Any]]],
) -> tuple[str | None, str | None]:
    for edge in outgoing.get(call_id, []):
        if edge.get("relation") not in {"USES_TOOL", "TOOL_CALL_RETURNED"}:
            continue
        tool = node_by_id.get(str(edge.get("target") or ""))
        if not tool or tool.get("type") != "tool":
            continue
        action = _normalize_action(_attrs(tool).get("native_name") or tool.get("name") or tool.get("id"))
        if action:
            return str(tool["id"]), action
    call = node_by_id.get(call_id)
    if call:
        action = _normalize_action(_attrs(call).get("tool_name") or call.get("name"))
        if action:
            return None, action
    return None, None


def _model_name_for_call(call: dict[str, Any]) -> str | None:
    attrs = _attrs(call)
    for key in ("codex_model", "model", "model_name"):
        value = attrs.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _model_observations(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    *,
    orchestration_calls: list[dict[str, Any]],
) -> dict[tuple[str, str], dict[str, Any]]:
    node_by_id = {str(node["id"]): node for node in nodes if isinstance(node.get("id"), str)}
    observations: dict[tuple[str, str], dict[str, Any]] = {}

    def add(
        owner: str,
        model: str,
        *,
        model_id: str | None = None,
        edge: dict[str, Any] | None = None,
        call: dict[str, Any] | None = None,
    ) -> None:
        key = (owner, model)
        row = observations.setdefault(
            key,
            {
                "owner": owner,
                "model": model,
                "model_ids": set(),
                "supporting_edge_ids": set(),
                "supporting_call_ids": set(),
                "first_sequence": None,
                "last_sequence": None,
                "first_seen": None,
                "last_seen": None,
            },
        )
        if model_id:
            row["model_ids"].add(model_id)
        if edge:
            if edge.get("id"):
                row["supporting_edge_ids"].add(str(edge["id"]))
            first, last = edge.get("first_sequence"), edge.get("last_sequence")
            if isinstance(first, int) and not isinstance(first, bool):
                row["first_sequence"] = first if row["first_sequence"] is None else min(row["first_sequence"], first)
            if isinstance(last, int) and not isinstance(last, bool):
                row["last_sequence"] = last if row["last_sequence"] is None else max(row["last_sequence"], last)
            for field, reducer in (("first_seen", min), ("last_seen", max)):
                value = edge.get(field)
                if value:
                    row[field] = str(value) if row[field] is None else reducer(str(row[field]), str(value))
        if call:
            call_id = call.get("id")
            if call_id:
                row["supporting_call_ids"].add(str(call_id))
            first, last = call.get("first_sequence"), call.get("last_sequence")
            if isinstance(first, int) and not isinstance(first, bool):
                row["first_sequence"] = first if row["first_sequence"] is None else min(row["first_sequence"], first)
            if isinstance(last, int) and not isinstance(last, bool):
                row["last_sequence"] = last if row["last_sequence"] is None else max(row["last_sequence"], last)
            for field, reducer in (("first_seen", min), ("last_seen", max)):
                value = call.get(field)
                if value:
                    row[field] = str(value) if row[field] is None else reducer(str(row[field]), str(value))

    for edge in edges:
        if str(edge.get("relation") or "").upper() not in _MODEL_RELATIONS:
            continue
        source = node_by_id.get(str(edge.get("source") or ""))
        target = node_by_id.get(str(edge.get("target") or ""))
        if not source or source.get("type") != "agent" or not target or target.get("type") != "model":
            continue
        add(str(source["id"]), str(target.get("name") or target["id"]), model_id=str(target["id"]), edge=edge)

    incoming_owner: dict[str, str] = {}
    for edge in edges:
        source = node_by_id.get(str(edge.get("source") or ""))
        target = node_by_id.get(str(edge.get("target") or ""))
        if source and source.get("type") == "agent" and target and "inference" in str(target.get("type") or ""):
            incoming_owner[str(target["id"])] = str(source["id"])
    for edge in edges:
        target = node_by_id.get(str(edge.get("target") or ""))
        owner = incoming_owner.get(str(edge.get("source") or ""))
        if not owner or not target or target.get("type") != "model":
            continue
        if str(edge.get("relation") or "").upper() not in _MODEL_RELATIONS:
            continue
        add(owner, str(target.get("name") or target["id"]), model_id=str(target["id"]), edge=edge)

    for row in orchestration_calls:
        owner, model = row.get("owner"), row.get("model")
        if isinstance(owner, str) and isinstance(model, str) and owner and model:
            add(owner, model, call=row["node"])
    return observations


def _parse_time(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _conversation_target_events(
    graph: dict[str, Any], aliases: dict[str, str]
) -> list[tuple[datetime, str, str]]:
    root = _run_root(graph)
    if root is None:
        return []
    try:
        entries = conversation_record_entries(graph, root)
    except (OSError, RuntimeError, ValueError):
        return []
    rows: list[tuple[datetime, str, str]] = []
    for entry in entries:
        preview = entry.get("conversation_preview") if isinstance(entry, dict) else None
        if not isinstance(preview, dict):
            continue
        for message in preview.get("messages") or []:
            if not isinstance(message, dict):
                continue
            recipient = message.get("recipient")
            when = _parse_time(message.get("timestamp"))
            if not isinstance(recipient, str) or when is None:
                continue
            target = _resolve_agent(recipient, aliases)
            if target:
                rows.append((when, target, str(message.get("kind") or "")))
    rows.sort(key=lambda item: (item[0], item[1], item[2]))
    return rows


def _nearest_message_target(
    call: dict[str, Any],
    *,
    message_events: list[tuple[datetime, str, str]],
    used: set[tuple[datetime, str]],
) -> str | None:
    when = _parse_time(call.get("first_seen") or call.get("last_seen"))
    if when is None:
        return None
    best: tuple[float, datetime, str] | None = None
    for event_time, target, kind in message_events:
        if (event_time, target) in used:
            continue
        if kind and "user" not in kind.lower():
            continue
        delta = abs((event_time - when).total_seconds())
        if delta > 12:
            continue
        candidate = (delta, event_time, target)
        if best is None or candidate < best:
            best = candidate
    if best is None:
        return None
    used.add((best[1], best[2]))
    return best[2]


def _spawn_targets(
    *,
    owner: str,
    calls: list[dict[str, Any]],
    spawn_edges: list[dict[str, Any]],
) -> dict[str, list[tuple[str, dict[str, Any]]]]:
    """Pair spawn evidence to the nearest preceding spawn call for the same owner."""

    result: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
    available = sorted(calls, key=lambda row: (row["last_moment"], row["id"]))
    for edge in sorted(
        (item for item in spawn_edges if item.get("source") == owner), key=_edge_order
    ):
        edge_sequence = edge.get("first_sequence")
        edge_time = str(edge.get("first_seen") or "")
        candidates = []
        for row in available:
            sequence, seen = row["last_moment"]
            before_sequence = (
                isinstance(edge_sequence, int)
                and sequence >= 0
                and sequence <= edge_sequence
            )
            before_time = bool(edge_time and seen and seen <= edge_time)
            if before_sequence or (not isinstance(edge_sequence, int) and before_time):
                candidates.append(row)
        if not candidates:
            continue
        chosen = max(candidates, key=lambda row: (row["last_moment"], row["id"]))
        result[chosen["id"]].append((str(edge["target"]), edge))
    return result


def _project_flow(projected: dict[str, Any]) -> dict[str, Any]:
    nodes = [deepcopy(node) for node in projected.get("nodes", []) if isinstance(node, dict)]
    edges = [deepcopy(edge) for edge in projected.get("edges", []) if isinstance(edge, dict)]
    node_by_id = {str(node["id"]): node for node in nodes if isinstance(node.get("id"), str)}
    incoming: dict[str, list[dict[str, Any]]] = defaultdict(list)
    outgoing: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in edges:
        source, target = edge.get("source"), edge.get("target")
        if isinstance(source, str):
            outgoing[source].append(edge)
        if isinstance(target, str):
            incoming[target].append(edge)

    aliases, agent_ids = _agent_lookup(nodes)
    depths = _agent_depths(nodes, edges)
    run_root = _run_root(projected)
    message_events = _conversation_target_events(projected, aliases)
    used_messages: set[tuple[datetime, str]] = set()

    orchestration_calls: list[dict[str, Any]] = []
    orchestration_tool_ids: set[str] = set()
    for call in nodes:
        if call.get("type") not in {"tool_call", "tool_call_observation"} or not isinstance(call.get("id"), str):
            continue
        call_id = str(call["id"])
        tool_id, action = _tool_for_call(call_id, node_by_id=node_by_id, outgoing=outgoing)
        if action is None:
            continue
        owner = _owner_for_call(call_id, node_by_id=node_by_id, incoming=incoming)
        model = _model_name_for_call(call)
        if owner not in agent_ids or not model:
            continue
        evidence = [*incoming.get(call_id, []), *outgoing.get(call_id, [])]
        first_sequence, first_seen = _moment(call, evidence)
        last_sequence, last_seen = _latest_moment(call, evidence)
        selectors, selector_support = _read_target_selectors(
            call_id,
            run_root=run_root,
            node_by_id=node_by_id,
            outgoing=outgoing,
        )
        targets = [
            target
            for selector in selectors
            if (target := _resolve_agent(selector, aliases))
        ]
        target_semantics = "provider_tool_input"
        if action == "send_input" and not targets:
            target = _nearest_message_target(
                call, message_events=message_events, used=used_messages
            )
            if target:
                targets = [target]
                target_semantics = "provider_conversation_temporal_correlation"
        orchestration_calls.append(
            {
                "id": call_id,
                "node": call,
                "owner": owner,
                "model": model,
                "action": action,
                "tool_id": tool_id,
                "targets": list(dict.fromkeys(targets)),
                "target_semantics": target_semantics,
                "selector_support": selector_support,
                "first_moment": (first_sequence, first_seen),
                "last_moment": (last_sequence, last_seen),
            }
        )
        if tool_id:
            orchestration_tool_ids.add(tool_id)
        if len(orchestration_calls) >= _MAX_ORCHESTRATION_CALLS:
            break

    model_observations = _model_observations(
        nodes, edges, orchestration_calls=orchestration_calls
    )
    if not orchestration_calls and not model_observations:
        return projected

    spawn_edges = [
        edge
        for edge in edges
        if edge.get("relation") == "SPAWNED_AGENT"
        and edge.get("source") in agent_ids
        and edge.get("target") in agent_ids
    ]
    spawn_calls_by_owner: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in orchestration_calls:
        if row["action"] == "spawn_agent":
            spawn_calls_by_owner[str(row["owner"])].append(row)
    spawn_assignments: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
    for owner, calls in spawn_calls_by_owner.items():
        paired = _spawn_targets(owner=owner, calls=calls, spawn_edges=spawn_edges)
        for call_id, rows in paired.items():
            spawn_assignments[call_id].extend(rows)

    for node in nodes:
        node_id = node.get("id")
        if node_id in depths and node.get("type") == "agent":
            node["attributes"] = {
                **_attrs(node),
                "viewer_flow_rank": depths[str(node_id)] * 3,
                "viewer_execution_flow_identity": True,
            }

    model_context_ids: dict[tuple[str, str], str] = {}
    new_nodes: list[dict[str, Any]] = []
    new_edges: list[dict[str, Any]] = []
    represented_model_ids: set[str] = set()
    for key, observation in sorted(
        model_observations.items(),
        key=lambda item: (
            depths.get(item[0][0], 0),
            item[1].get("first_sequence")
            if item[1].get("first_sequence") is not None
            else 2**63 - 1,
            item[0][1],
        ),
    ):
        owner, model = key
        context_id = _viewer_id("model-context", owner, model)
        model_context_ids[key] = context_id
        model_ids = sorted(observation["model_ids"])
        represented_model_ids.update(model_ids)
        depth = depths.get(owner, 0)
        new_nodes.append(
            {
                "id": context_id,
                "type": "model_context",
                "name": model,
                "first_seen": observation.get("first_seen"),
                "last_seen": observation.get("last_seen"),
                "attributes": {
                    "viewer_only": True,
                    "viewer_model_context": True,
                    "viewer_flow_rank": depth * 3 + 1,
                    "owner_agent_id": owner,
                    "model_name": model,
                    "semantic_model_ids": model_ids,
                    "supporting_edge_ids": sorted(observation["supporting_edge_ids"]),
                    "supporting_call_ids": sorted(observation["supporting_call_ids"]),
                },
            }
        )
        new_edges.append(
            {
                "id": _viewer_id("edge-model-context", owner, context_id),
                "source": owner,
                "target": context_id,
                "relation": "MODEL_CONTEXT",
                "count": max(
                    1,
                    len(observation["supporting_edge_ids"])
                    + len(observation["supporting_call_ids"]),
                ),
                "first_sequence": observation.get("first_sequence"),
                "last_sequence": observation.get("last_sequence"),
                "first_seen": observation.get("first_seen"),
                "last_seen": observation.get("last_seen"),
                "causal": False,
                "inferred": False,
                "viewer_only": True,
                "attributions": ["viewer_model_execution_context"],
                "supporting_edge_ids": sorted(observation["supporting_edge_ids"]),
                "supporting_call_ids": sorted(observation["supporting_call_ids"]),
            }
        )

    action_groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in orchestration_calls:
        action_groups[(str(row["owner"]), str(row["model"]), str(row["action"]))].append(row)

    represented_spawn_edge_ids: set[str] = set()
    action_target_rows: dict[tuple[str, str], dict[str, Any]] = {}
    for (owner, model, action), rows in sorted(
        action_groups.items(),
        key=lambda item: (
            depths.get(item[0][0], 0),
            min(row["first_moment"] for row in item[1]),
            item[0][2],
        ),
    ):
        context_id = model_context_ids.get((owner, model))
        if context_id is None:
            continue
        action_id = _viewer_id("orchestration", owner, model, action)
        depth = depths.get(owner, 0)
        first_row = min(rows, key=lambda row: (row["first_moment"], row["id"]))
        last_row = max(rows, key=lambda row: (row["last_moment"], row["id"]))
        call_ids = sorted(row["id"] for row in rows)
        new_nodes.append(
            {
                "id": action_id,
                "type": "tool_action",
                "name": action,
                "first_seen": first_row["first_moment"][1] or None,
                "last_seen": last_row["last_moment"][1] or None,
                "event_count": len(rows),
                "attributes": {
                    "viewer_only": True,
                    "viewer_orchestration_action": True,
                    "viewer_flow_rank": depth * 3 + 2,
                    "viewer_flow_first_sequence": (
                        None
                        if first_row["first_moment"][0] == 2**63 - 1
                        else first_row["first_moment"][0]
                    ),
                    "owner_agent_id": owner,
                    "model_name": model,
                    "action_kind": action,
                    "call_count": len(rows),
                    "supporting_call_ids": call_ids,
                },
            }
        )
        new_edges.append(
            {
                "id": _viewer_id("edge-model-action", context_id, action_id),
                "source": context_id,
                "target": action_id,
                "relation": "ORCHESTRATED_ACTION",
                "count": len(rows),
                "first_sequence": (
                    None
                    if first_row["first_moment"][0] == 2**63 - 1
                    else first_row["first_moment"][0]
                ),
                "last_sequence": (
                    None if last_row["last_moment"][0] < 0 else last_row["last_moment"][0]
                ),
                "first_seen": first_row["first_moment"][1] or None,
                "last_seen": last_row["last_moment"][1] or None,
                "causal": False,
                "inferred": False,
                "viewer_only": True,
                "attributions": ["viewer_orchestration_projection"],
                "supporting_call_ids": call_ids,
            }
        )

        for row in rows:
            targets = list(row["targets"])
            support_edge_ids: list[str] = []
            semantics = row["target_semantics"]
            if action == "spawn_agent":
                paired = spawn_assignments.get(row["id"], [])
                if paired:
                    targets = [target for target, _ in paired]
                    support_edge_ids = [
                        str(edge.get("id") or "")
                        for _, edge in paired
                        if edge.get("id")
                    ]
                    represented_spawn_edge_ids.update(support_edge_ids)
                    semantics = "provider_spawn_lifecycle_temporal_correlation"
            for target in targets:
                if target not in agent_ids or target == owner:
                    continue
                relation = _ACTION_RELATIONS[action]
                entry = action_target_rows.setdefault(
                    (action_id, target),
                    {
                        "source": action_id,
                        "target": target,
                        "relation": relation,
                        "count": 0,
                        "supporting_call_ids": [],
                        "supporting_edge_ids": [],
                        "selector_support_ids": [],
                        "source_semantics": set(),
                        "first_sequence": None,
                        "last_sequence": None,
                        "first_seen": None,
                        "last_seen": None,
                    },
                )
                entry["count"] += 1
                entry["supporting_call_ids"].append(row["id"])
                entry["supporting_edge_ids"].extend(support_edge_ids)
                entry["selector_support_ids"].extend(row["selector_support"])
                entry["source_semantics"].add(semantics)
                first_seq, first_seen = row["first_moment"]
                last_seq, last_seen = row["last_moment"]
                if first_seq != 2**63 - 1:
                    entry["first_sequence"] = (
                        first_seq
                        if entry["first_sequence"] is None
                        else min(entry["first_sequence"], first_seq)
                    )
                if last_seq >= 0:
                    entry["last_sequence"] = (
                        last_seq
                        if entry["last_sequence"] is None
                        else max(entry["last_sequence"], last_seq)
                    )
                if first_seen:
                    entry["first_seen"] = (
                        first_seen
                        if entry["first_seen"] is None
                        else min(entry["first_seen"], first_seen)
                    )
                if last_seen:
                    entry["last_seen"] = (
                        last_seen
                        if entry["last_seen"] is None
                        else max(entry["last_seen"], last_seen)
                    )

    for (action_id, target), row in sorted(action_target_rows.items()):
        source_semantics = sorted(row.pop("source_semantics"))
        inferred = any("correlation" in value for value in source_semantics)
        new_edges.append(
            {
                "id": _viewer_id(
                    "edge-action-agent", action_id, row["relation"], target
                ),
                **row,
                "supporting_call_ids": sorted(set(row["supporting_call_ids"])),
                "supporting_edge_ids": sorted(set(row["supporting_edge_ids"])),
                "selector_support_ids": sorted(set(row["selector_support_ids"])),
                "source_semantics": source_semantics,
                "causal": False,
                "inferred": inferred,
                "viewer_only": True,
                "attributions": ["viewer_orchestration_projection"],
            }
        )

    kept_nodes = [
        node
        for node in nodes
        if node.get("id") not in represented_model_ids
        and node.get("id") not in orchestration_tool_ids
    ]
    kept_node_ids = {
        str(node["id"]) for node in kept_nodes if isinstance(node.get("id"), str)
    }

    kept_edges: list[dict[str, Any]] = []
    for edge in edges:
        edge_id = str(edge.get("id") or "")
        source, target = edge.get("source"), edge.get("target")
        if edge_id in represented_spawn_edge_ids:
            continue
        if source in represented_model_ids or target in represented_model_ids:
            continue
        if source in orchestration_tool_ids or target in orchestration_tool_ids:
            continue
        if source in kept_node_ids and target in kept_node_ids:
            kept_edges.append(edge)

    result = deepcopy(projected)
    result["nodes"] = [*kept_nodes, *new_nodes]
    result["edges"] = [*kept_edges, *new_edges]
    result["node_count"] = len(result["nodes"])
    result["edge_count"] = len(result["edges"])
    metadata = dict(
        result.get("viewer_projection") or {"schema_version": "0.1", "viewer_only": True}
    )
    metadata.update(
        {
            "kind": "combined",
            "model_context_node_count": len(model_context_ids),
            "orchestration_action_node_count": len(action_groups),
            "orchestration_action_edge_count": len(action_target_rows),
            "orchestration_raw_tool_node_count_hidden": len(orchestration_tool_ids),
            "orchestration_spawn_edges_reanchored": len(represented_spawn_edge_ids),
            "execution_flow_projection": True,
        }
    )
    result["viewer_projection"] = metadata
    return result


def project_model_orchestration_viewer_graph(graph: dict[str, Any]) -> dict[str, Any]:
    """Project model-scoped orchestration flow without changing raw evidence.

    Agent identity is never duplicated. Model contexts and orchestration actions are
    viewer-only context nodes that re-anchor evidence-backed control flow.
    """

    return _project_flow(project_provider_neutral_viewer_graph(graph))
