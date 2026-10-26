from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .codex_adapter import append_semantic_records

_CONSUMPTION_SEMANTICS = (
    "included_in_provider_recorded_inference_request_context_not_proof_of_model_attention"
)


@dataclass(frozen=True)
class CodexMessageDiagnosticResult:
    status: str
    trace_root: str
    bundle_count: int = 0
    message_count: int = 0
    consumed_message_count: int = 0
    inference_membership_count: int = 0
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


def _node(entity_type: str, ident: str, name: str, **attrs: Any) -> dict[str, Any]:
    return {"type": entity_type, "id": ident, "name": name, "attributes": attrs}


def _agent(
    thread_id: str,
    threads: Mapping[str, Mapping[str, Any]],
    rollout: str,
) -> dict[str, Any]:
    thread = threads.get(thread_id, {})
    path = thread.get("agent_path")
    nickname = thread.get("nickname")
    name = (
        path
        if isinstance(path, str) and path
        else nickname
        if isinstance(nickname, str) and nickname
        else f"Codex agent {thread_id}"
    )
    attrs: dict[str, Any] = {
        "provider": "codex",
        "rollout_id": rollout,
        "thread_id": thread_id,
    }
    if isinstance(path, str) and path:
        attrs["agent_path"] = path
    if isinstance(nickname, str) and nickname:
        attrs["nickname"] = nickname
    if not thread:
        attrs["unresolved_thread_metadata"] = True
    return _node(
        "agent",
        f"agent:codex:rollout:{rollout}:thread:{thread_id}",
        name,
        **attrs,
    )


def _message(
    item_id: str,
    item: Mapping[str, Any],
    rollout: str,
) -> dict[str, Any]:
    routing = item.get("agent_message")
    attrs: dict[str, Any] = {
        "provider": "codex",
        "rollout_id": rollout,
        "conversation_item_id": item_id,
        "model_visible": True,
    }
    if isinstance(routing, dict):
        author = routing.get("author")
        recipient = routing.get("recipient")
        if isinstance(author, str) and author:
            attrs["author"] = author
        if isinstance(recipient, str) and recipient:
            attrs["recipient"] = recipient
    return _node(
        "agent_message",
        f"agent-message:codex:{rollout}:{item_id}",
        "Codex agent message",
        **attrs,
    )


def _inference(
    call_id: str,
    call: Mapping[str, Any],
    rollout: str,
) -> dict[str, Any]:
    attrs: dict[str, Any] = {
        "provider": "codex",
        "rollout_id": rollout,
        "inference_call_id": call_id,
    }
    for key in ("thread_id", "codex_turn_id", "model", "provider_name", "response_id"):
        value = call.get(key)
        if value is not None:
            attrs[key] = value
    return _node(
        "inference_call",
        f"inference-call:codex:{rollout}:{call_id}",
        str(call.get("model") or "Codex inference"),
        **attrs,
    )


def _event(
    ts: str,
    relation: str,
    source: dict[str, Any],
    target: dict[str, Any],
    **attrs: Any,
) -> dict[str, Any]:
    return {
        "timestamp": ts,
        "event_type": f"semantic.codex.rollout.message_diagnostic.{relation.lower()}",
        "relation": relation,
        "source": source,
        "target": target,
        "attributes": {
            "backend": "semantic",
            "provider": "codex",
            "evidence_source": "codex_rollout_trace",
            "attribution": "codex_rollout_message_diagnostic",
            "causal": False,
            "inferred": False,
            "diagnostic_semantics": "provider_reduced_state_exact_membership",
            **attrs,
        },
    }


def _state_events(
    state: Mapping[str, Any],
    bundle: Path,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    rollout = str(state.get("rollout_id") or state.get("trace_id") or bundle.name)
    trace = str(state.get("trace_id") or bundle.name)
    started = _iso(state.get("started_at_unix_ms"))
    threads = _maps(state, "threads")
    items = _maps(state, "conversation_items")
    inferences = _maps(state, "inference_calls")
    messages = {
        item_id: item
        for item_id, item in items.items()
        if isinstance(item.get("agent_message"), dict)
    }

    events: list[dict[str, Any]] = []
    consumed_messages: set[str] = set()
    inference_memberships = 0

    for call_id, call in inferences.items():
        request_item_ids = call.get("request_item_ids")
        if not isinstance(request_item_ids, list):
            continue
        inference_thread_id = call.get("thread_id")
        execution = call.get("execution")
        ts = _iso(
            execution.get("started_at_unix_ms") if isinstance(execution, dict) else None,
            started,
        )
        inference = _inference(call_id, call, rollout)

        for raw_item_id in request_item_ids:
            if not isinstance(raw_item_id, str) or not raw_item_id:
                continue
            item = messages.get(raw_item_id)
            if item is None:
                continue

            message_thread_id = item.get("thread_id")
            thread_match = (
                isinstance(inference_thread_id, str)
                and bool(inference_thread_id)
                and isinstance(message_thread_id, str)
                and bool(message_thread_id)
                and inference_thread_id == message_thread_id
            )
            message = _message(raw_item_id, item, rollout)
            common = {
                "trace_id": trace,
                "rollout_id": rollout,
                "request_item_id": raw_item_id,
                "inference_call_id": call_id,
                "message_thread_id": message_thread_id,
                "inference_thread_id": inference_thread_id,
                "thread_ownership_match": thread_match,
                "provider_request_item_membership_exact": True,
                "consumption_semantics": _CONSUMPTION_SEMANTICS,
            }
            events.append(
                _event(
                    ts,
                    "INCLUDED_AGENT_MESSAGE_IN_INFERENCE",
                    message,
                    inference,
                    **common,
                )
            )
            inference_memberships += 1

            if not thread_match:
                continue
            consumer = _agent(str(inference_thread_id), threads, rollout)
            events.append(
                _event(
                    ts,
                    "CONSUMED_AGENT_MESSAGE",
                    consumer,
                    message,
                    consumer_thread_matches_message_thread=True,
                    **common,
                )
            )
            consumed_messages.add(raw_item_id)

    return events, {
        "message_count": len(messages),
        "consumed_message_count": len(consumed_messages),
        "inference_membership_count": inference_memberships,
    }


def enrich_codex_message_consumption(
    *,
    trace_root: str | Path,
    semantic_sidecar: str | Path,
) -> CodexMessageDiagnosticResult:
    """Materialize exact Codex message-to-inference request membership.

    ``CONSUMED_AGENT_MESSAGE`` means that a routed message belonged to the same
    provider thread as an inference call and its stable conversation-item ID was
    present in that call's provider-recorded ``request_item_ids``. This proves
    request-context inclusion only; it does not prove model attention, reading,
    or semantic use of the message.
    """
    root = Path(trace_root).expanduser().resolve()
    sidecar = Path(semantic_sidecar).expanduser().resolve()
    bundles = (
        []
        if not root.is_dir()
        else sorted(
            candidate
            for candidate in root.iterdir()
            if candidate.is_dir()
            and candidate.name.startswith("trace-")
            and (candidate / "state.json").is_file()
        )
    )
    if not bundles:
        return CodexMessageDiagnosticResult(
            status="no_reduced_state",
            trace_root=str(root),
        )

    events: list[dict[str, Any]] = []
    errors: list[str] = []
    totals = {
        "message_count": 0,
        "consumed_message_count": 0,
        "inference_membership_count": 0,
    }
    imported = 0

    for bundle in bundles:
        try:
            state = json.loads((bundle / "state.json").read_text(encoding="utf-8"))
            if not isinstance(state, dict):
                raise ValueError("state.json must contain a JSON object")
            current, counts = _state_events(state, bundle)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            errors.append(f"{bundle.name}: {exc}")
            continue
        imported += 1
        events.extend(current)
        for key in totals:
            totals[key] += counts[key]

    if events:
        append_semantic_records(sidecar, events)
    status = (
        "imported"
        if imported == len(bundles)
        else "partial"
        if imported
        else "failed"
    )
    return CodexMessageDiagnosticResult(
        status=status,
        trace_root=str(root),
        bundle_count=len(bundles),
        semantic_event_count=len(events),
        errors=tuple(errors),
        **totals,
    )
