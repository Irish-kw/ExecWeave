from __future__ import annotations

import pytest

from execweave.provider_lifecycle import provider_lifecycle_annotation


@pytest.mark.parametrize(
    ("relation", "kind", "stage"),
    [
        ("OBSERVED_PROVIDER_SESSION", "provider_session", "observed"),
        ("OBSERVED_EXECUTION_STOP", "agent_execution", "stopped"),
        ("OBSERVED_EXECUTION_ERROR", "agent_execution", "error_observed"),
        (
            "OBSERVED_EXECUTION_ERROR_CONTENT",
            "agent_execution",
            "error_content_observed",
        ),
    ],
)
def test_antigravity_execution_relations_have_conservative_lifecycle(
    relation: str,
    kind: str,
    stage: str,
) -> None:
    event = {
        "relation": relation,
        "source": {
            "type": "provider_session",
            "id": "provider-session:antigravity:conversation-1",
            "attributes": {},
        },
        "target": {
            "type": "agent_execution",
            "id": "agent-execution:antigravity:conversation-1:2",
            "attributes": {},
        },
        "attributes": {
            "provider": "antigravity",
            "backend": "semantic",
            "causal": False,
        },
    }

    annotation = provider_lifecycle_annotation(event)

    assert annotation is not None
    assert annotation.to_dict() == {
        "schema_version": "0.1",
        "provider": "antigravity",
        "kind": kind,
        "stage": stage,
        "evidence_semantics": "classification_only",
    }
