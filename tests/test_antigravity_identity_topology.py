from __future__ import annotations

import json
from pathlib import Path

from execweave import agent_topology
from execweave.antigravity_adapter import antigravity_hook_to_semantic_events
from execweave.content_store import FullFidelityContentStore
from execweave.conversation_archive import antigravity_conversation_archive_events


def _transcript(tmp_path: Path, conversation_id: str) -> Path:
    path = (
        tmp_path
        / "antigravity-cli"
        / "brain"
        / conversation_id
        / ".system_generated"
        / "logs"
        / "transcript_full.jsonl"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"step_index": 1}) + "\n", encoding="utf-8")
    return path.resolve()


def _payload(tmp_path: Path, conversation_id: str = "conversation-r4") -> dict[str, object]:
    transcript = _transcript(tmp_path, conversation_id)
    workspace = (tmp_path / "workspace").resolve()
    workspace.mkdir(exist_ok=True)
    return {
        "conversationId": conversation_id,
        "workspacePaths": [str(workspace)],
        "transcriptPath": str(transcript),
        "artifactDirectoryPath": str(transcript.parents[3]),
        "modelName": "gemini-test",
        "stepIdx": 4,
        "toolCall": {"name": "run_command", "args": {"command": "pwd"}},
        "error": "",
    }


def test_antigravity_post_tool_uses_conversation_scoped_agent(tmp_path: Path) -> None:
    payload = _payload(tmp_path)

    events = antigravity_hook_to_semantic_events(
        payload,
        hook_event="PostToolUse",
        timestamp="2026-08-31T13:00:00Z",
    )
    requested = next(event for event in events if event["relation"] == "REQUESTED_TOOL_CALL")

    assert requested["source"]["id"] == "agent:antigravity:conversation:conversation-r4"
    assert requested["source"]["attributes"]["conversation_id"] == "conversation-r4"
    assert requested["source"]["attributes"]["identity_semantics"] == "provider_conversation_id"


def test_antigravity_preinvocation_uses_same_conversation_agent(tmp_path: Path) -> None:
    payload = _payload(tmp_path)

    events = antigravity_hook_to_semantic_events(
        payload,
        hook_event="PreInvocation",
        timestamp="2026-08-31T13:00:00Z",
    )
    observed = next(event for event in events if event["relation"] == "OBSERVED_PROVIDER_SESSION")

    assert observed["source"]["id"] == "agent:antigravity:conversation:conversation-r4"
    assert observed["target"]["id"] == "provider-session:antigravity:conversation-r4"


def test_antigravity_archive_does_not_claim_provider_root(tmp_path: Path) -> None:
    payload = _payload(tmp_path)
    events = antigravity_conversation_archive_events(
        payload,
        store=FullFidelityContentStore(tmp_path / "store"),
        timestamp="2026-08-31T13:00:00Z",
    )

    assert len(events) == 1
    source = events[0]["source"]
    assert source["id"] == "agent:antigravity:conversation:conversation-r4"
    attrs = source["attributes"]
    assert agent_topology.ATTR_ROOT_PATH not in attrs
    assert agent_topology.ATTR_ROOT_PATH_SOURCE not in attrs
    assert agent_topology.ATTR_ROOT_EVIDENCE not in attrs
    assert agent_topology.ATTR_ROLE not in attrs

    resolved = agent_topology.resolve_agent_topology(source)
    assert resolved.is_root is True
    assert resolved.topology_state == agent_topology.TOPOLOGY_DERIVED
    assert resolved.topology_evidence == agent_topology.EVIDENCE_NO_PARENT_EVIDENCE
    assert resolved.agent_path_source == agent_topology.PATH_EXECWEAVE_DERIVED


def test_antigravity_tool_and_archive_converge_on_same_agent(tmp_path: Path) -> None:
    payload = _payload(tmp_path, "conversation-shared")
    semantic = antigravity_hook_to_semantic_events(
        payload,
        hook_event="PostToolUse",
        timestamp="2026-08-31T13:00:00Z",
    )
    archived = antigravity_conversation_archive_events(
        payload,
        store=FullFidelityContentStore(tmp_path / "store"),
        timestamp="2026-08-31T13:00:01Z",
    )

    requested = next(event for event in semantic if event["relation"] == "REQUESTED_TOOL_CALL")
    assert archived
    assert requested["source"]["id"] == archived[0]["source"]["id"]
    assert requested["source"]["id"] == "agent:antigravity:conversation:conversation-shared"
