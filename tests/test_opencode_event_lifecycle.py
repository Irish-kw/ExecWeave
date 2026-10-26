from __future__ import annotations

import pytest

from execweave.provider_lifecycle import provider_lifecycle_annotation


def _event(relation: str) -> dict:
    return {
        "relation": relation,
        "source": {
            "type": "agent",
            "id": "agent:opencode:session:ses_1",
            "attributes": {},
        },
        "target": {
            "type": "entity",
            "id": f"target:{relation}",
            "attributes": {},
        },
        "attributes": {
            "provider": "opencode",
            "backend": "semantic",
            "causal": False,
        },
    }


@pytest.mark.parametrize(
    ("relation", "kind", "stage"),
    [
        ("OBSERVED_AGENT_SESSION_DELETED", "agent_session", "deleted"),
        ("OBSERVED_PROVIDER_SESSION_STATUS", "provider_session", "status_observed"),
        ("OBSERVED_PROVIDER_SESSION_IDLE", "provider_session", "idle_observed"),
        ("OBSERVED_PROVIDER_SESSION_ERROR", "provider_session", "error_observed"),
        ("OBSERVED_SESSION_DIFF", "session_diff", "observed"),
        ("OBSERVED_PERMISSION_REPLY", "permission", "replied"),
        ("PERMISSION_TARGETS_TOOL_CALL", "permission", "tool_call_targeted"),
        ("OBSERVED_TODO_STATE", "todo_state", "observed"),
        ("OBSERVED_MESSAGE_REMOVED", "agent_message", "removed"),
        ("OBSERVED_MESSAGE_PART_REMOVED", "agent_message_part", "removed"),
    ],
)
def test_opencode_event_bus_relations_have_cross_provider_lifecycle(
    relation: str,
    kind: str,
    stage: str,
) -> None:
    annotation = provider_lifecycle_annotation(_event(relation))
    assert annotation is not None
    assert annotation.to_dict() == {
        "schema_version": "0.1",
        "provider": "opencode",
        "kind": kind,
        "stage": stage,
        "evidence_semantics": "classification_only",
    }
