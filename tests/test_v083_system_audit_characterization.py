from __future__ import annotations

from pathlib import Path
from typing import Any

from execweave.antigravity_adapter import antigravity_hook_to_semantic_events
from execweave.content_evidence import content_observation_event
from execweave.content_store import FullFidelityContentStore
from execweave.conversation_archive import antigravity_conversation_archive_events
from execweave.conversation_records import conversation_record_entries
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


def _deployment_id(events: list[dict[str, object]]) -> str:
    return next(
        str(event["target"]["id"])
        for event in events
        if event.get("relation") == "ROUTED_TO_DEPLOYMENT"
    )


def _graph(events: list[dict[str, Any]]) -> dict[str, Any]:
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    for index, event in enumerate(events):
        for entity in (event.get("source"), event.get("target")):
            if not isinstance(entity, dict) or not isinstance(entity.get("id"), str):
                continue
            node = nodes.setdefault(
                entity["id"],
                {
                    "type": entity.get("type"),
                    "id": entity["id"],
                    "name": entity.get("name"),
                    "attributes": {},
                },
            )
            incoming = entity.get("attributes")
            if isinstance(incoming, dict):
                for key, value in incoming.items():
                    if value is None:
                        node["attributes"].setdefault(key, None)
                    elif node["attributes"].get(key) is None:
                        node["attributes"][key] = value
        source = event.get("source")
        target = event.get("target")
        if not isinstance(source, dict) or not isinstance(target, dict):
            continue
        if not isinstance(source.get("id"), str) or not isinstance(target.get("id"), str):
            continue
        edges.append(
            {
                "source": source["id"],
                "target": target["id"],
                "relation": event.get("relation"),
                "first_sequence": index,
                "last_sequence": index,
                "first_seen": event.get("timestamp"),
                "last_seen": event.get("timestamp"),
            }
        )
    return {"nodes": list(nodes.values()), "edges": edges}


def _antigravity_transcript(tmp_path: Path, conversation_id: str) -> Path:
    transcript = (
        tmp_path
        / "antigravity"
        / "brain"
        / conversation_id
        / ".system_generated"
        / "logs"
        / "transcript.jsonl"
    )
    transcript.parent.mkdir(parents=True, exist_ok=True)
    transcript.write_text("{}\n", encoding="utf-8")
    return transcript


def test_aud_001_characterizes_antigravity_cross_session_root_merge(tmp_path: Path) -> None:
    """AUD-001 is system-wide: distinct Antigravity conversations also share :root."""
    run_root = tmp_path / "run"
    store = FullFidelityContentStore(run_root)
    events: list[dict[str, Any]] = []
    for index, conversation_id in enumerate(("ag-root-one", "ag-root-two")):
        source = {
            "type": "agent",
            "id": f"agent:antigravity:conversation:{conversation_id}",
            "name": "Antigravity conversation",
            "attributes": {
                "provider": "antigravity",
                "conversation_id": conversation_id,
                "identity_semantics": "provider_conversation_id",
            },
        }
        reference = store.put_text(
            f"ANTIGRAVITY ROOT ANSWER {index + 1}",
            content_kind="antigravity.assistant_response",
        )
        events.append(
            content_observation_event(
                timestamp=f"2026-08-31T00:00:0{index}Z",
                provider="antigravity",
                source=source,
                reference=reference,
                relation="PRODUCED_ASSISTANT_RESPONSE",
                observed_field="text",
                evidence_source="provider_hook",
                attribution="antigravity_hook",
            )
        )

    previews = [
        entry["conversation_preview"]
        for entry in conversation_record_entries(_graph(events), run_root)
        if isinstance(entry.get("conversation_preview"), dict)
    ]

    assert len(previews) == 1
    assert previews[0]["thread_id"] == "antigravity:root"
    text = "\n".join(str(message.get("text") or "") for message in previews[0]["messages"])
    assert "ANTIGRAVITY ROOT ANSWER 1" in text
    assert "ANTIGRAVITY ROOT ANSWER 2" in text


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


def test_aud_003_characterizes_litellm_deployment_identity_collision() -> None:
    """AUD-003 also affects deployment nodes, not only request nodes."""
    payload = {"model": "same-model", "usage": {"prompt_tokens": 1}}
    first = litellm_response_to_events(
        payload,
        endpoint="http://127.0.0.1:4000",
        request_id="req-a",
        deployment_id="shared-deployment",
        timestamp=_TIMESTAMP,
    )
    second = litellm_response_to_events(
        payload,
        endpoint="http://127.0.0.1:4001",
        request_id="req-b",
        deployment_id="shared-deployment",
        timestamp=_TIMESTAMP,
    )

    assert _deployment_id(first) == _deployment_id(second)


def test_aud_004_characterizes_opencode_dual_agent_identity(tmp_path: Path) -> None:
    """AUD-004: one session is split across semantic, metadata and conversation sources."""
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
    metadata_agent = next(
        event["source"]["id"]
        for event in content
        if event.get("relation") == "OBSERVED_PROVIDER_METADATA"
    )
    conversation_agent = next(
        event["source"]["id"]
        for event in content
        if event.get("relation") == "OBSERVED_CHAT_MESSAGE"
    )

    assert semantic_agent == "agent:OpenCode"
    assert metadata_agent == "agent:OpenCode"
    assert conversation_agent == "agent:opencode:session:ses-audit-one"
    assert semantic_agent != conversation_agent
    assert metadata_agent != conversation_agent


def test_aud_005_characterizes_antigravity_fabricated_root_provenance(
    tmp_path: Path,
) -> None:
    """AUD-005: transcript ownership currently fabricates provider_session_root evidence."""
    conversation_id = "child-conversation"
    transcript = _antigravity_transcript(tmp_path, conversation_id)

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
    """AUD-006: ID-less PostToolUse and Stop for one conversation use two agent ids."""
    conversation_id = "shared-conversation"
    semantic = antigravity_hook_to_semantic_events(
        {"conversationId": conversation_id, "stepIdx": 7},
        hook_event="PostToolUse",
        timestamp=_TIMESTAMP,
    )

    transcript = _antigravity_transcript(tmp_path, conversation_id)
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


def test_aud_006_characterizes_antigravity_exact_tool_call_identity_split(
    tmp_path: Path,
) -> None:
    """AUD-006 also affects the exact toolCall path, not only the 2.0 fallback path."""
    conversation_id = "shared-conversation-exact-tool"
    semantic = antigravity_hook_to_semantic_events(
        {
            "conversationId": conversation_id,
            "stepIdx": 8,
            "toolCall": {"name": "read_file", "args": {"path": "README.md"}},
        },
        hook_event="PostToolUse",
        timestamp=_TIMESTAMP,
    )

    transcript = _antigravity_transcript(tmp_path, conversation_id)
    archived = antigravity_conversation_archive_events(
        {"conversationId": conversation_id, "transcriptPath": str(transcript)},
        store=FullFidelityContentStore(tmp_path / "run-exact"),
        timestamp=_TIMESTAMP,
    )

    requested = next(event for event in semantic if event.get("relation") == "REQUESTED_TOOL_CALL")
    semantic_agent = requested["source"]["id"]
    conversation_agent = archived[0]["source"]["id"]
    assert semantic_agent == "agent:Antigravity"
    assert conversation_agent == f"agent:antigravity:conversation:{conversation_id}"
    assert semantic_agent != conversation_agent
