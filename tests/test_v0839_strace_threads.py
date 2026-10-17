"""v0.8.39: native Linux thread groups are not processes."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from execweave.sink import JsonlSink
from execweave.strace_backend import StraceParser, TraceRecord


def _parse(tmp_path: Path, records: list[TraceRecord]) -> list[dict]:
    output = tmp_path / "events.jsonl"
    StraceParser(
        session_id="thread-fixture", sink=JsonlSink(output),
        watch_root=tmp_path, command=["python", "fixture.py"],
    ).parse(records)
    return [json.loads(line) for line in output.read_text().splitlines()]


@pytest.mark.parametrize("syscall", ["clone", "clone3"])
def test_thread_group_preserves_actual_subprocess_parent(tmp_path: Path, syscall: str) -> None:
    if syscall == "clone":
        thread_call = "clone(child_stack=NULL, flags=CLONE_VM|CLONE_THREAD|CLONE_SIGHAND) = 402"
    else:
        thread_call = (
            "clone3({flags=CLONE_VM|CLONE_THREAD|CLONE_SIGHAND, "
            "exit_signal=0, stack=NULL}, 88) = 402"
        )
    records = [
        TraceRecord(100.0, 401, thread_call),
        TraceRecord(100.1, 402, "clone(child_stack=NULL, flags=SIGCHLD) = 403"),
        TraceRecord(100.2, 403, 'openat(AT_FDCWD, "marker.txt", O_WRONLY|O_CREAT, 0666) = 3'),
        TraceRecord(100.3, 402, "+++ exited with 0 +++"),
        TraceRecord(100.4, 403, "+++ exited with 0 +++"),
    ]
    events = _parse(tmp_path, records)
    starts = [e for e in events if e["event_type"] == "process.started"]
    assert not any(e["target"]["id"] == "process:thread-fixture:402" for e in starts)
    child = next(e for e in starts if e["target"]["id"] == "process:thread-fixture:403")
    assert child["source"]["id"] == "process:thread-fixture:401"
    assert child["attributes"]["spawn_origin_tid"] == 402
    threads = [e for e in events if e["event_type"] == "thread.started"]
    assert len(threads) == 1
    assert threads[0]["target"]["attributes"]["tgid"] == 401
    assert any(e["event_type"] == "thread.exited" for e in events)
    assert not any(e["event_type"] == "process.exited" and
                   e["source"]["id"] == "process:thread-fixture:402" for e in events)
    opened = next(e for e in events if e["relation"] == "OPENED_WRITE")
    assert opened["source"]["id"] == "process:thread-fixture:403"


def test_equal_timestamp_thread_record_uses_preindexed_tgid(tmp_path: Path) -> None:
    events = _parse(tmp_path, [
        TraceRecord(10.0, 502, 'openat(AT_FDCWD, "observed.txt", O_RDONLY) = 3'),
        TraceRecord(10.0, 501, "clone(flags=CLONE_VM|CLONE_THREAD, child_stack=NULL) = 502"),
    ])
    read = next(e for e in events if e["relation"] == "OPENED_READ")
    assert read["source"]["id"] == "process:thread-fixture:501"
    assert not any(e["event_type"] == "process.started" and
                   e.get("target", {}).get("id") == "process:thread-fixture:502"
                   for e in events)


@pytest.mark.parametrize("args", [
    "clone(child_stack=NULL, flags=CLONE_VM|SIGCHLD) = 602",
    "clone3({flags=CLONE_VM, exit_signal=SIGCHLD}, 88) = 602",
])
def test_non_thread_clone_remains_actual_process(tmp_path: Path, args: str) -> None:
    events = _parse(tmp_path, [TraceRecord(15.0, 601, args)])
    assert any(e["event_type"] == "process.started" and
               e.get("target", {}).get("id") == "process:thread-fixture:602" and
               e["relation"] == "SPAWNED" for e in events)
    assert not any(e["event_type"] == "thread.started" for e in events)


def test_failed_clone_does_not_invent_process_or_thread(tmp_path: Path) -> None:
    events = _parse(tmp_path, [
        TraceRecord(16.0, 701, "clone(flags=CLONE_THREAD|CLONE_VM) = -1 EAGAIN (retry)")
    ])
    assert not any(e["event_type"] == "thread.started" for e in events)
    assert not any(e["relation"] == "SPAWNED" for e in events)
