from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

OPENCODE_EVENTS_REFERENCE = "https://opencode.ai/docs/plugins/"

OFFICIAL_OPENCODE_BUS_EVENTS = frozenset(
    {
        "command.executed",
        "file.edited",
        "file.watcher.updated",
        "installation.updated",
        "lsp.client.diagnostics",
        "lsp.updated",
        "message.part.removed",
        "message.part.updated",
        "message.removed",
        "message.updated",
        "permission.asked",
        "permission.replied",
        "server.connected",
        "session.compacted",
        "session.created",
        "session.deleted",
        "session.diff",
        "session.error",
        "session.idle",
        "session.status",
        "session.updated",
        "shell.env",
        "todo.updated",
        "tool.execute.after",
        "tool.execute.before",
        "tui.command.execute",
        "tui.prompt.append",
        "tui.toast.show",
    }
)

_ALREADY_PROJECTED_ELSEWHERE = frozenset(
    {
        "session.created",
        "session.updated",
        "message.updated",
        "message.part.updated",
        "tool.execute.before",
        "tool.execute.after",
    }
)


def _entity(
    entity_type: str,
    entity_id: str,
    *,
    name: str | None = None,
    attributes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "type": entity_type,
        "id": entity_id,
        "name": name,
        "attributes": attributes or {},
    }


def _root_agent() -> dict[str, Any]:
    return _entity(
        "agent",
        "agent:OpenCode",
        name="OpenCode",
        attributes={"provider": "opencode"},
    )


def _session_agent(session_id: str) -> dict[str, Any]:
    return _entity(
        "agent",
        f"agent:opencode:session:{session_id}",
        name="OpenCode session",
        attributes={
            "provider": "opencode",
            "session_id": session_id,
            "identity_semantics": "provider_session_id",
        },
    )


def _event(
    *,
    timestamp: str,
    event_type: str,
    relation: str,
    source: dict[str, Any],
    target: dict[str, Any],
    attributes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    merged: dict[str, Any] = {
        "backend": "semantic",
        "provider": "opencode",
        "evidence_source": "provider_plugin",
        "attribution": "opencode_official_event_bus",
        "causal": False,
        "inferred": False,
        "official_event_contract": True,
        "official_event_reference": OPENCODE_EVENTS_REFERENCE,
        "opencode_event_type": event_type,
    }
    if attributes:
        merged.update(attributes)
    return {
        "timestamp": timestamp,
        "event_type": f"semantic.opencode.{event_type.replace('.', '_')}",
        "relation": relation,
        "source": source,
        "target": target,
        "attributes": merged,
    }


def _body(raw_event: dict[str, Any]) -> dict[str, Any]:
    properties = raw_event.get("properties")
    if isinstance(properties, dict):
        return properties
    data = raw_event.get("data")
    if isinstance(data, dict):
        return data
    return raw_event


def _string(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _session_id(body: dict[str, Any], payload: dict[str, Any]) -> str | None:
    return (
        _string(body.get("sessionID"))
        or _string(body.get("sessionId"))
        or _string(body.get("session_id"))
        or _string(payload.get("sessionID"))
    )


def _digest(value: Any) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _observation(
    entity_type: str,
    *,
    event_type: str,
    body: dict[str, Any],
    timestamp: str,
    name: str,
    attributes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ident = _digest(
        {
            "event_type": event_type,
            "body": body,
            "observed_at": timestamp,
        }
    )
    merged = {
        "provider": "opencode",
        "identity_semantics": "collector_observation_hash_without_provider_event_id",
    }
    if attributes:
        merged.update(attributes)
    return _entity(
        entity_type,
        f"{entity_type}:opencode:{ident}",
        name=name,
        attributes=merged,
    )


def _permission_request(session_id: str, request_id: str) -> dict[str, Any]:
    return _entity(
        "permission_request",
        f"permission-request:opencode:{session_id}:{request_id}",
        name="OpenCode permission request",
        attributes={
            "provider": "opencode",
            "session_id": session_id,
            "permission_request_id": request_id,
            "identity_semantics": "provider_permission_request_id",
        },
    )


def _message(session_id: str, message_id: str) -> dict[str, Any]:
    return _entity(
        "agent_message",
        f"agent-message:opencode:{session_id}:{message_id}",
        name="OpenCode message",
        attributes={
            "provider": "opencode",
            "session_id": session_id,
            "message_id": message_id,
            "identity_semantics": "provider_message_id",
        },
    )


def _file_entity(raw_path: str, payload: dict[str, Any]) -> dict[str, Any]:
    candidate = Path(raw_path).expanduser()
    cwd = _string(payload.get("cwd"))
    if not candidate.is_absolute() and cwd is not None:
        candidate = Path(cwd) / candidate
    path = str(candidate)
    return _entity(
        "file",
        f"file:{path}",
        name=candidate.name or path,
        attributes={
            "provider": "opencode",
            "provider_path": raw_path,
            "declared_by_provider_event": True,
            "path_resolution_semantics": (
                "provider_absolute_path"
                if Path(raw_path).is_absolute()
                else "provider_relative_path_joined_to_plugin_cwd"
                if cwd is not None
                else "provider_relative_path_without_cwd"
            ),
        },
    )


def _session_deleted(
    body: dict[str, Any],
    payload: dict[str, Any],
    *,
    timestamp: str,
    event_type: str,
) -> list[dict[str, Any]]:
    session_id = _session_id(body, payload)
    if session_id is None:
        return []
    return [
        _event(
            timestamp=timestamp,
            event_type=event_type,
            relation="OBSERVED_AGENT_SESSION_DELETED",
            source=_root_agent(),
            target=_session_agent(session_id),
            attributes={
                "provider_session_id_exact": True,
                "session_info_present": isinstance(body.get("info"), dict),
            },
        )
    ]


def _session_status(
    body: dict[str, Any],
    payload: dict[str, Any],
    *,
    timestamp: str,
    event_type: str,
) -> list[dict[str, Any]]:
    session_id = _session_id(body, payload)
    status = body.get("status")
    if session_id is None or not isinstance(status, dict):
        return []
    status_type = _string(status.get("type"))
    if status_type is None:
        return []
    attributes: dict[str, Any] = {
        "provider_session_id_exact": True,
        "status_type": status_type,
        "status_payload_preserved_by_raw_event": True,
    }
    attempt = status.get("attempt")
    if isinstance(attempt, int) and not isinstance(attempt, bool) and attempt >= 0:
        attributes["retry_attempt"] = attempt
    next_value = status.get("next")
    if isinstance(next_value, (int, float)) and not isinstance(next_value, bool):
        attributes["retry_next"] = next_value
    target = _observation(
        "provider_session_status",
        event_type=event_type,
        body=body,
        timestamp=timestamp,
        name=f"OpenCode session status: {status_type}",
        attributes={"session_id": session_id, "status_type": status_type},
    )
    return [
        _event(
            timestamp=timestamp,
            event_type=event_type,
            relation="OBSERVED_PROVIDER_SESSION_STATUS",
            source=_session_agent(session_id),
            target=target,
            attributes=attributes,
        )
    ]


def _session_idle(
    body: dict[str, Any],
    payload: dict[str, Any],
    *,
    timestamp: str,
    event_type: str,
) -> list[dict[str, Any]]:
    session_id = _session_id(body, payload)
    if session_id is None:
        return []
    target = _observation(
        "provider_session_status",
        event_type=event_type,
        body=body,
        timestamp=timestamp,
        name="OpenCode session idle",
        attributes={"session_id": session_id, "status_type": "idle"},
    )
    return [
        _event(
            timestamp=timestamp,
            event_type=event_type,
            relation="OBSERVED_PROVIDER_SESSION_IDLE",
            source=_session_agent(session_id),
            target=target,
            attributes={"provider_session_id_exact": True},
        )
    ]


def _session_compacted(
    body: dict[str, Any],
    payload: dict[str, Any],
    *,
    timestamp: str,
    event_type: str,
) -> list[dict[str, Any]]:
    session_id = _session_id(body, payload)
    if session_id is None:
        return []
    target = _observation(
        "context_compaction",
        event_type=event_type,
        body=body,
        timestamp=timestamp,
        name="OpenCode session compaction",
        attributes={
            "session_id": session_id,
            "compaction_id_available": False,
        },
    )
    return [
        _event(
            timestamp=timestamp,
            event_type=event_type,
            relation="COMPACTED_CONTEXT",
            source=_session_agent(session_id),
            target=target,
            attributes={
                "provider_session_id_exact": True,
                "compaction_completion_observed_from_provider_event": True,
                "compaction_id_available": False,
            },
        )
    ]


def _session_error(
    body: dict[str, Any],
    payload: dict[str, Any],
    *,
    timestamp: str,
    event_type: str,
) -> list[dict[str, Any]]:
    if "error" not in body:
        return []
    session_id = _session_id(body, payload)
    target = _observation(
        "provider_error_observation",
        event_type=event_type,
        body=body,
        timestamp=timestamp,
        name="OpenCode session error",
        attributes={
            "session_id": session_id,
            "error_payload_preserved_by_raw_event": True,
        },
    )
    return [
        _event(
            timestamp=timestamp,
            event_type=event_type,
            relation="OBSERVED_PROVIDER_SESSION_ERROR",
            source=_session_agent(session_id) if session_id is not None else _root_agent(),
            target=target,
            attributes={
                "provider_session_id_exact": session_id is not None,
                "session_identity_available": session_id is not None,
                "error_payload_preserved_by_raw_event": True,
            },
        )
    ]


def _session_diff(
    body: dict[str, Any],
    payload: dict[str, Any],
    *,
    timestamp: str,
    event_type: str,
) -> list[dict[str, Any]]:
    session_id = _session_id(body, payload)
    diff = body.get("diff")
    if session_id is None or not isinstance(diff, list):
        return []
    target = _observation(
        "session_diff_observation",
        event_type=event_type,
        body={"sessionID": session_id, "diff_count": len(diff)},
        timestamp=timestamp,
        name="OpenCode session diff",
        attributes={"session_id": session_id, "file_diff_count": len(diff)},
    )
    return [
        _event(
            timestamp=timestamp,
            event_type=event_type,
            relation="OBSERVED_SESSION_DIFF",
            source=_session_agent(session_id),
            target=target,
            attributes={
                "provider_session_id_exact": True,
                "file_diff_count": len(diff),
                "diff_payload_preserved_by_raw_event": True,
            },
        )
    ]


def _permission_asked(
    body: dict[str, Any],
    *,
    timestamp: str,
    event_type: str,
) -> list[dict[str, Any]]:
    session_id = _string(body.get("sessionID"))
    request_id = _string(body.get("id"))
    permission = _string(body.get("permission"))
    if session_id is None or request_id is None or permission is None:
        return []
    patterns = body.get("patterns")
    always = body.get("always")
    request = _permission_request(session_id, request_id)
    attributes = {
        "provider_session_id_exact": True,
        "provider_permission_request_id_exact": True,
        "permission": permission,
        "pattern_count": len(patterns) if isinstance(patterns, list) else None,
        "always_pattern_count": len(always) if isinstance(always, list) else None,
        "request_payload_preserved_by_raw_event": True,
    }
    events = [
        _event(
            timestamp=timestamp,
            event_type=event_type,
            relation="OBSERVED_PERMISSION_REQUEST",
            source=_session_agent(session_id),
            target=request,
            attributes=attributes,
        )
    ]
    tool = body.get("tool")
    if isinstance(tool, dict):
        call_id = _string(tool.get("callID"))
        if call_id is not None:
            message_id = _string(tool.get("messageID"))
            call = _entity(
                "tool_call",
                f"tool-call:opencode:{session_id}:{call_id}",
                name="OpenCode tool call",
                attributes={
                    "provider": "opencode",
                    "session_id": session_id,
                    "call_id": call_id,
                    "identity_semantics": "provider_call_id",
                },
            )
            tool_attributes: dict[str, Any] = {
                "provider_session_id_exact": True,
                "provider_tool_call_id_exact": True,
            }
            if message_id is not None:
                tool_attributes["provider_message_id_exact"] = True
                tool_attributes["message_id"] = message_id
            events.append(
                _event(
                    timestamp=timestamp,
                    event_type=event_type,
                    relation="PERMISSION_TARGETS_TOOL_CALL",
                    source=request,
                    target=call,
                    attributes=tool_attributes,
                )
            )
    return events


def _permission_replied(
    body: dict[str, Any],
    *,
    timestamp: str,
    event_type: str,
) -> list[dict[str, Any]]:
    session_id = _string(body.get("sessionID"))
    request_id = _string(body.get("requestID"))
    reply = _string(body.get("reply"))
    if session_id is None or request_id is None or reply not in {"once", "always", "reject"}:
        return []
    return [
        _event(
            timestamp=timestamp,
            event_type=event_type,
            relation="OBSERVED_PERMISSION_REPLY",
            source=_session_agent(session_id),
            target=_permission_request(session_id, request_id),
            attributes={
                "provider_session_id_exact": True,
                "provider_permission_request_id_exact": True,
                "reply": reply,
            },
        )
    ]


def _file_edited(
    body: dict[str, Any],
    payload: dict[str, Any],
    *,
    timestamp: str,
    event_type: str,
) -> list[dict[str, Any]]:
    raw_path = _string(body.get("file"))
    if raw_path is None:
        return []
    return [
        _event(
            timestamp=timestamp,
            event_type=event_type,
            relation="OBSERVED_FILE_CHANGE",
            source=_root_agent(),
            target=_file_entity(raw_path, payload),
            attributes={"provider_file_path_exact": True},
        )
    ]


def _todo_updated(
    body: dict[str, Any],
    payload: dict[str, Any],
    *,
    timestamp: str,
    event_type: str,
) -> list[dict[str, Any]]:
    session_id = _session_id(body, payload)
    todos = body.get("todos")
    if session_id is None or not isinstance(todos, list):
        return []
    status_counts: dict[str, int] = {}
    for todo in todos:
        if not isinstance(todo, dict):
            continue
        status = _string(todo.get("status"))
        if status is not None:
            status_counts[status] = status_counts.get(status, 0) + 1
    target = _observation(
        "todo_state",
        event_type=event_type,
        body={"sessionID": session_id, "todo_count": len(todos), "status_counts": status_counts},
        timestamp=timestamp,
        name="OpenCode todo state",
        attributes={
            "session_id": session_id,
            "todo_count": len(todos),
            "status_counts": status_counts,
        },
    )
    return [
        _event(
            timestamp=timestamp,
            event_type=event_type,
            relation="OBSERVED_TODO_STATE",
            source=_session_agent(session_id),
            target=target,
            attributes={
                "provider_session_id_exact": True,
                "todo_count": len(todos),
                "todo_status_counts": status_counts,
                "todo_payload_preserved_by_raw_event": True,
            },
        )
    ]


def _message_removed(
    body: dict[str, Any],
    payload: dict[str, Any],
    *,
    timestamp: str,
    event_type: str,
) -> list[dict[str, Any]]:
    session_id = _session_id(body, payload)
    message_id = _string(body.get("messageID"))
    if session_id is None or message_id is None:
        return []
    return [
        _event(
            timestamp=timestamp,
            event_type=event_type,
            relation="OBSERVED_MESSAGE_REMOVED",
            source=_session_agent(session_id),
            target=_message(session_id, message_id),
            attributes={
                "provider_session_id_exact": True,
                "provider_message_id_exact": True,
            },
        )
    ]


def _message_part_removed(
    body: dict[str, Any],
    payload: dict[str, Any],
    *,
    timestamp: str,
    event_type: str,
) -> list[dict[str, Any]]:
    session_id = _session_id(body, payload)
    message_id = _string(body.get("messageID"))
    part_id = _string(body.get("partID"))
    if session_id is None or message_id is None or part_id is None:
        return []
    message = _message(session_id, message_id)
    part = _entity(
        "message_part",
        f"message-part:opencode:{session_id}:{message_id}:{part_id}",
        name="OpenCode message part",
        attributes={
            "provider": "opencode",
            "session_id": session_id,
            "message_id": message_id,
            "part_id": part_id,
            "identity_semantics": "provider_message_and_part_ids",
        },
    )
    return [
        _event(
            timestamp=timestamp,
            event_type=event_type,
            relation="OBSERVED_MESSAGE_PART_REMOVED",
            source=message,
            target=part,
            attributes={
                "provider_session_id_exact": True,
                "provider_message_id_exact": True,
                "provider_part_id_exact": True,
            },
        )
    ]


def opencode_official_event_semantic_events(
    payload: dict[str, Any],
    *,
    timestamp: str,
) -> list[dict[str, Any]]:
    """Project stable execution semantics from OpenCode's official event bus.

    The complete raw event is preserved separately by ``opencode_full_fidelity``.
    This projector keeps only stable identifiers, statuses, counts, and explicit
    provider linkages; it never reconstructs message/error/todo bodies from time
    proximity or duplicates those bodies into graph attributes.
    """

    if payload.get("hook_event_name") != "event":
        return []
    raw_event = payload.get("event")
    if not isinstance(raw_event, dict):
        return []
    event_type = _string(raw_event.get("type")) or _string(payload.get("event_type"))
    if (
        event_type is None
        or event_type not in OFFICIAL_OPENCODE_BUS_EVENTS
        or event_type in _ALREADY_PROJECTED_ELSEWHERE
    ):
        return []
    body = _body(raw_event)

    handlers = {
        "session.deleted": _session_deleted,
        "session.status": _session_status,
        "session.idle": _session_idle,
        "session.compacted": _session_compacted,
        "session.error": _session_error,
        "session.diff": _session_diff,
        "file.edited": _file_edited,
        "todo.updated": _todo_updated,
        "message.removed": _message_removed,
        "message.part.removed": _message_part_removed,
    }
    if event_type == "permission.asked":
        return _permission_asked(body, timestamp=timestamp, event_type=event_type)
    if event_type == "permission.replied":
        return _permission_replied(body, timestamp=timestamp, event_type=event_type)
    handler = handlers.get(event_type)
    if handler is None:
        return []
    return handler(
        body,
        payload,
        timestamp=timestamp,
        event_type=event_type,
    )
