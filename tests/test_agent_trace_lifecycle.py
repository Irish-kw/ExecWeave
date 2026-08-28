from __future__ import annotations

import pytest

from execweave.provider_lifecycle import provider_lifecycle_annotation


def _event(provider: str, relation: str) -> dict:
    return {
        "relation": relation,
        "source": {"type": "agent", "id": f"agent:{provider}", "attributes": {}},
        "target": {"type": "entity", "id": f"target:{relation}", "attributes": {}},
        "attributes": {"provider": provider, "backend": "semantic", "causal": False},
    }


@pytest.mark.parametrize(
    ("provider", "relation", "kind", "stage"),
    [
        ("codex", "SENT_AGENT_MESSAGE", "agent_message", "sent"),
        ("codex", "DELIVERED_AGENT_MESSAGE", "agent_message", "delivered"),
        ("opencode", "HAS_CHILD_AGENT_SESSION", "subagent", "child_session"),
        ("cursor", "PRODUCED_REASONING_TEXT", "reasoning", "provider_exposed_text"),
        ("codex", "STARTED_AGENT_TURN", "agent_turn", "started"),
        ("codex", "ISSUED_INFERENCE_IN_TURN", "agent_turn", "inference_issued"),
        ("codex", "OWNED_TERMINAL_SESSION", "terminal_session", "agent_owned"),
        ("codex", "HAS_TERMINAL_OPERATION", "terminal_session", "operation_observed"),
        ("codex", "INSTALLED_COMPACTION", "context_compaction", "installed"),
        ("codex", "HAS_COMPACTION_REQUEST_PAYLOAD", "context_compaction", "request_payload_observed"),
    ],
)
def test_agent_trace_relations_have_cross_provider_lifecycle(
    provider: str,
    relation: str,
    kind: str,
    stage: str,
) -> None:
    annotation = provider_lifecycle_annotation(_event(provider, relation))
    assert annotation is not None
    assert annotation.to_dict() == {
        "schema_version": "0.1",
        "provider": provider,
        "kind": kind,
        "stage": stage,
        "evidence_semantics": "classification_only",
    }
