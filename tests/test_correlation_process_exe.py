from __future__ import annotations

import json
from pathlib import Path

from execweave.correlation import correlate_tool_process
from execweave.schema import SCHEMA_VERSION


def _event(sequence: int, timestamp: str, event_type: str, relation: str, source, target=None):
    return {
        "schema_version": SCHEMA_VERSION,
        "event_id": f"exe-event-{sequence}",
        "session_id": "exe-session",
        "timestamp": timestamp,
        "event_type": event_type,
        "relation": relation,
        "source": source,
        "target": target,
        "sequence": sequence,
        "attributes": {},
    }


def test_portable_process_exe_matches_resolved_binary_when_cmdline_uses_symlink(
    tmp_path: Path,
) -> None:
    agent = {"type": "agent", "id": "agent:Claude Code", "name": "Claude Code", "attributes": {}}
    session = {"type": "session", "id": "session:exe-session", "name": "exe-session", "attributes": {}}
    call = {"type": "tool_call", "id": "tool-call:exe", "name": "Bash", "attributes": {}}
    command = {
        "type": "command",
        "id": "command:exe",
        "name": "python3.12 task.py",
        "attributes": {"command": '"/opt/python/bin/python3.12" task.py'},
    }
    process = {
        "type": "process",
        "id": "process:exe:1",
        "name": "python",
        "attributes": {
            "pid": 101,
            "cmdline": ["/opt/python/bin/python", "task.py"],
            "exe": "/opt/python/bin/python3.12",
        },
    }
    events = [
        _event(1, "2026-08-25T00:00:00Z", "session.started", "STARTED_SESSION", agent, session),
        _event(
            2,
            "2026-08-25T00:00:01Z",
            "semantic.claude.command.declared",
            "DECLARED_COMMAND",
            call,
            command,
        ),
        _event(
            3,
            "2026-08-25T00:00:01.100Z",
            "process.started",
            "SPAWNED",
            session,
            process,
        ),
        _event(4, "2026-08-25T00:00:03Z", "session.finished", "FINISHED_SESSION", session),
    ]
    source = tmp_path / "merged.jsonl"
    output = tmp_path / "correlated.jsonl"
    source.write_text(
        "".join(json.dumps(event, sort_keys=True) + "\n" for event in events),
        encoding="utf-8",
    )

    result = correlate_tool_process(source, output)

    assert result.correlated_tool_calls == 1
    correlated = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    inference = next(event for event in correlated if event["relation"] == "CORRELATED_WITH_PROCESS")
    assert inference["target"]["id"] == process["id"]
    assert inference["attributes"]["inference_method"] == "unique_process_exe_match"
    assert inference["attributes"]["confidence"] == 0.85
    assert inference["attributes"]["causal"] is False
    assert inference["attributes"]["inferred"] is True
