from __future__ import annotations

import json
from pathlib import Path

from execweave.codex_message_diagnostics import enrich_codex_message_consumption
from execweave.provider_lifecycle import provider_lifecycle_annotation


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def _bundle(tmp_path: Path) -> Path:
    root = tmp_path / "trace-root"
    bundle = root / "trace-message-diagnostic"
    started = 1_788_000_000_000
    _write(
        bundle / "state.json",
        {
            "trace_id": "trace-message-diagnostic",
            "rollout_id": "rollout-message-diagnostic",
            "started_at_unix_ms": started,
            "threads": {
                "root-thread": {
                    "thread_id": "root-thread",
                    "agent_path": "/root",
                    "nickname": "root",
                },
                "child-thread": {
                    "thread_id": "child-thread",
                    "agent_path": "/root/agent_b",
                    "nickname": "agent_b",
                },
            },
            "conversation_items": {
                "message-consumed": {
                    "item_id": "message-consumed",
                    "thread_id": "child-thread",
                    "role": "user",
                    "kind": "message",
                    "agent_message": {
                        "author": "/root",
                        "recipient": "/root/agent_b",
                    },
                },
                "message-cross-thread": {
                    "item_id": "message-cross-thread",
                    "thread_id": "root-thread",
                    "role": "user",
                    "kind": "message",
                    "agent_message": {
                        "author": "/root/agent_b",
                        "recipient": "/root",
                    },
                },
                "ordinary-user-input": {
                    "item_id": "ordinary-user-input",
                    "thread_id": "child-thread",
                    "role": "user",
                    "kind": "message",
                    "agent_message": None,
                },
            },
            "inference_calls": {
                "inf-child": {
                    "inference_call_id": "inf-child",
                    "thread_id": "child-thread",
                    "codex_turn_id": "turn-child",
                    "model": "gpt-5.6-codex",
                    "execution": {
                        "started_at_unix_ms": started + 5000,
                        "status": "completed",
                    },
                    "request_item_ids": [
                        "message-consumed",
                        "message-cross-thread",
                        "ordinary-user-input",
                    ],
                },
                "inf-without-membership-list": {
                    "inference_call_id": "inf-without-membership-list",
                    "thread_id": "child-thread",
                    "model": "gpt-5.6-codex",
                    "execution": {
                        "started_at_unix_ms": started + 6000,
                        "status": "completed",
                    },
                },
            },
        },
    )
    return root


def test_codex_message_consumption_requires_exact_request_membership_and_thread_owner(
    tmp_path: Path,
) -> None:
    root = _bundle(tmp_path)
    sidecar = tmp_path / "run" / "semantic.jsonl"

    result = enrich_codex_message_consumption(
        trace_root=root,
        semantic_sidecar=sidecar,
    )

    assert result.status == "imported"
    assert result.bundle_count == 1
    assert result.message_count == 2
    assert result.consumed_message_count == 1
    assert result.inference_membership_count == 2
    assert result.semantic_event_count == 3

    events = [
        json.loads(line)
        for line in sidecar.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    memberships = [
        event
        for event in events
        if event["relation"] == "INCLUDED_AGENT_MESSAGE_IN_INFERENCE"
    ]
    consumed = [
        event for event in events if event["relation"] == "CONSUMED_AGENT_MESSAGE"
    ]
    assert len(memberships) == 2
    assert len(consumed) == 1

    exact = next(
        event
        for event in memberships
        if event["attributes"]["request_item_id"] == "message-consumed"
    )
    assert exact["source"]["id"] == (
        "agent-message:codex:rollout-message-diagnostic:message-consumed"
    )
    assert exact["target"]["id"] == (
        "inference-call:codex:rollout-message-diagnostic:inf-child"
    )
    assert exact["attributes"]["provider_request_item_membership_exact"] is True
    assert exact["attributes"]["thread_ownership_match"] is True
    assert exact["attributes"]["causal"] is False
    assert exact["attributes"]["inferred"] is False
    assert exact["attributes"]["consumption_semantics"] == (
        "included_in_provider_recorded_inference_request_context_"
        "not_proof_of_model_attention"
    )

    cross = next(
        event
        for event in memberships
        if event["attributes"]["request_item_id"] == "message-cross-thread"
    )
    assert cross["attributes"]["thread_ownership_match"] is False
    assert all(
        event["target"]["id"]
        != "agent-message:codex:rollout-message-diagnostic:message-cross-thread"
        for event in consumed
    )

    consumed_event = consumed[0]
    assert consumed_event["source"]["id"] == (
        "agent:codex:rollout:rollout-message-diagnostic:thread:child-thread"
    )
    assert consumed_event["target"]["id"] == (
        "agent-message:codex:rollout-message-diagnostic:message-consumed"
    )
    assert consumed_event["attributes"]["consumer_thread_matches_message_thread"] is True

    stages = {
        provider_lifecycle_annotation(event).stage
        for event in events
        if provider_lifecycle_annotation(event) is not None
    }
    assert {"included_in_inference", "consumed"}.issubset(stages)


def test_codex_message_consumption_is_noop_without_reduced_state(tmp_path: Path) -> None:
    result = enrich_codex_message_consumption(
        trace_root=tmp_path / "missing",
        semantic_sidecar=tmp_path / "run" / "semantic.jsonl",
    )
    assert result.status == "no_reduced_state"
    assert result.semantic_event_count == 0
