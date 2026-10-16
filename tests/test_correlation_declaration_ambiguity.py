from __future__ import annotations

import json
from pathlib import Path

from execweave.correlation import correlate_tool_process
from execweave.schema import SCHEMA_VERSION

_START = "2026-08-25T00:00:00Z"
_FINISH = "2026-08-25T00:00:09Z"


def _entity(entity_type: str, entity_id: str, name: str, attributes=None) -> dict:
    return {"type": entity_type, "id": entity_id, "name": name, "attributes": attributes or {}}


def _event(sequence, timestamp, event_type, relation, source, target=None, attributes=None):
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


class _Stream:
    def __init__(self) -> None:
        self.session = _entity("session", "session:s1", "s1")
        agent = _entity("agent", "agent:root", "root")
        self.events = [_event(1, _START, "session.started", "STARTED_SESSION", agent, self.session)]

    def declare(self, call_id: str, timestamp: str, command: str) -> None:
        self.events.append(
            _event(
                len(self.events) + 1,
                timestamp,
                "semantic.command.declared",
                "DECLARED_COMMAND",
                _entity("tool_call", call_id, "Bash"),
                _entity("command", f"command:{call_id}", command, {"command": command}),
                {"backend": "semantic", "causal": False},
            )
        )

    def process(self, pid: int, timestamp: str, cmdline: list[str], exe: str | None = None) -> str:
        process_id = f"process:{pid}:1"
        attributes = {"pid": pid, "cmdline": cmdline}
        if exe is not None:
            attributes["exe"] = exe
        self.events.append(
            _event(
                len(self.events) + 1,
                timestamp,
                "process.started",
                "SPAWNED",
                self.session,
                _entity("process", process_id, cmdline[0], attributes),
                {"backend": "portable", "attribution": "polling", "causal": False},
            )
        )
        return process_id

    def correlate(self, tmp_path: Path):
        self.events.append(
            _event(
                len(self.events) + 1, _FINISH, "session.finished", "FINISHED_SESSION", self.session
            )
        )
        source = tmp_path / "merged.jsonl"
        output = tmp_path / "correlated.jsonl"
        source.write_text(
            "".join(json.dumps(event, sort_keys=True) + "\n" for event in self.events),
            encoding="utf-8",
        )
        result = correlate_tool_process(source, output)
        bridges = [
            json.loads(line)
            for line in output.read_text(encoding="utf-8").splitlines()
            if "CORRELATED_WITH_PROCESS" in line
        ]
        return result, bridges


def test_declarations_sharing_a_timestamp_do_not_both_claim_one_process(tmp_path: Path) -> None:
    stream = _Stream()
    stream.declare("tool-call:a", "2026-08-25T00:00:01Z", "python task.py")
    stream.declare("tool-call:b", "2026-08-25T00:00:01Z", "python task.py")
    stream.process(41, "2026-08-25T00:00:01.100Z", ["python", "task.py"])

    result, bridges = stream.correlate(tmp_path)

    assert bridges == []
    assert result.correlated_tool_calls == 0
    assert result.skipped_ambiguous == 2


def test_tied_declarations_are_still_bounded_by_the_next_later_declaration(
    tmp_path: Path,
) -> None:
    stream = _Stream()
    stream.declare("tool-call:a", "2026-08-25T00:00:01Z", "python a.py")
    stream.declare("tool-call:b", "2026-08-25T00:00:01Z", "node b.js")
    stream.declare("tool-call:c", "2026-08-25T00:00:01.200Z", "python c.py")
    process_id = stream.process(42, "2026-08-25T00:00:01.300Z", ["python", "c.py"])

    result, bridges = stream.correlate(tmp_path)

    assert [(bridge["source"]["id"], bridge["target"]["id"]) for bridge in bridges] == [
        ("tool-call:c", process_id)
    ]
    assert result.correlated_tool_calls == 1


def test_process_on_a_shared_window_boundary_is_not_claimed(tmp_path: Path) -> None:
    stream = _Stream()
    stream.declare("tool-call:a", "2026-08-25T00:00:01Z", "python task.py")
    stream.declare("tool-call:b", "2026-08-25T00:00:01.200Z", "python task.py")
    stream.process(43, "2026-08-25T00:00:01.200Z", ["python", "task.py"])

    result, bridges = stream.correlate(tmp_path)

    assert bridges == []
    assert result.skipped_ambiguous == 2


def test_option_only_argument_tail_does_not_match_another_program(tmp_path: Path) -> None:
    stream = _Stream()
    stream.declare("tool-call:a", "2026-08-25T00:00:01Z", "node -v")
    stream.process(44, "2026-08-25T00:00:01.100Z", ["python3", "-v"], exe="/usr/bin/python3")

    result, bridges = stream.correlate(tmp_path)

    assert bridges == []
    assert result.skipped_no_match == 1


def test_argument_tail_with_an_operand_still_matches_an_interpreter_alias(
    tmp_path: Path,
) -> None:
    stream = _Stream()
    stream.declare("tool-call:a", "2026-08-25T00:00:01Z", "python3.12 -u script.py")
    process_id = stream.process(
        45,
        "2026-08-25T00:00:01.100Z",
        ["/opt/framework/Python", "-u", "script.py"],
        exe="/opt/framework/Python",
    )

    result, bridges = stream.correlate(tmp_path)

    assert [bridge["target"]["id"] for bridge in bridges] == [process_id]
    assert bridges[0]["attributes"]["inference_method"] == "unique_process_argv_tail_match"
    assert result.correlated_tool_calls == 1
