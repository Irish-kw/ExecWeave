from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import execweave.collector as collector_module
from execweave.collector import ProcessSnapshot, RuntimeCollector
from execweave.fidelity import derive_fidelity
from execweave.filesystem import SessionFileEventHandler
from execweave.schema import Entity
from execweave.sink import JsonlSink
from execweave.strace_backend import StraceParser, TraceRecord
from watchdog.events import FileModifiedEvent


class MemorySink:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.events = []

    def emit(self, event) -> None:
        self.events.append(event)

    def dicts(self) -> list[dict]:
        return [event.to_dict() for event in self.events]


class FakeProcess:
    def __init__(self, snapshot: ProcessSnapshot) -> None:
        self.pid = snapshot.pid
        self.snapshot = snapshot
        self.children_now: list[FakeProcess] = []
        self.connections_now: list[object] = []

    def children(self, *, recursive: bool) -> list[FakeProcess]:
        assert recursive is True
        return list(self.children_now)

    def net_connections(self, *, kind: str) -> list[object]:
        assert kind == "inet"
        return list(self.connections_now)


def _snapshot(pid: int, ppid: int) -> ProcessSnapshot:
    return ProcessSnapshot(
        pid=pid,
        ppid=ppid,
        name=f"p{pid}",
        cmdline=[f"p{pid}"],
        exe=None,
        create_time=float(pid),
    )


def _session() -> Entity:
    return Entity(type="session", id="session:threat", name="threat")


def _patch_snapshots(monkeypatch) -> None:
    monkeypatch.setattr(
        collector_module,
        "_safe_process_snapshot",
        lambda proc: getattr(proc, "snapshot", None),
    )


def test_portable_child_existing_only_between_samples_is_not_invented(
    monkeypatch, tmp_path: Path
) -> None:
    _patch_snapshots(monkeypatch)
    sink = MemorySink(tmp_path / "events.jsonl")
    collector = RuntimeCollector(
        session_id="threat",
        sink=sink,
        watch_root=tmp_path,
        poll_interval=0.10,
        collect_filesystem=False,
        collect_network=False,
    )
    root = FakeProcess(_snapshot(100, 1))
    collector._record_process_start(root.snapshot, parent=_session(), relation="LAUNCHED")

    collector._sample_process_tree(root)
    child = FakeProcess(_snapshot(101, 100))
    root.children_now = [child]  # Exists after one observation ...
    root.children_now = []  # ... and exits before the next observation.
    collector._sample_process_tree(root)

    assert not any(
        event.target is not None and event.target.attributes.get("pid") == 101
        for event in sink.events
    )
    fidelity = derive_fidelity(sink.dicts())
    assert "short_lived_process_capture" in fidelity["claims_not_supported"]
    assert fidelity["sampled_evidence_present"] is True


def test_portable_socket_existing_only_between_samples_is_not_invented(
    monkeypatch, tmp_path: Path
) -> None:
    _patch_snapshots(monkeypatch)
    sink = MemorySink(tmp_path / "events.jsonl")
    collector = RuntimeCollector(
        session_id="threat",
        sink=sink,
        watch_root=tmp_path,
        poll_interval=0.10,
        collect_filesystem=False,
        collect_network=True,
    )
    root = FakeProcess(_snapshot(200, 1))
    collector._record_process_start(root.snapshot, parent=_session(), relation="LAUNCHED")

    collector._sample_process_tree(root)
    root.connections_now = [
        SimpleNamespace(
            laddr=("127.0.0.1", 50000),
            raddr=("203.0.113.10", 443),
            status="ESTABLISHED",
        )
    ]
    root.connections_now = []  # Socket closes before the next process/socket poll.
    collector._sample_process_tree(root)

    assert not any(event.event_type == "network.connection" for event in sink.events)


def test_outliving_child_is_not_falsely_reported_exited_when_root_observation_ends(
    monkeypatch, tmp_path: Path
) -> None:
    sink = MemorySink(tmp_path / "events.jsonl")
    collector = RuntimeCollector(
        session_id="threat",
        sink=sink,
        watch_root=tmp_path,
        collect_filesystem=False,
        collect_network=False,
    )
    child = _snapshot(301, 300)
    collector._record_process_start(child, parent=_session(), relation="SPAWNED")
    monkeypatch.setattr(collector_module.psutil, "pid_exists", lambda pid: pid == child.pid)

    collector._mark_disappeared_processes(set())

    assert child.pid in collector._seen_processes
    assert not any(
        event.event_type == "process.exited"
        and event.source is not None
        and event.source.attributes.get("pid") == child.pid
        for event in sink.events
    )


def test_portable_filesystem_change_stays_session_correlated_and_noncausal(
    tmp_path: Path,
) -> None:
    sink = MemorySink(tmp_path / "events.jsonl")
    session = _session()
    handler = SessionFileEventHandler(
        session_id="threat",
        session_entity=session,
        sink=sink,
    )

    handler.on_any_event(FileModifiedEvent(str(tmp_path / "changed.txt")))

    event = sink.events[0]
    assert event.source == session
    assert event.relation == "OBSERVED_FILE_CHANGE"
    assert event.attributes["attribution"] == "session_observation"
    assert event.attributes["causal"] is False


def test_strace_trace_keeps_short_lived_child_spawn_attribution(tmp_path: Path) -> None:
    output = tmp_path / "events.jsonl"
    parser = StraceParser(
        session_id="native-threat",
        sink=JsonlSink(output),
        watch_root=tmp_path,
        command=["agent"],
    )
    parser.parse(
        [
            TraceRecord(10.0, 400, "clone(child_stack=NULL, flags=SIGCHLD) = 401"),
            TraceRecord(10.000001, 401, 'openat(AT_FDCWD, "child.txt", O_RDONLY) = 3'),
            TraceRecord(10.000002, 401, "+++ exited with 0 +++"),
        ]
    )
    events = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    child_start = next(
        event
        for event in events
        if event["event_type"] == "process.started"
        and event["target"]["id"] == "process:native-threat:401"
    )

    assert child_start["relation"] == "SPAWNED"
    assert child_start["source"]["id"] == "process:native-threat:400"
    assert child_start["attributes"]["attribution"] == "syscall"
