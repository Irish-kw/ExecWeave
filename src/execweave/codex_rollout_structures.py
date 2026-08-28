from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .codex_adapter import append_semantic_records
from .content_evidence import content_observation_event
from .content_store import ContentReference, FullFidelityContentStore


@dataclass(frozen=True)
class CodexStructureImportResult:
    status: str
    trace_root: str
    bundle_count: int = 0
    turn_count: int = 0
    terminal_session_count: int = 0
    compaction_count: int = 0
    compaction_request_count: int = 0
    semantic_event_count: int = 0
    errors: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _iso(value: object, fallback: str | None = None) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return datetime.fromtimestamp(float(value) / 1000.0, timezone.utc).isoformat().replace(
            "+00:00", "Z"
        )
    return fallback or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _maps(state: Mapping[str, Any], key: str) -> dict[str, dict[str, Any]]:
    value = state.get(key)
    if not isinstance(value, dict):
        return {}
    return {str(k): v for k, v in value.items() if isinstance(v, dict)}


def _node(kind: str, ident: str, name: str, **attrs: Any) -> dict[str, Any]:
    return {"type": kind, "id": ident, "name": name, "attributes": attrs}


def _agent(thread_id: str, threads: Mapping[str, Mapping[str, Any]], rollout: str) -> dict[str, Any]:
    thread = threads.get(thread_id, {})
    path = thread.get("agent_path")
    nickname = thread.get("nickname")
    name = path if isinstance(path, str) and path else nickname if isinstance(nickname, str) and nickname else f"Codex agent {thread_id}"
    return _node(
        "agent",
        f"agent:codex:rollout:{rollout}:thread:{thread_id}",
        name,
        provider="codex",
        rollout_id=rollout,
        thread_id=thread_id,
        agent_path=path,
        nickname=nickname,
        unresolved_thread_metadata=not bool(thread),
    )


def _turn(turn_id: str, value: Mapping[str, Any], rollout: str) -> dict[str, Any]:
    return _node(
        "agent_turn",
        f"agent-turn:codex:{rollout}:{turn_id}",
        f"Codex turn {turn_id}",
        provider="codex",
        rollout_id=rollout,
        codex_turn_id=turn_id,
        thread_id=value.get("thread_id"),
        execution=value.get("execution"),
        identity_semantics="provider_codex_turn_id",
    )


def _conversation(item_id: str, value: Mapping[str, Any], rollout: str) -> dict[str, Any]:
    return _node(
        "conversation_item",
        f"conversation-item:codex:{rollout}:{item_id}",
        f"{value.get('role', 'conversation')}:{value.get('kind', 'item')}",
        provider="codex",
        rollout_id=rollout,
        item_id=item_id,
        thread_id=value.get("thread_id"),
        codex_turn_id=value.get("codex_turn_id"),
        role=value.get("role"),
        channel=value.get("channel"),
        kind=value.get("kind"),
    )


def _existing(kind: str, ident: str, value: Mapping[str, Any], rollout: str) -> dict[str, Any]:
    if kind == "inference_call":
        return _node(
            kind,
            f"inference-call:codex:{rollout}:{ident}",
            str(value.get("model") or "Codex inference"),
            provider="codex",
            rollout_id=rollout,
            inference_call_id=ident,
        )
    if kind == "tool_call":
        native = value.get("kind")
        label = native.get("type") if isinstance(native, dict) else native
        return _node(
            kind,
            f"tool-call:codex:rollout:{rollout}:{ident}",
            str(label or "tool"),
            provider="codex",
            rollout_id=rollout,
            tool_call_id=ident,
        )
    if kind == "code_cell":
        return _node(
            kind,
            f"code-cell:codex:{rollout}:{ident}",
            "Codex code-mode cell",
            provider="codex",
            rollout_id=rollout,
            code_cell_id=ident,
        )
    return _node(
        "terminal_operation",
        f"terminal-operation:codex:{rollout}:{ident}",
        str(value.get("kind") or "terminal operation"),
        provider="codex",
        rollout_id=rollout,
        operation_id=ident,
        terminal_id=value.get("terminal_id"),
        tool_call_id=value.get("tool_call_id"),
    )


def _terminal(terminal_id: str, value: Mapping[str, Any], rollout: str) -> dict[str, Any]:
    return _node(
        "terminal_session",
        f"terminal-session:codex:{rollout}:{terminal_id}",
        f"Terminal {terminal_id}",
        provider="codex",
        rollout_id=rollout,
        terminal_id=terminal_id,
        thread_id=value.get("thread_id"),
        created_by_operation_id=value.get("created_by_operation_id"),
        execution=value.get("execution"),
        identity_semantics="provider_terminal_id",
    )


def _compaction(compaction_id: str, value: Mapping[str, Any], rollout: str) -> dict[str, Any]:
    return _node(
        "compaction",
        f"compaction:codex:{rollout}:{compaction_id}",
        f"Compaction {compaction_id}",
        provider="codex",
        rollout_id=rollout,
        compaction_id=compaction_id,
        thread_id=value.get("thread_id"),
        codex_turn_id=value.get("codex_turn_id"),
        installed_at_unix_ms=value.get("installed_at_unix_ms"),
        marker_item_id=value.get("marker_item_id"),
    )


def _request(request_id: str, value: Mapping[str, Any], rollout: str) -> dict[str, Any]:
    return _node(
        "compaction_request",
        f"compaction-request:codex:{rollout}:{request_id}",
        str(value.get("model") or "Codex compaction request"),
        provider="codex",
        rollout_id=rollout,
        compaction_request_id=request_id,
        compaction_id=value.get("compaction_id"),
        thread_id=value.get("thread_id"),
        codex_turn_id=value.get("codex_turn_id"),
        execution=value.get("execution"),
        provider_name=value.get("provider_name"),
    )


def _event(ts: str, relation: str, source: dict[str, Any], target: dict[str, Any], **attrs: Any) -> dict[str, Any]:
    return {
        "timestamp": ts,
        "event_type": f"semantic.codex.rollout.structure.{relation.lower()}",
        "relation": relation,
        "source": source,
        "target": target,
        "attributes": {
            "backend": "semantic",
            "provider": "codex",
            "evidence_source": "codex_rollout_trace",
            "attribution": "codex_rollout_structure",
            "causal": False,
            "inferred": False,
            **attrs,
        },
    }


def _start(value: Mapping[str, Any], fallback: str) -> str:
    execution = value.get("execution")
    return _iso(execution.get("started_at_unix_ms"), fallback) if isinstance(execution, dict) else fallback


def _raw_reference(
    bundle: Path,
    raw_id: str,
    raw_ref: Mapping[str, Any],
    store: FullFidelityContentStore,
    cache: dict[str, ContentReference],
) -> ContentReference | None:
    if raw_id in cache:
        return cache[raw_id]
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
    raw = path.read_bytes()
    media = "application/octet-stream"
    try:
        json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        pass
    else:
        media = "application/json"
    ref = store.put_bytes(
        raw,
        content_kind="codex.compaction.raw_payload",
        media_type=media,
        representation="codex_rollout_raw_payload",
    )
    cache[raw_id] = ref
    return ref


def _state_events(
    state: Mapping[str, Any], bundle: Path, store: FullFidelityContentStore
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    rollout = str(state.get("rollout_id") or state.get("trace_id") or bundle.name)
    trace = str(state.get("trace_id") or bundle.name)
    started = _iso(state.get("started_at_unix_ms"))
    threads = _maps(state, "threads")
    turns = _maps(state, "codex_turns")
    items = _maps(state, "conversation_items")
    inferences = _maps(state, "inference_calls")
    tools = _maps(state, "tool_calls")
    cells = _maps(state, "code_cells")
    terminals = _maps(state, "terminal_sessions")
    operations = _maps(state, "terminal_operations")
    compactions = _maps(state, "compactions")
    requests = _maps(state, "compaction_requests")
    raw_payloads = _maps(state, "raw_payloads")
    common = {"trace_id": trace, "rollout_id": rollout}
    events: list[dict[str, Any]] = []

    for turn_id, value in turns.items():
        turn = _turn(turn_id, value, rollout)
        ts = _start(value, started)
        owner = _agent(str(value.get("thread_id") or "unknown"), threads, rollout)
        events.append(_event(ts, "STARTED_AGENT_TURN", owner, turn, execution=value.get("execution"), **common))
        for item_id in value.get("input_item_ids") or []:
            item = items.get(str(item_id))
            if isinstance(item_id, str) and item:
                events.append(_event(ts, "TRIGGERED_AGENT_TURN", _conversation(item_id, item, rollout), turn, provider_turn_input_exact=True, **common))

    for item_id, value in items.items():
        turn_id = value.get("codex_turn_id")
        turn_value = turns.get(str(turn_id)) if turn_id is not None else None
        if isinstance(turn_id, str) and turn_value:
            events.append(_event(_iso(value.get("first_seen_at_unix_ms"), started), "OBSERVED_IN_AGENT_TURN", _turn(turn_id, turn_value, rollout), _conversation(item_id, value, rollout), provider_codex_turn_id_exact=True, **common))

    for collection, kind, turn_field, relation in (
        (inferences, "inference_call", "codex_turn_id", "ISSUED_INFERENCE_IN_TURN"),
        (tools, "tool_call", "started_by_codex_turn_id", "STARTED_TOOL_CALL_IN_TURN"),
        (cells, "code_cell", "codex_turn_id", "EXECUTED_CODE_CELL_IN_TURN"),
    ):
        for ident, value in collection.items():
            turn_id = value.get(turn_field)
            turn_value = turns.get(str(turn_id)) if turn_id is not None else None
            if isinstance(turn_id, str) and turn_value:
                events.append(_event(_start(value, started), relation, _turn(turn_id, turn_value, rollout), _existing(kind, ident, value, rollout), provider_codex_turn_id_exact=True, **common))

    for terminal_id, value in terminals.items():
        ts = _start(value, started)
        terminal = _terminal(terminal_id, value, rollout)
        owner = _agent(str(value.get("thread_id") or "unknown"), threads, rollout)
        events.append(_event(ts, "OWNED_TERMINAL_SESSION", owner, terminal, terminal_lifetime_distinct_from_operation=True, **common))
        creator_id = value.get("created_by_operation_id")
        creator = operations.get(str(creator_id)) if creator_id is not None else None
        if isinstance(creator_id, str) and creator:
            events.append(_event(ts, "CREATED_TERMINAL_SESSION", _existing("terminal_operation", creator_id, creator, rollout), terminal, provider_created_by_operation_id_exact=True, **common))
        for operation_id in value.get("operation_ids") or []:
            operation = operations.get(str(operation_id))
            if isinstance(operation_id, str) and operation:
                events.append(_event(ts, "HAS_TERMINAL_OPERATION", terminal, _existing("terminal_operation", operation_id, operation, rollout), provider_operation_membership_exact=True, **common))

    for compaction_id, value in compactions.items():
        ts = _iso(value.get("installed_at_unix_ms"), started)
        compact = _compaction(compaction_id, value, rollout)
        owner = _agent(str(value.get("thread_id") or "unknown"), threads, rollout)
        events.append(_event(ts, "INSTALLED_COMPACTION", owner, compact, history_replacement_checkpoint=True, **common))
        turn_id = value.get("codex_turn_id")
        turn_value = turns.get(str(turn_id)) if turn_id is not None else None
        if isinstance(turn_id, str) and turn_value:
            events.append(_event(ts, "INSTALLED_COMPACTION_IN_TURN", _turn(turn_id, turn_value, rollout), compact, provider_codex_turn_id_exact=True, **common))
        marker_id = value.get("marker_item_id")
        marker = items.get(str(marker_id)) if marker_id is not None else None
        if isinstance(marker_id, str) and marker:
            events.append(_event(ts, "MARKED_BY_CONVERSATION_ITEM", compact, _conversation(marker_id, marker, rollout), **common))
        for item_id in value.get("input_item_ids") or []:
            item = items.get(str(item_id))
            if isinstance(item_id, str) and item:
                events.append(_event(ts, "INPUT_TO_COMPACTION", _conversation(item_id, item, rollout), compact, **common))
        for item_id in value.get("replacement_item_ids") or []:
            item = items.get(str(item_id))
            if isinstance(item_id, str) and item:
                events.append(_event(ts, "INSTALLED_REPLACEMENT_ITEM", compact, _conversation(item_id, item, rollout), **common))
        for request_id in value.get("request_ids") or []:
            request_value = requests.get(str(request_id))
            if isinstance(request_id, str) and request_value:
                events.append(_event(ts, "COMPUTED_BY_COMPACTION_REQUEST", compact, _request(request_id, request_value, rollout), **common))

    cache: dict[str, ContentReference] = {}
    for request_id, value in requests.items():
        ts = _start(value, started)
        request = _request(request_id, value, rollout)
        owner = _agent(str(value.get("thread_id") or "unknown"), threads, rollout)
        events.append(_event(ts, "MADE_COMPACTION_REQUEST", owner, request, execution=value.get("execution"), **common))
        turn_id = value.get("codex_turn_id")
        turn_value = turns.get(str(turn_id)) if turn_id is not None else None
        if isinstance(turn_id, str) and turn_value:
            events.append(_event(ts, "REQUESTED_COMPACTION_IN_TURN", _turn(turn_id, turn_value, rollout), request, provider_codex_turn_id_exact=True, **common))
        model = value.get("model")
        if isinstance(model, str) and model:
            events.append(_event(ts, "USED_MODEL", request, _node("model", f"model:codex:{model}", model, provider="codex", provider_name=value.get("provider_name")), **common))
        for field, relation in (("raw_request_payload_id", "HAS_COMPACTION_REQUEST_PAYLOAD"), ("raw_response_payload_id", "HAS_COMPACTION_RESPONSE_PAYLOAD")):
            raw_id = value.get(field)
            raw_ref = raw_payloads.get(str(raw_id)) if raw_id is not None else None
            if isinstance(raw_id, str) and raw_ref:
                reference = _raw_reference(bundle, raw_id, raw_ref, store, cache)
                if reference is not None:
                    events.append(content_observation_event(timestamp=ts, provider="codex", source=request, reference=reference, relation=relation, observed_field=field, evidence_source="codex_rollout_trace", attribution="codex_rollout_structure", event_type="semantic.codex.rollout.compaction.payload", attributes={"structural_linkage": True, "trace_id": trace, "rollout_id": rollout, "raw_payload_id": raw_id}))

    return events, {
        "turn_count": len(turns),
        "terminal_session_count": len(terminals),
        "compaction_count": len(compactions),
        "compaction_request_count": len(requests),
    }


def enrich_codex_rollout_structures(
    *, trace_root: str | Path, semantic_sidecar: str | Path
) -> CodexStructureImportResult:
    """Materialize stable Codex turn, terminal-session, and compaction structure."""
    root = Path(trace_root).expanduser().resolve()
    sidecar = Path(semantic_sidecar).expanduser().resolve()
    bundles = [] if not root.is_dir() else sorted(
        candidate
        for candidate in root.iterdir()
        if candidate.is_dir() and candidate.name.startswith("trace-") and (candidate / "state.json").is_file()
    )
    if not bundles:
        return CodexStructureImportResult(status="no_reduced_state", trace_root=str(root))

    store = FullFidelityContentStore(sidecar.parent)
    events: list[dict[str, Any]] = []
    errors: list[str] = []
    totals = {"turn_count": 0, "terminal_session_count": 0, "compaction_count": 0, "compaction_request_count": 0}
    imported = 0
    for bundle in bundles:
        try:
            state = json.loads((bundle / "state.json").read_text(encoding="utf-8"))
            if not isinstance(state, dict):
                raise ValueError("state.json must contain a JSON object")
            current, counts = _state_events(state, bundle, store)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            errors.append(f"{bundle.name}: {exc}")
            continue
        imported += 1
        events.extend(current)
        for key in totals:
            totals[key] += counts[key]

    if events:
        append_semantic_records(sidecar, events)
    status = "imported" if imported == len(bundles) else "partial" if imported else "failed"
    return CodexStructureImportResult(status=status, trace_root=str(root), bundle_count=len(bundles), semantic_event_count=len(events), errors=tuple(errors), **totals)
