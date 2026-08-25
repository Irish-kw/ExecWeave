from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .schema import SCHEMA_VERSION


@dataclass(frozen=True)
class ValidationResult:
    path: str
    valid: bool
    event_count: int
    errors: list[str]
    warnings: list[str]
    session_ids: list[str]
    schema_versions: list[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "valid": self.valid,
            "event_count": self.event_count,
            "errors": self.errors,
            "warnings": self.warnings,
            "session_ids": self.session_ids,
            "schema_versions": self.schema_versions,
        }


def _valid_timestamp(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _validate_entity(
    entity: object,
    *,
    line_number: int,
    field_name: str,
    errors: list[str],
) -> None:
    if entity is None:
        return
    if not isinstance(entity, dict):
        errors.append(f"line {line_number}: {field_name} must be an object or null")
        return
    for key in ("type", "id"):
        value = entity.get(key)
        if not isinstance(value, str) or not value:
            errors.append(f"line {line_number}: {field_name}.{key} must be a non-empty string")


def validate_event_stream(
    path: str | Path,
    *,
    require_complete_session: bool = True,
) -> ValidationResult:
    stream_path = Path(path).expanduser().resolve()
    errors: list[str] = []
    warnings: list[str] = []
    session_ids: set[str] = set()
    schema_versions: set[str] = set()
    event_ids: set[str] = set()
    sequences: list[int] = []
    event_types: list[str] = []
    event_count = 0

    if not stream_path.exists():
        return ValidationResult(
            path=str(stream_path),
            valid=False,
            event_count=0,
            errors=["event stream does not exist"],
            warnings=[],
            session_ids=[],
            schema_versions=[],
        )

    for line_number, raw_line in enumerate(
        stream_path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1
    ):
        if not raw_line.strip():
            warnings.append(f"line {line_number}: empty line ignored")
            continue
        try:
            payload: Any = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            errors.append(f"line {line_number}: invalid JSON: {exc.msg}")
            continue
        if not isinstance(payload, dict):
            errors.append(f"line {line_number}: event must be a JSON object")
            continue

        event_count += 1
        schema_version = payload.get("schema_version")
        if isinstance(schema_version, str):
            schema_versions.add(schema_version)
        else:
            errors.append(f"line {line_number}: schema_version must be a string")

        event_id = payload.get("event_id")
        if not isinstance(event_id, str) or not event_id:
            errors.append(f"line {line_number}: event_id must be a non-empty string")
        elif event_id in event_ids:
            errors.append(f"line {line_number}: duplicate event_id {event_id}")
        else:
            event_ids.add(event_id)

        session_id = payload.get("session_id")
        if not isinstance(session_id, str) or not session_id:
            errors.append(f"line {line_number}: session_id must be a non-empty string")
        else:
            session_ids.add(session_id)

        sequence = payload.get("sequence")
        if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1:
            errors.append(f"line {line_number}: sequence must be a positive integer")
        else:
            sequences.append(sequence)

        timestamp = payload.get("timestamp")
        if not _valid_timestamp(timestamp):
            errors.append(f"line {line_number}: timestamp must be ISO-8601")

        event_type = payload.get("event_type")
        if not isinstance(event_type, str) or not event_type:
            errors.append(f"line {line_number}: event_type must be a non-empty string")
        else:
            event_types.append(event_type)

        relation = payload.get("relation")
        if not isinstance(relation, str) or not relation:
            errors.append(f"line {line_number}: relation must be a non-empty string")

        _validate_entity(payload.get("source"), line_number=line_number, field_name="source", errors=errors)
        _validate_entity(payload.get("target"), line_number=line_number, field_name="target", errors=errors)

        attributes = payload.get("attributes")
        if not isinstance(attributes, dict):
            errors.append(f"line {line_number}: attributes must be an object")

    if event_count == 0:
        errors.append("event stream contains no events")

    if len(session_ids) > 1:
        errors.append(
            "event stream contains multiple session IDs: " + ", ".join(sorted(session_ids))
        )

    if sequences:
        expected = list(range(1, len(sequences) + 1))
        if sequences != expected:
            errors.append(
                "sequence is not contiguous from 1; "
                f"observed first/last={sequences[0]}/{sequences[-1]} count={len(sequences)}"
            )

    if schema_versions and schema_versions != {SCHEMA_VERSION}:
        warnings.append(
            "stream schema differs from current ExecWeave schema "
            f"{SCHEMA_VERSION}: {', '.join(sorted(schema_versions))}"
        )

    if require_complete_session and event_count:
        starts = event_types.count("session.started")
        finishes = event_types.count("session.finished")
        if starts != 1:
            errors.append(f"expected exactly one session.started event, found {starts}")
        if finishes != 1:
            errors.append(f"expected exactly one session.finished event, found {finishes}")
        if event_types and event_types[0] != "session.started":
            warnings.append("first event is not session.started")
        if event_types and event_types[-1] != "session.finished":
            warnings.append("last event is not session.finished")

    return ValidationResult(
        path=str(stream_path),
        valid=not errors,
        event_count=event_count,
        errors=errors,
        warnings=warnings,
        session_ids=sorted(session_ids),
        schema_versions=sorted(schema_versions),
    )
