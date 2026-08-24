from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

SCHEMA_VERSION = "0.2"


@dataclass(frozen=True)
class Entity:
    """A graph entity referenced by a runtime event."""

    type: str
    id: str
    name: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuntimeEvent:
    """One graph-ready observation represented as source -> relation -> target."""

    schema_version: str
    event_id: str
    session_id: str
    timestamp: str
    event_type: str
    relation: str
    source: Entity | None
    target: Entity | None
    sequence: int | None = None
    attributes: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        session_id: str,
        event_type: str,
        relation: str,
        source: Entity | None = None,
        target: Entity | None = None,
        attributes: dict[str, Any] | None = None,
        timestamp: str | None = None,
    ) -> "RuntimeEvent":
        return cls(
            schema_version=SCHEMA_VERSION,
            event_id=str(uuid4()),
            session_id=session_id,
            timestamp=timestamp
            or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            event_type=event_type,
            relation=relation,
            source=source,
            target=target,
            attributes=attributes or {},
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
