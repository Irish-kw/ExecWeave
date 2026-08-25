from __future__ import annotations

import json
from pathlib import Path

from execweave.correlation import correlate_tool_process
from execweave.graph import build_execution_graph
from execweave.schema import SCHEMA_VERSION
from execweave.validate import validate_event_stream


def _entity(entity_type: str, entity_id: str, name: str, attributes=None):
    return {"type": entity_type, "id": entity_id, "name": name, "attributes": attributes or {}}


def _event(
    sequence: int,
    timestamp: str,
    event_type: str,
    relation: str,
    source,
    target=None,
    attributes=None,
):
    return {
        "schema_version": SCHEMA_VERSION,
        "event_id": f"event-{sequence}",
        "session_id": "s1",
        "timestamp": timestamp,
        "event_type": event_type,
        "relation": relation,
        "source": source,
        "target": target,
        "sequence": sequence,
        "attributes": attributes or {},
    }


def _write(path: Path, events: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(event, sort_keys=True) + "\n" for event in events),
        encoding="utf-8",
    )


def _base(command: str) -> tuple[list[dict], dict, dict, dict]:
    agent = _entity("agent", "agent:Claude Code", "Claude Code")
    session = _entity("session", "session:s1", "s1")
    call = _entity("tool_call", "tool-call:1", "Bash")
    command_entity = _entity("command", "command:1", command, {"command": command})
    events = [
        _event(1, "2026-08-25T00:00:00Z", "session.started", "STARTED_SESSION", agent, session),
        _event(
            2,
            "2026-08-25T00:00:01Z",
            "semantic.claude.command.declared",
            "DECLARED_COMMAND",
            call,
            command_entity,
            {"backend": "semantic", "causal": False},
        ),
    ]
    return events, session, call, command_entity


def _finish(events: list[dict], session: dict, sequence: int, timestamp="2026-08-25T00:00:04Z"):
    events.append(_event(sequence, timestamp, "session.finished", "FINISHED_SESSION", session))


def test_unique_portable_cmdline_match_creates_inferred_noncausal_edge(tmp_path: Path) -> None:
    events, session, _, _ = _base("python task.py")
    process = _entity(
        "process",
        "process:42:1",
        "python",
        {"pid": 42, "cmdline": ["/usr/bin/python", "task.py"]},
    )
    events.append(
        _event(
            3,
            "2026-08-25T00:00:01.100Z",
            "process.started",
            "SPAWNED",
            session,
            process,
            {"backend": "portable", "attribution": "polling", "causal": False},
        )
    )
    _finish(events, session, 4)
    source = tmp_path / "merged.jsonl"
    output = tmp_path / "correlated.jsonl"
    _write(source, events)

    result = correlate_tool_process(source, output)

    assert result.correlated_tool_calls == 1
    assert result.skipped_ambiguous == 0
    assert validate_event_stream(output).valid is True
    correlated = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    inference = next(event for event in correlated if event["relation"] == "CORRELATED_WITH_PROCESS")
    assert inference["source"]["id"] == "tool-call:1"
    assert inference["target"]["id"] == process["id"]
    assert inference["attributes"]["causal"] is False
    assert inference["attributes"]["inferred"] is True
    assert inference["attributes"]["inference_method"] == "unique_process_cmdline_match"
    assert inference["attributes"]["confidence_semantics"] == "heuristic_score_not_probability"

    graph = build_execution_graph(output).to_dict()
    edge = next(edge for edge in graph["edges"] if edge["relation"] == "CORRELATED_WITH_PROCESS")
    assert edge["inferred"] is True
    assert edge["causal"] is False
    assert edge["inference_methods"] == ["unique_process_cmdline_match"]
    assert edge["confidence_min"] == 0.8
    assert edge["confidence_max"] == 0.8
    assert "event-2" in edge["supporting_event_ids"]
    assert "event-3" in edge["supporting_event_ids"]


def test_unique_strace_exec_match_creates_bridge(tmp_path: Path) -> None:
    events, session, _, _ = _base("npm test")
    process = _entity("process", "process:s1:51", "51", {"pid": 51})
    executable = _entity("executable", "executable:/usr/bin/npm", "npm")
    events.extend(
        [
            _event(
                3,
                "2026-08-25T00:00:01.050Z",
                "process.started",
                "SPAWNED",
                session,
                process,
                {"backend": "strace", "attribution": "syscall", "causal": True},
            ),
            _event(
                4,
                "2026-08-25T00:00:01.060Z",
                "process.exec",
                "EXECUTED",
                process,
                executable,
                {"backend": "strace", "attribution": "syscall", "causal": True},
            ),
        ]
    )
    _finish(events, session, 5)
    source = tmp_path / "merged.jsonl"
    output = tmp_path / "correlated.jsonl"
    _write(source, events)

    result = correlate_tool_process(source, output)

    assert result.correlated_tool_calls == 1
    inference = next(
        json.loads(line)
        for line in output.read_text(encoding="utf-8").splitlines()
        if "CORRELATED_WITH_PROCESS" in line
    )
    assert inference["target"]["id"] == process["id"]
    assert inference["attributes"]["inference_method"] == "unique_exec_basename_match"
    assert inference["attributes"]["confidence"] == 0.9


def test_ambiguous_matching_processes_emit_no_bridge(tmp_path: Path) -> None:
    events, session, _, _ = _base("python task.py")
    for sequence, pid, timestamp in (
        (3, 61, "2026-08-25T00:00:01.100Z"),
        (4, 62, "2026-08-25T00:00:01.200Z"),
    ):
        process = _entity(
            "process",
            f"process:{pid}:1",
            "python",
            {"pid": pid, "cmdline": ["python", "task.py"]},
        )
        events.append(
            _event(
                sequence,
                timestamp,
                "process.started",
                "SPAWNED",
                session,
                process,
                {"backend": "portable"},
            )
        )
    _finish(events, session, 5)
    source = tmp_path / "merged.jsonl"
    output = tmp_path / "correlated.jsonl"
    _write(source, events)

    result = correlate_tool_process(source, output)

    assert result.correlated_tool_calls == 0
    assert result.skipped_ambiguous == 1
    assert "CORRELATED_WITH_PROCESS" not in output.read_text(encoding="utf-8")


def test_shell_builtin_and_compound_command_are_not_correlated(tmp_path: Path) -> None:
    for command in ("echo hello", "cd repo && python task.py"):
        events, session, _, _ = _base(command)
        process = _entity(
            "process",
            "process:77:1",
            "python",
            {"pid": 77, "cmdline": ["python", "task.py"]},
        )
        events.append(
            _event(
                3,
                "2026-08-25T00:00:01.100Z",
                "process.started",
                "SPAWNED",
                session,
                process,
                {"backend": "portable"},
            )
        )
        _finish(events, session, 4)
        source = tmp_path / f"{len(command)}.jsonl"
        output = tmp_path / f"{len(command)}.out.jsonl"
        _write(source, events)
        result = correlate_tool_process(source, output)
        assert result.correlated_tool_calls == 0
        assert result.skipped_unsupported == 1


def test_next_tool_call_clips_matching_window(tmp_path: Path) -> None:
    events, session, _, _ = _base("python first.py")
    second_call = _entity("tool_call", "tool-call:2", "Bash")
    second_command = _entity(
        "command",
        "command:2",
        "python second.py",
        {"command": "python second.py"},
    )
    events.append(
        _event(
            3,
            "2026-08-25T00:00:01.200Z",
            "semantic.claude.command.declared",
            "DECLARED_COMMAND",
            second_call,
            second_command,
            {"backend": "semantic", "causal": False},
        )
    )
    process = _entity(
        "process",
        "process:88:1",
        "python",
        {"pid": 88, "cmdline": ["python", "second.py"]},
    )
    events.append(
        _event(
            4,
            "2026-08-25T00:00:01.300Z",
            "process.started",
            "SPAWNED",
            session,
            process,
            {"backend": "portable"},
        )
    )
    _finish(events, session, 5)
    source = tmp_path / "merged.jsonl"
    output = tmp_path / "correlated.jsonl"
    _write(source, events)

    result = correlate_tool_process(source, output)

    assert result.tool_calls_considered == 2
    assert result.correlated_tool_calls == 1
    assert result.skipped_no_match == 1
    inference = next(
        json.loads(line)
        for line in output.read_text(encoding="utf-8").splitlines()
        if "CORRELATED_WITH_PROCESS" in line
    )
    assert inference["source"]["id"] == "tool-call:2"
