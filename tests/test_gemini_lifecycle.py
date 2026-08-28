from __future__ import annotations

import pytest

from execweave.provider_lifecycle import provider_lifecycle_annotation


def _event(relation: str) -> dict:
    return {
        "relation": relation,
        "source": {"type": "agent", "id": "agent:Gemini CLI", "attributes": {}},
        "target": {"type": "entity", "id": f"target:{relation}", "attributes": {}},
        "attributes": {
            "provider": "gemini",
            "backend": "semantic",
            "causal": False,
        },
    }


@pytest.mark.parametrize(
    ("relation", "kind", "stage"),
    [
        ("OBSERVED_AGENT_TURN_START", "agent_turn", "start_observed"),
        ("OBSERVED_AGENT_TURN_END", "agent_turn", "end_observed"),
        ("OBSERVED_MODEL_REQUEST_TARGET", "model", "request_target_observed"),
        (
            "OBSERVED_TOOL_SELECTION_MODEL_REQUEST",
            "model",
            "tool_selection_request_observed",
        ),
        (
            "OBSERVED_MODEL_RESPONSE_CHUNK",
            "assistant_response",
            "model_stream_chunk_observed",
        ),
        ("OBSERVED_AGENT_PROMPT", "prompt", "observed"),
        (
            "OBSERVED_LLM_REQUEST_BEFORE_MODEL",
            "inference_request",
            "before_model_observed",
        ),
        (
            "OBSERVED_LLM_REQUEST_BEFORE_TOOL_SELECTION",
            "inference_request",
            "before_tool_selection_observed",
        ),
        (
            "OBSERVED_LLM_REQUEST_FOR_RESPONSE",
            "inference_request",
            "response_request_observed",
        ),
        (
            "OBSERVED_TOOL_INPUT_BEFORE_EXECUTION",
            "tool_call",
            "input_observed_before_execution",
        ),
        (
            "OBSERVED_AGENT_RESPONSE_CANDIDATE",
            "assistant_response",
            "turn_candidate_observed",
        ),
    ],
)
def test_gemini_official_evidence_has_cross_provider_lifecycle(
    relation: str,
    kind: str,
    stage: str,
) -> None:
    annotation = provider_lifecycle_annotation(_event(relation))
    assert annotation is not None
    assert annotation.provider == "gemini"
    assert annotation.kind == kind
    assert annotation.stage == stage
    assert annotation.to_dict()["evidence_semantics"] == "classification_only"
