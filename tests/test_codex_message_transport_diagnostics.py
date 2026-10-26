from __future__ import annotations

import json
from pathlib import Path

from execweave.codex_message_transport_diagnostics import (
    enrich_codex_message_transport_diagnostics,
)


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def _bundle(tmp_path: Path) -> Path:
    root = tmp_path / "trace-root"
    bundle = root / "trace-message-transport"
    payloads = bundle / "payloads"
    payloads.mkdir(parents=True)
    started = 1_788_000_000_000

    raw_payloads: dict[str, dict[str, object]] = {}

    def raw(raw_id: str, value: object) -> None:
        _write(payloads / f"{raw_id}.json", value)
        raw_payloads[raw_id] = {
            "raw_payload_id": raw_id,
            "kind": {"type": "test_payload"},
            "path": f"payloads/{raw_id}.json",
        }

    raw(
        "matched-invocation",
        {
            "name": "send_message",
            "arguments": {"agent_path": "/root/child", "message": "same-message"},
        },
    )
    raw("matched-carried", {"message": "same-message"})
    raw(
        "mismatch-invocation",
        {
            "name": "send_message",
            "arguments": {"agent_path": "/root/child", "message": "nonempty"},
        },
    )
    raw("mismatch-carried", {"message": ""})

    state = {
        "trace_id": "trace-message-transport",
        "rollout_id": "rollout-message-transport",
        "started_at_unix_ms": started,
        "ended_at_unix_ms": started + 5000,
        "raw_payloads": raw_payloads,
        "tool_calls": {
            "tool-match": {
                "tool_call_id": "tool-match",
                "kind": {"type": "send_message"},
                "raw_invocation_payload_id": "matched-invocation",
            },
            "tool-mismatch": {
                "tool_call_id": "tool-mismatch",
                "kind": {"type": "send_message"},
                "raw_invocation_payload_id": "mismatch-invocation",
            },
            "tool-unavailable": {
                "tool_call_id": "tool-unavailable",
                "kind": {"type": "send_message"},
            },
        },
        "conversation_items": {
            "message-match": {
                "item_id": "message-match",
                "thread_id": "child-thread",
                "agent_message": {"author": "/root", "recipient": "/root/child"},
                "body": {"parts": [{"type": "text", "text": "same-message"}]},
            },
            "message-mismatch": {
                "item_id": "message-mismatch",
                "thread_id": "child-thread",
                "agent_message": {"author": "/root", "recipient": "/root/child"},
                "body": {"parts": [{"type": "text", "text": ""}]},
            },
            "message-unavailable": {
                "item_id": "message-unavailable",
                "thread_id": "child-thread",
                "agent_message": {"author": "/root", "recipient": "/root/child"},
                "body": {"parts": [{"type": "text", "text": "routed-only"}]},
            },
        },
        "interaction_edges": {
            "edge-match": {
                "edge_id": "edge-match",
                "kind": "send_message",
                "source": {"type": "tool_call", "tool_call_id": "tool-match"},
                "target": {"type": "conversation_item", "item_id": "message-match"},
                "carried_raw_payload_ids": ["matched-carried"],
            },
            "edge-mismatch": {
                "edge_id": "edge-mismatch",
                "kind": "send_message",
                "source": {"type": "tool_call", "tool_call_id": "tool-mismatch"},
                "target": {"type": "conversation_item", "item_id": "message-mismatch"},
                "carried_raw_payload_ids": ["mismatch-carried"],
            },
            "edge-unavailable": {
                "edge_id": "edge-unavailable",
                "kind": "send_message",
                "source": {"type": "tool_call", "tool_call_id": "tool-unavailable"},
                "target": {"type": "conversation_item", "item_id": "message-unavailable"},
                "carried_raw_payload_ids": [],
            },
        },
    }
    _write(bundle / "state.json", state)
    return root


def test_transport_diagnostics_compare_exact_linked_message_representations(
    tmp_path: Path,
) -> None:
    root = _bundle(tmp_path)
    sidecar = tmp_path / "run" / "semantic.jsonl"

    result = enrich_codex_message_transport_diagnostics(
        trace_root=root,
        semantic_sidecar=sidecar,
    )

    assert result.status == "imported"
    assert result.bundle_count == 1
    assert result.compared_message_count == 3
    assert result.matched_message_count == 1
    assert result.mismatched_message_count == 1
    assert result.unavailable_message_count == 1
    assert result.semantic_event_count == 3

    events = [json.loads(line) for line in sidecar.read_text(encoding="utf-8").splitlines()]
    relations = [event["relation"] for event in events]
    assert relations == [
        "AGENT_MESSAGE_PAYLOAD_MATCHED",
        "AGENT_MESSAGE_PAYLOAD_MISMATCH",
        "AGENT_MESSAGE_PAYLOAD_COMPARISON_UNAVAILABLE",
    ]

    matched = events[0]
    assert matched["attributes"]["stable_linkage_exact"] is True
    assert matched["attributes"]["recipient_match"] is True
    assert matched["attributes"]["representations_compared"] == 3
    assert matched["attributes"]["invocation_message"]["sha256"] == (
        matched["attributes"]["routed_message"]["sha256"]
    )
    assert matched["attributes"]["transport_messages"][0]["sha256"] == (
        matched["attributes"]["routed_message"]["sha256"]
    )

    mismatch = events[1]
    assert mismatch["attributes"]["invocation_message"]["utf8_bytes"] == len("nonempty")
    assert mismatch["attributes"]["routed_message"]["utf8_bytes"] == 0
    assert mismatch["attributes"]["transport_messages"][0]["utf8_bytes"] == 0
    assert mismatch["attributes"]["invocation_message"]["sha256"] != (
        mismatch["attributes"]["routed_message"]["sha256"]
    )

    unavailable = events[2]
    assert unavailable["attributes"]["representations_compared"] == 1
    assert unavailable["target"]["attributes"]["status"] == "comparison_unavailable"

    serialized = json.dumps(events)
    assert "same-message" not in serialized
    assert "nonempty" not in serialized
    assert "routed-only" not in serialized
    assert "not_delivery_failure_proof" in serialized


def test_transport_diagnostics_are_noop_without_reduced_state(tmp_path: Path) -> None:
    result = enrich_codex_message_transport_diagnostics(
        trace_root=tmp_path / "missing",
        semantic_sidecar=tmp_path / "run" / "semantic.jsonl",
    )

    assert result.status == "no_reduced_state"
    assert result.semantic_event_count == 0
