from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from pathlib import Path
from typing import Any

ORPHAN_FILES_NODE_ID = "viewer-cluster:orphan-files"
MODEL_RELATIONS = {"USED_MODEL": 0, "INVOKED_MODEL": 1, "REQUESTED_MODEL": 2}


def _attrs(node: dict[str, Any]) -> dict[str, Any]:
    value = node.get("attributes")
    return value if isinstance(value, dict) else {}


def _provider(node: dict[str, Any]) -> str:
    attrs = _attrs(node)
    for key in ("provider", "provider_name", "gateway", "runtime"):
        value = attrs.get(key)
        if isinstance(value, str) and value:
            return value.lower()
    parts = str(node.get("id") or "").split(":", 2)
    return parts[1].lower() if len(parts) > 2 else "unknown"


def _entries(graph: dict[str, Any]) -> list[dict[str, Any]]:
    source = graph.get("source_path")
    if not isinstance(source, str) or not source:
        return []
    try:
        from .conversation_records import conversation_record_entries

        return conversation_record_entries(graph, Path(source).expanduser().resolve(strict=False).parent)
    except (OSError, RuntimeError, ValueError):
        return []


def _roots(nodes: list[dict[str, Any]], entries: list[dict[str, Any]]) -> tuple[list[str], dict[str, list[str]]]:
    agents = {str(n["id"]): n for n in nodes if n.get("type") == "agent" and isinstance(n.get("id"), str)}
    roots: set[str] = set()
    by_provider: dict[str, set[str]] = defaultdict(set)
    for node_id, node in agents.items():
        attrs = _attrs(node)
        if attrs.get("agent_role") == "root" or "/root" in {
            str(node.get("name") or ""), str(attrs.get("agent_path") or ""), str(attrs.get("root_agent_path") or "")
        }:
            roots.add(node_id)
    for entry in entries:
        preview = entry.get("conversation_preview") if isinstance(entry, dict) else None
        source_id = entry.get("source_id") if isinstance(entry, dict) else None
        if isinstance(preview, dict) and preview.get("is_root") is True and isinstance(source_id, str) and source_id in agents:
            roots.add(source_id)
            by_provider[str(entry.get("provider") or _provider(agents[source_id])).lower()].add(source_id)
    if not roots and len(agents) == 1:
        roots.add(next(iter(agents)))
    for root in roots:
        provider = _provider(agents[root])
        if provider != "unknown":
            by_provider[provider].add(root)
    return sorted(roots), {key: sorted(value) for key, value in by_provider.items()}


def _components(ids: set[str], edges: list[dict[str, Any]]) -> list[list[str]]:
    parent = {value: value for value in ids}
    def find(value: str) -> str:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value
    for edge in edges:
        if edge.get("relation") != "SAME_INFERENCE_REQUEST":
            continue
        a, b = edge.get("source"), edge.get("target")
        if isinstance(a, str) and a in ids and isinstance(b, str) and b in ids:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra
    groups: dict[str, list[str]] = defaultdict(list)
    for value in ids:
        groups[find(value)].append(value)
    return [sorted(value) for value in groups.values()]


def _matching_entries(ids: set[str], entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        entry for entry in entries if isinstance(entry, dict)
        and (entry.get("source_id") in ids or entry.get("evidence_source_id") in ids)
    ]


def _messages(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[Any, ...]] = set()
    out: list[dict[str, Any]] = []
    for entry in entries:
        preview = entry.get("conversation_preview")
        if not isinstance(preview, dict):
            continue
        for message in preview.get("messages") or []:
            if not isinstance(message, dict) or not isinstance(message.get("text"), str) or not message["text"].strip():
                continue
            key = (message.get("timestamp"), message.get("ordinal"), message.get("kind"), message.get("sender"), message["text"])
            if key in seen:
                continue
            seen.add(key)
            text = message["text"]
            out.append({
                "timestamp": message.get("timestamp"), "ordinal": message.get("ordinal"),
                "kind": message.get("kind"), "sender": message.get("sender"),
                "recipient": message.get("recipient"), "phase": message.get("phase"),
                "text": text[:4000], "text_truncated": len(text) > 4000,
            })
    out.sort(key=lambda m: (str(m.get("timestamp") or ""), m.get("ordinal") if isinstance(m.get("ordinal"), int) else 2**63 - 1))
    return out


def _content_refs(ids: set[str], edges: list[dict[str, Any]], node_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for edge in edges:
        a, b = edge.get("source"), edge.get("target")
        if a not in ids and b not in ids:
            continue
        other = b if a in ids else a
        node = node_by_id.get(str(other))
        if not node or node.get("type") != "observed_content":
            continue
        key = (str(other), str(edge.get("relation") or ""))
        if key in seen:
            continue
        seen.add(key)
        attrs = _attrs(node)
        out.append({"id": other, "relation": edge.get("relation"), "content_kind": attrs.get("content_kind"), "path": attrs.get("path"), "sha256": attrs.get("sha256")})
    return out


def collapse_inference_requests(nodes: list[dict[str, Any]], edges: list[dict[str, Any]], entries: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    node_by_id = {str(n["id"]): n for n in nodes if isinstance(n.get("id"), str)}
    request_ids = {node_id for node_id, node in node_by_id.items() if node.get("type") == "inference_request"}
    if not request_ids:
        return nodes, edges, {"collapsed_request_count": 0, "logical_inference_count": 0, "direct_inference_edge_count": 0, "unresolved": []}
    roots, roots_by_provider = _roots(nodes, entries)
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    unresolved: list[dict[str, Any]] = []
    hidden_content: set[str] = set()
    for component in _components(request_ids, edges):
        members = set(component)
        matches = _matching_entries(members, entries)
        owner = next((str(e.get("source_id")) for e in matches if node_by_id.get(str(e.get("source_id")), {}).get("type") == "agent"), None)
        if owner is None:
            providers = {str(e.get("provider") or "").lower() for e in matches if e.get("provider")}
            if not providers:
                providers = {_provider(node_by_id[value]) for value in members}
            candidates = {root for provider in providers for root in roots_by_provider.get(provider, [])}
            owner = next(iter(candidates)) if len(candidates) == 1 else (roots[0] if len(roots) == 1 else None)
        model_edges = [
            edge for edge in edges if edge.get("source") in members and edge.get("relation") in MODEL_RELATIONS
            and isinstance(edge.get("target"), str) and node_by_id.get(str(edge.get("target")), {}).get("type") == "model"
        ]
        model_edges.sort(key=lambda edge: MODEL_RELATIONS.get(str(edge.get("relation")), 99))
        model_id = str(model_edges[0]["target"]) if model_edges else None
        if owner is None or model_id is None:
            unresolved.append({"request_ids": sorted(members), "reason": "missing_owner" if owner is None else "missing_model"})
            continue
        related = [edge for edge in edges if edge.get("source") in members or edge.get("target") in members]
        first_seen = min((str(edge.get("first_seen")) for edge in related if edge.get("first_seen")), default=None)
        last_seen = max((str(edge.get("last_seen")) for edge in related if edge.get("last_seen")), default=None)
        seqs = [edge.get("first_sequence") for edge in related if isinstance(edge.get("first_sequence"), int)]
        last_seqs = [edge.get("last_sequence") for edge in related if isinstance(edge.get("last_sequence"), int)]
        refs = _content_refs(members, edges, node_by_id)
        hidden_content.update(str(ref["id"]) for ref in refs if ref.get("id"))
        providers = sorted({_provider(node_by_id[value]) for value in members})
        grouped[(owner, model_id)].append({
            "request_ids": sorted(members), "provider": providers[0] if len(providers) == 1 else providers,
            "model_id": model_id, "first_seen": first_seen, "last_seen": last_seen,
            "first_sequence": min(seqs) if seqs else None, "last_sequence": max(last_seqs) if last_seqs else None,
            "messages": _messages(matches), "content_references": refs,
        })
    hidden = set(request_ids)
    for content_id in list(hidden_content):
        incident = [edge for edge in edges if edge.get("source") == content_id or edge.get("target") == content_id]
        if all((edge.get("source") in request_ids or edge.get("target") in request_ids) for edge in incident):
            hidden.add(content_id)
    kept_nodes = [deepcopy(node) for node in nodes if node.get("id") not in hidden]
    kept_edges = [deepcopy(edge) for edge in edges if edge.get("source") not in hidden and edge.get("target") not in hidden]
    for (owner, model_id), occurrences in grouped.items():
        occurrences.sort(key=lambda item: (str(item.get("first_seen") or ""), item.get("first_sequence") if isinstance(item.get("first_sequence"), int) else 2**63 - 1))
        kept_edges.append({
            "id": f"viewer:{owner}--INFERRED-->{model_id}", "source": owner, "target": model_id,
            "relation": "INFERRED", "count": len(occurrences), "evidence_event_count": len(occurrences),
            "first_seen": occurrences[0].get("first_seen"), "last_seen": occurrences[-1].get("last_seen"),
            "first_sequence": occurrences[0].get("first_sequence"), "last_sequence": occurrences[-1].get("last_sequence"),
            "causal": False, "inferred": False, "viewer_only": True,
            "attributions": ["viewer_provider_inference_projection"], "viewer_occurrences": occurrences,
        })
    return kept_nodes, kept_edges, {
        "collapsed_request_count": len(request_ids), "logical_inference_count": sum(len(v) for v in grouped.values()),
        "direct_inference_edge_count": len(grouped), "unresolved": unresolved,
    }


def _file_path(node: dict[str, Any]) -> str:
    attrs = _attrs(node)
    for value in (attrs.get("path"), attrs.get("file_path"), attrs.get("source_path"), attrs.get("target_path"), node.get("name"), node.get("id")):
        if isinstance(value, str) and value:
            return value.removeprefix("file:").removeprefix("directory:")
    return "unknown"


def collapse_orphan_files(nodes: list[dict[str, Any]], edges: list[dict[str, Any]], root_id: str | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any] | None]:
    degree: dict[str, int] = defaultdict(int)
    for edge in edges:
        for value in (edge.get("source"), edge.get("target")):
            if isinstance(value, str): degree[value] += 1
    members = [node for node in nodes if node.get("type") in {"file", "directory"} and isinstance(node.get("id"), str) and degree.get(str(node["id"]), 0) == 0]
    if not members: return nodes, edges, None
    entries = [{"id": n.get("id"), "type": n.get("type"), "name": n.get("name"), "path": _file_path(n), "first_seen": n.get("first_seen"), "last_seen": n.get("last_seen"), "event_count": int(n.get("event_count") or 0), "event_types": list(n.get("event_types") or [])} for n in sorted(members, key=_file_path)]
    first = min((str(n.get("first_seen")) for n in members if n.get("first_seen")), default=None)
    last = max((str(n.get("last_seen")) for n in members if n.get("last_seen")), default=None)
    cluster = {"id": ORPHAN_FILES_NODE_ID, "type": "file_cluster", "name": "Files / directories", "attributes": {"viewer_only": True, "collapsed": True, "expandable": True, "reason": "orphan_file_directory_nodes", "member_count": len(members), "entries": entries, "viewer_occurrences": entries}, "first_seen": first, "last_seen": last, "event_count": sum(int(n.get("event_count") or 0) for n in members)}
    ids = {str(n["id"]) for n in members}
    out_nodes = [deepcopy(n) for n in nodes if n.get("id") not in ids] + [cluster]
    out_edges = [deepcopy(e) for e in edges]
    edge_id = None
    if root_id:
        edge_id = f"viewer:{root_id}--OBSERVED_FILES-->{ORPHAN_FILES_NODE_ID}"
        out_edges.append({"id": edge_id, "source": root_id, "target": ORPHAN_FILES_NODE_ID, "relation": "OBSERVED_FILES", "count": len(members), "first_seen": first, "last_seen": last, "causal": False, "inferred": False, "viewer_only": True})
    return out_nodes, out_edges, {"cluster_node_id": ORPHAN_FILES_NODE_ID, "cluster_edge_id": edge_id, "nodes": deepcopy(members), "edges": [], "viewer_only": True}


def orphan_audit(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> dict[str, Any]:
    degree: dict[str, int] = defaultdict(int)
    for edge in edges:
        for value in (edge.get("source"), edge.get("target")):
            if isinstance(value, str): degree[value] += 1
    grouped: dict[str, list[str]] = defaultdict(list)
    for node in nodes:
        node_id = node.get("id")
        if isinstance(node_id, str) and degree.get(node_id, 0) == 0:
            grouped[str(node.get("type") or "unknown")].append(node_id)
    by_type = [{"node_type": kind, "count": len(ids), "examples": sorted(ids)[:8]} for kind, ids in sorted(grouped.items())]
    return {"count": sum(item["count"] for item in by_type), "by_type": by_type}


def project_provider_neutral_viewer_graph(graph: dict[str, Any]) -> dict[str, Any]:
    """Provider-neutral display projection; raw graph/evidence remains unchanged."""
    from . import viewer_projection_base as base
    from .viewer_external_endpoints import LOCAL_NODE_ID, collapse_local_endpoints

    decorated = base.decorate_viewer_content_references(graph)
    filtered, hook_nodes, hook_edges = base._without_internal_hook_processes(decorated)
    nodes = [deepcopy(n) for n in filtered.get("nodes", []) if isinstance(n, dict)]
    edges = [deepcopy(e) for e in filtered.get("edges", []) if isinstance(e, dict)]
    entries = _entries(graph)
    nodes, edges, inference = collapse_inference_requests(nodes, edges, entries)
    roots, _ = _roots(nodes, entries)
    nodes, edges, files = collapse_orphan_files(nodes, edges, roots[0] if len(roots) == 1 else None)
    nodes, edges, local = collapse_local_endpoints(nodes, edges)

    per_model: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in edges:
        if edge.get("relation") == "INFERRED" and isinstance(edge.get("target"), str) and isinstance(edge.get("viewer_occurrences"), list):
            per_model[str(edge["target"])].extend(deepcopy(edge["viewer_occurrences"]))
    if per_model:
        rewritten = []
        for node in nodes:
            node_id = node.get("id")
            if not isinstance(node_id, str) or node_id not in per_model:
                rewritten.append(node); continue
            occurrences = sorted(per_model[node_id], key=lambda item: (str(item.get("first_seen") or ""), item.get("first_sequence") if isinstance(item.get("first_sequence"), int) else 2**63 - 1))
            rewritten.append({**node, "attributes": {**_attrs(node), "viewer_inference_occurrences": occurrences, "viewer_inference_count": len(occurrences)}})
        nodes = rewritten

    result = deepcopy(filtered)
    result.update({"nodes": nodes, "edges": edges, "node_count": len(nodes), "edge_count": len(edges)})
    meta = dict(result.get("viewer_projection") or {"schema_version": "0.1", "viewer_only": True})
    meta.update({
        "kind": "provider_neutral_semantics", "local_endpoint_policy": "all_loopback",
        "local_endpoint_count": len(local.get("nodes") or []) if local else 0,
        "orphan_file_node_count": len(files.get("nodes") or []) if files else 0,
        "inference_request_count": inference["collapsed_request_count"], "logical_inference_count": inference["logical_inference_count"],
        "direct_inference_edge_count": inference["direct_inference_edge_count"], "unresolved_inference_requests": inference["unresolved"],
        "internal_hook_node_count": len(hook_nodes), "internal_hook_edge_count": len(hook_edges),
    })
    payload = deepcopy(result.get("expansion")) if isinstance(result.get("expansion"), dict) else {}
    clusters = deepcopy(payload.get("clusters")) if isinstance(payload.get("clusters"), dict) else {}
    if local: clusters[LOCAL_NODE_ID] = local
    if files: clusters[ORPHAN_FILES_NODE_ID] = files
    if clusters:
        payload.setdefault("schema_version", "0.1"); payload["clusters"] = clusters; result["expansion"] = payload
    meta["orphan_audit"] = orphan_audit(nodes, edges)
    result["viewer_projection"] = meta
    return result
