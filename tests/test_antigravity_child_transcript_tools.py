from __future__ import annotations

import json
from pathlib import Path

from execweave.antigravity_full_fidelity import antigravity_hook_to_content_events
from execweave.content_store import FullFidelityContentStore
from execweave.graph import GraphAccumulator


def _transcript(root: Path, conversation_id: str) -> Path:
    path = (
        root
        / "antigravity-cli"
        / "brain"
        / conversation_id
        / ".system_generated"
        / "logs"
        / "transcript_full.jsonl"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _write(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_child_transcript_write_to_file_is_owned_by_child_agent(tmp_path: Path) -> None:
    parent_id = "parent-0000"
    child_id = "child-0000"
    parent = _transcript(tmp_path, parent_id)
    child = _transcript(tmp_path, child_id)
    target = tmp_path / "agent_child.md"
    _write(
        child,
        [
            {
                "step_index": 3,
                "source": "MODEL",
                "type": "PLANNER_RESPONSE",
                "status": "DONE",
                "tool_calls": [
                    {
                        "name": "write_to_file",
                        "args": {
                            # AGY's transcript stores scalar tool arguments as JSON strings.
                            "TargetFile": json.dumps(str(target)),
                            "CodeContent": json.dumps("# child"),
                        },
                    }
                ],
            }
        ],
    )
    _write(
        parent,
        [
            {
                "step_index": 1,
                "source": "MODEL",
                "type": "PLANNER_RESPONSE",
                "status": "DONE",
                "tool_calls": [
                    {
                        "name": "invoke_subagent",
                        "args": {
                            "Subagents": [
                                {
                                    "Model": "inherit",
                                    "Prompt": "make a file",
                                    "Role": "Writer",
                                    "TypeName": "Writer",
                                }
                            ]
                        },
                    }
                ],
            },
            {
                "step_index": 2,
                "source": "MODEL",
                "type": "GENERIC",
                "status": "DONE",
                "content": (
                    "Created the following subagents:\n"
                    + json.dumps(
                        {
                            "conversationId": child_id,
                            "logAbsoluteUri": child.resolve().as_uri(),
                            "workspaceUris": [tmp_path.resolve().as_uri()],
                        }
                    )
                ),
            },
        ],
    )

    payload = {
        "conversationId": parent_id,
        "workspacePaths": [str(tmp_path.resolve())],
        "transcriptPath": str(parent),
        "stepIdx": 9,
        "toolCall": {"name": "schedule", "args": {"Action": "run"}},
        "error": "",
    }
    store = FullFidelityContentStore(tmp_path / "run")
    events = antigravity_hook_to_content_events(
        payload,
        hook_event="PostToolUse",
        store=store,
        timestamp="2026-09-02T00:00:00Z",
    )
    graph = GraphAccumulator(session_id="agy-test", source_path=tmp_path / "events.jsonl")
    for event in events:
        graph.apply(event)

    child_agent = f"agent:antigravity:conversation:{child_id}"
    child_tool_calls = [
        edge
        for edge in graph.to_dict()["edges"]
        if edge["source"] == child_agent and edge["relation"] == "REQUESTED_TOOL_CALL"
    ]
    assert len(child_tool_calls) == 1
    tool_call = child_tool_calls[0]["target"]
    file_id = f"file:{target.resolve()}"
    assert any(
        edge["source"] == tool_call
        and edge["relation"] == "DECLARED_TARGET"
        and edge["target"] == file_id
        for edge in graph.to_dict()["edges"]
    )
