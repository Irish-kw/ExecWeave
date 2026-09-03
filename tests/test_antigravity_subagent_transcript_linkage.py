from __future__ import annotations

import json
from pathlib import Path

from execweave.antigravity_full_fidelity import antigravity_hook_to_content_events
from execweave.content_store import FullFidelityContentStore


def _subagent(prompt: str, workspace: str = "inherit") -> dict:
    return {
        "Prompt": prompt,
        "Role": "security reviewer",
        "TypeName": "research",
        "Workspace": workspace,
    }


def _layout(tmp_path: Path, *, parent_id: str = "parent-conversation") -> tuple[Path, Path]:
    workspace = (tmp_path / "workspace").resolve()
    workspace.mkdir(exist_ok=True)
    transcript = (
        tmp_path
        / "antigravity-cli"
        / "brain"
        / parent_id
        / ".system_generated"
        / "logs"
        / "transcript_full.jsonl"
    )
    transcript.parent.mkdir(parents=True, exist_ok=True)
    return workspace, transcript


def _child_result(
    tmp_path: Path,
    child_id: str,
    *,
    workspace: Path | None,
    uri_child_id: str | None = None,
) -> dict:
    uri_id = uri_child_id or child_id
    child_transcript = (
        tmp_path
        / "antigravity-cli"
        / "brain"
        / uri_id
        / ".system_generated"
        / "logs"
        / "transcript_full.jsonl"
    )
    result = {
        "conversationId": child_id,
        "logAbsoluteUri": child_transcript.resolve().as_uri(),
    }
    if workspace is not None:
        result["workspaceUris"] = [workspace.as_uri()]
    return result


def _pair(subagents: list[dict], results: list[dict]) -> list[dict]:
    content = "Created the following subagents:\n" + "\n".join(
        json.dumps(result, sort_keys=True) for result in results
    )
    return [
        {
            "step_index": 7,
            "source": "MODEL",
            "type": "PLANNER_RESPONSE",
            "status": "DONE",
            "tool_calls": [
                {
                    "name": "invoke_subagent",
                    "args": {"Subagents": subagents},
                }
            ],
        },
        {
            "step_index": 8,
            "source": "MODEL",
            "type": "INVOKE_SUBAGENT",
            "status": "DONE",
            "content": content,
        },
    ]


def _write_transcript(
    transcript: Path,
    records: list[dict],
    *,
    newline: bool = True,
) -> None:
    text = "\n".join(json.dumps(record, sort_keys=True) for record in records)
    if newline:
        text += "\n"
    transcript.write_text(text, encoding="utf-8")


def _payload(
    workspace: Path,
    transcript: Path,
    subagents: list[dict],
    *,
    parent_id: str = "parent-conversation",
) -> dict:
    return {
        "conversationId": parent_id,
        "workspacePaths": [str(workspace)],
        "transcriptPath": str(transcript),
        "artifactDirectoryPath": str(transcript.parents[3]),
        "modelName": "agy-test",
        "stepIdx": 7,
        "error": "",
        "toolCall": {
            "name": "invoke_subagent",
            "args": {"Subagents": subagents},
        },
    }


def _events(payload: dict, tmp_path: Path) -> list[dict]:
    return antigravity_hook_to_content_events(
        payload,
        hook_event="PostToolUse",
        store=FullFidelityContentStore(tmp_path / "store"),
        timestamp="2026-08-28T00:00:00Z",
    )


def _assignments(events: list[dict]) -> list[dict]:
    return [event for event in events if event["relation"] == "ASSIGNED_AGENT_TASK"]


def test_antigravity_transcript_single_child_exact_join(tmp_path: Path) -> None:
    workspace, transcript = _layout(tmp_path)
    subagents = [_subagent("inspect authentication paths")]
    _write_transcript(
        transcript,
        _pair(
            subagents,
            [_child_result(tmp_path, "child-a", workspace=workspace)],
        ),
    )

    events = _events(_payload(workspace, transcript, subagents), tmp_path)
    requested = next(event for event in events if event["relation"] == "REQUESTED_SUBTASK")
    assigned = _assignments(events)

    assert len(assigned) == 1
    assert assigned[0]["source"]["id"] == requested["target"]["id"]
    assert assigned[0]["target"]["id"] == "agent:antigravity:conversation:child-a"
    assert assigned[0]["attributes"]["provider_child_identity_exact"] is True


def test_antigravity_transcript_multi_child_uses_provider_order(tmp_path: Path) -> None:
    workspace, transcript = _layout(tmp_path)
    subagents = [_subagent("inspect auth"), _subagent("inspect storage")]
    results = [
        _child_result(tmp_path, "child-a", workspace=workspace),
        _child_result(tmp_path, "child-b", workspace=workspace),
    ]
    _write_transcript(transcript, _pair(subagents, results))

    assigned = _assignments(_events(_payload(workspace, transcript, subagents), tmp_path))

    assert [event["source"]["attributes"]["subagent_index"] for event in assigned] == [0, 1]
    assert [event["target"]["attributes"]["conversation_id"] for event in assigned] == [
        "child-a",
        "child-b",
    ]


def test_antigravity_transcript_count_mismatch_abstains(tmp_path: Path) -> None:
    workspace, transcript = _layout(tmp_path)
    subagents = [_subagent("one"), _subagent("two")]
    _write_transcript(
        transcript,
        _pair(subagents, [_child_result(tmp_path, "child-a", workspace=workspace)]),
    )

    events = _events(_payload(workspace, transcript, subagents), tmp_path)

    assert not _assignments(events)
    assert len([event for event in events if event["relation"] == "REQUESTED_SUBTASK"]) == 2


def test_antigravity_transcript_duplicate_child_abstains(tmp_path: Path) -> None:
    workspace, transcript = _layout(tmp_path)
    subagents = [_subagent("one"), _subagent("two")]
    child = _child_result(tmp_path, "child-a", workspace=workspace)
    _write_transcript(transcript, _pair(subagents, [child, child]))

    assert not _assignments(_events(_payload(workspace, transcript, subagents), tmp_path))


def test_antigravity_transcript_parent_equals_child_abstains(tmp_path: Path) -> None:
    workspace, transcript = _layout(tmp_path)
    subagents = [_subagent("one")]
    _write_transcript(
        transcript,
        _pair(
            subagents,
            [_child_result(tmp_path, "parent-conversation", workspace=workspace)],
        ),
    )

    assert not _assignments(_events(_payload(workspace, transcript, subagents), tmp_path))


def test_antigravity_transcript_mismatched_log_uri_abstains(tmp_path: Path) -> None:
    workspace, transcript = _layout(tmp_path)
    subagents = [_subagent("one")]
    _write_transcript(
        transcript,
        _pair(
            subagents,
            [
                _child_result(
                    tmp_path,
                    "child-a",
                    workspace=workspace,
                    uri_child_id="different-child",
                )
            ],
        ),
    )

    assert not _assignments(_events(_payload(workspace, transcript, subagents), tmp_path))


def test_antigravity_transcript_noncanonical_log_uri_abstains(tmp_path: Path) -> None:
    workspace, transcript = _layout(tmp_path)
    subagents = [_subagent("one")]
    result = _child_result(tmp_path, "child-a", workspace=workspace)
    result["logAbsoluteUri"] += "#fragment"
    _write_transcript(transcript, _pair(subagents, [result]))

    assert not _assignments(_events(_payload(workspace, transcript, subagents), tmp_path))


def test_antigravity_transcript_workspace_mismatch_abstains(tmp_path: Path) -> None:
    workspace, transcript = _layout(tmp_path)
    other = (tmp_path / "other-workspace").resolve()
    other.mkdir()
    subagents = [_subagent("one")]
    _write_transcript(
        transcript,
        _pair(subagents, [_child_result(tmp_path, "child-a", workspace=other)]),
    )

    assert not _assignments(_events(_payload(workspace, transcript, subagents), tmp_path))


def test_antigravity_transcript_torn_write_abstains(tmp_path: Path) -> None:
    workspace, transcript = _layout(tmp_path)
    subagents = [_subagent("one")]
    _write_transcript(
        transcript,
        _pair(subagents, [_child_result(tmp_path, "child-a", workspace=workspace)]),
        newline=False,
    )

    events = _events(_payload(workspace, transcript, subagents), tmp_path)

    assert any(event["relation"] == "REQUESTED_SUBTASK" for event in events)
    assert not _assignments(events)


def test_antigravity_transcript_ambiguous_pair_abstains(tmp_path: Path) -> None:
    workspace, transcript = _layout(tmp_path)
    subagents = [_subagent("one")]
    pair = _pair(subagents, [_child_result(tmp_path, "child-a", workspace=workspace)])
    _write_transcript(transcript, pair + pair)

    assert not _assignments(_events(_payload(workspace, transcript, subagents), tmp_path))


def test_antigravity_no_transcript_keeps_request_only_evidence(tmp_path: Path) -> None:
    workspace, transcript = _layout(tmp_path)
    subagents = [_subagent("one")]

    events = _events(_payload(workspace, transcript, subagents), tmp_path)

    assert any(event["relation"] == "REQUESTED_SUBTASK" for event in events)
    assert not _assignments(events)


def test_antigravity_transcript_does_not_use_timing_to_bridge_records(tmp_path: Path) -> None:
    workspace, transcript = _layout(tmp_path)
    subagents = [_subagent("one")]
    records = _pair(subagents, [_child_result(tmp_path, "child-a", workspace=workspace)])
    records.insert(
        1,
        {
            "step_index": 100,
            "source": "SYSTEM",
            "type": "CHECKPOINT",
            "status": "DONE",
        },
    )
    _write_transcript(transcript, records)

    assert not _assignments(_events(_payload(workspace, transcript, subagents), tmp_path))


def test_antigravity_parent_result_does_not_claim_child_lifecycle(tmp_path: Path) -> None:
    workspace, transcript = _layout(tmp_path)
    subagents = [_subagent("one")]
    _write_transcript(
        transcript,
        _pair(subagents, [_child_result(tmp_path, "child-a", workspace=workspace)]),
    )

    events = _events(_payload(workspace, transcript, subagents), tmp_path)
    assigned = _assignments(events)[0]
    relations = {event["relation"] for event in events}

    assert assigned["attributes"]["timing_inference_used"] is False
    assert assigned["attributes"]["child_lifecycle_inferred"] is False
    assert assigned["attributes"]["child_lifecycle_authority"] == "child_provider_hooks"
    assert assigned["target"]["attributes"]["execution_observed"] is False
    assert assigned["target"]["attributes"]["lifecycle_authority"] == "child_provider_hooks"
    assert "SPAWNED_AGENT" not in relations
    assert "RETURNED_AGENT_RESULT" not in relations
    assert "CLOSED_AGENT" not in relations
    serialized = json.dumps(assigned, sort_keys=True)
    assert "transcriptPath" not in serialized
    assert "logAbsoluteUri" not in serialized
