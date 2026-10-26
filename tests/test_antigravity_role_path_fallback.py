"""When Agy omits graph parent evidence, derive /root/<Role> from the parent transcript."""

from __future__ import annotations

import json
from pathlib import Path

from execweave.agent_topology import (
    EVIDENCE_VALIDATED_CHILD_TRANSCRIPT,
    PATH_EXECWEAVE_DERIVED,
    ROOT_PATH,
)
from execweave.antigravity_full_fidelity import antigravity_hook_to_content_events
from execweave.antigravity_subagent_linkage import derived_child_agent_path, transcript_subagent_links
from execweave.content_store import FullFidelityContentStore
from execweave.conversation_records import conversation_record_entries
from execweave.graph import GraphAccumulator


PARENT = "parent-conversation"
CHILD = "child-conversation"
CHILD_PATH = "/root/security reviewer"


def _brain(tmp_path: Path, conversation_id: str) -> Path:
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


def _write(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def _spec() -> dict[str, str]:
    return {
        "Model": "inherit",
        "Prompt": "inspect authentication paths",
        "Role": "security reviewer",
        "TypeName": "research",
        "Workspace": "inherit",
    }


def _parent_rows(tmp_path: Path) -> list[dict[str, object]]:
    child_transcript = _brain(tmp_path, CHILD)
    result = (
        "Created the following subagents:\n"
        + json.dumps(
            {
                "conversationId": CHILD,
                "logAbsoluteUri": child_transcript.resolve().as_uri(),
                "workspaceUris": [tmp_path.resolve().as_uri()],
            }
        )
    )
    return [
        {
            "step_index": 0,
            "source": "USER_EXPLICIT",
            "type": "USER_INPUT",
            "status": "DONE",
            "created_at": "2026-09-02T01:00:00Z",
            "content": "<USER_REQUEST>root request</USER_REQUEST>",
        },
        {
            "step_index": 1,
            "source": "MODEL",
            "type": "PLANNER_RESPONSE",
            "status": "DONE",
            "created_at": "2026-09-02T01:00:01Z",
            "tool_calls": [{"name": "invoke_subagent", "args": {"Subagents": [_spec()]}}],
        },
        {
            "step_index": 2,
            "source": "MODEL",
            "type": "GENERIC",
            "status": "DONE",
            "created_at": "2026-09-02T01:00:02Z",
            "content": result,
        },
        {
            "step_index": 3,
            "source": "MODEL",
            "type": "PLANNER_RESPONSE",
            "status": "DONE",
            "created_at": "2026-09-02T01:00:03Z",
            "content": "root planner reply",
        },
    ]


def test_derived_path_prefers_role_then_type_then_id() -> None:
    assert derived_child_agent_path({"Role": "Sartre", "TypeName": "research"}, "abc") == "/root/Sartre"
    assert derived_child_agent_path({"TypeName": "research"}, "abc") == "/root/research"
    assert derived_child_agent_path({}, "child/id") == "/root/child-id"


def test_schedule_post_tool_use_assigns_child_from_parent_transcript(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    parent_transcript = _brain(tmp_path, PARENT)
    child_transcript = _brain(tmp_path, CHILD)
    _write(parent_transcript, _parent_rows(tmp_path))
    _write(
        child_transcript,
        [
            {
                "step_index": 0,
                "source": "MODEL",
                "type": "PLANNER_RESPONSE",
                "status": "DONE",
                "created_at": "2026-09-02T01:00:05Z",
                "content": "child planner reply",
            }
        ],
    )
    payload = {
        "conversationId": PARENT,
        "workspacePaths": [str(workspace.resolve())],
        "transcriptPath": str(parent_transcript),
        "stepIdx": 9,
        "toolCall": {"name": "schedule", "args": {"Action": "run"}},
        "error": "",
    }
    events = antigravity_hook_to_content_events(
        payload,
        hook_event="PostToolUse",
        store=FullFidelityContentStore(tmp_path / "store"),
        timestamp="2026-09-02T01:00:04Z",
    )
    assigned = [event for event in events if event["relation"] == "ASSIGNED_AGENT_TASK"]
    assert len(assigned) == 1
    child = assigned[0]["target"]
    assert child["id"] == f"agent:antigravity:conversation:{CHILD}"
    assert child["attributes"]["parent_agent_path"] == ROOT_PATH
    assert child["attributes"]["parent_scope_id"] == PARENT
    assert "child_agent_path" not in child["attributes"]
    assert child["attributes"]["agent_nickname"] == "security reviewer"


def test_projection_fallback_stamps_role_path_when_graph_has_no_parent(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    store = FullFidelityContentStore(run_root)
    parent_transcript = _brain(tmp_path, PARENT)
    child_transcript = _brain(tmp_path, CHILD)
    _write(parent_transcript, _parent_rows(tmp_path))
    _write(
        child_transcript,
        [
            {
                "step_index": 0,
                "source": "MODEL",
                "type": "PLANNER_RESPONSE",
                "status": "DONE",
                "created_at": "2026-09-02T01:00:05Z",
                "content": "child planner reply",
            }
        ],
    )
    graph = GraphAccumulator(session_id="agy-role-fallback", source_path=run_root / "events.jsonl")
    for conversation_id, path in ((PARENT, parent_transcript), (CHILD, child_transcript)):
        payload = {
            "conversationId": conversation_id,
            "workspacePaths": [str(tmp_path.resolve())],
            "transcriptPath": str(path),
            "executionNum": 1,
            "terminationReason": "done",
            "fullyIdle": True,
        }
        for event in antigravity_hook_to_content_events(
            payload,
            hook_event="Stop",
            store=store,
            timestamp="2026-09-02T01:03:00Z",
        ):
            graph.apply(event)
    materialized = graph.to_dict()
    child_node = next(
        node
        for node in materialized["nodes"]
        if node["id"] == f"agent:antigravity:conversation:{CHILD}"
    )
    assert child_node["attributes"]["parent_agent_path"] == ROOT_PATH
    assert "child_agent_path" not in child_node["attributes"]

    for node in materialized["nodes"]:
        attrs = node.get("attributes")
        if not isinstance(attrs, dict):
            continue
        for key in (
            "parent_agent_path",
            "parent_scope_id",
            "parent_relation_source",
            "child_agent_path",
            "agent_role",
        ):
            attrs.pop(key, None)

    entries = conversation_record_entries(materialized, run_root)
    child_entry = next(
        entry
        for entry in entries
        if entry.get("source_id") == f"agent:antigravity:conversation:{CHILD}"
        and isinstance(entry.get("conversation_preview"), dict)
    )
    preview = child_entry["conversation_preview"]
    assert preview["agent_path"] == CHILD_PATH
    assert preview["is_root"] is False
    assert preview["agent_path_source"] == PATH_EXECWEAVE_DERIVED
    assert preview["topology_evidence"] == EVIDENCE_VALIDATED_CHILD_TRANSCRIPT
    texts = [message.get("text") for message in preview["messages"]]
    assert "inspect authentication paths" in texts
    assert "child planner reply" in texts
    task = next(message for message in preview["messages"] if message.get("text") == "inspect authentication paths")
    assert task["recipient"] == CHILD_PATH
    assert task["content_role"] == "antigravity_addressed_task"
    reply = next(message for message in preview["messages"] if message.get("text") == "child planner reply")
    assert reply["sender"] == CHILD_PATH


def test_transcript_links_abstain_when_pair_is_ambiguous() -> None:
    spec = _spec()
    request = {
        "source": "MODEL",
        "type": "PLANNER_RESPONSE",
        "status": "DONE",
        "tool_calls": [{"name": "invoke_subagent", "args": {"Subagents": [spec]}}],
    }
    result = {
        "source": "MODEL",
        "type": "GENERIC",
        "status": "DONE",
        "content": "Created the following subagents:\n"
        + json.dumps({"conversationId": CHILD, "logAbsoluteUri": "file:///tmp/x"}),
    }
    assert transcript_subagent_links([request, result, request, result], parent_id=PARENT) == []
    unique = transcript_subagent_links([request, result], parent_id=PARENT)
    assert len(unique) == 1
    assert unique[0]["conversation_id"] == CHILD
    assert unique[0]["agent_path"] == CHILD_PATH
