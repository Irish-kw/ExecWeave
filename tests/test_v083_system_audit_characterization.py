from __future__ import annotations

from pathlib import Path

from execweave.antigravity_adapter import antigravity_hook_to_semantic_events
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


def test_aud_002_characterizes_vllm_request_identity_collision() -> None:
    """AUD-002: distinct endpoints currently collapse onto one request node id."""
    payload = {
        "model": "same-model",
        "usage": {"prompt_tokens": 1, "completion_tokens": 1},
    }
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

    assert _served_request_id(first) == _served_request_id(second)


def test_aud_003_characterizes_litellm_request_identity_collision() -> None:
    """AUD-003: distinct LiteLLM endpoints currently collapse onto one request node id."""
    payload = {
        "model": "same-model",
        "usage": {"prompt_tokens": 1, "completion_tokens": 1},
    }
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

    assert _served_request_id(first) == _served_request_id(second)


def test_aud_004_characterizes_opencode_dual_agent_identity(tmp_path: Path) -> None:
    """AUD-004: semantic and conversation paths currently name the same session differently."""
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

    assert semantic_agent != conversation_agent
    assert semantic_agent == "agent:OpenCode"
    assert conversation_agent == "agent:opencode:session:ses-audit-one"


def test_aud_005_characterizes_antigravity_fabricated_root_provenance(
    tmp_path: Path,
) -> None:
    """AUD-005: transcript ownership currently fabricates provider_session_root evidence."""
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
    assert attrs.get("root_topology_evidence") == "provider_session_root"


def test_aud_006_characterizes_antigravity_tool_conversation_identity_split(
    tmp_path: Path,
) -> None:
    """AUD-006: one exact conversation id currently produces two graph agent ids."""
    conversation_id = "shared-conversation"
    semantic = antigravity_hook_to_semantic_events(
        {"conversationId": conversation_id, "stepIdx": 7},
        hook_event="PostToolUse",
        timestamp=_TIMESTAMP,
    )

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
    archived = antigravity_conversation_archive_events(
        {"conversationId": conversation_id, "transcriptPath": str(transcript)},
        store=FullFidelityContentStore(tmp_path / "run"),
        timestamp=_TIMESTAMP,
    )

    assert semantic and archived
    semantic_agent = semantic[0]["source"]["id"]
    conversation_agent = archived[0]["source"]["id"]
    assert semantic_agent == "agent:Antigravity"
    assert conversation_agent == f"agent:antigravity:conversation:{conversation_id}"
    assert semantic_agent != conversation_agent
