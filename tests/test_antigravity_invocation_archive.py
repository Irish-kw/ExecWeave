from __future__ import annotations

import json
from pathlib import Path

from execweave.antigravity_full_fidelity import antigravity_hook_to_content_events
from execweave.content_store import FullFidelityContentStore
from execweave.conversation_records import conversation_record_entries
from execweave.graph import GraphAccumulator


def _brain_transcript(tmp_path: Path, conversation_id: str) -> Path:
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
    return path


def test_antigravity_postinvocation_archives_transcript_like_codex_lifecycle(tmp_path: Path) -> None:
    """Codex snapshots on lifecycle events; Agy PostInvocation already has transcriptPath."""
    conversation_id = "conversation-live"
    transcript = _brain_transcript(tmp_path, conversation_id)
    transcript.write_text(
        json.dumps(
            {
                "step_index": 0,
                "source": "USER_EXPLICIT",
                "type": "USER_INPUT",
                "status": "DONE",
                "created_at": "2026-09-01T13:00:00Z",
                "content": "<USER_REQUEST>visible main prompt</USER_REQUEST>",
            },
            ensure_ascii=False,
        )
        + "\n"
        + json.dumps(
            {
                "step_index": 1,
                "source": "MODEL",
                "type": "PLANNER_RESPONSE",
                "status": "DONE",
                "created_at": "2026-09-01T13:00:01Z",
                "content": "visible main response",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    payload = {
        "conversationId": conversation_id,
        "workspacePaths": [str(tmp_path / "workspace")],
        "transcriptPath": str(transcript),
        "artifactDirectoryPath": str(transcript.parents[3]),
        "modelName": "agy-test",
        "initialNumSteps": 2,
        "invocationNum": 0,
    }
    store = FullFidelityContentStore(tmp_path / "run")
    events = antigravity_hook_to_content_events(
        payload, hook_event="PostInvocation", store=store, timestamp="2026-09-01T13:00:02Z"
    )
    archived = [event for event in events if event["relation"] == "HAS_CONVERSATION_TRANSCRIPT"]
    assert len(archived) == 1
    source_id = f"agent:antigravity:conversation:{conversation_id}"
    assert archived[0]["source"]["id"] == source_id

    graph = GraphAccumulator(session_id="agy-postinvocation", source_path=tmp_path / "events.jsonl")
    for event in events:
        graph.apply(event)
    entries = conversation_record_entries(graph.to_dict(), tmp_path / "run")
    previews = [
        entry["conversation_preview"]
        for entry in entries
        if entry.get("source_id") == source_id and isinstance(entry.get("conversation_preview"), dict)
    ]
    assert previews
    texts = [message.get("text") for message in previews[0]["messages"]]
    assert "visible main prompt" in texts
    assert "visible main response" in texts


def test_antigravity_preinvocation_archives_existing_transcript(tmp_path: Path) -> None:
    conversation_id = "conversation-pre"
    transcript = _brain_transcript(tmp_path, conversation_id)
    transcript.write_text(
        json.dumps(
            {
                "step_index": 0,
                "source": "USER_EXPLICIT",
                "type": "USER_INPUT",
                "status": "DONE",
                "created_at": "2026-09-01T13:04:00Z",
                "content": "<USER_REQUEST>prompt before model</USER_REQUEST>",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    payload = {
        "conversationId": conversation_id,
        "workspacePaths": [str(tmp_path)],
        "transcriptPath": str(transcript),
        "artifactDirectoryPath": str(transcript.parents[3]),
        "modelName": "agy-test",
        "initialNumSteps": 1,
        "invocationNum": 0,
    }
    events = antigravity_hook_to_content_events(
        payload,
        hook_event="PreInvocation",
        store=FullFidelityContentStore(tmp_path / "run"),
        timestamp="2026-09-01T13:04:01Z",
    )
    assert [event["relation"] for event in events].count("HAS_CONVERSATION_TRANSCRIPT") == 1
