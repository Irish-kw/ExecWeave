from __future__ import annotations

import io
import json
from pathlib import Path

from execweave.claude_child_transcript import claude_child_transcript_semantic_events
from execweave.claude_hook_cli import main as claude_hook_main
from execweave.graph import GraphAccumulator


def _transcript(root: Path, session_id: str, agent_id: str) -> Path:
    path = root / session_id / "subagents" / f"agent-{agent_id}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _payload(transcript: Path, *, session_id: str = "session-1", agent_id: str = "agent-7") -> dict:
    return {
        "hook_event_name": "SubagentStop",
        "session_id": session_id,
        "agent_id": agent_id,
        "agent_type": "Explore",
        "cwd": str(transcript.parents[2]),
        "transcript_path": str(transcript.parents[2] / f"{session_id}.jsonl"),
        "agent_transcript_path": str(transcript),
    }


def test_child_transcript_write_is_owned_by_child_and_declares_file(tmp_path: Path) -> None:
    transcript = _transcript(tmp_path, "session-1", "agent-7")
    target = tmp_path / "child.md"
    transcript.write_text(
        json.dumps(
            {
                "type": "assistant",
                "agentId": "agent-7",
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "toolu-child-write",
                            "name": "Write",
                            "input": {"file_path": str(target), "content": "# child"},
                        }
                    ],
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    events = claude_child_transcript_semantic_events(
        _payload(transcript),
        timestamp="2026-09-02T00:00:00Z",
    )
    graph = GraphAccumulator(session_id="claude-test", source_path=tmp_path / "events.jsonl")
    for event in events:
        graph.apply(event)
    rendered = graph.to_dict()

    child_id = "agent:claude:session-1:subagent:agent-7"
    call_id = "tool-call:claude:session-1:toolu-child-write"
    file_id = f"file:{target.resolve()}"
    assert any(
        edge["source"] == child_id
        and edge["target"] == call_id
        and edge["relation"] == "REQUESTED_TOOL_CALL"
        for edge in rendered["edges"]
    )
    assert any(
        edge["source"] == call_id
        and edge["target"] == file_id
        and edge["relation"] == "DECLARED_TARGET"
        for edge in rendered["edges"]
    )
    assert all(edge["source"] != "agent:Claude Code" for edge in rendered["edges"] if edge["target"] == call_id)


def test_child_transcript_result_reuses_tool_call_identity(tmp_path: Path) -> None:
    transcript = _transcript(tmp_path, "session-1", "agent-7")
    transcript.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "type": "assistant",
                        "agentId": "agent-7",
                        "message": {
                            "content": [
                                {
                                    "type": "tool_use",
                                    "id": "toolu-child-read",
                                    "name": "Read",
                                    "input": {"file_path": str(tmp_path / "notes.md")},
                                }
                            ]
                        },
                    }
                ),
                json.dumps(
                    {
                        "type": "user",
                        "agentId": "agent-7",
                        "message": {
                            "content": [
                                {
                                    "type": "tool_result",
                                    "tool_use_id": "toolu-child-read",
                                    "content": "# notes",
                                }
                            ]
                        },
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    events = claude_child_transcript_semantic_events(
        _payload(transcript),
        timestamp="2026-09-02T00:00:00Z",
    )

    returned = next(event for event in events if event["relation"] == "TOOL_CALL_SUCCEEDED")
    assert returned["source"]["id"] == "tool-call:claude:session-1:toolu-child-read"
    assert returned["target"]["id"] == "tool:claude:Read"


def test_child_transcript_replay_deduplicates_existing_edges(tmp_path: Path) -> None:
    transcript = _transcript(tmp_path, "session-1", "agent-7")
    target = tmp_path / "child.md"
    transcript.write_text(
        json.dumps(
            {
                "type": "assistant",
                "agentId": "agent-7",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "toolu-child-write",
                            "name": "Write",
                            "input": {"file_path": str(target)},
                        }
                    ]
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    sidecar = tmp_path / "semantic.jsonl"
    sidecar.write_text(
        json.dumps(
            {
                "relation": "REQUESTED_TOOL_CALL",
                "source": {"id": "agent:claude:session-1:subagent:agent-7"},
                "target": {"id": "tool-call:claude:session-1:toolu-child-write"},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    events = claude_child_transcript_semantic_events(
        _payload(transcript),
        timestamp="2026-09-02T00:00:00Z",
        sidecar=sidecar,
    )

    assert not any(event["relation"] == "REQUESTED_TOOL_CALL" for event in events)
    assert any(event["relation"] == "DECLARED_TARGET" for event in events)


def test_hook_cli_persists_child_file_graph_and_transcript_archive(
    monkeypatch,
    tmp_path: Path,
) -> None:
    transcript = _transcript(tmp_path, "session-1", "agent-7")
    target = tmp_path / "child.md"
    transcript.write_text(
        json.dumps(
            {
                "type": "assistant",
                "agentId": "agent-7",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "toolu-child-write",
                            "name": "Write",
                            "input": {"file_path": str(target)},
                        }
                    ]
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    sidecar = tmp_path / "semantic.jsonl"
    payload = _payload(transcript)
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))

    assert claude_hook_main(["--sidecar", str(sidecar)]) == 0
    records = [json.loads(line) for line in sidecar.read_text(encoding="utf-8").splitlines()]

    assert any(
        record["relation"] == "DECLARED_TARGET"
        and record["source"]["id"] == "tool-call:claude:session-1:toolu-child-write"
        and record["target"]["id"] == f"file:{target.resolve()}"
        for record in records
    )
    assert any(
        record["relation"] == "HAS_CONVERSATION_TRANSCRIPT"
        and record["source"]["id"] == "agent:claude:session-1:subagent:agent-7"
        for record in records
    )


def test_child_transcript_rejects_unvalidated_path(tmp_path: Path) -> None:
    transcript = tmp_path / "arbitrary.jsonl"
    transcript.write_text("{}\n", encoding="utf-8")
    payload = {
        "hook_event_name": "SubagentStop",
        "session_id": "session-1",
        "agent_id": "agent-7",
        "transcript_path": str(tmp_path / "session-1.jsonl"),
        "agent_transcript_path": str(transcript),
    }

    assert claude_child_transcript_semantic_events(
        payload,
        timestamp="2026-09-02T00:00:00Z",
    ) == []
