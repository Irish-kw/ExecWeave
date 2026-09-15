"""Public framework adapter SDK.

Framework integrations translate authoritative callbacks/events into canonical
records here. The core collector never guesses logical agents from process
names or network traffic.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Mapping
from uuid import uuid4

from ..content_store import ContentReference, FullFidelityContentStore
from ..schema import SCHEMA_VERSION

CaptureMode = Literal[
    "metadata_only",
    "content_ref_only",
    "prompt_only",
    "prompt_and_response",
]

CANONICAL_EVENT_TYPES = frozenset(
    {
        "AGENT_CREATED", "AGENT_STARTED", "AGENT_STOPPED",
        "TASK_CREATED", "TASK_ASSIGNED", "TASK_STARTED", "TASK_UPDATED",
        "TASK_COMPLETED", "TASK_FAILED",
        "MESSAGE_SENT", "MESSAGE_RECEIVED", "MESSAGE_UNROUTED",
        "MODEL_REQUEST", "MODEL_RESPONSE", "MODEL_FAILURE",
        "TOOL_CALL", "TOOL_RESULT", "TOOL_FAILURE",
        "MESSAGE_CONTENT_RECORDED", "MODEL_CONTENT_RECORDED", "TOOL_CONTENT_RECORDED",
    }
)
_CAPTURE_MODES = frozenset({"metadata_only", "content_ref_only", "prompt_only", "prompt_and_response"})
_HIDDEN_CONTENT_MARKERS = frozenset({
    "chain_of_thought", "chain-of-thought", "internal_reasoning",
    "hidden_reasoning", "thinking_tokens", "private_reasoning",
})
_ID_SAFE = re.compile(r"[^A-Za-z0-9_.:-]+")
_CREDENTIAL_KEYS = frozenset({
    "authorization", "proxy-authorization", "cookie", "set-cookie",
    "x-api-key", "api-key", "api_key", "apikey", "access_token",
    "refresh_token", "client_secret", "password", "token",
})


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def stable_id(entity_type: str, native_id: str | int | None, *, framework: str, run_id: str) -> str:
    """Create a deterministic run-scoped ID without timestamps or content."""
    if not entity_type or not framework or not run_id:
        raise ValueError("entity_type, framework, and run_id are required")
    native = str(native_id).strip() if native_id is not None else "anonymous"
    native = native or "anonymous"
    def clean(value):
        return _ID_SAFE.sub("_", str(value).strip())
    if native_id is not None:
        return f"{clean(entity_type).lower()}:{clean(framework).lower()}:{clean(run_id)}:{clean(native)}"
    digest = hashlib.sha256(f"{entity_type}\0{framework}\0{run_id}".encode()).hexdigest()[:20]
    return f"{clean(entity_type).lower()}:{clean(framework).lower()}:{clean(run_id)}:{digest}"


def _clean_metadata(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _clean_metadata(child)
            for key, child in value.items()
            if str(key).lower() not in _CREDENTIAL_KEYS
        }
    if isinstance(value, list):
        return [_clean_metadata(child) for child in value]
    if isinstance(value, tuple):
        return [_clean_metadata(child) for child in value]
    return value


def _string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _entity_label(entity: EntityRef | None) -> str | None:
    if entity is None:
        return None
    return entity.name or entity.id


@dataclass(frozen=True)
class EntityRef:
    type: str
    id: str
    name: str | None = None
    attributes: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.type or not self.id:
            raise ValueError("entity type and id must be non-empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "id": self.id,
            "name": self.name,
            "attributes": _clean_metadata(dict(self.attributes)),
        }


@dataclass(frozen=True)
class ProcessRef:
    pid: int
    create_time: float | None = None
    executable: str | None = None

    def to_entity(self) -> EntityRef:
        if self.pid <= 0:
            raise ValueError("process pid must be positive")
        attributes: dict[str, Any] = {"pid": self.pid}
        if self.create_time is not None:
            attributes["create_time"] = float(self.create_time)
        if self.executable:
            attributes["executable"] = self.executable
        identity = f"{self.pid}:{self.create_time}" if self.create_time is not None else str(self.pid)
        return EntityRef("process_reference", f"process-reference:{identity}", self.executable or f"pid {self.pid}", attributes)


@dataclass(frozen=True)
class AdapterCapabilities:
    events: tuple[str, ...] = ()
    entities: tuple[str, ...] = ("agent", "task", "message", "model", "tool", "process")
    content_modes: tuple[str, ...] = ("metadata_only",)
    authoritative_surfaces: tuple[str, ...] = ()
    known_limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        unknown = set(self.events) - CANONICAL_EVENT_TYPES
        if unknown:
            raise ValueError(f"unknown canonical event types: {sorted(unknown)}")
        unknown_modes = set(self.content_modes) - _CAPTURE_MODES
        if unknown_modes:
            raise ValueError(f"unknown capture modes: {sorted(unknown_modes)}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FrameworkCompatibility:
    framework: str
    detected_version: str | None
    tested_versions: tuple[str, ...] = ()
    compatibility_status: Literal["verified", "warn", "unsupported", "unknown"] = "unknown"
    capabilities: AdapterCapabilities = field(default_factory=AdapterCapabilities)
    known_limitations: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["capabilities"] = self.capabilities.to_dict()
        return result


@dataclass(frozen=True)
class ContentCapturePolicy:
    mode: CaptureMode = "metadata_only"
    redact_metadata: bool = True

    def __post_init__(self) -> None:
        if self.mode not in _CAPTURE_MODES:
            raise ValueError(f"unsupported capture mode: {self.mode}")

    def allows(self, content_kind: str) -> bool:
        normalized = content_kind.strip().lower()
        if any(marker in normalized for marker in _HIDDEN_CONTENT_MARKERS):
            return False
        if self.mode == "metadata_only":
            return False
        if self.mode == "prompt_only":
            return any(token in normalized for token in ("prompt", "request", "message", "task"))
        return True


class ContentWriter:
    """Policy-aware facade over the run-local content-addressed store."""

    def __init__(self, run_root: str | Path, *, policy: ContentCapturePolicy = ContentCapturePolicy()) -> None:
        self.policy = policy
        self.store = FullFidelityContentStore(run_root)

    def put_text(self, value: str, *, content_kind: str, media_type: str = "text/plain; charset=utf-8") -> ContentReference | None:
        if not isinstance(value, str):
            raise TypeError("content value must be text")
        if not self.policy.allows(content_kind):
            return None
        return self.store.put_text(value, content_kind=content_kind, media_type=media_type)

    def put_json(self, value: Any, *, content_kind: str) -> ContentReference | None:
        if not self.policy.allows(content_kind):
            return None
        return self.store.put_json(value, content_kind=content_kind)

    def reference_attributes(self, reference: ContentReference | None) -> dict[str, Any]:
        if reference is None:
            return {"capture_mode": "metadata_only", "content_available": False}
        return {
            "capture_mode": "content_ref_only",
            "content_available": True,
            "content_ref": reference.path,
            "content_sha256": reference.sha256,
            "content_kind": reference.content_kind,
            "content_media_type": reference.media_type,
            "content_size_bytes": reference.size_bytes,
            "content_complete_from_source": reference.complete_from_source,
        }


class SemanticWriter:
    """Append canonical semantic records to the active ExecWeave sidecar."""

    _process_locks: dict[str, threading.Lock] = {}

    def __init__(self, path: str | Path | None = None) -> None:
        configured = path or os.environ.get("EXECWEAVE_SEMANTIC_SIDECAR")
        self.path = Path(configured).expanduser().resolve() if configured else None

    @property
    def enabled(self) -> bool:
        return self.path is not None

    def emit(self, *, event_type: str, relation: str, source: EntityRef | None = None, target: EntityRef | None = None, attributes: Mapping[str, Any] | None = None, timestamp: str | None = None, event_id: str | None = None) -> dict[str, Any]:
        if event_type not in CANONICAL_EVENT_TYPES:
            raise ValueError(f"unsupported canonical event type: {event_type}")
        if not relation:
            raise ValueError("relation must not be empty")
        if self.path is None:
            raise RuntimeError("semantic output is disabled; set EXECWEAVE_SEMANTIC_SIDECAR or pass a path")
        record = {
            "schema_version": SCHEMA_VERSION,
            "event_id": event_id or f"semantic:{uuid4()}",
            "timestamp": timestamp or utc_now(),
            "event_type": event_type,
            "relation": relation,
            "source": source.to_dict() if source is not None else None,
            "target": target.to_dict() if target is not None else None,
            "attributes": _clean_metadata(dict(attributes or {})),
        }
        self.append(record)
        return record

    def append(self, record: Mapping[str, Any]) -> None:
        if self.path is None:
            raise RuntimeError("semantic output is disabled")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(dict(record), ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        lock = self._process_locks.setdefault(str(self.path), threading.Lock())
        with lock:
            lock_dir = self.path.with_name(self.path.name + ".lock")
            deadline = time.monotonic() + 5.0
            while True:
                try:
                    lock_dir.mkdir()
                    break
                except FileExistsError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError(f"timed out waiting for semantic sidecar lock: {lock_dir}")
                    time.sleep(0.01)
            try:
                with self.path.open("a", encoding="utf-8", newline="\n") as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
            finally:
                lock_dir.rmdir()


@dataclass(frozen=True)
class AgentRecord:
    agent: EntityRef
    role: str | None = None
    process: ProcessRef | None = None
    parent_agent: EntityRef | None = None
    attributes: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TaskRecord:
    task: EntityRef
    owner: EntityRef | None = None
    parent_task: EntityRef | None = None
    attributes: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MessageRecord:
    message: EntityRef
    source: EntityRef | None
    target: EntityRef | None
    role: str | None = None
    task: EntityRef | None = None
    parent_message: EntityRef | None = None
    content: str | None = None
    content_kind: str = "message"
    direction: Literal["sent", "received"] = "sent"
    attributes: Mapping[str, Any] = field(default_factory=dict)
    content_payload: Any | None = None


@dataclass(frozen=True)
class ModelCallRecord:
    model_call: EntityRef
    requesting_agent: EntityRef | None
    model: EntityRef
    request: Any | None = None
    response: Any | None = None
    content_kind: str = "model_request"
    status: Literal["request", "response", "failure"] = "request"
    task: EntityRef | None = None
    attributes: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolCallRecord:
    tool_call: EntityRef
    requesting_agent: EntityRef | None
    tool: EntityRef
    arguments: Any | None = None
    result: Any | None = None
    status: Literal["call", "result", "failure"] = "call"
    task: EntityRef | None = None
    attributes: Mapping[str, Any] = field(default_factory=dict)


class AdapterContext:
    """Run-scoped state shared by a framework adapter."""

    def __init__(self, *, framework: str, run_id: str | None = None, session_id: str | None = None, conversation_id: str | None = None, sidecar: str | Path | None = None, content_root: str | Path | None = None, capture_policy: ContentCapturePolicy = ContentCapturePolicy(), process: ProcessRef | None = None) -> None:
        if not framework.strip():
            raise ValueError("framework must not be empty")
        self.framework = framework.strip().lower()
        self.run_id = run_id or os.environ.get("EXECWEAVE_RUN_ID") or uuid4().hex
        self.session_id = session_id or os.environ.get("EXECWEAVE_SESSION_ID") or self.run_id
        self.conversation_id = conversation_id or os.environ.get("EXECWEAVE_CONVERSATION_ID")
        self.writer = SemanticWriter(sidecar)
        root = Path(content_root or (self.writer.path.parent if self.writer.path else Path.cwd()))
        self.content = ContentWriter(root, policy=capture_policy)
        self.capture_policy = capture_policy
        self.process = process

    @classmethod
    def from_environment(cls, framework: str, *, capture_mode: CaptureMode = "metadata_only", content_root: str | Path | None = None, run_id: str | None = None, session_id: str | None = None, conversation_id: str | None = None, process: ProcessRef | None = None) -> "AdapterContext":
        return cls(framework=framework, run_id=run_id, session_id=session_id, conversation_id=conversation_id, content_root=content_root, capture_policy=ContentCapturePolicy(capture_mode), process=process)

    def entity(self, entity_type: str, native_id: str | int | None, *, name: str | None = None, attributes: Mapping[str, Any] | None = None) -> EntityRef:
        values = dict(attributes or {})
        values.setdefault("framework", self.framework)
        values.setdefault("run_id", self.run_id)
        values.setdefault("session_id", self.session_id)
        if self.conversation_id:
            values.setdefault("conversation_id", self.conversation_id)
        return EntityRef(entity_type, stable_id(entity_type, native_id, framework=self.framework, run_id=self.run_id), name or _string(native_id), values)

    def emit(self, event_type: str, relation: str, *, source: EntityRef | None = None, target: EntityRef | None = None, attributes: Mapping[str, Any] | None = None, timestamp: str | None = None) -> dict[str, Any]:
        values = {"framework": self.framework, "run_id": self.run_id, "session_id": self.session_id, "capture_mode": self.capture_policy.mode, **dict(attributes or {})}
        if self.conversation_id:
            values.setdefault("conversation_id", self.conversation_id)
        return self.writer.emit(event_type=event_type, relation=relation, source=source, target=target, attributes=values, timestamp=timestamp)

    def correlate_process(self, entity: EntityRef, process: ProcessRef | None = None) -> dict[str, Any] | None:
        reference = process or self.process
        if reference is None:
            return None
        return self.emit("AGENT_STARTED", "CORRELATED_WITH_PROCESS", source=entity, target=reference.to_entity(), attributes={"correlation_kind": "logical_agent_to_process"})

    def record_agent(self, record: AgentRecord, *, event_type: str = "AGENT_CREATED") -> EntityRef:
        self.emit(event_type, event_type, source=record.agent, attributes={"role": record.role, **dict(record.attributes)})
        if record.process is not None or self.process is not None:
            self.correlate_process(record.agent, record.process)
        if record.parent_agent is not None:
            self.emit("AGENT_CREATED", "PARENT_AGENT", source=record.parent_agent, target=record.agent, attributes={"relationship": "child_agent", **dict(record.attributes)})
        return record.agent

    def record_task(self, record: TaskRecord, *, event_type: str = "TASK_CREATED") -> EntityRef:
        self.emit(event_type, event_type, source=record.owner, target=record.task, attributes={"parent_task_id": record.parent_task.id if record.parent_task else None, **dict(record.attributes)})
        if record.parent_task is not None:
            self.emit("TASK_CREATED", "PARENT_TASK", source=record.parent_task, target=record.task, attributes={"parent_task_id": record.parent_task.id})
        return record.task

    def record_message(self, record: MessageRecord) -> EntityRef:
        content_kind = f"{self.framework}.agent_message"
        message_payload = record.content_payload if record.content_payload is not None else {
            "message_id": record.message.id,
            "text": record.content,
            "sender": _entity_label(record.source),
            "recipient": _entity_label(record.target),
            "role": record.role,
            "kind": "agent_message",
            "phase": "received" if record.direction == "received" else "sent",
            "content_state": "plaintext",
        }
        reference = self.content.put_json(message_payload, content_kind=content_kind) if record.content is not None else None
        attrs = {"message_id": record.message.id, "role": record.role, "task_id": record.task.id if record.task else None, "parent_message_id": record.parent_message.id if record.parent_message else None, "sender_agent_id": record.source.id if record.source and record.source.type == "agent" else None, "recipient_agent_id": record.target.id if record.target and record.target.type == "agent" else None, **self.content.reference_attributes(reference), **dict(record.attributes)}
        event_type = "MESSAGE_SENT" if record.direction == "sent" else "MESSAGE_RECEIVED"
        self.emit(event_type, event_type, source=record.source, target=record.target or record.message, attributes=attrs)
        if reference is not None:
            content = EntityRef("observed_content", f"observed-content:message:sha256:{reference.sha256}", reference.content_kind, reference.to_dict())
            participants: list[tuple[EntityRef, str]] = []
            for side, participant in (("sender", record.source), ("recipient", record.target)):
                if participant is None or participant.type != "agent":
                    continue
                if any(existing.id == participant.id for existing, _ in participants):
                    participants = [(existing, "sender_and_recipient" if existing.id == participant.id else existing_side) for existing, existing_side in participants]
                    continue
                participants.append((participant, side))
            if not participants:
                participants = [(record.message, "message")]
            for participant, side in participants:
                self.emit(
                    "MESSAGE_CONTENT_RECORDED",
                    "HAS_MESSAGE_CONTENT",
                    source=participant,
                    target=content,
                    attributes={
                        "message_id": record.message.id,
                        "conversation_scope": "agent" if participant.type == "agent" else "message",
                        "conversation_side": side,
                        "conversation_agent_id": participant.id if participant.type == "agent" else None,
                        **self.content.reference_attributes(reference),
                    },
                )
        return record.message

    def record_model_call(self, record: ModelCallRecord) -> EntityRef:
        if record.status == "request":
            event_type, relation, value, kind = "MODEL_REQUEST", "REQUESTS_MODEL_CALL", record.request, f"{self.framework}.model_request"
        elif record.status == "response":
            event_type, relation, value, kind = "MODEL_RESPONSE", "MODEL_CALL_RESPONDS", record.response, f"{self.framework}.model_response"
        else:
            event_type, relation, value, kind = "MODEL_FAILURE", "MODEL_CALL_FAILED", record.response or record.request, f"{self.framework}.model_failure"
        reference = self.content.put_text(value, content_kind=kind) if isinstance(value, str) else self.content.put_json(value, content_kind=kind) if value is not None else None
        attrs = {"model_call_id": record.model_call.id, "task_id": record.task.id if record.task else None, "requesting_agent_id": record.requesting_agent.id if record.requesting_agent else None, **self.content.reference_attributes(reference), **dict(record.attributes)}
        self.emit(event_type, relation, source=record.requesting_agent, target=record.model, attributes=attrs)
        if reference is not None:
            content = EntityRef("observed_content", f"observed-content:model:sha256:{reference.sha256}", reference.content_kind, reference.to_dict())
            self.emit(
                "MODEL_CONTENT_RECORDED",
                "HAS_MODEL_CONTENT",
                source=record.requesting_agent or record.model_call,
                target=content,
                attributes={
                    "model_call_id": record.model_call.id,
                    "conversation_scope": "agent" if record.requesting_agent is not None else "model_call",
                    "conversation_agent_id": record.requesting_agent.id if record.requesting_agent else None,
                    **self.content.reference_attributes(reference),
                },
            )
        return record.model_call

    def record_tool_call(self, record: ToolCallRecord) -> EntityRef:
        if record.status == "call":
            event_type, relation, value, kind = "TOOL_CALL", "REQUESTS_TOOL_CALL", record.arguments, "tool_arguments"
        elif record.status == "result":
            event_type, relation, value, kind = "TOOL_RESULT", "TOOL_CALL_RETURNS", record.result, "tool_result"
        else:
            event_type, relation, value, kind = "TOOL_FAILURE", "TOOL_CALL_FAILED", record.result or record.arguments, "tool_failure"
        reference = self.content.put_text(value, content_kind=kind) if isinstance(value, str) else self.content.put_json(value, content_kind=kind) if value is not None else None
        attrs = {"tool_call_id": record.tool_call.id, "task_id": record.task.id if record.task else None, "requesting_agent_id": record.requesting_agent.id if record.requesting_agent else None, **self.content.reference_attributes(reference), **dict(record.attributes)}
        self.emit(event_type, relation, source=record.requesting_agent, target=record.tool, attributes=attrs)
        if reference is not None:
            content = EntityRef("observed_content", f"observed-content:tool:sha256:{reference.sha256}", reference.content_kind, reference.to_dict())
            self.emit("TOOL_CONTENT_RECORDED", "HAS_TOOL_CONTENT", source=record.tool_call, target=content, attributes={"tool_call_id": record.tool_call.id, **self.content.reference_attributes(reference)})
        return record.tool_call


class FrameworkAdapter:
    """Base class for framework-specific authoritative event adapters."""

    framework_name = "generic"
    capabilities = AdapterCapabilities()

    def __init__(self, context: AdapterContext) -> None:
        if context.framework != self.framework_name:
            raise ValueError(f"context framework {context.framework!r} does not match {self.framework_name!r}")
        self.context = context

    @classmethod
    def compatibility(cls) -> FrameworkCompatibility:
        return FrameworkCompatibility(framework=cls.framework_name, detected_version=None, capabilities=cls.capabilities, known_limitations=cls.capabilities.known_limitations)

    def entity(self, entity_type: str, native_id: str | int | None, **kwargs: Any) -> EntityRef:
        return self.context.entity(entity_type, native_id, **kwargs)

    def emit(self, event_type: str, relation: str, **kwargs: Any) -> dict[str, Any]:
        return self.context.emit(event_type, relation, **kwargs)

    def agent(self, native_id: str | int, *, name: str | None = None, **attributes: Any) -> EntityRef:
        native = _ID_SAFE.sub("_", str(native_id).strip()) or "agent"
        values = {
            "conversation_scope": "framework_agent",
            "conversation_agent_id": str(native_id),
            "conversation_agent_path": f"/{self.framework_name}/{native}",
            **attributes,
        }
        return self.entity("agent", native_id, name=name, attributes=values)

    def task(self, native_id: str | int, *, name: str | None = None, **attributes: Any) -> EntityRef:
        return self.entity("task", native_id, name=name, attributes=attributes)

    def model(self, native_id: str | int, *, name: str | None = None, **attributes: Any) -> EntityRef:
        return self.entity("model", native_id, name=name, attributes=attributes)

    def tool(self, native_id: str | int, *, name: str | None = None, **attributes: Any) -> EntityRef:
        return self.entity("tool", native_id, name=name, attributes=attributes)
