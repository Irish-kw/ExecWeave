from __future__ import annotations

from pathlib import Path

from execweave.agent_trace import opencode_session_agent
from execweave.content_store import FullFidelityContentStore
from execweave.opencode_adapter import opencode_plugin_to_semantic_events
from execweave.opencode_full_fidelity import opencode_plugin_to_content_events

SESSION_ID = "ses-aud-004"
EXPECTED_AGENT_ID = f"agent:opencode:session:{SESSION_ID}"


def _payload() -> dict[str, object]:
    return {
        "hook_event_name": "chat.message",
        "sessionID": SESSION_ID,
        "agent": "build",
        "model": {"providerID": "openai", "modelID": "gpt-5.6"},
        "message": {"role": "user", "content": "identity regression"},
        "parts": [{"type": "text", "text": "identity regression"}],
    }


def test_opencode_semantic_and_content_paths_share_session_agent(tmp_path: Path) -> None:
    payload = _payload()
    semantic = opencode_plugin_to_semantic_events(
        payload,
        timestamp="2026-08-31T12:00:00Z",
    )
    store = FullFidelityContentStore(tmp_path / "run")
    content = opencode_plugin_to_content_events(
        payload,
        store=store,
        timestamp="2026-08-31T12:00:00Z",
    )

    semantic_agent_ids = {
        event["source"]["id"]
        for event in semantic
        if event.get("relation") == "USED_MODEL"
    }
    content_agent_ids = {
        event["source"]["id"]
        for event in content
        if event.get("relation")
        in {"OBSERVED_PROVIDER_METADATA", "OBSERVED_CHAT_MESSAGE", "OBSERVED_CHAT_MESSAGE_PARTS"}
    }

    assert semantic_agent_ids == {EXPECTED_AGENT_ID}
    assert content_agent_ids == {EXPECTED_AGENT_ID}
    assert opencode_session_agent(SESSION_ID, agent_name="build")["id"] == EXPECTED_AGENT_ID
    assert "agent:OpenCode" not in semantic_agent_ids | content_agent_ids


def test_opencode_tool_request_uses_session_agent() -> None:
    events = opencode_plugin_to_semantic_events(
        {
            "hook_event_name": "tool.execute.before",
            "sessionID": SESSION_ID,
            "agent": "build",
            "callID": "call-1",
            "tool": "bash",
            "args": {"command": "printf ok"},
        },
        timestamp="2026-08-31T12:00:01Z",
    )
    requested = next(event for event in events if event["relation"] == "REQUESTED_TOOL_CALL")
    assert requested["source"]["id"] == EXPECTED_AGENT_ID


def test_opencode_unscoped_payload_keeps_provider_root_fallback(tmp_path: Path) -> None:
    store = FullFidelityContentStore(tmp_path / "run")
    events = opencode_plugin_to_content_events(
        {
            "hook_event_name": "chat.message",
            "message": {"role": "user", "content": "unscoped"},
        },
        store=store,
        timestamp="2026-08-31T12:00:02Z",
    )
    sources = {
        event["source"]["id"]
        for event in events
        if event.get("relation") in {"OBSERVED_PROVIDER_METADATA", "OBSERVED_CHAT_MESSAGE"}
    }
    assert sources == {"agent:OpenCode"}
