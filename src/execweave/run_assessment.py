"""Conservative run assessment from declared graph metadata, without file I/O.

Process exit, native task reports, and content availability are different facts.
A task-completed event is not an independent test result. A well-formed content
reference is not proof that its bytes exist or that capture was exhaustive.
"""
from __future__ import annotations

import re

from .task_validation import assessment_subjects
from typing import Any

SCHEMA_VERSION = "0.1"
MAX_RECORDS = 100_000
_REFERENCE = re.compile(r"content/sha256/([0-9a-f]{64})\.(?:txt|json|bin)")


def _object(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _native(record: dict[str, Any]) -> bool:
    attributes = _object(record.get("attributes"))
    return not any(
        scope.get(flag) is not None and scope.get(flag) is not False
        for scope in (record, attributes)
        for flag in ("inferred", "viewer_only")
    )


def _execution(graph: dict[str, Any]) -> dict[str, Any]:
    outcome = _object(graph.get("session_outcome"))
    code = outcome.get("return_code")
    code = code if type(code) is int else None
    event_id = _text(outcome.get("event_id"))
    result = {
        "state": "unknown", "reason": "no_terminal_evidence", "return_code": code,
        "event_id": event_id, "timestamp": _text(outcome.get("timestamp")),
        "task_success_implied": False,
    }
    if outcome.get("recorder_finished") is not True or event_id is None:
        return result
    if any(key in outcome and type(outcome[key]) is not bool
           for key in ("collector_failed", "interrupted")):
        result["reason"] = "invalid_terminal_metadata"
        return result
    state = (
        "collector_failed" if outcome.get("collector_failed") is True else
        "interrupted" if outcome.get("interrupted") is True else
        "succeeded" if code == 0 else "failed" if code is not None else "unknown"
    )
    declared = outcome.get("state")
    if declared not in (None, state):
        result["reason"] = "conflicting_terminal_metadata"
        return result
    result.update(state=state, reason="recorded_terminal_event" if state != "unknown"
                  else "terminal_exit_unavailable")
    return result


def build_run_assessment(graph: dict[str, Any], *, max_records: int = MAX_RECORDS) -> dict[str, Any]:
    """Read only graph nodes/edges and named expansion containers.

    The inspection budget bounds work and provenance lists. Exhaustion or a
    compact/projected input is reported, not converted into a complete inventory.
    Provider bodies and arbitrary nested dictionaries are never interpreted.
    """
    if type(max_records) is not int or max_records < 0:
        raise ValueError("max_records must be a nonnegative integer")
    graph = _object(graph)
    remaining = max_records
    nodes: dict[str, dict[str, Any]] = {}
    ambiguous: set[str] = set()
    edges: list[dict[str, Any]] = []
    limited = False
    invalid = 0

    def collect(container: dict[str, Any]) -> None:
        nonlocal remaining, limited, invalid
        for key in ("nodes", "edges"):
            items = container.get(key)
            if not isinstance(items, list):
                invalid += 1
                continue
            for item in items:
                if remaining == 0:
                    limited = True
                    return
                remaining -= 1
                if not isinstance(item, dict):
                    invalid += 1
                    continue
                if key == "edges":
                    edges.append(item)
                    continue
                node_id = _text(item.get("id"))
                if node_id is None:
                    invalid += 1
                    continue
                if node_id in nodes and nodes[node_id] != item:
                    ambiguous.add(node_id)
                else:
                    nodes[node_id] = item

    collect(graph)
    expansion = _object(graph.get("expansion")).get("clusters", {})
    if isinstance(expansion, dict):
        for cluster in expansion.values():
            if remaining == 0:
                limited = True
                break
            remaining -= 1
            if isinstance(cluster, dict):
                collect(cluster)
            else:
                invalid += 1
    else:
        invalid += 1
    for node_id in ambiguous:
        nodes.pop(node_id, None)
    task_ids = {key for key, node in nodes.items() if node.get("type") == "task" and _native(node)}
    completed: set[str] = set()
    failed: set[str] = set()
    reports: list[dict[str, Any]] = []
    for edge in edges:
        if not _native(edge) or _text(edge.get("relation")) not in {"TASK_COMPLETED", "TASK_FAILED"}:
            continue
        target = edge.get("target")
        source = nodes.get(edge.get("source")) if isinstance(edge.get("source"), str) else None
        if not isinstance(target, str) or target not in task_ids or not source:
            continue
        if source.get("type") not in ("agent", "task") or not _native(source):
            continue
        (completed if edge["relation"] == "TASK_COMPLETED" else failed).add(target)
        if len(reports) < 20:
            reports.append({"task_id": target, "edge_id": _text(edge.get("id")),
                            "relation": edge["relation"], "source_id": edge.get("source")})

    counts = {key: 0 for key in ("declared", "valid_references", "invalid_references",
                               "source_partial", "source_completeness_unknown", "opaque", "redacted")}
    files: set[str] = set()
    for node in nodes.values():
        if node.get("type") != "observed_content" or not _native(node):
            continue
        a = _object(node.get("attributes"))
        counts["declared"] += 1
        path, digest = a.get("path"), a.get("sha256")
        match = _REFERENCE.fullmatch(path) if isinstance(path, str) else None
        size_ok = "size_bytes" not in a or (type(a["size_bytes"]) is int and a["size_bytes"] >= 0)
        valid = match is not None and match[1] == digest and size_ok
        counts["valid_references" if valid else "invalid_references"] += 1
        if valid:
            files.add(path)
        if a.get("complete_from_source") is False:
            counts["source_partial"] += 1
        elif a.get("complete_from_source") is not True:
            counts["source_completeness_unknown"] += 1
        representation = _text(a.get("representation"))
        if representation in {"opaque_encrypted", "opaque_signed", "encrypted"}:
            counts["opaque"] += 1
        if representation == "redacted" or a.get("redacted") is True:
            counts["redacted"] += 1

    projected = bool(graph.get("live_payload_compact") or graph.get("viewer_projection"))
    scope = "partial" if limited or invalid or ambiguous or projected else "declared_graph"
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": _text(graph.get("run_id")),
        "session_id": _text(graph.get("session_id")),
        "source_path": _text(graph.get("source_path")),
        "scope": "published_graph_metadata",
        "inspection": {"state": scope, "limit_reached": limited,
                       "inspected_records": max_records - remaining,
                       "invalid_records": invalid, "ambiguous_node_ids": len(ambiguous)},
        "execution": _execution(graph),
        "task_validation": {**assessment_subjects(list(nodes.values())), "state": "unverified", "reason": "no_independent_validation_contract",
                            "declared_tasks": len(task_ids), "reported_completed": len(completed),
                            "reported_failed": len(failed), "both_reported": len(completed & failed),
                            "reports": reports},
        "content": {**counts, "unique_declared_files": len(files), "bytes_verified": None,
                    "state": "declared_gaps" if counts["invalid_references"] or counts["source_partial"]
                    else "not_verified", "archive_state": "not_checked_in_this_view"},
    }
