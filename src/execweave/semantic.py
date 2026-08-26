from __future__ import annotations

import json
import os
import tempfile
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .schema import SCHEMA_VERSION
from .validate import validate_event_stream


@dataclass(frozen=True)
class SemanticMergeResult:
    runtime_event_count: int
    semantic_event_count: int
    merged_event_count: int
    resolved_process_references: int
    unresolved_process_references: int
    session_id: str
    output: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class _ProcessCandidate:
    pid: int
    entity: dict[str, Any]
    create_time: float | None


def _parse_timestamp(value: object, *, context: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{context}: timestamp must be a non-empty ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{context}: timestamp must be ISO-8601") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _load_jsonl(path: Path, *, label: str) -> list[dict[str, Any]]:
    if not path.exists():
        raise ValueError(f"{label} does not exist: {path}")
    records: list[dict[str, Any]] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{label} line {line_number}: invalid JSON: {exc.msg}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"{label} line {line_number}: record must be a JSON object")
        records.append(payload)
    return records


def _validate_entity(entity: object, *, context: str) -> None:
    if entity is None:
        return
    if not isinstance(entity, dict):
        raise ValueError(f"{context} must be an object or null")
    for key in ("type", "id"):
        value = entity.get(key)
        if not isinstance(value, str) or not value:
            raise ValueError(f"{context}.{key} must be a non-empty string")
    attributes = entity.get("attributes", {})
    if not isinstance(attributes, dict):
        raise ValueError(f"{context}.attributes must be an object")


def _process_candidates(runtime_events: list[dict[str, Any]]) -> dict[int, list[_ProcessCandidate]]:
    by_pid: dict[int, dict[str, _ProcessCandidate]] = {}
    for event in runtime_events:
        for entity in (event.get("source"), event.get("target")):
            if not isinstance(entity, dict) or entity.get("type") != "process":
                continue
            entity_id = entity.get("id")
            attributes = entity.get("attributes") or {}
            if not isinstance(entity_id, str) or not isinstance(attributes, dict):
                continue
            pid = attributes.get("pid")
            if not isinstance(pid, int) or isinstance(pid, bool):
                continue
            create_time_raw = attributes.get("create_time")
            create_time = (
                float(create_time_raw)
                if isinstance(create_time_raw, (int, float)) and not isinstance(create_time_raw, bool)
                else None
            )
            by_pid.setdefault(pid, {})[entity_id] = _ProcessCandidate(
                pid=pid,
                entity=deepcopy(entity),
                create_time=create_time,
            )
    return {pid: list(candidates.values()) for pid, candidates in by_pid.items()}


def _resolve_process_reference(
    entity: dict[str, Any],
    *,
    timestamp: datetime,
    candidates: dict[int, list[_ProcessCandidate]],
) -> tuple[dict[str, Any], bool]:
    if entity.get("type") != "process_reference":
        return deepcopy(entity), False
    attributes = entity.get("attributes") or {}
    pid = attributes.get("pid") if isinstance(attributes, dict) else None
    if not isinstance(pid, int) or isinstance(pid, bool):
        unresolved = deepcopy(entity)
        unresolved.setdefault("attributes", {})["unresolved"] = True
        return unresolved, False

    options = candidates.get(pid, [])
    if not options:
        unresolved = deepcopy(entity)
        unresolved.setdefault("attributes", {})["unresolved"] = True
        return unresolved, False

    explicit_create_time = attributes.get("create_time") if isinstance(attributes, dict) else None
    if isinstance(explicit_create_time, (int, float)) and not isinstance(explicit_create_time, bool):
        exact = [
            candidate
            for candidate in options
            if candidate.create_time is not None
            and abs(candidate.create_time - float(explicit_create_time)) < 0.001
        ]
        if len(exact) == 1:
            return deepcopy(exact[0].entity), True

    if len(options) == 1:
        return deepcopy(options[0].entity), True

    event_epoch = timestamp.timestamp()
    started = [
        candidate
        for candidate in options
        if candidate.create_time is not None and candidate.create_time <= event_epoch
    ]
    if started:
        latest = max(candidate.create_time or 0.0 for candidate in started)
        nearest = [
            candidate
            for candidate in started
            if candidate.create_time is not None and abs(candidate.create_time - latest) < 0.001
        ]
        if len(nearest) == 1:
            return deepcopy(nearest[0].entity), True

    unresolved = deepcopy(entity)
    unresolved.setdefault("attributes", {})["unresolved"] = True
    unresolved["attributes"]["candidate_process_ids"] = sorted(
        candidate.entity["id"] for candidate in options if isinstance(candidate.entity.get("id"), str)
    )
    return unresolved, False


def _normalize_semantic_record(
    record: dict[str, Any],
    *,
    line_number: int,
    session_id: str,
    started_at: datetime,
    finished_at: datetime | None,
    candidates: dict[int, list[_ProcessCandidate]],
) -> tuple[dict[str, Any], int, int]:
    context = f"semantic sidecar line {line_number}"
    timestamp = _parse_timestamp(record.get("timestamp"), context=context)
    if timestamp < started_at:
        raise ValueError(f"{context}: timestamp precedes the runtime session start")
    if finished_at is not None and timestamp > finished_at:
        raise ValueError(f"{context}: timestamp is outside the runtime session interval")

    event_type = record.get("event_type")
    relation = record.get("relation")
    if not isinstance(event_type, str) or not event_type:
        raise ValueError(f"{context}: event_type must be a non-empty string")
    if not isinstance(relation, str) or not relation:
        raise ValueError(f"{context}: relation must be a non-empty string")

    source = record.get("source")
    target = record.get("target")
    _validate_entity(source, context=f"{context}.source")
    _validate_entity(target, context=f"{context}.target")
    attributes = record.get("attributes", {})
    if not isinstance(attributes, dict):
        raise ValueError(f"{context}: attributes must be an object")

    resolved = 0
    unresolved = 0
    resolution_map: dict[str, str] = {}
    normalized_entities: list[dict[str, Any] | None] = []
    for entity in (source, target):
        if entity is None:
            normalized_entities.append(None)
            continue
        original_id = entity.get("id") if isinstance(entity, dict) else None
        normalized, did_resolve = _resolve_process_reference(
            entity,
            timestamp=timestamp,
            candidates=candidates,
        )
        if entity.get("type") == "process_reference":
            if did_resolve:
                resolved += 1
                if isinstance(original_id, str) and isinstance(normalized.get("id"), str):
                    resolution_map[original_id] = normalized["id"]
            else:
                unresolved += 1
        normalized_entities.append(normalized)

    normalized_attributes = deepcopy(attributes)
    normalized_attributes.setdefault("backend", "semantic")
    normalized_attributes.setdefault("attribution", "semantic_sidecar")
    if resolution_map:
        normalized_attributes["resolved_process_references"] = resolution_map

    event_id = record.get("event_id")
    if not isinstance(event_id, str) or not event_id:
        event_id = f"semantic:{uuid4()}"

    return (
        {
            "schema_version": SCHEMA_VERSION,
            "event_id": event_id,
            "session_id": session_id,
            "timestamp": record["timestamp"],
            "event_type": event_type,
            "relation": relation,
            "source": normalized_entities[0],
            "target": normalized_entities[1],
            "sequence": None,
            "attributes": normalized_attributes,
        },
        resolved,
        unresolved,
    )


class LiveSemanticNormalizer:
    """Normalize append-only specialized records for disposable live graph state.

    Live normalization is provisional: it resolves process references only against
    process identities observed so far. The final artifact is rebuilt through
    ``merge_semantic_sidecar`` after the runtime session closes.
    """

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self._started_at: datetime | None = None
        self._candidates: dict[int, dict[str, _ProcessCandidate]] = {}

    @property
    def ready(self) -> bool:
        return self._started_at is not None

    def reset(self) -> None:
        self._started_at = None
        self._candidates.clear()

    def observe_runtime_event(self, event: dict[str, Any]) -> None:
        if event.get("event_type") == "session.started":
            self._started_at = _parse_timestamp(
                event.get("timestamp"),
                context="live session.started",
            )

        for entity in (event.get("source"), event.get("target")):
            if not isinstance(entity, dict) or entity.get("type") != "process":
                continue
            entity_id = entity.get("id")
            attributes = entity.get("attributes") or {}
            if not isinstance(entity_id, str) or not isinstance(attributes, dict):
                continue
            pid = attributes.get("pid")
            if not isinstance(pid, int) or isinstance(pid, bool):
                continue
            create_time_raw = attributes.get("create_time")
            create_time = (
                float(create_time_raw)
                if isinstance(create_time_raw, (int, float))
                and not isinstance(create_time_raw, bool)
                else None
            )
            self._candidates.setdefault(pid, {})[entity_id] = _ProcessCandidate(
                pid=pid,
                entity=deepcopy(entity),
                create_time=create_time,
            )

    def normalize(
        self,
        record: dict[str, Any],
        *,
        line_number: int,
    ) -> dict[str, Any] | None:
        if self._started_at is None:
            return None
        candidates = {
            pid: list(by_id.values()) for pid, by_id in self._candidates.items()
        }
        normalized, _, _ = _normalize_semantic_record(
            record,
            line_number=line_number,
            session_id=self.session_id,
            started_at=self._started_at,
            finished_at=None,
            candidates=candidates,
        )
        attributes = normalized.get("attributes")
        if isinstance(attributes, dict):
            attributes["live_normalization_provisional"] = True
        return normalized


def merge_semantic_sidecar(
    runtime_path: str | Path,
    semantic_path: str | Path,
    output_path: str | Path,
) -> SemanticMergeResult:
    runtime = Path(runtime_path).expanduser().resolve()
    semantic = Path(semantic_path).expanduser().resolve()
    output = Path(output_path).expanduser().resolve()
    if output.exists() and output.stat().st_size > 0:
        raise FileExistsError(f"ExecWeave merged event stream already exists: {output}")

    validation = validate_event_stream(runtime, require_complete_session=True)
    if not validation.valid:
        raise ValueError("invalid runtime event stream: " + "; ".join(validation.errors))
    runtime_events = _load_jsonl(runtime, label="runtime event stream")
    sidecar_records = _load_jsonl(semantic, label="semantic sidecar")
    if not sidecar_records:
        raise ValueError("semantic sidecar contains no events")

    starts = [event for event in runtime_events if event.get("event_type") == "session.started"]
    finishes = [event for event in runtime_events if event.get("event_type") == "session.finished"]
    if len(starts) != 1 or len(finishes) != 1:
        raise ValueError("runtime event stream must contain exactly one session start and finish")
    session_id = validation.session_ids[0]
    started_at = _parse_timestamp(starts[0].get("timestamp"), context="session.started")
    finished_at = _parse_timestamp(finishes[0].get("timestamp"), context="session.finished")
    candidates = _process_candidates(runtime_events)

    semantic_events: list[dict[str, Any]] = []
    resolved_total = 0
    unresolved_total = 0
    for line_number, record in enumerate(sidecar_records, start=1):
        normalized, resolved, unresolved = _normalize_semantic_record(
            record,
            line_number=line_number,
            session_id=session_id,
            started_at=started_at,
            finished_at=finished_at,
            candidates=candidates,
        )
        semantic_events.append(normalized)
        resolved_total += resolved
        unresolved_total += unresolved

    runtime_body = [
        deepcopy(event)
        for event in runtime_events
        if event.get("event_type") not in {"session.started", "session.finished"}
    ]
    decorated: list[tuple[datetime, int, int, dict[str, Any]]] = []
    for index, event in enumerate(runtime_body):
        decorated.append(
            (
                _parse_timestamp(event.get("timestamp"), context=f"runtime event {index + 1}"),
                0,
                index,
                event,
            )
        )
    for index, event in enumerate(semantic_events):
        decorated.append(
            (
                _parse_timestamp(event.get("timestamp"), context=f"semantic event {index + 1}"),
                1,
                index,
                event,
            )
        )
    decorated.sort(key=lambda item: (item[0], item[1], item[2]))

    merged = [deepcopy(starts[0]), *[item[3] for item in decorated], deepcopy(finishes[0])]
    for sequence, event in enumerate(merged, start=1):
        event["sequence"] = sequence

    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".execweave-semantic-", suffix=".jsonl", dir=output.parent)
    os.close(fd)
    temp_path = Path(temp_name)
    try:
        temp_path.write_text(
            "".join(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n" for event in merged),
            encoding="utf-8",
        )
        merged_validation = validate_event_stream(temp_path, require_complete_session=True)
        if not merged_validation.valid:
            raise ValueError("merged semantic event stream is invalid: " + "; ".join(merged_validation.errors))
        temp_path.replace(output)
    finally:
        if temp_path.exists():
            temp_path.unlink()

    return SemanticMergeResult(
        runtime_event_count=len(runtime_events),
        semantic_event_count=len(semantic_events),
        merged_event_count=len(merged),
        resolved_process_references=resolved_total,
        unresolved_process_references=unresolved_total,
        session_id=session_id,
        output=str(output),
    )
