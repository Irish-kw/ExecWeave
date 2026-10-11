import json
import shutil
import sys
from pathlib import Path

import pytest

from execweave.sink import JsonlSink
from execweave.strace_backend import (
    StraceParser,
    StraceRuntimeCollector,
    TraceRecord,
    _merge_unfinished,
)


def _events(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def test_merge_unfinished_syscall() -> None:
    lines = [
        "1720000000.100000 connect(3, {sa_family=AF_INET, <unfinished ...>",
        (
            "1720000000.200000 <... connect resumed>sin_port=htons(443), "
            'sin_addr=inet_addr("1.2.3.4")}, 16) = 0'
        ),
    ]
    merged = _merge_unfinished(lines)
    assert len(merged) == 1
    assert merged[0].startswith("1720000000.100000 connect(")
    assert "1.2.3.4" in merged[0]


def test_strace_parser_builds_process_file_and_network_edges(tmp_path: Path) -> None:
    output = tmp_path / "events.jsonl"
    parser = StraceParser(
        session_id="s1",
        sink=JsonlSink(output),
        watch_root=tmp_path,
        command=["python", "agent.py"],
    )
    records = [
        TraceRecord(
            1720000000.0,
            100,
            'execve("/usr/bin/python", ["python", "agent.py"], 0x0) = 0',
        ),
        TraceRecord(1720000000.1, 100, "clone(child_stack=NULL, flags=SIGCHLD) = 101"),
        TraceRecord(
            1720000000.2,
            101,
            'openat(AT_FDCWD, "notes.txt", O_RDONLY|O_CLOEXEC) = 3</tmp/notes.txt>',
        ),
        TraceRecord(
            1720000000.3,
            101,
            (
                'openat(AT_FDCWD, "out.txt", O_WRONLY|O_CREAT|O_TRUNC, '
                "0666) = 4</tmp/out.txt>"
            ),
        ),
        TraceRecord(
            1720000000.4,
            101,
            (
                "connect(5, {sa_family=AF_INET, sin_port=htons(443), "
                'sin_addr=inet_addr("1.2.3.4")}, 16) = 0'
            ),
        ),
        TraceRecord(1720000000.5, 101, "+++ exited with 0 +++"),
    ]
    parser.parse(records)
    events = _events(output)
    relations = [event["relation"] for event in events]
    assert "LAUNCHED" in relations
    assert "EXECUTED" in relations
    assert "SPAWNED" in relations
    assert "OPENED_READ" in relations
    assert "OPENED_WRITE" in relations
    assert "CONNECTED_TO" in relations
    assert "EXITED" in relations
    file_events = [event for event in events if event["event_type"] == "filesystem.open"]
    assert all(event["attributes"]["causal"] is True for event in file_events)
    assert all(event["source"]["id"].startswith("process:s1:") for event in file_events)


def test_equal_timestamp_child_is_not_misclassified_as_root(tmp_path: Path) -> None:
    output = tmp_path / "events.jsonl"
    parser = StraceParser(
        session_id="same-ts",
        sink=JsonlSink(output),
        watch_root=tmp_path,
        command=["agent"],
    )
    # Deliberately place the child record first at the same timestamp. The parser
    # must still learn the parent relationship from clone() before emitting nodes.
    records = [
        TraceRecord(10.0, 201, 'openat(AT_FDCWD, "child.txt", O_RDONLY) = 3'),
        TraceRecord(10.0, 200, "clone(child_stack=NULL, flags=SIGCHLD) = 201"),
    ]
    parser.parse(records)
    events = _events(output)
    child_start = next(
        event
        for event in events
        if event["event_type"] == "process.started"
        and event["target"]["id"] == "process:same-ts:201"
    )
    assert child_start["relation"] == "SPAWNED"
    assert child_start["source"]["id"] == "process:same-ts:200"
    assert not any(
        event["event_type"] == "process.started"
        and event["target"]["id"] == "process:same-ts:201"
        and event["relation"] == "LAUNCHED"
        for event in events
    )


def test_nonblocking_connect_is_preserved_as_attempt(tmp_path: Path) -> None:
    output = tmp_path / "events.jsonl"
    parser = StraceParser(
        session_id="async-connect",
        sink=JsonlSink(output),
        watch_root=tmp_path,
        command=["agent"],
    )
    parser.parse(
        [
            TraceRecord(
                20.0,
                300,
                (
                    "connect(7, {sa_family=AF_INET, sin_port=htons(443), "
                    'sin_addr=inet_addr("203.0.113.10")}, 16) = '
                    "-1 EINPROGRESS (Operation now in progress)"
                ),
            )
        ]
    )
    events = _events(output)
    attempt = next(event for event in events if event["event_type"] == "network.connection_attempt")
    assert attempt["relation"] == "CONNECT_ATTEMPTED"
    assert attempt["target"]["id"] == "network_endpoint:203.0.113.10:443"
    assert attempt["attributes"]["errno"] == "EINPROGRESS"
    assert attempt["attributes"]["connected"] is False
    assert attempt["attributes"]["causal"] is True


def test_chdir_changes_relative_path_resolution(tmp_path: Path) -> None:
    output = tmp_path / "events.jsonl"
    parser = StraceParser(
        session_id="s2",
        sink=JsonlSink(output),
        watch_root=tmp_path,
        command=["agent"],
    )
    child = tmp_path / "child"
    records = [
        TraceRecord(1.0, 10, f'chdir("{child}") = 0'),
        TraceRecord(1.1, 10, 'openat(AT_FDCWD, "x.txt", O_RDONLY) = 3'),
    ]
    parser.parse(records)
    events = _events(output)
    opened = next(event for event in events if event["event_type"] == "filesystem.open")
    assert opened["target"]["id"] == f"file:{child / 'x.txt'}"


def test_strace_runtime_integration_when_available(tmp_path: Path) -> None:
    if shutil.which("strace") is None or not sys.platform.startswith("linux"):
        pytest.skip("strace integration requires Linux strace")

    output = tmp_path / "events.jsonl"
    collector = StraceRuntimeCollector(
        session_id="integration",
        sink=JsonlSink(output),
        watch_root=tmp_path,
        keep_raw_trace=False,
    )
    code = (
        "from pathlib import Path; import subprocess; "
        "p=Path('probe.txt'); p.write_text('ok'); p.read_text(); "
        "subprocess.run(['/bin/true'], check=True); p.unlink()"
    )
    rc = collector.run([sys.executable, "-c", code])
    assert rc == 0
    events = _events(output)
    relations = {event["relation"] for event in events}
    assert "SPAWNED" in relations
    assert "OPENED_WRITE" in relations
    assert "OPENED_READ" in relations
    assert "DELETED" in relations
    assert any(
        event["event_type"] == "filesystem.open"
        and event["target"]["id"].endswith("probe.txt")
        and event["attributes"]["causal"] is True
        for event in events
    )
