from __future__ import annotations

import json
import os
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .codex_adapter import append_semantic_records
from .content_evidence import content_observation_event
from .content_store import ContentReference, FullFidelityContentStore

CODEX_ROLLOUT_TRACE_ROOT_ENV = "CODEX_ROLLOUT_TRACE_ROOT"

_STATE_FILE = "state.json"
_MANIFEST_FILE = "manifest.json"
_RAW_TRACE_FILE = "trace.jsonl"
_BUNDLE_PREFIX = "trace-"


@dataclass(frozen=True)
class CodexRolloutImportResult:
    """Summary of one post-run Codex rollout-trace import."""

    status: str
    trace_root: str
    bundle_count: int = 0
    reduced_bundle_count: int = 0
    semantic_event_count: int = 0
    raw_payload_count: int = 0
    conversation_item_count: int = 0
    reasoning_text_count: int = 0
    reasoning_summary_count: int = 0
    encoded_reasoning_count: int = 0
    agent_message_count: int = 0
    interaction_edge_count: int = 0
    tool_call_count: int = 0
    inference_call_count: int = 0
    terminal_operation_count: int = 0
    code_cell_count: int = 0
    errors: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def codex_rollout_trace_environment(run_dir: str | Path) -> dict[str, str]:
    """Environment needed to opt Codex into its local raw rollout trace."""

    root = Path(run_dir).expanduser().resolve() / "codex-rollout-trace"
    return {CODEX_ROLLOUT_TRACE_ROOT_ENV: str(root)}


def _iso_from_unix_ms(value: object, *, fallback: str | None = None) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return datetime.fromtimestamp(float(value) / 1000.0, timezone.utc).isoformat().replace(
            "+00:00", "Z"
        )
    if fallback is not None:
        return fallback
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _entity(
    entity_type: str,
    entity_id: str,
    *,
    name: str | None = None,
    attributes: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "type": entity_type,
        "id": entity_id,
        "name": name,
        "attributes": dict(attributes or {}),
    }


def _event(
    *,
    timestamp: str,
    event_type: str,
    relation: str,
    source: dict[str, Any],
    target: dict[str, Any],
    attributes: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    merged: dict[str, Any] = {
        "backend": "semantic",
        "provider": "codex",
        "evidence_source": "codex_rollout_trace",
        "attribution": "codex_rollout_trace",
        "causal": False,
        "inferred": False,
    }
    if attributes:
        merged.update(attributes)
    return {
        "timestamp": timestamp,
        "event_type": event_type,
        "relation": relation,
        "source": source,
        "target": target,
        "attributes": merged,
    }


def _thread_entity(thread: Mapping[str, Any], *, rollout_id: str) -> dict[str, Any]:
    thread_id = str(thread.get("thread_id") or "unknown")
    path = thread.get("agent_path")
    nickname = thread.get("nickname")
    name = (
        str(path)
        if isinstance(path, str) and path
        else str(nickname)
        if isinstance(nickname, str) and nickname
        else f"Codex agent {thread_id}"
    )
    attrs: dict[str, Any] = {
        "provider": "codex",
        "rollout_id": rollout_id,
        "thread_id": thread_id,
    }
    for key in ("agent_path", "nickname", "origin", "execution", "default_model"):
        value = thread.get(key)
        if value is not None:
            attrs[key] = value
    return _entity(
        "agent",
        f"agent:codex:rollout:{rollout_id}:thread:{thread_id}",
        name=name,
        attributes=attrs,
    )


def _unknown_thread_entity(thread_id: str, *, rollout_id: str) -> dict[str, Any]:
    return _entity(
        "agent",
        f"agent:codex:rollout:{rollout_id}:thread:{thread_id}",
        name=f"Codex agent {thread_id}",
        attributes={
            "provider": "codex",
            "rollout_id": rollout_id,
            "thread_id": thread_id,
            "unresolved_thread_metadata": True,
        },
    )


def _conversation_entity(
    item_id: str, item: Mapping[str, Any], *, rollout_id: str
) -> dict[str, Any]:
    attrs: dict[str, Any] = {"provider": "codex", "rollout_id": rollout_id, "item_id": item_id}
    for key in ("thread_id", "codex_turn_id", "role", "channel", "kind", "call_id", "agent_message"):
        value = item.get(key)
        if value is not None:
            attrs[key] = value
    return _entity(
        "conversation_item",
        f"conversation-item:codex:{rollout_id}:{item_id}",
        name=f"{item.get('role', 'conversation')}:{item.get('kind', 'item')}",
        attributes=attrs,
    )


def _message_entity(item_id: str, item: Mapping[str, Any], *, rollout_id: str) -> dict[str, Any]:
    routing = item.get("agent_message")
    attrs: dict[str, Any] = {
        "provider": "codex",
        "rollout_id": rollout_id,
        "conversation_item_id": item_id,
        "model_visible": True,
    }
    if isinstance(routing, dict):
        attrs["author"] = routing.get("author")
        attrs["recipient"] = routing.get("recipient")
    return _entity(
        "agent_message",
        f"agent-message:codex:{rollout_id}:{item_id}",
        name="Codex agent message",
        attributes=attrs,
    )


def _tool_call_entity(call_id: str, call: Mapping[str, Any], *, rollout_id: str) -> dict[str, Any]:
    attrs: dict[str, Any] = {
        "provider": "codex",
        "rollout_id": rollout_id,
        "tool_call_id": call_id,
    }
    for key in (
        "mcp_call_id",
        "model_visible_call_id",
        "code_mode_runtime_tool_id",
        "thread_id",
        "started_by_codex_turn_id",
        "execution",
        "requester",
        "kind",
        "summary",
    ):
        value = call.get(key)
        if value is not None:
            attrs[key] = value
    kind = call.get("kind")
    kind_name = _tag_name(kind) or "tool"
    return _entity(
        "tool_call",
        f"tool-call:codex:rollout:{rollout_id}:{call_id}",
        name=kind_name,
        attributes=attrs,
    )


def _inference_entity(call_id: str, call: Mapping[str, Any], *, rollout_id: str) -> dict[str, Any]:
    attrs: dict[str, Any] = {
        "provider": "codex",
        "rollout_id": rollout_id,
        "inference_call_id": call_id,
    }
    for key in (
        "thread_id",
        "codex_turn_id",
        "execution",
        "model",
        "provider_name",
        "response_id",
        "upstream_request_id",
        "usage",
        "request_item_ids",
        "response_item_ids",
        "tool_call_ids_started_by_response",
    ):
        value = call.get(key)
        if value is not None:
            attrs[key] = value
    return _entity(
        "inference_call",
        f"inference-call:codex:{rollout_id}:{call_id}",
        name=str(call.get("model") or "Codex inference"),
        attributes=attrs,
    )


def _terminal_entity(
    operation_id: str, operation: Mapping[str, Any], *, rollout_id: str
) -> dict[str, Any]:
    attrs: dict[str, Any] = {
        "provider": "codex",
        "rollout_id": rollout_id,
        "operation_id": operation_id,
    }
    for key in ("terminal_id", "tool_call_id", "kind", "execution"):
        value = operation.get(key)
        if value is not None:
            attrs[key] = value
    return _entity(
        "terminal_operation",
        f"terminal-operation:codex:{rollout_id}:{operation_id}",
        name=str(operation.get("kind") or "terminal operation"),
        attributes=attrs,
    )


def _code_cell_entity(cell_id: str, cell: Mapping[str, Any], *, rollout_id: str) -> dict[str, Any]:
    attrs: dict[str, Any] = {
        "provider": "codex",
        "rollout_id": rollout_id,
        "code_cell_id": cell_id,
    }
    for key in (
        "model_visible_call_id",
        "thread_id",
        "codex_turn_id",
        "runtime_cell_id",
        "execution",
        "runtime_status",
        "nested_tool_call_ids",
        "wait_tool_call_ids",
    ):
        value = cell.get(key)
        if value is not None:
            attrs[key] = value
    return _entity(
        "code_cell",
        f"code-cell:codex:{rollout_id}:{cell_id}",
        name="Codex code-mode cell",
        attributes=attrs,
    )


def _interaction_entity(
    edge_id: str, edge: Mapping[str, Any], *, rollout_id: str
) -> dict[str, Any]:
    kind = _tag_name(edge.get("kind")) or str(edge.get("kind") or "interaction")
    attrs = {
        "provider": "codex",
        "rollout_id": rollout_id,
        "interaction_edge_id": edge_id,
        "kind": edge.get("kind"),
        "source_anchor": edge.get("source"),
        "target_anchor": edge.get("target"),
        "started_at_unix_ms": edge.get("started_at_unix_ms"),
        "ended_at_unix_ms": edge.get("ended_at_unix_ms"),
        "carried_item_ids": edge.get("carried_item_ids") or [],
        "carried_raw_payload_ids": edge.get("carried_raw_payload_ids") or [],
    }
    return _entity(
        "agent_interaction",
        f"agent-interaction:codex:{rollout_id}:{edge_id}",
        name=kind,
        attributes=attrs,
    )


def _tag_name(value: object) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        tagged = value.get("type")
        if isinstance(tagged, str):
            return tagged
    return None


def _content_kind_suffix(kind: object) -> str:
    if isinstance(kind, str) and kind:
        return kind
    if isinstance(kind, dict):
        value = kind.get("type")
        if isinstance(value, str) and value:
            extra = kind.get("value")
            if isinstance(extra, str) and extra:
                return f"{value}.{extra}"
            return value
    return "unknown"


def _raw_payload_reference(
    *,
    bundle: Path,
    raw_payload_id: str,
    raw_ref: Mapping[str, Any],
    store: FullFidelityContentStore,
    cache: dict[str, ContentReference],
) -> ContentReference | None:
    cache_key = f"{bundle}:{raw_payload_id}"
    if cache_key in cache:
        return cache[cache_key]
    relative = raw_ref.get("path")
    if not isinstance(relative, str) or not relative:
        return None
    try:
        path = (bundle / relative).resolve()
        path.relative_to(bundle.resolve())
    except (OSError, ValueError):
        return None
    if not path.is_file():
        return None
    kind = _content_kind_suffix(raw_ref.get("kind"))
    raw = path.read_bytes()
    try:
        json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        reference = store.put_bytes(
            raw,
            content_kind=f"codex.rollout.raw_payload.{kind}",
            media_type="application/octet-stream",
            representation="codex_rollout_raw_payload",
        )
    else:
        reference = store.put_bytes(
            raw,
            content_kind=f"codex.rollout.raw_payload.{kind}",
            media_type="application/json",
            representation="codex_rollout_raw_json",
        )
    cache[cache_key] = reference
    return reference


def _content_event(
    *,
    store: FullFidelityContentStore,
    value: Any,
    content_kind: str,
    timestamp: str,
    source: dict[str, Any],
    relation: str,
    observed_field: str,
    attributes: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    reference = (
        store.put_text(value, content_kind=content_kind)
        if isinstance(value, str)
        else store.put_json(value, content_kind=content_kind)
    )
    return content_observation_event(
        timestamp=timestamp,
        provider="codex",
        source=source,
        reference=reference,
        relation=relation,
        observed_field=observed_field,
        evidence_source="codex_rollout_trace",
        attribution="codex_rollout_trace",
        event_type="semantic.codex.rollout.content.observed",
        attributes=dict(attributes or {}),
    )


def _raw_content_event(
    *,
    reference: ContentReference,
    timestamp: str,
    source: dict[str, Any],
    relation: str,
    observed_field: str,
    attributes: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return content_observation_event(
        timestamp=timestamp,
        provider="codex",
        source=source,
        reference=reference,
        relation=relation,
        observed_field=observed_field,
        evidence_source="codex_rollout_trace",
        attribution="codex_rollout_trace",
        event_type="semantic.codex.rollout.raw_payload.observed",
        attributes=dict(attributes or {}),
    )


def _body_parts(item: Mapping[str, Any]) -> list[dict[str, Any]]:
    body = item.get("body")
    if not isinstance(body, dict):
        return []
    parts = body.get("parts")
    return [part for part in parts if isinstance(part, dict)] if isinstance(parts, list) else []


def _find_thread_by_path(
    path: object,
    *,
    threads: Mapping[str, Mapping[str, Any]],
    rollout_id: str,
) -> dict[str, Any] | None:
    if not isinstance(path, str) or not path:
        return None
    for thread in threads.values():
        if thread.get("agent_path") == path:
            return _thread_entity(thread, rollout_id=rollout_id)
    return _entity(
        "agent",
        f"agent:codex:rollout:{rollout_id}:path:{path}",
        name=path,
        attributes={
            "provider": "codex",
            "rollout_id": rollout_id,
            "agent_path": path,
            "unresolved_thread_id": True,
        },
    )


def _thread_for_item(
    item: Mapping[str, Any],
    *,
    threads: Mapping[str, Mapping[str, Any]],
    rollout_id: str,
) -> dict[str, Any]:
    thread_id = item.get("thread_id")
    if isinstance(thread_id, str):
        thread = threads.get(thread_id)
        if isinstance(thread, Mapping):
            return _thread_entity(thread, rollout_id=rollout_id)
        return _unknown_thread_entity(thread_id, rollout_id=rollout_id)
    return _unknown_thread_entity("unknown", rollout_id=rollout_id)


def _anchor_entity(
    anchor: object,
    *,
    rollout_id: str,
    threads: Mapping[str, Mapping[str, Any]],
    conversation_items: Mapping[str, Mapping[str, Any]],
    tool_calls: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any] | None:
    if not isinstance(anchor, dict):
        return None
    anchor_type = anchor.get("type")
    if anchor_type == "thread":
        thread_id = anchor.get("thread_id")
        if isinstance(thread_id, str):
            thread = threads.get(thread_id)
            return (
                _thread_entity(thread, rollout_id=rollout_id)
                if isinstance(thread, Mapping)
                else _unknown_thread_entity(thread_id, rollout_id=rollout_id)
            )
    if anchor_type == "conversation_item":
        item_id = anchor.get("item_id")
        if isinstance(item_id, str):
            item = conversation_items.get(item_id)
            return _conversation_entity(
                item_id,
                item if isinstance(item, Mapping) else {},
                rollout_id=rollout_id,
            )
    if anchor_type == "tool_call":
        tool_call_id = anchor.get("tool_call_id")
        if isinstance(tool_call_id, str):
            call = tool_calls.get(tool_call_id)
            return _tool_call_entity(
                tool_call_id,
                call if isinstance(call, Mapping) else {},
                rollout_id=rollout_id,
            )
    return None


def _owner_agent_for_anchor(
    anchor: object,
    *,
    rollout_id: str,
    threads: Mapping[str, Mapping[str, Any]],
    conversation_items: Mapping[str, Mapping[str, Any]],
    tool_calls: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any] | None:
    if not isinstance(anchor, dict):
        return None
    anchor_type = anchor.get("type")
    thread_id: object = None
    if anchor_type == "thread":
        thread_id = anchor.get("thread_id")
    elif anchor_type == "conversation_item":
        item_id = anchor.get("item_id")
        item = conversation_items.get(str(item_id)) if item_id is not None else None
        if isinstance(item, Mapping):
            thread_id = item.get("thread_id")
    elif anchor_type == "tool_call":
        call_id = anchor.get("tool_call_id")
        call = tool_calls.get(str(call_id)) if call_id is not None else None
        if isinstance(call, Mapping):
            thread_id = call.get("thread_id")
    if not isinstance(thread_id, str) or not thread_id:
        return None
    thread = threads.get(thread_id)
    return (
        _thread_entity(thread, rollout_id=rollout_id)
        if isinstance(thread, Mapping)
        else _unknown_thread_entity(thread_id, rollout_id=rollout_id)
    )


def _direct_interaction_relation(kind: object) -> str:
    normalized = _tag_name(kind) or str(kind or "")
    mapping = {
        "spawn_agent": "SPAWNED_AGENT",
        "assign_agent_task": "ASSIGNED_AGENT_TASK",
        "send_message": "SENT_AGENT_MESSAGE",
        "agent_result": "RETURNED_AGENT_RESULT",
        "close_agent": "CLOSED_AGENT",
    }
    return mapping.get(normalized, f"CODEX_INTERACTION_{normalized.upper() or 'UNKNOWN'}")


def _state_events(
    state: Mapping[str, Any],
    *,
    bundle: Path,
    store: FullFidelityContentStore,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    rollout_id = str(state.get("rollout_id") or state.get("trace_id") or bundle.name)
    trace_id = str(state.get("trace_id") or bundle.name)
    started = _iso_from_unix_ms(state.get("started_at_unix_ms"))
    ended = _iso_from_unix_ms(state.get("ended_at_unix_ms"), fallback=started)

    threads_raw = state.get("threads")
    conversations_raw = state.get("conversation_items")
    tools_raw = state.get("tool_calls")
    inferences_raw = state.get("inference_calls")
    interactions_raw = state.get("interaction_edges")
    terminal_ops_raw = state.get("terminal_operations")
    code_cells_raw = state.get("code_cells")
    raw_payloads_raw = state.get("raw_payloads")

    threads = (
        {str(key): value for key, value in threads_raw.items() if isinstance(value, dict)}
        if isinstance(threads_raw, dict)
        else {}
    )
    conversation_items = (
        {str(key): value for key, value in conversations_raw.items() if isinstance(value, dict)}
        if isinstance(conversations_raw, dict)
        else {}
    )
    tool_calls = (
        {str(key): value for key, value in tools_raw.items() if isinstance(value, dict)}
        if isinstance(tools_raw, dict)
        else {}
    )
    inference_calls = (
        {str(key): value for key, value in inferences_raw.items() if isinstance(value, dict)}
        if isinstance(inferences_raw, dict)
        else {}
    )
    interaction_edges = (
        {str(key): value for key, value in interactions_raw.items() if isinstance(value, dict)}
        if isinstance(interactions_raw, dict)
        else {}
    )
    terminal_operations = (
        {str(key): value for key, value in terminal_ops_raw.items() if isinstance(value, dict)}
        if isinstance(terminal_ops_raw, dict)
        else {}
    )
    code_cells = (
        {str(key): value for key, value in code_cells_raw.items() if isinstance(value, dict)}
        if isinstance(code_cells_raw, dict)
        else {}
    )
    raw_payloads = (
        {str(key): value for key, value in raw_payloads_raw.items() if isinstance(value, dict)}
        if isinstance(raw_payloads_raw, dict)
        else {}
    )

    root_thread_id = str(state.get("root_thread_id") or "unknown")
    root_thread = threads.get(root_thread_id)
    root_agent = (
        _thread_entity(root_thread, rollout_id=rollout_id)
        if isinstance(root_thread, Mapping)
        else _unknown_thread_entity(root_thread_id, rollout_id=rollout_id)
    )

    events: list[dict[str, Any]] = []
    counts = {
        "raw_payload_count": 0,
        "conversation_item_count": len(conversation_items),
        "reasoning_text_count": 0,
        "reasoning_summary_count": 0,
        "encoded_reasoning_count": 0,
        "agent_message_count": 0,
        "interaction_edge_count": len(interaction_edges),
        "tool_call_count": len(tool_calls),
        "inference_call_count": len(inference_calls),
        "terminal_operation_count": len(terminal_operations),
        "code_cell_count": len(code_cells),
    }
    raw_cache: dict[str, ContentReference] = {}

    events.append(
        _content_event(
            store=store,
            value=state,
            content_kind="codex.rollout.reduced_state",
            timestamp=ended,
            source=root_agent,
            relation="HAS_REDUCED_ROLLOUT_STATE",
            observed_field="state.json",
            attributes={"trace_id": trace_id, "rollout_id": rollout_id},
        )
    )
    manifest_path = bundle / _MANIFEST_FILE
    if manifest_path.is_file():
        try:
            manifest_value: Any = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            manifest_value = manifest_path.read_bytes().decode("utf-8", errors="replace")
        events.append(
            _content_event(
                store=store,
                value=manifest_value,
                content_kind="codex.rollout.manifest",
                timestamp=started,
                source=root_agent,
                relation="HAS_ROLLOUT_MANIFEST",
                observed_field="manifest.json",
                attributes={"trace_id": trace_id, "rollout_id": rollout_id},
            )
        )
    trace_path = bundle / _RAW_TRACE_FILE
    if trace_path.is_file():
        trace_reference = store.put_bytes(
            trace_path.read_bytes(),
            content_kind="codex.rollout.raw_event_log",
            media_type="application/x-ndjson",
            representation="codex_rollout_trace_jsonl",
        )
        events.append(
            _raw_content_event(
                reference=trace_reference,
                timestamp=ended,
                source=root_agent,
                relation="HAS_RAW_ROLLOUT_EVENT_LOG",
                observed_field="trace.jsonl",
                attributes={"trace_id": trace_id, "rollout_id": rollout_id},
            )
        )

    for thread_id, thread in threads.items():
        agent = _thread_entity(thread, rollout_id=rollout_id)
        execution = thread.get("execution")
        thread_started = (
            execution.get("started_at_unix_ms")
            if isinstance(execution, dict)
            else state.get("started_at_unix_ms")
        )
        events.append(
            _event(
                timestamp=_iso_from_unix_ms(thread_started, fallback=started),
                event_type="semantic.codex.rollout.agent.observed",
                relation="HAS_AGENT_THREAD",
                source=root_agent,
                target=agent,
                attributes={
                    "trace_id": trace_id,
                    "rollout_id": rollout_id,
                    "thread_id": thread_id,
                    "agent_path": thread.get("agent_path"),
                    "origin": thread.get("origin"),
                    "execution": execution,
                },
            )
        )
        origin = thread.get("origin")
        if isinstance(origin, dict) and origin.get("type") == "spawned":
            parent_id = origin.get("parent_thread_id")
            if isinstance(parent_id, str):
                parent = threads.get(parent_id)
                parent_agent = (
                    _thread_entity(parent, rollout_id=rollout_id)
                    if isinstance(parent, Mapping)
                    else _unknown_thread_entity(parent_id, rollout_id=rollout_id)
                )
                events.append(
                    _event(
                        timestamp=_iso_from_unix_ms(thread_started, fallback=started),
                        event_type="semantic.codex.rollout.agent.spawned",
                        relation="SPAWNED_AGENT",
                        source=parent_agent,
                        target=agent,
                        attributes={
                            "trace_id": trace_id,
                            "rollout_id": rollout_id,
                            "spawn_edge_id": origin.get("spawn_edge_id"),
                            "task_name": origin.get("task_name"),
                            "agent_role": origin.get("agent_role"),
                            "source_semantics": "reduced_thread_origin",
                        },
                    )
                )

    for item_id, item in conversation_items.items():
        item_ts = _iso_from_unix_ms(item.get("first_seen_at_unix_ms"), fallback=started)
        item_entity = _conversation_entity(item_id, item, rollout_id=rollout_id)
        owner = _thread_for_item(item, threads=threads, rollout_id=rollout_id)
        relation = (
            "PRODUCED_CONVERSATION_ITEM"
            if item.get("role") in {"assistant", "tool"}
            else "RECEIVED_CONVERSATION_ITEM"
        )
        events.append(
            _event(
                timestamp=item_ts,
                event_type="semantic.codex.rollout.conversation.observed",
                relation=relation,
                source=owner,
                target=item_entity,
                attributes={
                    "trace_id": trace_id,
                    "rollout_id": rollout_id,
                    "role": item.get("role"),
                    "channel": item.get("channel"),
                    "kind": item.get("kind"),
                    "call_id": item.get("call_id"),
                    "model_visible": True,
                },
            )
        )
        events.append(
            _content_event(
                store=store,
                value=item,
                content_kind="codex.rollout.conversation_item",
                timestamp=item_ts,
                source=item_entity,
                relation="HAS_CONVERSATION_PAYLOAD",
                observed_field="conversation_item",
                attributes={
                    "trace_id": trace_id,
                    "rollout_id": rollout_id,
                    "role": item.get("role"),
                    "channel": item.get("channel"),
                    "kind": item.get("kind"),
                    "model_visible": True,
                },
            )
        )

        kind = item.get("kind")
        if kind == "reasoning":
            for index, part in enumerate(_body_parts(item)):
                part_type = part.get("type")
                common = {
                    "trace_id": trace_id,
                    "rollout_id": rollout_id,
                    "conversation_item_id": item_id,
                    "part_index": index,
                    "channel": item.get("channel"),
                    "model_visible": True,
                }
                if part_type == "text" and isinstance(part.get("text"), str):
                    counts["reasoning_text_count"] += 1
                    events.append(
                        _content_event(
                            store=store,
                            value=part["text"],
                            content_kind="codex.reasoning.text",
                            timestamp=item_ts,
                            source=owner,
                            relation="PRODUCED_REASONING_TEXT",
                            observed_field=f"body.parts[{index}].text",
                            attributes={**common, "reasoning_representation": "plaintext"},
                        )
                    )
                elif part_type == "summary" and isinstance(part.get("text"), str):
                    counts["reasoning_summary_count"] += 1
                    events.append(
                        _content_event(
                            store=store,
                            value=part["text"],
                            content_kind="codex.reasoning.summary",
                            timestamp=item_ts,
                            source=owner,
                            relation="PRODUCED_REASONING_SUMMARY",
                            observed_field=f"body.parts[{index}].text",
                            attributes={**common, "reasoning_representation": "summary"},
                        )
                    )
                elif part_type == "encoded" and isinstance(part.get("value"), str):
                    counts["encoded_reasoning_count"] += 1
                    events.append(
                        _content_event(
                            store=store,
                            value=part["value"],
                            content_kind="codex.reasoning.encoded",
                            timestamp=item_ts,
                            source=owner,
                            relation="PRODUCED_ENCODED_REASONING",
                            observed_field=f"body.parts[{index}].value",
                            attributes={
                                **common,
                                "reasoning_representation": "encoded",
                                "reasoning_readable": False,
                                "encoded_label": part.get("label"),
                            },
                        )
                    )

        routing = item.get("agent_message")
        if isinstance(routing, dict):
            author = _find_thread_by_path(
                routing.get("author"), threads=threads, rollout_id=rollout_id
            )
            recipient = _find_thread_by_path(
                routing.get("recipient"), threads=threads, rollout_id=rollout_id
            )
            if author is not None and recipient is not None:
                counts["agent_message_count"] += 1
                message = _message_entity(item_id, item, rollout_id=rollout_id)
                events.append(
                    _event(
                        timestamp=item_ts,
                        event_type="semantic.codex.rollout.agent_message.sent",
                        relation="SENT_AGENT_MESSAGE",
                        source=author,
                        target=message,
                        attributes={
                            "trace_id": trace_id,
                            "rollout_id": rollout_id,
                            "conversation_item_id": item_id,
                            "author": routing.get("author"),
                            "recipient": routing.get("recipient"),
                            "model_visible": True,
                        },
                    )
                )
                events.append(
                    _event(
                        timestamp=item_ts,
                        event_type="semantic.codex.rollout.agent_message.delivered",
                        relation="DELIVERED_AGENT_MESSAGE",
                        source=message,
                        target=recipient,
                        attributes={
                            "trace_id": trace_id,
                            "rollout_id": rollout_id,
                            "conversation_item_id": item_id,
                            "author": routing.get("author"),
                            "recipient": routing.get("recipient"),
                            "model_visible": True,
                        },
                    )
                )
                events.append(
                    _content_event(
                        store=store,
                        value=item.get("body") or {},
                        content_kind="codex.agent_message.payload",
                        timestamp=item_ts,
                        source=message,
                        relation="HAS_AGENT_MESSAGE_PAYLOAD",
                        observed_field="body",
                        attributes={
                            "trace_id": trace_id,
                            "rollout_id": rollout_id,
                            "conversation_item_id": item_id,
                            "author": routing.get("author"),
                            "recipient": routing.get("recipient"),
                            "model_visible": True,
                        },
                    )
                )

    for call_id, call in inference_calls.items():
        execution = call.get("execution")
        call_ts = _iso_from_unix_ms(
            execution.get("started_at_unix_ms") if isinstance(execution, dict) else None,
            fallback=started,
        )
        inference = _inference_entity(call_id, call, rollout_id=rollout_id)
        thread_id = call.get("thread_id")
        thread = threads.get(str(thread_id)) if thread_id is not None else None
        owner = (
            _thread_entity(thread, rollout_id=rollout_id)
            if isinstance(thread, Mapping)
            else _unknown_thread_entity(str(thread_id or "unknown"), rollout_id=rollout_id)
        )
        events.append(
            _event(
                timestamp=call_ts,
                event_type="semantic.codex.rollout.inference.started",
                relation="MADE_INFERENCE_CALL",
                source=owner,
                target=inference,
                attributes={
                    "trace_id": trace_id,
                    "rollout_id": rollout_id,
                    "execution": execution,
                    "usage": call.get("usage"),
                },
            )
        )
        model = call.get("model")
        if isinstance(model, str) and model:
            events.append(
                _event(
                    timestamp=call_ts,
                    event_type="semantic.codex.rollout.inference.model",
                    relation="USED_MODEL",
                    source=inference,
                    target=_entity(
                        "model",
                        f"model:codex:{model}",
                        name=model,
                        attributes={
                            "provider": "codex",
                            "provider_name": call.get("provider_name"),
                        },
                    ),
                    attributes={"trace_id": trace_id, "rollout_id": rollout_id},
                )
            )
        for field, relation in (
            ("raw_request_payload_id", "HAS_INFERENCE_REQUEST_PAYLOAD"),
            ("raw_response_payload_id", "HAS_INFERENCE_RESPONSE_PAYLOAD"),
        ):
            raw_id = call.get(field)
            raw_ref = raw_payloads.get(str(raw_id)) if raw_id is not None else None
            if isinstance(raw_id, str) and isinstance(raw_ref, Mapping):
                reference = _raw_payload_reference(
                    bundle=bundle,
                    raw_payload_id=raw_id,
                    raw_ref=raw_ref,
                    store=store,
                    cache=raw_cache,
                )
                if reference is not None:
                    events.append(
                        _raw_content_event(
                            reference=reference,
                            timestamp=call_ts,
                            source=inference,
                            relation=relation,
                            observed_field=field,
                            attributes={
                                "trace_id": trace_id,
                                "rollout_id": rollout_id,
                                "raw_payload_id": raw_id,
                                "model_visible_boundary": True,
                            },
                        )
                    )

    for call_id, call in tool_calls.items():
        execution = call.get("execution")
        call_ts = _iso_from_unix_ms(
            execution.get("started_at_unix_ms") if isinstance(execution, dict) else None,
            fallback=started,
        )
        tool_call = _tool_call_entity(call_id, call, rollout_id=rollout_id)
        thread_id = call.get("thread_id")
        thread = threads.get(str(thread_id)) if thread_id is not None else None
        owner = (
            _thread_entity(thread, rollout_id=rollout_id)
            if isinstance(thread, Mapping)
            else _unknown_thread_entity(str(thread_id or "unknown"), rollout_id=rollout_id)
        )
        events.append(
            _event(
                timestamp=call_ts,
                event_type="semantic.codex.rollout.tool.started",
                relation="EXECUTED_TOOL_CALL",
                source=owner,
                target=tool_call,
                attributes={
                    "trace_id": trace_id,
                    "rollout_id": rollout_id,
                    "tool_kind": call.get("kind"),
                    "requester": call.get("requester"),
                    "execution": execution,
                },
            )
        )
        kind_name = _tag_name(call.get("kind")) or "unknown"
        events.append(
            _event(
                timestamp=call_ts,
                event_type="semantic.codex.rollout.tool.kind",
                relation="USES_TOOL",
                source=tool_call,
                target=_entity(
                    "tool",
                    f"tool:codex:{kind_name}",
                    name=kind_name,
                    attributes={"provider": "codex", "native_kind": call.get("kind")},
                ),
                attributes={"trace_id": trace_id, "rollout_id": rollout_id},
            )
        )
        for field, relation in (
            ("raw_invocation_payload_id", "HAS_TOOL_INPUT"),
            ("raw_result_payload_id", "HAS_TOOL_OUTPUT"),
        ):
            raw_id = call.get(field)
            raw_ref = raw_payloads.get(str(raw_id)) if raw_id is not None else None
            if isinstance(raw_id, str) and isinstance(raw_ref, Mapping):
                reference = _raw_payload_reference(
                    bundle=bundle,
                    raw_payload_id=raw_id,
                    raw_ref=raw_ref,
                    store=store,
                    cache=raw_cache,
                )
                if reference is not None:
                    events.append(
                        _raw_content_event(
                            reference=reference,
                            timestamp=call_ts,
                            source=tool_call,
                            relation=relation,
                            observed_field=field,
                            attributes={
                                "trace_id": trace_id,
                                "rollout_id": rollout_id,
                                "raw_payload_id": raw_id,
                                "requester": call.get("requester"),
                                "tool_kind": call.get("kind"),
                            },
                        )
                    )
        runtime_ids = call.get("raw_runtime_payload_ids")
        if isinstance(runtime_ids, list):
            for index, raw_id in enumerate(runtime_ids):
                raw_ref = raw_payloads.get(str(raw_id)) if raw_id is not None else None
                if isinstance(raw_id, str) and isinstance(raw_ref, Mapping):
                    reference = _raw_payload_reference(
                        bundle=bundle,
                        raw_payload_id=raw_id,
                        raw_ref=raw_ref,
                        store=store,
                        cache=raw_cache,
                    )
                    if reference is not None:
                        events.append(
                            _raw_content_event(
                                reference=reference,
                                timestamp=call_ts,
                                source=tool_call,
                                relation="HAS_TOOL_RUNTIME_PAYLOAD",
                                observed_field=f"raw_runtime_payload_ids[{index}]",
                                attributes={
                                    "trace_id": trace_id,
                                    "rollout_id": rollout_id,
                                    "raw_payload_id": raw_id,
                                },
                            )
                        )

    for operation_id, operation in terminal_operations.items():
        execution = operation.get("execution")
        op_ts = _iso_from_unix_ms(
            execution.get("started_at_unix_ms") if isinstance(execution, dict) else None,
            fallback=started,
        )
        terminal = _terminal_entity(operation_id, operation, rollout_id=rollout_id)
        tool_call_id = operation.get("tool_call_id")
        call = tool_calls.get(str(tool_call_id)) if tool_call_id is not None else None
        source = (
            _tool_call_entity(str(tool_call_id), call, rollout_id=rollout_id)
            if tool_call_id is not None and isinstance(call, Mapping)
            else root_agent
        )
        events.append(
            _event(
                timestamp=op_ts,
                event_type="semantic.codex.rollout.terminal.operation",
                relation="STARTED_TERMINAL_OPERATION",
                source=source,
                target=terminal,
                attributes={
                    "trace_id": trace_id,
                    "rollout_id": rollout_id,
                    "terminal_id": operation.get("terminal_id"),
                    "operation_kind": operation.get("kind"),
                    "execution": execution,
                },
            )
        )
        if "request" in operation:
            events.append(
                _content_event(
                    store=store,
                    value=operation["request"],
                    content_kind="codex.terminal.request",
                    timestamp=op_ts,
                    source=terminal,
                    relation="HAS_TERMINAL_REQUEST",
                    observed_field="request",
                    attributes={"trace_id": trace_id, "rollout_id": rollout_id},
                )
            )
        if operation.get("result") is not None:
            events.append(
                _content_event(
                    store=store,
                    value=operation["result"],
                    content_kind="codex.terminal.result",
                    timestamp=_iso_from_unix_ms(
                        execution.get("ended_at_unix_ms") if isinstance(execution, dict) else None,
                        fallback=op_ts,
                    ),
                    source=terminal,
                    relation="HAS_TERMINAL_RESULT",
                    observed_field="result",
                    attributes={"trace_id": trace_id, "rollout_id": rollout_id},
                )
            )

    for cell_id, cell in code_cells.items():
        execution = cell.get("execution")
        cell_ts = _iso_from_unix_ms(
            execution.get("started_at_unix_ms") if isinstance(execution, dict) else None,
            fallback=started,
        )
        cell_entity = _code_cell_entity(cell_id, cell, rollout_id=rollout_id)
        thread_id = cell.get("thread_id")
        thread = threads.get(str(thread_id)) if thread_id is not None else None
        owner = (
            _thread_entity(thread, rollout_id=rollout_id)
            if isinstance(thread, Mapping)
            else _unknown_thread_entity(str(thread_id or "unknown"), rollout_id=rollout_id)
        )
        events.append(
            _event(
                timestamp=cell_ts,
                event_type="semantic.codex.rollout.code_cell.started",
                relation="EXECUTED_CODE_CELL",
                source=owner,
                target=cell_entity,
                attributes={
                    "trace_id": trace_id,
                    "rollout_id": rollout_id,
                    "runtime_status": cell.get("runtime_status"),
                    "execution": execution,
                },
            )
        )
        source_js = cell.get("source_js")
        if isinstance(source_js, str):
            events.append(
                _content_event(
                    store=store,
                    value=source_js,
                    content_kind="codex.code_cell.source_js",
                    timestamp=cell_ts,
                    source=cell_entity,
                    relation="HAS_CODE_CELL_SOURCE",
                    observed_field="source_js",
                    attributes={"trace_id": trace_id, "rollout_id": rollout_id},
                )
            )
        for nested in cell.get("nested_tool_call_ids") or []:
            nested_call = tool_calls.get(str(nested))
            if isinstance(nested, str) and isinstance(nested_call, Mapping):
                events.append(
                    _event(
                        timestamp=cell_ts,
                        event_type="semantic.codex.rollout.code_cell.tool",
                        relation="ISSUED_NESTED_TOOL_CALL",
                        source=cell_entity,
                        target=_tool_call_entity(nested, nested_call, rollout_id=rollout_id),
                        attributes={"trace_id": trace_id, "rollout_id": rollout_id},
                    )
                )

    for edge_id, edge in interaction_edges.items():
        edge_ts = _iso_from_unix_ms(edge.get("started_at_unix_ms"), fallback=started)
        interaction = _interaction_entity(edge_id, edge, rollout_id=rollout_id)
        source = _anchor_entity(
            edge.get("source"),
            rollout_id=rollout_id,
            threads=threads,
            conversation_items=conversation_items,
            tool_calls=tool_calls,
        )
        target = _anchor_entity(
            edge.get("target"),
            rollout_id=rollout_id,
            threads=threads,
            conversation_items=conversation_items,
            tool_calls=tool_calls,
        )
        relation = _direct_interaction_relation(edge.get("kind"))
        common = {
            "trace_id": trace_id,
            "rollout_id": rollout_id,
            "interaction_edge_id": edge_id,
            "interaction_kind": edge.get("kind"),
            "started_at_unix_ms": edge.get("started_at_unix_ms"),
            "ended_at_unix_ms": edge.get("ended_at_unix_ms"),
            "carried_item_ids": edge.get("carried_item_ids") or [],
            "carried_raw_payload_ids": edge.get("carried_raw_payload_ids") or [],
            "direct_information_flow": True,
            "source_semantics": "codex_reduced_interaction_edge",
        }
        if source is not None:
            events.append(
                _event(
                    timestamp=edge_ts,
                    event_type="semantic.codex.rollout.interaction.started",
                    relation="STARTED_AGENT_INTERACTION",
                    source=source,
                    target=interaction,
                    attributes=common,
                )
            )
        if target is not None:
            events.append(
                _event(
                    timestamp=edge_ts,
                    event_type="semantic.codex.rollout.interaction.targeted",
                    relation="TARGETED_BY_AGENT_INTERACTION",
                    source=interaction,
                    target=target,
                    attributes=common,
                )
            )
        if source is not None and target is not None:
            events.append(
                _event(
                    timestamp=edge_ts,
                    event_type="semantic.codex.rollout.interaction.flow",
                    relation=relation,
                    source=source,
                    target=target,
                    attributes=common,
                )
            )
        source_agent = _owner_agent_for_anchor(
            edge.get("source"),
            rollout_id=rollout_id,
            threads=threads,
            conversation_items=conversation_items,
            tool_calls=tool_calls,
        )
        target_agent = _owner_agent_for_anchor(
            edge.get("target"),
            rollout_id=rollout_id,
            threads=threads,
            conversation_items=conversation_items,
            tool_calls=tool_calls,
        )
        if (
            source_agent is not None
            and target_agent is not None
            and source_agent["id"] != target_agent["id"]
        ):
            events.append(
                _event(
                    timestamp=edge_ts,
                    event_type="semantic.codex.rollout.agent_to_agent.flow",
                    relation=relation,
                    source=source_agent,
                    target=target_agent,
                    attributes={
                        **common,
                        "normalized_agent_to_agent": True,
                        "source_anchor": edge.get("source"),
                        "target_anchor": edge.get("target"),
                    },
                )
            )
        for index, raw_id in enumerate(edge.get("carried_raw_payload_ids") or []):
            raw_ref = raw_payloads.get(str(raw_id)) if raw_id is not None else None
            if isinstance(raw_id, str) and isinstance(raw_ref, Mapping):
                reference = _raw_payload_reference(
                    bundle=bundle,
                    raw_payload_id=raw_id,
                    raw_ref=raw_ref,
                    store=store,
                    cache=raw_cache,
                )
                if reference is not None:
                    events.append(
                        _raw_content_event(
                            reference=reference,
                            timestamp=edge_ts,
                            source=interaction,
                            relation="CARRIED_RAW_PAYLOAD",
                            observed_field=f"carried_raw_payload_ids[{index}]",
                            attributes={**common, "raw_payload_id": raw_id},
                        )
                    )

    for raw_id, raw_ref in raw_payloads.items():
        reference = _raw_payload_reference(
            bundle=bundle,
            raw_payload_id=raw_id,
            raw_ref=raw_ref,
            store=store,
            cache=raw_cache,
        )
        if reference is not None:
            events.append(
                _raw_content_event(
                    reference=reference,
                    timestamp=ended,
                    source=root_agent,
                    relation="HAS_RAW_CODEX_PAYLOAD",
                    observed_field=f"raw_payloads.{raw_id}",
                    attributes={
                        "trace_id": trace_id,
                        "rollout_id": rollout_id,
                        "raw_payload_id": raw_id,
                        "raw_payload_kind": raw_ref.get("kind"),
                    },
                )
            )
    counts["raw_payload_count"] = len(raw_cache)
    return events, counts


def _load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _reduce_bundle(codex_executable: str, bundle: Path, state_path: Path) -> str | None:
    try:
        completed = subprocess.run(
            [
                codex_executable,
                "debug",
                "trace-reduce",
                str(bundle),
                "--output",
                str(state_path),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return str(exc)
    if completed.returncode == 0 and state_path.is_file():
        return None
    detail = (completed.stderr or completed.stdout or "").strip()
    if len(detail) > 500:
        detail = detail[:497] + "..."
    return detail or f"trace-reduce exited {completed.returncode}"


def _bundle_dirs(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    bundles: list[Path] = []
    for candidate in root.iterdir():
        if (
            candidate.is_dir()
            and candidate.name.startswith(_BUNDLE_PREFIX)
            and (candidate / _MANIFEST_FILE).is_file()
            and (candidate / _RAW_TRACE_FILE).is_file()
        ):
            bundles.append(candidate)
    return sorted(bundles)


def import_codex_rollout_traces(
    *,
    trace_root: str | Path,
    semantic_sidecar: str | Path,
    codex_executable: str = "codex",
) -> CodexRolloutImportResult:
    """Import Codex's local rollout trace as full-fidelity ExecWeave semantics.

    Newer Codex builds can record a first-party raw rollout bundle when
    ``CODEX_ROLLOUT_TRACE_ROOT`` is set. ExecWeave enables that bundle for the
    child Codex process, invokes Codex's own offline reducer after the run, then
    imports both the reduced semantic objects and the raw payload evidence.

    Plaintext or summarized reasoning is preserved when Codex actually exposes
    it in the reduced conversation. Encoded/encrypted reasoning is kept as opaque
    evidence and is never mislabeled as readable chain-of-thought.
    """

    root = Path(trace_root).expanduser().resolve()
    sidecar = Path(semantic_sidecar).expanduser().resolve()
    bundles = _bundle_dirs(root)
    if not bundles:
        return CodexRolloutImportResult(
            status="no_trace_bundles",
            trace_root=str(root),
        )

    store = FullFidelityContentStore(sidecar.parent)
    all_events: list[dict[str, Any]] = []
    errors: list[str] = []
    totals = {
        "raw_payload_count": 0,
        "conversation_item_count": 0,
        "reasoning_text_count": 0,
        "reasoning_summary_count": 0,
        "encoded_reasoning_count": 0,
        "agent_message_count": 0,
        "interaction_edge_count": 0,
        "tool_call_count": 0,
        "inference_call_count": 0,
        "terminal_operation_count": 0,
        "code_cell_count": 0,
    }
    reduced_bundle_count = 0

    for bundle in bundles:
        state_path = bundle / _STATE_FILE
        if not state_path.is_file():
            error = _reduce_bundle(codex_executable, bundle, state_path)
            if error is not None:
                errors.append(f"{bundle.name}: {error}")
                continue
        try:
            state = _load_json_object(state_path)
            events, counts = _state_events(state, bundle=bundle, store=store)
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"{bundle.name}: {exc}")
            continue
        reduced_bundle_count += 1
        all_events.extend(events)
        for key in totals:
            totals[key] += counts[key]

    if all_events:
        append_semantic_records(sidecar, all_events)

    if reduced_bundle_count == len(bundles):
        status = "imported"
    elif reduced_bundle_count:
        status = "partial"
    else:
        status = "reduction_failed"

    return CodexRolloutImportResult(
        status=status,
        trace_root=str(root),
        bundle_count=len(bundles),
        reduced_bundle_count=reduced_bundle_count,
        semantic_event_count=len(all_events),
        errors=tuple(errors),
        **totals,
    )
