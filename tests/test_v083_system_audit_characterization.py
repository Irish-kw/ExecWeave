from __future__ import annotations

from pathlib import Path

import pytest

from execweave.content_store import FullFidelityContentStore
from execweave.conversation_archive import antigravity_conversation_archive_events
from execweave.inference_gateway import litellm_response_to_events
from execweave.model_runtime import vllm_response_to_events
from execweave.opencode_adapter import opencode_plugin_to_semantic_events
from execweave.opencode_full_fidelity import opencode_plugin_to_content_events


_TIMESTAMP = "2026-08-31T00:00:00Z"


def _served_request_id(events: list[dict[str, object]]) -> str:
    return next(
        str(event["target"]["id"])
        for event in events
        if event.get("relation") == "SERVED_INFERENCE"
    )


@pytest.mark.xfail(
    strict=True,
    reason="AUD-002: local runtime request identity is not endpoint scoped on v0.8.2/main",
)
def test_aud_002_vllm_request_identity_is_endpoint_scoped() -> None:
    payload = {"model": "same-model", "usage": {"prompt_tokens": 1, "completion_tokens": 1}}
    first = vllm_response_to_events(
        payload,
        endpoint="http://127.0.0.1:8000",
        request_id="same-native-id",
        timestamp=_TIMESTAMP,
    )
    second = vllm_response_to_events(
        payload,
        endpoint="http://127.0.0.1:8001",
        request_id="same-native-id",
        timestamp=_TIMESTAMP,
    )

    assert _served_request_id(first) != _served_request_id(second)


@pytest.mark.xfail(
    strict=True,
    reason="AUD-003: gateway request identity is not endpoint scoped on v0.8.2/main",
)
def test_aud_003_litellm_request_identity_is_endpoint_scoped() -> None:
    payload = {"model": "same-model", "usage": {"prompt_tokens": 1, "completion_tokens": 1}}
    first = litellm_response_to_events(
        payload,
        endpoint="http://127.0.0.1:4000",
        request_id="same-native-id",
        timestamp=_TIMESTAMP,
    )
    second = litellm_response_to_events(
        payload,
        endpoint="http://127.0.0.1:4001",
        request_id="same-native-id",
        timestamp=_TIMESTAMP,
    )

    assert _served_request_id(first) != _served_request_id(second)


@pytest.mark.xfail(
    strict=True,
    reason="AUD-004: OpenCode semantic and conversation paths use different agent IDs",
)
def test_aud_004_opencode_one_session_has_one_agent_identity(tmp_path: Path) -> None:
    payload = {
        "hook_event_name": "chat.message",
        "sessionID": "ses-audit-one",
        "message": {"role": "user", "content": "hello"},
        "model": {"providerID": "anthropic", "modelID": "claude-audit"},
    }
    semantic = opencode_plugin_to_semantic_events(payload, timestamp=_TIMESTAMP)
    content = opencode_plugin_to_content_events(
        payload,
        store=FullFidelityContentStore(tmp_path / "run"),
        timestamp=_TIMESTAMP,
    )

    semantic_agent = next(
        event["source"]["id"]
        for event in semantic
        if event.get("relation") == "USED_MODEL"
    )
    conversation_agent = next(
        event["source"]["id"]
        for event in content
        if event.get("relation") == "OBSERVED_CHAT_MESSAGE"
    )

    assert semantic_agent == conversation_agent


@pytest.mark.xfail(
    strict=True,
    reason="AUD-005: a validated Antigravity transcript is incorrectly stamped provider_session_root",
)
def test_aud_005_antigravity_transcript_does_not_fabricate_root_provenance(
    tmp_path: Path,
) -> None:
    conversation_id = "child-conversation"
    transcript = (
        tmp_path
        / "antigravity"
        / "brain"
        / conversation_id
        / ".system_generated"
        / "logs"
        / "transcript.jsonl"
    )
    transcript.parent.mkdir(parents=True)
    transcript.write_text("{}\n", encoding="utf-8")

    events = antigravity_conversation_archive_events(
        {"conversationId": conversation_id, "transcriptPath": str(transcript)},
        store=FullFidelityContentStore(tmp_path / "run"),
        timestamp=_TIMESTAMP,
    )

    assert events
    attrs = events[0]["source"]["attributes"]
    assert attrs.get("root_topology_evidence") != "provider_session_root"
