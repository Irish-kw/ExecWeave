from __future__ import annotations

import io
import json
import sys

from execweave.antigravity_hook_cli import main as antigravity_hook_main


def test_antigravity_preinvocation_cli_emits_transcript_aware_visibility(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    sidecar = tmp_path / "semantic.jsonl"
    monkeypatch.setenv("EXECWEAVE_SEMANTIC_SIDECAR", str(sidecar))
    payload = {
        "invocationNum": 3,
        "initialNumSteps": 10,
        "conversationId": "conversation-1",
        "workspacePaths": [str(tmp_path)],
        "transcriptPath": str(tmp_path / "transcript.jsonl"),
        "artifactDirectoryPath": str(tmp_path / "artifacts"),
        "modelName": "agy-test",
    }
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))

    assert antigravity_hook_main(["--event", "PreInvocation", "--strict"]) == 0

    captured = capsys.readouterr()
    assert json.loads(captured.out) == {}
    assert captured.err == ""
    records = [json.loads(line) for line in sidecar.read_text().splitlines()]
    visibility = next(
        record
        for record in records
        if record["relation"] == "DECLARES_AGENT_TRACE_VISIBILITY"
    )
    capability = visibility["target"]["attributes"]
    assert capability["agent_identity_visibility"] == (
        "provider_exposed_validated_transcript_child_identity"
    )
    assert capability["subagent_visibility"] == (
        "provider_exposed_request_and_validated_assignment_only"
    )
    assert capability["child_lifecycle_visibility"] == "provider_child_hooks_only"
    assert capability["reasoning_visibility"] == "not_exposed_by_source"
    assert capability["transcript_linkage_semantics"] == "live_verified_implementation_wire"
