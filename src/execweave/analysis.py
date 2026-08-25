from __future__ import annotations

import ipaddress
from collections import Counter, defaultdict, deque
from dataclasses import asdict, dataclass, field
from pathlib import PurePath
from typing import Any


_SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2, "info": 3}
_SENSITIVE_MARKERS = (
    "/.ssh/",
    "\\.ssh\\",
    "/.aws/credentials",
    "\\.aws\\credentials",
    "/.config/gcloud/",
    "\\.config\\gcloud\\",
    "/.azure/",
    "\\.azure\\",
    "/.kube/config",
    "\\.kube\\config",
    "/.docker/config.json",
    "\\.docker\\config.json",
    "/.npmrc",
    "\\.npmrc",
    "/.pypirc",
    "\\.pypirc",
    "/.netrc",
    "\\.netrc",
)
_SENSITIVE_BASENAMES = {
    ".env",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "credentials",
    "credentials.json",
    "service-account.json",
}
_FILE_RELATIONS = {"OPENED_READ", "OPENED_READ_WRITE", "OPENED_WRITE"}
_NETWORK_RELATIONS = {"CONNECTED_TO", "CONNECT_ATTEMPTED"}


@dataclass(frozen=True)
class Finding:
    rule_id: str
    severity: str
    title: str
    summary: str
    node_ids: list[str] = field(default_factory=list)
    edge_ids: list[str] = field(default_factory=list)
    evidence_event_ids: list[str] = field(default_factory=list)
    attributes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _node_map(graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        node["id"]: node
        for node in graph.get("nodes", [])
        if isinstance(node, dict) and isinstance(node.get("id"), str)
    }


def _resource_text(node: dict[str, Any]) -> str:
    return f"{node.get('id', '')} {node.get('name', '')}".lower()


def _is_sensitive_file(node: dict[str, Any]) -> bool:
    if node.get("type") != "file":
        return False
    text = _resource_text(node)
    if any(marker in text for marker in _SENSITIVE_MARKERS):
        return True
    name = str(node.get("name") or "").lower()
    if name in _SENSITIVE_BASENAMES:
        return True
    node_id = str(node.get("id") or "")
    _, _, raw_path = node_id.partition(":")
    if raw_path:
        try:
            return PurePath(raw_path).name.lower() in _SENSITIVE_BASENAMES
        except (TypeError, ValueError):
            return False
    return False


def _endpoint_host(node: dict[str, Any]) -> str | None:
    if node.get("type") != "network_endpoint":
        return None
    raw = str(node.get("name") or "")
    if not raw:
        node_id = str(node.get("id") or "")
        _, _, raw = node_id.partition(":")
    if not raw:
        return None
    if raw.startswith("[") and "]" in raw:
        return raw[1 : raw.index("]")]
    if raw.count(":") == 1:
        return raw.rsplit(":", 1)[0]
    return raw


def _is_external_endpoint(node: dict[str, Any]) -> bool:
    host = _endpoint_host(node)
    if host is None:
        return False
    normalized = host.strip().lower()
    if normalized in {"localhost", "ip6-localhost"}:
        return False
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError:
        return True
    return not (
        address.is_loopback
        or address.is_private
        or address.is_link_local
        or address.is_multicast
        or address.is_unspecified
        or address.is_reserved
    )


def _event_ids(edge: dict[str, Any], limit: int = 24) -> list[str]:
    values = edge.get("event_ids") or []
    return [str(value) for value in values if isinstance(value, str)][:limit]


def _edge_sequence(edge: dict[str, Any], key: str) -> int | None:
    value = edge.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _causal_spawn_adjacency(
    edges: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    adjacency: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in edges:
        if edge.get("relation") != "SPAWNED" or edge.get("causal") is not True:
            continue
        source = edge.get("source")
        target = edge.get("target")
        if isinstance(source, str) and isinstance(target, str):
            adjacency[source].append(edge)
    for values in adjacency.values():
        values.sort(
            key=lambda edge: (
                _edge_sequence(edge, "first_sequence") or 0,
                str(edge.get("target") or ""),
            )
        )
    return dict(adjacency)


def _descendant_spawn_paths(
    process_id: str,
    adjacency: dict[str, list[dict[str, Any]]],
    *,
    after_sequence: int | None,
    max_depth: int = 4,
) -> list[tuple[str, list[dict[str, Any]]]]:
    """Return chronological causal SPAWNED paths created after a source observation."""
    results: list[tuple[str, list[dict[str, Any]]]] = []
    queue: deque[tuple[str, list[dict[str, Any]], set[str], int | None]] = deque()
    queue.append((process_id, [], {process_id}, after_sequence))

    while queue:
        current, path, seen, minimum_sequence = queue.popleft()
        if len(path) >= max_depth:
            continue
        for edge in adjacency.get(current, []):
            child = edge.get("target")
            if not isinstance(child, str) or child in seen:
                continue
            spawn_sequence = _edge_sequence(edge, "first_sequence")
            if minimum_sequence is not None:
                if spawn_sequence is None or spawn_sequence < minimum_sequence:
                    continue
            next_path = [*path, edge]
            results.append((child, next_path))
            queue.append(
                (
                    child,
                    next_path,
                    {*seen, child},
                    spawn_sequence if spawn_sequence is not None else minimum_sequence,
                )
            )
    return results


def analyze_graph(graph: dict[str, Any]) -> dict[str, Any]:
    """Run conservative, explainable rules over one execution graph.

    Findings never upgrade co-occurrence into byte-level data-flow. Sensitive-file
    access followed by network activity is a prioritization signal, not proof that
    file contents were transmitted. The same rule applies across child processes:
    SPAWNED proves process lineage, not data inheritance or IPC.
    """
    nodes = _node_map(graph)
    edges = [edge for edge in graph.get("edges", []) if isinstance(edge, dict)]
    findings: list[Finding] = []
    sensitive_by_process: dict[str, list[dict[str, Any]]] = {}
    external_by_process: dict[str, list[dict[str, Any]]] = {}

    for edge in edges:
        source_id = edge.get("source")
        target_id = edge.get("target")
        relation = edge.get("relation")
        if not isinstance(source_id, str) or not isinstance(target_id, str):
            continue
        source = nodes.get(source_id)
        target = nodes.get(target_id)
        if source is None or target is None or source.get("type") != "process":
            continue

        if relation in _FILE_RELATIONS and _is_sensitive_file(target):
            causal = edge.get("causal") is True
            severity = "high" if relation in {"OPENED_READ_WRITE", "OPENED_WRITE"} else "medium"
            if not causal:
                severity = "low"
            findings.append(
                Finding(
                    rule_id="sensitive-file-access",
                    severity=severity,
                    title="Process accessed a sensitive-looking file",
                    summary=(
                        f"{source_id} has {relation} evidence for {target_id}. "
                        "Review whether this resource was required for the agent task."
                    ),
                    node_ids=[source_id, target_id],
                    edge_ids=[str(edge.get("id") or "")],
                    evidence_event_ids=_event_ids(edge),
                    attributes={
                        "relation": relation,
                        "causal": edge.get("causal"),
                        "data_flow_proven": False,
                    },
                )
            )
            if causal:
                sensitive_by_process.setdefault(source_id, []).append(edge)

        if relation in _NETWORK_RELATIONS and _is_external_endpoint(target):
            causal = edge.get("causal") is True
            findings.append(
                Finding(
                    rule_id="external-network-contact",
                    severity="info" if relation == "CONNECTED_TO" else "low",
                    title="Process contacted an external network endpoint",
                    summary=f"{source_id} emitted {relation} evidence for {target_id}.",
                    node_ids=[source_id, target_id],
                    edge_ids=[str(edge.get("id") or "")],
                    evidence_event_ids=_event_ids(edge),
                    attributes={
                        "relation": relation,
                        "causal": edge.get("causal"),
                        "endpoint_host": _endpoint_host(target),
                    },
                )
            )
            if causal:
                external_by_process.setdefault(source_id, []).append(edge)

    # Same-process correlation with strict chronological ordering when sequences exist.
    for process_id in sorted(set(sensitive_by_process).intersection(external_by_process)):
        for file_edge in sensitive_by_process[process_id]:
            file_target = str(file_edge.get("target") or "")
            file_last = _edge_sequence(file_edge, "last_sequence")
            for net_edge in external_by_process[process_id]:
                net_target = str(net_edge.get("target") or "")
                net_first = _edge_sequence(net_edge, "first_sequence")
                if file_last is not None and net_first is not None and net_first < file_last:
                    continue
                relation = str(net_edge.get("relation") or "")
                severity = "high" if relation == "CONNECTED_TO" else "medium"
                findings.append(
                    Finding(
                        rule_id="possible-sensitive-file-to-network-path",
                        severity=severity,
                        title="Sensitive-file access was followed by external network activity",
                        summary=(
                            f"{process_id} accessed {file_target} and later produced {relation} "
                            f"evidence for {net_target}. This is a prioritization signal only: "
                            "ExecWeave has not proven that bytes from the file were transmitted."
                        ),
                        node_ids=[process_id, file_target, net_target],
                        edge_ids=[
                            str(file_edge.get("id") or ""),
                            str(net_edge.get("id") or ""),
                        ],
                        evidence_event_ids=[
                            *_event_ids(file_edge, 12),
                            *_event_ids(net_edge, 12),
                        ],
                        attributes={
                            "file_relation": file_edge.get("relation"),
                            "network_relation": relation,
                            "file_last_sequence": file_last,
                            "network_first_sequence": net_first,
                            "causal_process_attribution": True,
                            "data_flow_proven": False,
                            "exfiltration_proven": False,
                        },
                    )
                )

    # Graph-native delegated path: sensitive access -> causal SPAWNED chain -> network.
    # This proves chronological process lineage only. It does not prove inheritance,
    # IPC, taint propagation, or that the child received bytes from the sensitive file.
    spawn_adjacency = _causal_spawn_adjacency(edges)
    for source_process, file_edges in sorted(sensitive_by_process.items()):
        for file_edge in file_edges:
            file_target = str(file_edge.get("target") or "")
            file_last = _edge_sequence(file_edge, "last_sequence")
            for descendant, spawn_path in _descendant_spawn_paths(
                source_process,
                spawn_adjacency,
                after_sequence=file_last,
            ):
                spawn_last = _edge_sequence(spawn_path[-1], "first_sequence")
                for net_edge in external_by_process.get(descendant, []):
                    net_first = _edge_sequence(net_edge, "first_sequence")
                    if spawn_last is not None:
                        if net_first is None or net_first < spawn_last:
                            continue
                    relation = str(net_edge.get("relation") or "")
                    net_target = str(net_edge.get("target") or "")
                    process_chain = [source_process]
                    process_chain.extend(str(edge.get("target") or "") for edge in spawn_path)
                    spawn_edge_ids = [str(edge.get("id") or "") for edge in spawn_path]
                    spawn_event_ids = [
                        event_id
                        for edge in spawn_path
                        for event_id in _event_ids(edge, 8)
                    ]
                    findings.append(
                        Finding(
                            rule_id="possible-delegated-sensitive-file-to-network-path",
                            severity="medium" if relation == "CONNECTED_TO" else "low",
                            title=(
                                "Sensitive-file access was followed by child-process "
                                "external network activity"
                            ),
                            summary=(
                                f"{source_process} accessed {file_target}, then a causal SPAWNED "
                                f"chain reached {descendant}, which later produced {relation} "
                                f"evidence for {net_target}. Process lineage is proven, but "
                                "ExecWeave has not proven data inheritance, IPC, or exfiltration."
                            ),
                            node_ids=[source_process, file_target, *process_chain[1:], net_target],
                            edge_ids=[
                                str(file_edge.get("id") or ""),
                                *spawn_edge_ids,
                                str(net_edge.get("id") or ""),
                            ],
                            evidence_event_ids=[
                                *_event_ids(file_edge, 8),
                                *spawn_event_ids,
                                *_event_ids(net_edge, 8),
                            ],
                            attributes={
                                "delegation_hops": len(spawn_path),
                                "process_chain": process_chain,
                                "file_last_sequence": file_last,
                                "spawn_sequences": [
                                    _edge_sequence(edge, "first_sequence")
                                    for edge in spawn_path
                                ],
                                "network_first_sequence": net_first,
                                "causal_process_lineage": True,
                                "data_inheritance_proven": False,
                                "ipc_proven": False,
                                "data_flow_proven": False,
                                "exfiltration_proven": False,
                            },
                        )
                    )

    findings.sort(
        key=lambda finding: (
            _SEVERITY_ORDER.get(finding.severity, 99),
            finding.rule_id,
            finding.node_ids,
        )
    )
    counts = Counter(finding.severity for finding in findings)
    return {
        "analysis_schema_version": "0.2",
        "session_id": graph.get("session_id"),
        "finding_count": len(findings),
        "severity_counts": {
            severity: counts.get(severity, 0) for severity in ("high", "medium", "low", "info")
        },
        "limitations": [
            "Findings are rule-based prioritization signals, not proof of malicious intent.",
            "Sensitive-file-to-network findings do not prove byte-level data flow or exfiltration.",
            "SPAWNED lineage does not prove data inheritance, IPC, or taint propagation.",
            "Collector coverage and attribution strength depend on the backend.",
        ],
        "findings": [finding.to_dict() for finding in findings],
    }
