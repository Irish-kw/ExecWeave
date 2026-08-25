from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from execweave.correlation import correlate_tool_process
from execweave.schema import SCHEMA_VERSION


def test_canonical_path_identity_matches_symlinked_cmdline(tmp_path: Path) -> None:
    real = tmp_path / "python3.12"
    alias = tmp_path / "python"
    real.write_text("placeholder", encoding="utf-8")
    try:
        os.symlink(real, alias)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not available in this environment")

    agent = {"type": "agent", "id": "agent:Claude Code", "name": "Claude Code", "attributes": {}}
    session = {"type": "session", "id": "session:path", "name": "path", "attributes": {}}
    call = {"type": "tool_call", "id": "tool-call:path", "name": "Bash", "attributes": {}}
    command = {
        "type": "command",
        "id": "command:path",
        "name": "python",
        "attributes": {"command": f'"{real}" task.py'},
    }
    process = {
        "type": "process",
        "id": "process:path:1",
        "name": "python",
        "attributes": {"pid": 201, "cmdline": [str(alias), "task.py"], "exe": None},
    }

    def event(sequence, timestamp, event_type, relation, source, target=None):
        return {
            "schema_version": SCHEMA_VERSION,
            "event_id": f"path-event-{sequence}",
            "session_id": "path",
            "timestamp": timestamp,
            "event_type": event_type,
            "relation": relation,
            "source": source,
            "target": target,
            "sequence": sequence,
            "attributes": {},
        }

    events = [
        event(1, "2026-08-25T00:00:00Z", "session.started", "STARTED_SESSION", agent, session),
        event(2, "2026-08-25T00:00:01Z", "semantic.claude.command.declared", "DECLARED_COMMAND", call, command),
        event(3, "2026-08-25T00:00:01.100Z", "process.started", "SPAWNED", session, process),
        event(4, "2026-08-25T00:00:03Z", "session.finished", "FINISHED_SESSION", session),
    ]
    source = tmp_path / "merged.jsonl"
    output = tmp_path / "correlated.jsonl"
    source.write_text(
        "".join(json.dumps(item, sort_keys=True) + "\n" for item in events),
        encoding="utf-8",
    )

    result = correlate_tool_process(source, output)

    assert result.correlated_tool_calls == 1
    inference = next(
        json.loads(line)
        for line in output.read_text(encoding="utf-8").splitlines()
        if "CORRELATED_WITH_PROCESS" in line
    )
    assert inference["target"]["id"] == process["id"]
    assert inference["attributes"]["inference_method"] == "unique_process_cmdline_match"
    assert inference["attributes"]["causal"] is False
    assert inference["attributes"]["inferred"] is True
