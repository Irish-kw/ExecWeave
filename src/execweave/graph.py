from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .validate import validate_event_stream

GRAPH_SCHEMA_VERSION = "0.1"


@dataclass
class GraphNode:
    id: str
    type: str
    name: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    first_seen: str | None = None
    last_seen: str | None = None
    event_count: int = 0
    event_types: set[str] = field(default_factory=set)

    def observe(self, entity: dict[str, Any], event: dict[str, Any]) -> None:
        self.name = self.name or entity.get("name")
        incoming = entity.get("attributes") or {}
        if isinstance(incoming, dict):
            for key, value in incoming.items():
                self.attributes.setdefault(key, value)
        timestamp = event.get("timestamp")
        if isinstance(timestamp, str):
            self.first_seen = min(self.first_seen, timestamp) if self.first_seen else timestamp
            self.last_seen = max(self.last_seen, timestamp) if self.last_seen else timestamp
        self.event_count += 1
        event_type = event.get("event_type")
        if isinstance(event_type, str):
            self.event_types.add(event_type)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["event_types"] = sorted(self.event_types)
        return payload


@dataclass
class GraphEdge:
    id: str
    source: str
    target: str
    relation: str
    count: int = 0
    first_seen: str | None = None
    last_seen: str | None = None
    first_sequence: int | None = None
    last_sequence: int | None = None
    event_ids: list[str] = field(default_factory=list)
    event_types: set[str] = field(default_factory=set)
    backends: set[str] = field(default_factory=set)
    attributions: set[str] = field(default_factory=set)
    causal_values: set[bool] = field(default_factory=set)
    inferred_values: set[bool] = field(default_factory=set)
    inference_methods: set[str] = field(default_factory=set)
    identity_exact_values: set[bool] = field(default_factory=set)
    identity_methods: set[str] = field(default_factory=set)
    identity_hashes: set[str] = field(default_factory=set)
    confidence_values: list[float] = field(default_factory=list)
    confidence_semantics: set[str] = field(default_factory=set)
    supporting_event_ids: set[str] = field(default_factory=set)

    def observe(self, event: dict[str, Any]) -> None:
        self.count += 1
        timestamp = event.get("timestamp")
        if isinstance(timestamp, str):
            self.first_seen = min(self.first_seen, timestamp) if self.first_seen else timestamp
            self.last_seen = max(self.last_seen, timestamp) if self.last_seen else timestamp
        sequence = event.get("sequence")
        if isinstance(sequence, int) and not isinstance(sequence, bool):
            self.first_sequence = (
                min(self.first_sequence, sequence) if self.first_sequence is not None else sequence
            )
            self.last_sequence = (
                max(self.last_sequence, sequence) if self.last_sequence is not None else sequence
            )
        event_id = event.get("event_id")
        if isinstance(event_id, str):
            self.event_ids.append(event_id)
        event_type = event.get("event_type")
        if isinstance(event_type, str):
            self.event_types.add(event_type)
        attributes = event.get("attributes") or {}
        if isinstance(attributes, dict):
            backend = attributes.get("backend")
            if isinstance(backend, str):
                self.backends.add(backend)
            attribution = attributes.get("attribution")
            if isinstance(attribution, str):
                self.attributions.add(attribution)
            causal = attributes.get("causal")
            if isinstance(causal, bool):
                self.causal_values.add(causal)
            inferred = attributes.get("inferred")
            if isinstance(inferred, bool):
                self.inferred_values.add(inferred)
            method = attributes.get("inference_method")
            if isinstance(method, str) and method:
                self.inference_methods.add(method)
            identity_exact = attributes.get("identity_exact")
            if isinstance(identity_exact, bool):
                self.identity_exact_values.add(identity_exact)
            identity_method = attributes.get("identity_method")
            if isinstance(identity_method, str) and identity_method:
                self.identity_methods.add(identity_method)
            identity_hash = attributes.get("shared_request_id_hash")
            if isinstance(identity_hash, str) and identity_hash:
                self.identity_hashes.add(identity_hash)
            confidence = attributes.get("confidence")
            if isinstance(confidence, (int, float)) and not isinstance(confidence, bool):
                self.confidence_values.append(float(confidence))
            semantics = attributes.get("confidence_semantics")
            if isinstance(semantics, str) and semantics:
                self.confidence_semantics.add(semantics)
            supporting = attributes.get("supporting_event_ids")
            if isinstance(supporting, list):
                self.supporting_event_ids.update(
                    value for value in supporting if isinstance(value, str) and value
                )

    def to_dict(self) -> dict[str, Any]:
        if self.causal_values == {True}:
            causal: bool | None = True
        elif self.causal_values == {False}:
            causal = False
        else:
            causal = None
        if self.inferred_values == {True}:
            inferred: bool | None = True
        elif self.inferred_values == {False}:
            inferred = False
        else:
            inferred = None
        if self.identity_exact_values == {True}:
            identity_exact: bool | None = True
        elif self.identity_exact_values == {False}:
            identity_exact = False
        else:
            identity_exact = None
        return {
            "id": self.id,
            "source": self.source,
            "target": self.target,
            "relation": self.relation,
            "count": self.count,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "first_sequence": self.first_sequence,
            "last_sequence": self.last_sequence,
            "event_ids": self.event_ids,
            "event_types": sorted(self.event_types),
            "backends": sorted(self.backends),
            "attributions": sorted(self.attributions),
            "causal": causal,
            "inferred": inferred,
            "inference_methods": sorted(self.inference_methods),
            "identity_exact": identity_exact,
            "identity_methods": sorted(self.identity_methods),
            "identity_hashes": sorted(self.identity_hashes),
            "confidence_min": min(self.confidence_values) if self.confidence_values else None,
            "confidence_max": max(self.confidence_values) if self.confidence_values else None,
            "confidence_semantics": sorted(self.confidence_semantics),
            "supporting_event_ids": sorted(self.supporting_event_ids),
        }


@dataclass
class ExecutionGraph:
    session_id: str
    source_path: str
    source_schema_versions: list[str]
    event_count: int
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    built_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "graph_schema_version": GRAPH_SCHEMA_VERSION,
            "session_id": self.session_id,
            "source_path": self.source_path,
            "source_schema_versions": self.source_schema_versions,
            "event_count": self.event_count,
            "node_count": len(self.nodes),
            "edge_count": len(self.edges),
            "built_at": self.built_at,
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
        }


def _edge_id(source: str, relation: str, target: str) -> str:
    return f"{source}--{relation}-->{target}"


def _load_events(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def build_execution_graph(
    path: str | Path,
    *,
    allow_incomplete: bool = False,
) -> ExecutionGraph:
    source_path = Path(path).expanduser().resolve()
    validation = validate_event_stream(
        source_path,
        require_complete_session=not allow_incomplete,
    )
    if not validation.valid:
        details = "; ".join(validation.errors)
        raise ValueError(f"invalid ExecWeave event stream: {details}")

    events = _load_events(source_path)
    nodes: dict[str, GraphNode] = {}
    edges: dict[tuple[str, str, str], GraphEdge] = {}

    for event in events:
        source = event.get("source")
        target = event.get("target")

        for entity in (source, target):
            if not isinstance(entity, dict):
                continue
            entity_id = entity.get("id")
            entity_type = entity.get("type")
            if not isinstance(entity_id, str) or not isinstance(entity_type, str):
                continue
            node = nodes.get(entity_id)
            if node is None:
                node = GraphNode(
                    id=entity_id,
                    type=entity_type,
                    name=entity.get("name") if isinstance(entity.get("name"), str) else None,
                )
                nodes[entity_id] = node
            node.observe(entity, event)

        if not isinstance(source, dict) or not isinstance(target, dict):
            continue
        source_id = source.get("id")
        target_id = target.get("id")
        relation = event.get("relation")
        if not all(isinstance(value, str) and value for value in (source_id, target_id, relation)):
            continue
        key = (source_id, relation, target_id)
        edge = edges.get(key)
        if edge is None:
            edge = GraphEdge(
                id=_edge_id(source_id, relation, target_id),
                source=source_id,
                target=target_id,
                relation=relation,
            )
            edges[key] = edge
        edge.observe(event)

    session_id = validation.session_ids[0] if validation.session_ids else "unknown"
    return ExecutionGraph(
        session_id=session_id,
        source_path=str(source_path),
        source_schema_versions=validation.schema_versions,
        event_count=len(events),
        nodes=sorted(nodes.values(), key=lambda node: (node.type, node.id)),
        edges=sorted(edges.values(), key=lambda edge: (edge.source, edge.relation, edge.target)),
    )


def write_execution_graph(
    graph: ExecutionGraph,
    path: str | Path,
    *,
    metadata: dict[str, Any] | None = None,
) -> Path:
    output = Path(path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and output.stat().st_size > 0:
        raise FileExistsError(f"ExecWeave graph output already exists: {output}")
    payload = graph.to_dict()
    if metadata is not None:
        payload["metadata"] = metadata
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output
