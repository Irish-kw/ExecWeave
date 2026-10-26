from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .codex_adapter import append_semantic_records


@dataclass(frozen=True)
class CodexMessageTransportDiagnosticResult:
    status: str
    trace_root: str
    bundle_count: int = 0
    compared_message_count: int = 0
    matched_message_count: int = 0
    mismatched_message_count: int = 0
    unavailable_message_count: int = 0
    semantic_event_count: int = 0
    errors: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _iso_from_unix_ms(value: object, fallback: str | None = None) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return datetime.fromtimestamp(float(value) / 1000.0, timezone.utc).isoformat().replace(
            "+00:00", "Z"
        )
    return fallback or "1970-01-01T00:00:00Z"


def _maps(state: Mapping[str, Any], key: str) -> dict[str, dict[str, Any]]:
    value = state.get(key)
    if not isinstance(value, dict):
        return {}
    return {str(k): v for k, v in value.items() if isinstance(v, dict)}


def _tag_name(value: object) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        tagged = value.get("type")
        return tagged if isinstance(tagged, str) else None
    return None


def _safe_json_payload(
    bundle: Path,
    raw_payloads: Mapping[str, Mapping[str, Any]],
    raw_payload_id: object,
) -> dict[str, Any] | None:
    if not isinstance(raw_payload_id, str) or not raw_payload_id:
        return None
    raw_ref = raw_payloads.get(raw_payload_id)
    if not isinstance(raw_ref, Mapping):
        return None
    relative = raw_ref.get("path")
    if not isinstance(relative, str) or not relative:
        return None
    try:
        bundle_root = bundle.resolve()
        path = (bundle / relative).resolve()
        path.relative_to(bundle_root)
    except (OSError, ValueError):
        return None
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _arguments(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    value = payload.get("arguments")
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return None
        return decoded if isinstance(decoded, dict) else None
    return None


def _invocation_message(payload: Mapping[str, Any] | None) -> tuple[str | None, str | None]:
    if payload is None:
        return None, None
    args = _arguments(payload)
    if args is None:
        return None, None
    message = args.get("message")
    text = message if isinstance(message, str) else None
    recipient = None
    for key in ("agent_path", "recipient", "target_agent_path"):
        value = args.get(key)
        if isinstance(value, str) and value:
            recipient = value
            break
    return text, recipient


def _body_message(value: object) -> str | None:
    if not isinstance(value, dict):
        return None
    direct = value.get("message")
    if isinstance(direct, str):
        return direct
    body = value.get("body")
    candidate = body if isinstance(body, dict) else value
    parts = candidate.get("parts")
    if not isinstance(parts, list):
        return None
    texts = [
        part.get("text")
        for part in parts
        if isinstance(part, dict) and isinstance(part.get("text"), str)
    ]
    if not texts:
        return None
    return "".join(texts)


def _fingerprint(text: str | None) -> dict[str, Any] | None:
    if text is None:
        return None
    raw = text.encode("utf-8")
    return {
        "sha256": hashlib.sha256(raw).hexdigest(),
        "utf8_bytes": len(raw),
        "empty": len(raw) == 0,
    }


def _message_node(item_id: str, item: Mapping[str, Any], rollout: str) -> dict[str, Any]:
    routing = item.get("agent_message")
    attrs: dict[str, Any] = {
        "provider": "codex",
        "rollout_id": rollout,
        "conversation_item_id": item_id,
        "model_visible": True,
    }
    if isinstance(routing, dict):
        for key in ("author", "recipient"):
            value = routing.get(key)
            if isinstance(value, str) and value:
                attrs[key] = value
    return {
        "type": "agent_message",
        "id": f"agent-message:codex:{rollout}:{item_id}",
        "name": "Codex agent message",
        "attributes": attrs,
    }


def _diagnostic_node(
    *,
    rollout: str,
    edge_id: str,
    status: str,
    attributes: dict[str, Any],
) -> dict[str, Any]:
    return {
        "type": "agent_message_transport_diagnostic",
        "id": f"agent-message-transport-diagnostic:codex:{rollout}:{edge_id}",
        "name": f"Codex message payload {status.replace('_', ' ')}",
        "attributes": {
            "provider": "codex",
            "status": status,
            **attributes,
        },
    }


def _relation(status: str) -> str:
    return {
        "matched": "AGENT_MESSAGE_PAYLOAD_MATCHED",
        "mismatch": "AGENT_MESSAGE_PAYLOAD_MISMATCH",
        "comparison_unavailable": "AGENT_MESSAGE_PAYLOAD_COMPARISON_UNAVAILABLE",
    }[status]


def _event(
    *,
    timestamp: str,
    relation: str,
    source: dict[str, Any],
    target: dict[str, Any],
    attributes: dict[str, Any],
) -> dict[str, Any]:
    return {
        "timestamp": timestamp,
        "event_type": f"semantic.codex.rollout.message_transport.{relation.lower()}",
        "relation": relation,
        "source": source,
        "target": target,
        "attributes": {
            "backend": "semantic",
            "provider": "codex",
            "evidence_source": "codex_rollout_trace",
            "attribution": "codex_message_transport_diagnostic",
            "causal": False,
            "inferred": False,
            "stable_linkage_exact": True,
            "payload_comparison_semantics": (
                "exact_provider_linked_send_invocation_transport_and_routed_message_text;"
                "not_delivery_failure_proof"
            ),
            **attributes,
        },
    }


def _state_events(
    state: Mapping[str, Any],
    bundle: Path,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    rollout = str(state.get("rollout_id") or state.get("trace_id") or bundle.name)
    timestamp = _iso_from_unix_ms(
        state.get("ended_at_unix_ms"),
        _iso_from_unix_ms(state.get("started_at_unix_ms")),
    )
    raw_payloads = _maps(state, "raw_payloads")
    tool_calls = _maps(state, "tool_calls")
    items = _maps(state, "conversation_items")
    interactions = _maps(state, "interaction_edges")

    events: list[dict[str, Any]] = []
    counts = {"matched": 0, "mismatch": 0, "comparison_unavailable": 0}

    for edge_id, edge in interactions.items():
        if _tag_name(edge.get("kind")) != "send_message":
            continue
        source_anchor = edge.get("source")
        target_anchor = edge.get("target")
        if not isinstance(source_anchor, dict) or source_anchor.get("type") != "tool_call":
            continue
        if not isinstance(target_anchor, dict) or target_anchor.get("type") != "conversation_item":
            continue
        tool_call_id = source_anchor.get("tool_call_id")
        item_id = target_anchor.get("item_id")
        if not isinstance(tool_call_id, str) or not tool_call_id:
            continue
        if not isinstance(item_id, str) or not item_id:
            continue
        tool_call = tool_calls.get(tool_call_id)
        item = items.get(item_id)
        if tool_call is None or item is None or not isinstance(item.get("agent_message"), dict):
            continue

        invocation_id = tool_call.get("raw_invocation_payload_id")
        invocation_payload = _safe_json_payload(bundle, raw_payloads, invocation_id)
        invocation_text, invocation_recipient = _invocation_message(invocation_payload)

        carried_ids = edge.get("carried_raw_payload_ids")
        carried_ids = carried_ids if isinstance(carried_ids, list) else []
        carried_texts: list[str] = []
        carried_fingerprints: list[dict[str, Any]] = []
        observed_carried_ids: list[str] = []
        for raw_id in carried_ids:
            payload = _safe_json_payload(bundle, raw_payloads, raw_id)
            text = _body_message(payload)
            if not isinstance(raw_id, str) or text is None:
                continue
            observed_carried_ids.append(raw_id)
            carried_texts.append(text)
            fingerprint = _fingerprint(text)
            if fingerprint is not None:
                carried_fingerprints.append(fingerprint)

        routed_text = _body_message(item.get("body"))
        observed_values = [
            value
            for value in [invocation_text, *carried_texts, routed_text]
            if value is not None
        ]
        if len(observed_values) < 2:
            status = "comparison_unavailable"
        elif all(value == observed_values[0] for value in observed_values[1:]):
            status = "matched"
        else:
            status = "mismatch"
        counts[status] += 1

        routing = item.get("agent_message")
        routed_recipient = routing.get("recipient") if isinstance(routing, dict) else None
        recipient_match = (
            invocation_recipient == routed_recipient
            if isinstance(invocation_recipient, str) and isinstance(routed_recipient, str)
            else None
        )

        attrs: dict[str, Any] = {
            "interaction_edge_id": edge_id,
            "tool_call_id": tool_call_id,
            "conversation_item_id": item_id,
            "invocation_raw_payload_id": invocation_id,
            "carried_raw_payload_ids": observed_carried_ids,
            "invocation_message": _fingerprint(invocation_text),
            "transport_messages": carried_fingerprints,
            "routed_message": _fingerprint(routed_text),
            "invocation_recipient": invocation_recipient,
            "routed_recipient": routed_recipient,
            "recipient_match": recipient_match,
            "representations_compared": len(observed_values),
        }
        message = _message_node(item_id, item, rollout)
        diagnostic = _diagnostic_node(
            rollout=rollout,
            edge_id=edge_id,
            status=status,
            attributes=attrs,
        )
        events.append(
            _event(
                timestamp=timestamp,
                relation=_relation(status),
                source=message,
                target=diagnostic,
                attributes=attrs,
            )
        )

    return events, counts


def enrich_codex_message_transport_diagnostics(
    *,
    trace_root: str | Path,
    semantic_sidecar: str | Path,
) -> CodexMessageTransportDiagnosticResult:
    """Compare exact provider-linked Codex send-message representations.

    This compares message text from a send_message raw invocation, raw payloads
    explicitly carried by the same interaction edge, and the routed conversation
    item targeted by that edge. A mismatch means those provider-linked
    representations differ; it is not by itself proof of a delivery failure.
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
        return CodexMessageTransportDiagnosticResult(
            status="no_reduced_state",
            trace_root=str(root),
        )

    events: list[dict[str, Any]] = []
    errors: list[str] = []
    totals = {"matched": 0, "mismatch": 0, "comparison_unavailable": 0}
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
    status = "imported" if imported == len(bundles) else "partial" if imported else "failed"
    return CodexMessageTransportDiagnosticResult(
        status=status,
        trace_root=str(root),
        bundle_count=len(bundles),
        compared_message_count=sum(totals.values()),
        matched_message_count=totals["matched"],
        mismatched_message_count=totals["mismatch"],
        unavailable_message_count=totals["comparison_unavailable"],
        semantic_event_count=len(events),
        errors=tuple(errors),
    )
