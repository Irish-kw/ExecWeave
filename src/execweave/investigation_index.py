"""Bounded investigation records from recorded streams and explicit graph edges.

A graph edge can aggregate many messages. Native occurrence IDs, not aggregate
counts, pair send/receive and request/result observations here. This index never
reads provider bodies or workspace files, and never establishes task success.
"""
from __future__ import annotations

import copy
import hashlib
import json
from itertools import islice
import os
from pathlib import Path
import re
import stat
from typing import Any

from .content_integrity import ArchiveReadError, _path_descriptor_stat, _reject_link, _signature

MAX_EVENTS = 100_000
MAX_OBSERVATIONS = 10_000
MAX_BYTES = 32 * 1024 * 1024
MAX_LINE_BYTES = 1024 * 1024
MAX_GRAPH_RECORDS = 100_000
_PATH = re.compile(r"content/sha256/([0-9a-f]{64})\.(?:txt|json|bin)")
_STREAMS = frozenset({"events.jsonl", "semantic.jsonl", "events.semantic.jsonl", "events.correlated.jsonl"})
_PHASES = {
    "MESSAGE_SENT": ("message", "sent", "message_id"),
    "MESSAGE_RECEIVED": ("message", "received", "message_id"),
    "MESSAGE_UNROUTED": ("message", "unrouted", "message_id"),
    "MODEL_REQUEST": ("model", "request", "model_call_id"),
    "MODEL_RESPONSE": ("model", "response", "model_call_id"),
    "MODEL_FAILURE": ("model", "failure", "model_call_id"),
    "TOOL_CALL": ("tool", "request", "tool_call_id"),
    "TOOL_RESULT": ("tool", "response", "tool_call_id"),
    "TOOL_FAILURE": ("tool", "failure", "tool_call_id"),
}


def _obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _id(value: Any) -> str | None:
    # Oversized IDs are rejected, never truncated into another identity.
    return value if isinstance(value, str) and 0 < len(value) <= 2048 else None


def _native(value: dict[str, Any]) -> bool:
    return all(part.get(key) is None or part.get(key) is False
               for part in (value, _obj(value.get("attributes")))
               for key in ("inferred", "viewer_only"))


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _constant(value: str) -> None:
    raise ValueError("nonfinite JSON")


def _scan(root: Path, names: list[str], session: str | None,
          *, max_events: int, max_observations: int, max_bytes: int) -> dict[str, Any]:
    report: dict[str, Any] = {
        "state": "unavailable", "scanned_events": 0, "retained_observations": 0,
        "scope_rejected": 0, "invalid_records": 0, "missing_occurrence_ids": 0,
        "conflicting_event_ids": 0, "limit_reached": False, "streams": [],
        "diagnostics": [],
    }
    records: dict[tuple[str, ...], dict[str, Any]] = {}
    conflicts: set[tuple[str, ...]] = set()
    used_bytes = 0

    def diagnostic(code: str, stream: str) -> None:
        if len(report["diagnostics"]) < 20:
            report["diagnostics"].append({"code": code, "stream": stream})

    for name in names:
        file_records: dict[tuple[str, ...], dict[str, Any]] = {}
        stream = {"name": name, "state": "unavailable", "bytes_read": 0}
        report["streams"].append(stream)
        descriptor = None
        try:
            _reject_link(root)
            path = root / name
            _reject_link(path)
            descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0)
                                 | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode):
                raise ValueError("not_regular_file")
            with os.fdopen(descriptor, "rb") as handle:
                descriptor = None
                line_no = 0
                while True:
                    budget = max_bytes - used_bytes
                    if budget <= 0 or report["scanned_events"] >= max_events:
                        # An exact boundary is complete only at EOF.
                        if handle.read(1):
                            report["limit_reached"] = True
                        break
                    raw = handle.readline(min(MAX_LINE_BYTES + 1, budget + 1))
                    if not raw:
                        break
                    line_no += 1
                    used_bytes += len(raw)
                    stream["bytes_read"] += len(raw)
                    if len(raw) > MAX_LINE_BYTES or used_bytes > max_bytes:
                        report["limit_reached"] = True
                        diagnostic("line_or_byte_limit", name)
                        break
                    if not raw.strip():
                        continue
                    report["scanned_events"] += 1
                    try:
                        event = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_unique,
                                           parse_constant=_constant)
                        if not isinstance(event, dict):
                            raise ValueError("event_not_object")
                    except (ValueError, RecursionError):
                        report["invalid_records"] += 1
                        diagnostic("invalid_event", name)
                        continue
                    phase = _PHASES.get(event.get("event_type")) if isinstance(event.get("event_type"), str) else None
                    if phase is None or not _native(event):
                        continue
                    a = _obj(event.get("attributes"))
                    declared = [part["session_id"] for part in (event, a) if "session_id" in part]
                    if not session or not declared or any(x != session for x in declared):
                        report["scope_rejected"] += 1
                        continue
                    source, target = _obj(event.get("source")), _obj(event.get("target"))
                    if not _native(source) or not _native(target):
                        report["invalid_records"] += 1
                        continue
                    framework = _id(a.get("framework")) or _id(_obj(source.get("attributes")).get("framework"))
                    # Only the framework SDK emits these canonical event names.
                    # Provider-native events remain available through the existing inspector.
                    if framework not in {"camel", "autogen", "metagpt"}:
                        report["invalid_records"] += 1
                        diagnostic("unsupported_canonical_emitter", name)
                        continue
                    kind, state, native_key = phase
                    native_id = _id(a.get(native_key))
                    event_id = _id(event.get("event_id"))
                    if not native_id:
                        report["missing_occurrence_ids"] += 1
                    owner = _id(source.get("id")) if source.get("type") in ("agent", "user") else None
                    target_id = _id(target.get("id")) if target.get("type") in ("agent", "user", "model", "tool") else None
                    if kind != "message" and source.get("type") != "agent":
                        owner = None
                    expected = a.get("sender_agent_id" if kind == "message" else "requesting_agent_id")
                    recipient = a.get("recipient_agent_id") if kind == "message" else None
                    if ((expected is not None and expected != owner) or
                            (recipient is not None and recipient != target_id)):
                        report["invalid_records"] += 1
                        diagnostic("conflicting_participants", name)
                        continue
                    key = (framework, "event", event_id) if event_id else (framework, "line", name, str(line_no))
                    item = {
                        "kind": kind, "phase": state, "framework": framework,
                        "namespace": _id(a.get("run_id")) or session,
                        "native_id": native_id, "event_id": event_id,
                        "owner_id": owner, "target_id": target_id,
                        "source_name": str(source.get("name") or owner or "Unknown sender")[:256],
                        "target_name": str(target.get("name") or target_id or "Unknown recipient")[:256],
                        "stream": name, "line": line_no, "timestamp": _id(event.get("timestamp")),
                        "reference": {"path": a.get("content_ref"), "sha256": a.get("content_sha256"),
                                      "size_bytes": a.get("content_size_bytes"),
                                      "content_kind": _id(a.get("content_kind")),
                                      "complete_from_source": a.get("content_complete_from_source") if type(a.get("content_complete_from_source")) is bool else None},
                        "capture_mode": a.get("capture_mode") if isinstance(a.get("capture_mode"), str) and a.get("capture_mode") in {
                            "metadata_only", "content_ref_only", "prompt_only", "prompt_and_response"} else None,
                        "fingerprint": hashlib.sha256(raw).hexdigest(),
                    }
                    previous = file_records.get(key) or records.get(key)
                    if key in conflicts:
                        continue
                    if previous:
                        # Identical retries/replay are not additional deliveries.
                        left = {k: v for k, v in previous.items() if k not in {"stream", "line", "fingerprint"}}
                        right = {k: v for k, v in item.items() if k not in {"stream", "line", "fingerprint"}}
                        if left != right:
                            conflicts.add(key)
                            file_records.pop(key, None)
                            records.pop(key, None)
                        continue
                    if len(file_records) + len(records) >= max_observations:
                        report["limit_reached"] = True
                        break
                    file_records[key] = item
                after = os.fstat(handle.fileno())
                _reject_link(path)
                if _signature(before) != _signature(after) or _signature(after) != _signature(_path_descriptor_stat(path)):
                    raise ValueError("stream_changed_during_scan")
            records.update(file_records)
            stream["state"] = "partial" if report["limit_reached"] else "scanned"
        except (ArchiveReadError, OSError, RuntimeError, ValueError) as exc:
            stream["state"] = "unavailable"
            diagnostic(type(exc).__name__ + ":" + str(exc)[:120], name)
        finally:
            if descriptor is not None:
                os.close(descriptor)
        if report["limit_reached"]:
            break
    report["conflicting_event_ids"] = len(conflicts)
    report["retained_observations"] = len(records)
    if any(s["state"] == "scanned" for s in report["streams"]):
        report["state"] = "scanned_selected_streams"
    if (report["limit_reached"] or report["scope_rejected"] or report["invalid_records"] or conflicts or
            any(s["state"] != "scanned" for s in report["streams"])):
        report["state"] = "partial" if records else "unavailable"
    return {"observations": list(records.values()), "inspection": report}


class InvestigationCache:
    """One bounded stream snapshot per Live state; no process-global content cache."""

    def __init__(self) -> None:
        # Publish the key and value atomically; concurrent HTTP readers must
        # never observe a new scope key paired with an older run's snapshot.
        self.entry: tuple[object, dict[str, Any]] | None = None


def _graph_nodes(graph: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]], bool]:
    nodes: dict[str, dict[str, Any]] = {}
    ambiguous: set[str] = set()
    edges = []
    containers = [graph]
    clusters = _obj(_obj(graph.get("expansion")).get("clusters"))
    containers.extend(v for v in islice(clusters.values(), 1000) if isinstance(v, dict))
    remaining = MAX_GRAPH_RECORDS
    partial = len(clusters) > 1000
    for container in containers:
        for kind in ("nodes", "edges"):
            rows = container.get(kind, [])
            if not isinstance(rows, list):
                partial = True
                continue
            for row in rows:
                if not remaining:
                    return {k: v for k, v in nodes.items() if k not in ambiguous}, edges, True
                remaining -= 1
                if not isinstance(row, dict):
                    partial = True
                    continue
                if not _native(row):
                    continue
                if kind == "edges":
                    edges.append(row)
                elif _id(row.get("id")):
                    key = row["id"]
                    if key in nodes and nodes[key] != row:
                        ambiguous.add(key)
                    else:
                        nodes[key] = row
    return {k: v for k, v in nodes.items() if k not in ambiguous}, edges, partial or bool(ambiguous)


def build_investigation_index(graph: dict[str, Any], run_root: str | Path, *,
                              cache: InvestigationCache | None = None,
                              max_events: int = MAX_EVENTS, max_observations: int = MAX_OBSERVATIONS,
                              max_bytes: int = MAX_BYTES) -> dict[str, Any]:
    """Join only native occurrences in this run; reference bytes are never opened.

    File names are a fixed allowlist under the supplied run folder. Original
    absolute source paths are labels, not file access capabilities. Old archives
    without streams still provide graph-backed roles and snapshot references.
    """
    if any(type(x) is not int or x < 0 for x in (max_events, max_observations, max_bytes)):
        raise ValueError("inspection limits must be nonnegative integers")
    root = Path(run_root).expanduser().absolute()
    session = _id(graph.get("session_id"))
    source = _id(graph.get("source_path"))
    source_name = re.split(r"[/\\]", source or "")[-1]
    names = [source_name] if source_name in _STREAMS and (root / source_name).exists() else []
    if not names or names == ["events.jsonl"]:
        if (root / "semantic.jsonl").exists():
            names = ["semantic.jsonl"]
    names = list(dict.fromkeys(names))
    signatures = []
    for name in names:
        try:
            _reject_link(root / name)
            value = (root / name).stat()
            signatures.append((name, _signature(value)))
        except (ArchiveReadError, OSError, RuntimeError, ValueError):
            signatures.append((name, None))
    cache_key = (str(root), session, source, tuple(signatures), max_events, max_observations, max_bytes)
    cached = cache.entry if cache is not None else None
    if cached is not None and cached[0] == cache_key:
        scanned = cached[1]
    else:
        scanned = _scan(root, names, session, max_events=max_events,
                        max_observations=max_observations, max_bytes=max_bytes)
        # Do not cache an in-flight partial/mutating scan as a stable success.
        if cache is not None:
            cache.entry = (cache_key, scanned) if scanned["inspection"]["state"] == "scanned_selected_streams" else None
    nodes, edges, graph_partial = _graph_nodes(graph)
    declared: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for node in nodes.values():
        a = _obj(node.get("attributes"))
        if node.get("type") == "observed_content" and isinstance(a.get("path"), str) and isinstance(a.get("sha256"), str):
            declared.setdefault((a["path"], a["sha256"]), []).append(a)

    def registered(ref: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
        path, digest = ref.get("path"), ref.get("sha256")
        if path is None and digest is None:
            return "not_recorded", None
        match = _PATH.fullmatch(path) if isinstance(path, str) else None
        if not match or match[1] != digest or type(ref.get("size_bytes")) is not int or ref["size_bytes"] < 0:
            return "invalid_reference", None
        matches = declared.get((path, digest), [])
        if not matches or any(type(a.get("size_bytes")) is not int or a["size_bytes"] != ref["size_bytes"] for a in matches):
            return "not_in_graph_inventory", None
        # All references displayed here are also covered by the existing graph
        # reference verifier. No hidden second class of archive references.
        return "registered_not_read", {
            "path": path, "sha256": digest, "size_bytes": ref["size_bytes"],
            "content_kind": _id(ref.get("content_kind")),
            "complete_from_source": ref.get("complete_from_source") if type(ref.get("complete_from_source")) is bool else None,
        }

    groups: dict[tuple[Any, ...], dict[str, Any]] = {}
    for observation in scanned["observations"]:
        o = observation
        key = (o["namespace"], o["framework"], o["kind"],
               o["native_id"] if o["native_id"] and o["owner_id"] and o["target_id"] else (o["stream"], o["line"]), o["owner_id"], o["target_id"])
        row = groups.setdefault(key, {
            "key": json.dumps(key, ensure_ascii=False, separators=(",", ":")),
            "kind": o["kind"], "native_id": o["native_id"], "framework": o["framework"],
            "owner_id": o["owner_id"], "target_id": o["target_id"],
            "source_name": o["source_name"], "target_name": o["target_name"],
            "identity_bound": bool(o["native_id"] and o["owner_id"] and o["target_id"]),
            "observations": [], "references": [], "phases": [],
        })
        phase = o["phase"]
        if phase not in row["phases"]:
            row["phases"].append(phase)
        state, reference = registered(o["reference"])
        row["observations"].append({k: o[k] for k in ("phase", "event_id", "stream", "line", "timestamp", "capture_mode")})
        # Keep each observed phase separate even if the bytes have equal hashes.
        row["references"].append({"phase": phase, "state": state, "reference": reference,
                                  "event_id": o["event_id"]})
    rows = list(groups.values())
    agents = [{"id": n["id"], "name": str(n.get("name") or n["id"])[:256],
               "provider": str(_obj(n.get("attributes")).get("provider") or "unknown")[:80],
               "role": str(_obj(n.get("attributes")).get("role") or _obj(n.get("attributes")).get("agent_role") or "")[:256]}
              for n in nodes.values() if n.get("type") == "agent"]
    files = []
    outgoing: dict[str, list[dict[str, Any]]] = {}
    incoming: dict[str, list[dict[str, Any]]] = {}
    for edge in edges:
        if _id(edge.get("source")) and _id(edge.get("target")):
            outgoing.setdefault(edge["source"], []).append(edge)
            incoming.setdefault(edge["target"], []).append(edge)
    for n in nodes.values():
        if n.get("type") not in ("file", "artifact"):
            continue
        snapshots = []
        related_content = []
        for e in outgoing.get(n["id"], []):
            peer = nodes.get(e["target"], {})
            if peer.get("type") != "observed_content":
                continue
            state, ref = registered(_obj(peer.get("attributes")))
            record = {"relation": _id(e.get("relation")), "edge_id": _id(e.get("id")),
                      "timestamp": _id(e.get("first_seen")), "state": state, "reference": ref}
            # Only the capture contract that explicitly records file bytes before
            # a read establishes a file snapshot. An arbitrary associated payload
            # is still inspectable, but is not silently promoted to file contents.
            destination = snapshots if e.get("relation") == "OBSERVED_FILE_CONTENT_BEFORE_READ" else related_content
            destination.append(record)
        relations = [{"source": e.get("source"), "target": e.get("target"), "relation": e.get("relation"),
                      "edge_id": e.get("id"), "causal": e.get("causal")}
                     for e in incoming.get(n["id"], [])[:50]]
        files.append({"id": n["id"], "name": str(n.get("name") or n["id"])[:512],
                      "snapshots": snapshots[:50], "snapshot_count": len(snapshots),
                      "related_content": related_content[:50], "related_content_count": len(related_content),
                      "relations": relations, "relation_count": len(incoming.get(n["id"], []))})
    event_call_ids = {r["native_id"] for r in rows if r["kind"] != "message" and r["native_id"]}
    call_relations = {"HAS_TOOL_INPUT": "request", "HAS_TOOL_OUTPUT": "response",
                      "OBSERVED_INFERENCE_REQUEST": "request", "OBSERVED_INFERENCE_RESPONSE": "response"}
    owners = {"REQUESTED_TOOL_CALL", "REQUESTS_TOOL_CALL", "ISSUED_TOOL_CALL", "REQUESTS_MODEL_CALL"}
    for n in nodes.values():
        if n.get("type") not in ("tool_call", "model_call", "inference_request") or n["id"] in event_call_ids:
            continue
        # Framework call records use the event-stream contract above. Do not
        # revive a rejected framework occurrence through its aggregate graph.
        if _id(_obj(n.get("attributes")).get("framework")) in {"camel", "autogen", "metagpt"}:
            continue
        kind = "tool" if n["type"] == "tool_call" else "model"
        candidates = sorted({e["source"] for e in incoming.get(n["id"], [])
                             if _id(e.get("relation")) in owners and nodes.get(e["source"], {}).get("type") == "agent"})
        owner = candidates[0] if len(candidates) == 1 else None
        target_type = "tool" if kind == "tool" else "model"
        targets = sorted({e["target"] for e in outgoing.get(n["id"], [])
                          if _id(e.get("relation")) in {"USES_TOOL", "USED_MODEL"} and nodes.get(e["target"], {}).get("type") == target_type})
        target = targets[0] if len(targets) == 1 else None
        refs = []
        phases = []
        for e in outgoing.get(n["id"], []):
            peer = nodes.get(e["target"], {})
            if peer.get("type") != "observed_content":
                continue
            relation = _id(e.get("relation"))
            phase = call_relations.get(relation, "supplemental_content")
            if phase not in phases:
                phases.append(phase)
            state, ref = registered(_obj(peer.get("attributes")))
            refs.append({"phase": phase, "relation": relation, "state": state, "reference": ref,
                         "edge_id": _id(e.get("id")), "event_ids": [_id(x) for x in e.get("event_ids", [])[:20]]
                         if isinstance(e.get("event_ids"), list) else []})
        rows.append({"key": "graph:" + n["id"], "kind": kind, "native_id": n["id"],
                     "framework": _id(_obj(n.get("attributes")).get("provider")),
                     "owner_id": owner, "target_id": target,
                     "source_name": str(nodes.get(owner, {}).get("name") or owner or "Unknown owner")[:256],
                     "target_name": str(nodes.get(target, {}).get("name") or n.get("name") or n["id"])[:256],
                     "identity_bound": bool(owner and target), "observation_basis": "explicit_graph_call",
                     "owner_candidates": candidates[:20], "target_candidates": targets[:20],
                     "observations": [], "references": refs[:50], "reference_count": len(refs), "phases": phases})
    inspection = copy.deepcopy(scanned["inspection"])
    inspection["graph_inventory_partial"] = graph_partial or bool(graph.get("live_payload_compact")) or bool(graph.get("viewer_projection"))
    inspection["agent_rows_omitted"] = max(0, len(agents) - 10_000)
    inspection["call_rows_omitted"] = max(0, sum(r["kind"] != "message" for r in rows) - 10_000)
    inspection["artifact_rows_omitted"] = max(0, len(files) - 10_000)
    if inspection["agent_rows_omitted"] or inspection["artifact_rows_omitted"] or inspection["call_rows_omitted"]:
        inspection["graph_inventory_partial"] = True
    return {
        "schema_version": "0.1", "scope": "recorded_event_investigation", "session_id": session,
        "source_path": source, "inspection": inspection, "agents": agents[:10_000],
        "messages": [r for r in rows if r["kind"] == "message"],
        "calls": [r for r in rows if r["kind"] in {"tool", "model"}][:10_000], "artifacts": files[:10_000],
        "limits": {"events": max_events, "observations": max_observations, "stream_bytes": max_bytes,
                   "agents": 10_000, "calls": 10_000, "artifacts": 10_000, "references_per_graph_row": 50},
        "denominator_version": "observed-native-occurrences-v1",
    }
