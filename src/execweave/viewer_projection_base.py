from __future__ import annotations

import hashlib
import ipaddress
import json
import webbrowser
from collections import defaultdict
from copy import deepcopy
from pathlib import Path
from typing import Any

from .graph_ops import load_graph
from .viewer import (
    VIEWER_MAX_DOM_ELEMENTS as VIEWER_MAX_DOM_ELEMENTS,
    VIEWER_MAX_EDGES as VIEWER_MAX_EDGES,
    VIEWER_MAX_NODES as VIEWER_MAX_NODES,
    render_graph_html as _render_graph_html,
)
from .viewer_content_inspector import (
    decorate_viewer_content_references,
    inject_standalone_content_inspector,
)

EPHEMERAL_PORT_MIN = 49152
LOOPBACK_CLUSTER_THRESHOLD = 4
_PROJECTION_SCHEMA_VERSION = "0.1"
_INTERNAL_HOOK_TOKENS = (
    "execweave-claude-hook",
    "execweave-codex-hook",
    "execweave-antigravity-hook",
    "execweave-cursor-hook",
    "execweave-opencode-hook",
    "execweave-opencode-plugin",
)


def _endpoint_host_port(node: dict[str, Any]) -> tuple[str, int] | None:
    raw = node.get("name")
    if not isinstance(raw, str) or not raw:
        node_id = node.get("id")
        if not isinstance(node_id, str) or not node_id.startswith("endpoint:"):
            return None
        raw = node_id[len("endpoint:") :]
    host, separator, port_text = raw.rpartition(":")
    if not separator or not host or not port_text:
        return None
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    try:
        port = int(port_text)
        address = ipaddress.ip_address(host)
    except ValueError:
        return None
    if not (EPHEMERAL_PORT_MIN <= port <= 65535):
        return None
    if address.version == 4:
        if not address.is_loopback:
            return None
    elif address != ipaddress.IPv6Address("::1"):
        return None
    return str(address), port


def _viewer_cluster_id(source: str, member_ids: list[str]) -> str:
    raw = json.dumps(
        [source, *sorted(member_ids)],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"viewer-cluster:loopback-ephemeral:{digest}"


def _string_values(values: list[object]) -> list[str]:
    return sorted({value for value in values if isinstance(value, str) and value})


def _int_values(values: list[object]) -> list[int]:
    return [value for value in values if isinstance(value, int) and not isinstance(value, bool)]


def _common_boolean(values: list[object]) -> bool | None:
    booleans = {value for value in values if isinstance(value, bool)}
    return booleans.pop() if len(booleans) == 1 else None


def _entity_hook_text(entity: dict[str, Any]) -> str:
    values: list[str] = []
    for key in ("name", "id"):
        value = entity.get(key)
        if isinstance(value, str):
            values.append(value)
    attributes = entity.get("attributes")
    if isinstance(attributes, dict):
        for key in ("exe", "command"):
            value = attributes.get(key)
            if isinstance(value, str):
                values.append(value)
        cmdline = attributes.get("cmdline")
        if isinstance(cmdline, list):
            values.extend(value for value in cmdline if isinstance(value, str))
        elif isinstance(cmdline, str):
            values.append(cmdline)
    return " ".join(values).lower()


def _is_internal_hook_process(entity: dict[str, Any]) -> bool:
    if entity.get("type") != "process":
        return False

    # Direct hook executables are unambiguously internal. Wrapper shells/interpreters
    # are treated as internal only for the auto-installed hook invocation, avoiding
    # false positives when a user's unrelated command merely mentions a hook name.
    attributes = entity.get("attributes")
    executable_values: list[str] = []
    for value in (entity.get("name"), entity.get("id")):
        if isinstance(value, str):
            executable_values.append(value)
    if isinstance(attributes, dict):
        exe = attributes.get("exe")
        if isinstance(exe, str):
            executable_values.append(exe)
    for value in executable_values:
        basename = value.replace("\\", "/").rsplit("/", 1)[-1].lower()
        for suffix in (".exe", ".cmd", ".bat", ".ps1", ".py"):
            if basename.endswith(suffix):
                basename = basename[: -len(suffix)]
                break
        if basename in _INTERNAL_HOOK_TOKENS:
            return True

    text = _entity_hook_text(entity)
    return "--auto" in text and any(token in text for token in _INTERNAL_HOOK_TOKENS)


def internal_hook_process_ids_in_event(event: dict[str, object]) -> set[str]:
    """Return process IDs directly identifying an ExecWeave hook helper."""
    ids: set[str] = set()
    for key in ("source", "target"):
        entity = event.get(key)
        if not isinstance(entity, dict) or not _is_internal_hook_process(entity):
            continue
        entity_id = entity.get("id")
        if isinstance(entity_id, str) and entity_id:
            ids.add(entity_id)
    return ids


def is_internal_hook_runtime_event(event: dict[str, object]) -> bool:
    """Return True for OS-runtime events directly naming an ExecWeave hook helper.

    Provider semantic tool/model/content events are intentionally not matched. Raw
    evidence files remain unchanged; live state additionally tracks descendants of
    these helper process IDs so their spawned/runtime noise can stay out of the UI.
    """
    return bool(internal_hook_process_ids_in_event(event))


def _internal_hook_process_ids(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
) -> set[str]:
    node_by_id = {
        node["id"]: node for node in nodes if isinstance(node.get("id"), str)
    }
    internal = {
        str(node["id"])
        for node in nodes
        if isinstance(node.get("id"), str) and _is_internal_hook_process(node)
    }
    changed = True
    while changed:
        changed = False
        for edge in edges:
            if edge.get("relation") != "SPAWNED":
                continue
            source = edge.get("source")
            target = edge.get("target")
            if not isinstance(source, str) or source not in internal or not isinstance(target, str):
                continue
            target_node = node_by_id.get(target)
            if target_node is None or target_node.get("type") != "process" or target in internal:
                continue
            internal.add(target)
            changed = True
    return internal


def _without_internal_hook_processes(
    graph: dict[str, Any],
) -> tuple[dict[str, Any], set[str], set[str]]:
    nodes = [node for node in graph.get("nodes", []) if isinstance(node, dict)]
    edges = [edge for edge in graph.get("edges", []) if isinstance(edge, dict)]
    internal_ids = _internal_hook_process_ids(nodes, edges)
    if not internal_ids:
        return graph, set(), set()
    removed_edge_ids = {
        str(edge["id"])
        for edge in edges
        if isinstance(edge.get("id"), str)
        and (edge.get("source") in internal_ids or edge.get("target") in internal_ids)
    }
    projected = deepcopy(graph)
    projected["nodes"] = [
        deepcopy(node) for node in nodes if node.get("id") not in internal_ids
    ]
    projected["edges"] = [
        deepcopy(edge)
        for edge in edges
        if edge.get("source") not in internal_ids and edge.get("target") not in internal_ids
    ]
    projected["node_count"] = len(projected["nodes"])
    projected["edge_count"] = len(projected["edges"])
    return projected, internal_ids, removed_edge_ids


def strip_internal_hook_processes(graph: dict[str, Any]) -> dict[str, Any]:
    """Return a graph copy without ExecWeave hook-helper process nodes/edges."""
    filtered, _, _ = _without_internal_hook_processes(graph)
    return filtered


def strip_internal_hook_execution_graph(graph: Any) -> Any:
    """Remove hook-helper process nodes/edges from a materialized graph object.

    Raw event streams remain unchanged. This keeps record/live graph artifacts from
    treating ExecWeave's own hook executables and their descendants as agent work.
    """
    payload = strip_internal_hook_processes(graph.to_dict())
    allowed_nodes = {
        node["id"]
        for node in payload.get("nodes", [])
        if isinstance(node, dict) and isinstance(node.get("id"), str)
    }
    allowed_edges = {
        edge["id"]
        for edge in payload.get("edges", [])
        if isinstance(edge, dict) and isinstance(edge.get("id"), str)
    }
    graph.nodes = [node for node in graph.nodes if node.id in allowed_nodes]
    graph.edges = [edge for edge in graph.edges if edge.id in allowed_edges]
    return graph


def _cluster_for_group(
    source: str,
    members: list[tuple[dict[str, Any], dict[str, Any], int]],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    members = sorted(members, key=lambda item: str(item[0].get("id") or ""))
    member_nodes = [deepcopy(node) for node, _, _ in members]
    member_edges = [deepcopy(edge) for _, edge, _ in members]
    member_ids = [
        str(node["id"]) for node in member_nodes if isinstance(node.get("id"), str)
    ]
    ports = [port for _, _, port in members]
    cluster_id = _viewer_cluster_id(source, member_ids)
    cluster_edge_id = f"{source}--CONNECTED_TO-->{cluster_id}"

    node_first_seen = _string_values([node.get("first_seen") for node in member_nodes])
    node_last_seen = _string_values([node.get("last_seen") for node in member_nodes])
    edge_first_seen = _string_values([edge.get("first_seen") for edge in member_edges])
    edge_last_seen = _string_values([edge.get("last_seen") for edge in member_edges])
    first_sequences = _int_values([edge.get("first_sequence") for edge in member_edges])
    last_sequences = _int_values([edge.get("last_sequence") for edge in member_edges])
    event_ids = [
        event_id
        for edge in member_edges
        for event_id in (edge.get("event_ids") or [])
        if isinstance(event_id, str) and event_id
    ]
    event_types = _string_values(
        [
            event_type
            for edge in member_edges
            for event_type in (edge.get("event_types") or [])
        ]
    )
    backends = _string_values(
        [backend for edge in member_edges for backend in (edge.get("backends") or [])]
    )
    attributions = _string_values(
        [
            attribution
            for edge in member_edges
            for attribution in (edge.get("attributions") or [])
        ]
    )
    cluster_node = {
        "id": cluster_id,
        "type": "network_endpoint_cluster",
        "name": f"{len(member_nodes)} localhost ephemeral endpoints",
        "attributes": {
            "viewer_only": True,
            "collapsed": True,
            "expandable": True,
            "member_count": len(member_nodes),
            "member_type": "network_endpoint",
            "reason": "loopback_ephemeral_ports",
            "port_min": min(ports),
            "port_max": max(ports),
        },
        "first_seen": min(node_first_seen) if node_first_seen else None,
        "last_seen": max(node_last_seen) if node_last_seen else None,
        "event_count": sum(int(node.get("event_count") or 0) for node in member_nodes),
        "event_types": event_types,
    }
    cluster_edge = {
        "id": cluster_edge_id,
        "source": source,
        "target": cluster_id,
        "relation": "CONNECTED_TO",
        "count": sum(max(1, int(edge.get("count") or 0)) for edge in member_edges),
        "first_seen": min(edge_first_seen) if edge_first_seen else None,
        "last_seen": max(edge_last_seen) if edge_last_seen else None,
        "first_sequence": min(first_sequences) if first_sequences else None,
        "last_sequence": max(last_sequences) if last_sequences else None,
        "event_ids": event_ids[:32],
        "event_ids_truncated": len(event_ids) > 32,
        "evidence_event_count": len(event_ids),
        "event_types": event_types,
        "backends": backends,
        "attributions": attributions,
        "causal": _common_boolean([edge.get("causal") for edge in member_edges]),
        "collapsed_member_count": len(member_nodes),
        "viewer_only": True,
    }
    expansion = {
        "cluster_node_id": cluster_id,
        "cluster_edge_id": cluster_edge_id,
        "nodes": member_nodes,
        "edges": member_edges,
        "viewer_only": True,
    }
    return cluster_node, cluster_edge, expansion


def _projection_metadata(
    *,
    cluster_count: int,
    collapsed_node_count: int,
    collapsed_edge_count: int,
    internal_hook_node_count: int,
    internal_hook_edge_count: int,
) -> dict[str, Any]:
    if cluster_count and internal_hook_node_count:
        kind = "combined"
    elif cluster_count:
        kind = "loopback_ephemeral_ports"
    else:
        kind = "internal_hook_processes"
    return {
        "schema_version": _PROJECTION_SCHEMA_VERSION,
        "viewer_only": True,
        "kind": kind,
        "cluster_count": cluster_count,
        "collapsed_node_count": collapsed_node_count,
        "collapsed_edge_count": collapsed_edge_count,
        "internal_hook_node_count": internal_hook_node_count,
        "internal_hook_edge_count": internal_hook_edge_count,
        "threshold": LOOPBACK_CLUSTER_THRESHOLD,
        "ephemeral_port_min": EPHEMERAL_PORT_MIN,
    }


def project_viewer_graph(graph: dict[str, Any]) -> dict[str, Any]:
    """Apply bounded presentation-only projections without changing raw evidence.

    Full-fidelity content nodes receive validated, viewer-only reference metadata.
    ExecWeave's own hook helper processes are removed from the dashboard projection,
    while provider semantic tool/model/content evidence remains visible. Noisy
    localhost ephemeral endpoints are then collapsed only when they satisfy the
    existing conservative leaf/group rules.
    """
    decorated = decorate_viewer_content_references(graph)
    filtered, internal_hook_ids, internal_hook_edge_ids = _without_internal_hook_processes(
        decorated
    )
    nodes = [node for node in filtered.get("nodes", []) if isinstance(node, dict)]
    edges = [edge for edge in filtered.get("edges", []) if isinstance(edge, dict)]
    node_by_id = {
        node["id"]: node for node in nodes if isinstance(node.get("id"), str)
    }
    incident: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in edges:
        source = edge.get("source")
        target = edge.get("target")
        if isinstance(source, str):
            incident[source].append(edge)
        if isinstance(target, str) and target != source:
            incident[target].append(edge)

    groups: dict[str, list[tuple[dict[str, Any], dict[str, Any], int]]] = defaultdict(list)
    for node in nodes:
        node_id = node.get("id")
        if node.get("type") != "network_endpoint" or not isinstance(node_id, str):
            continue
        parsed = _endpoint_host_port(node)
        if parsed is None:
            continue
        node_edges = incident.get(node_id, [])
        if len(node_edges) != 1:
            continue
        edge = node_edges[0]
        source = edge.get("source")
        if (
            edge.get("target") != node_id
            or edge.get("relation") != "CONNECTED_TO"
            or not isinstance(edge.get("id"), str)
            or not isinstance(source, str)
        ):
            continue
        source_node = node_by_id.get(source)
        if source_node is None or source_node.get("type") != "process":
            continue
        groups[source].append((node, edge, parsed[1]))

    qualifying = {
        source: members
        for source, members in groups.items()
        if len(members) >= LOOPBACK_CLUSTER_THRESHOLD
    }
    if not qualifying and not internal_hook_ids:
        return decorated
    if not qualifying:
        projected = deepcopy(filtered)
        projected["viewer_projection"] = _projection_metadata(
            cluster_count=0,
            collapsed_node_count=0,
            collapsed_edge_count=0,
            internal_hook_node_count=len(internal_hook_ids),
            internal_hook_edge_count=len(internal_hook_edge_ids),
        )
        return projected

    collapsed_node_ids: set[str] = set()
    collapsed_edge_ids: set[str] = set()
    cluster_nodes: list[dict[str, Any]] = []
    cluster_edges: list[dict[str, Any]] = []
    expansion_clusters: dict[str, dict[str, Any]] = {}
    for source, members in sorted(qualifying.items()):
        cluster_node, cluster_edge, expansion = _cluster_for_group(source, members)
        cluster_nodes.append(cluster_node)
        cluster_edges.append(cluster_edge)
        expansion_clusters[cluster_node["id"]] = expansion
        collapsed_node_ids.update(
            str(node["id"])
            for node, _, _ in members
            if isinstance(node.get("id"), str)
        )
        collapsed_edge_ids.update(
            str(edge["id"])
            for _, edge, _ in members
            if isinstance(edge.get("id"), str)
        )

    projected = deepcopy(filtered)
    projected["nodes"] = [
        deepcopy(node) for node in nodes if node.get("id") not in collapsed_node_ids
    ] + cluster_nodes
    projected["edges"] = [
        deepcopy(edge) for edge in edges if edge.get("id") not in collapsed_edge_ids
    ] + cluster_edges
    projected["node_count"] = len(projected["nodes"])
    projected["edge_count"] = len(projected["edges"])

    existing_expansion = projected.get("expansion")
    expansion_payload = (
        deepcopy(existing_expansion) if isinstance(existing_expansion, dict) else {}
    )
    existing_clusters = expansion_payload.get("clusters")
    merged_clusters = (
        deepcopy(existing_clusters) if isinstance(existing_clusters, dict) else {}
    )
    merged_clusters.update(expansion_clusters)
    expansion_payload.setdefault("schema_version", _PROJECTION_SCHEMA_VERSION)
    expansion_payload["clusters"] = merged_clusters
    projected["expansion"] = expansion_payload
    projected["viewer_projection"] = _projection_metadata(
        cluster_count=len(expansion_clusters),
        collapsed_node_count=len(collapsed_node_ids),
        collapsed_edge_count=len(collapsed_edge_ids),
        internal_hook_node_count=len(internal_hook_ids),
        internal_hook_edge_count=len(internal_hook_edge_ids),
    )
    return projected


def render_graph_html(graph: dict[str, Any]) -> str:
    html = _render_graph_html(project_viewer_graph(graph))
    return inject_standalone_content_inspector(html)


def write_graph_html(
    graph: dict[str, Any],
    path: str | Path,
    *,
    open_browser: bool = False,
) -> Path:
    output = Path(path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and output.stat().st_size > 0:
        raise FileExistsError(f"ExecWeave viewer output already exists: {output}")
    output.write_text(render_graph_html(graph), encoding="utf-8")
    if open_browser:
        webbrowser.open(output.as_uri())
    return output


def build_viewer_from_graph(
    graph_path: str | Path,
    output_path: str | Path,
    *,
    open_browser: bool = False,
) -> Path:
    graph = load_graph(graph_path)
    return write_graph_html(graph, output_path, open_browser=open_browser)
