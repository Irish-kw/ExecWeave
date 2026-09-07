from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import psutil
import pytest

import execweave.collector as collector_module
import execweave.filesystem as filesystem_module
from execweave.collector import ProcessSnapshot, RuntimeCollector
from execweave.dashboard_shell import DASHBOARD_HTML
from execweave.fidelity import derive_fidelity
from execweave.filesystem import FileWatcher
from execweave.schema import Entity
from execweave.sink import JsonlSink


def _events(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _snapshot(pid: int, create_time: float, *, ppid: int = 1) -> ProcessSnapshot:
    return ProcessSnapshot(
        pid=pid,
        ppid=ppid,
        name=f"p{pid}",
        cmdline=[f"p{pid}"],
        exe=None,
        create_time=create_time,
    )


def _collector(tmp_path: Path, *, network: bool = False) -> RuntimeCollector:
    return RuntimeCollector(
        session_id="audit",
        sink=JsonlSink(tmp_path / "events.jsonl"),
        watch_root=tmp_path,
        poll_interval=0.02,
        collect_filesystem=False,
        collect_network=network,
    )


def test_pid_reuse_records_distinct_lifetimes(tmp_path: Path) -> None:
    collector = _collector(tmp_path)
    parent = Entity(type="session", id="session:audit", name="audit")
    old = _snapshot(424242, 100.0)
    new = _snapshot(424242, 200.0)

    collector._record_process_start(old, parent=parent, relation="SPAWNED")
    collector._record_process_start(new, parent=parent, relation="SPAWNED")

    events = _events(collector.sink.path)
    assert [event["event_type"] for event in events] == [
        "process.started",
        "process.exited",
        "process.started",
    ]
    assert events[0]["target"]["id"] != events[2]["target"]["id"]
    assert events[1]["attributes"]["reason"] == "pid_reused"
    assert collector._seen_processes[424242].create_time == 200.0


def test_disappearance_check_does_not_confuse_reused_pid_with_same_process(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    collector = _collector(tmp_path)
    parent = Entity(type="session", id="session:audit", name="audit")
    old = _snapshot(31337, 10.0)
    new = _snapshot(31337, 20.0)
    collector._record_process_start(old, parent=parent, relation="SPAWNED")

    monkeypatch.setattr(collector_module.psutil, "pid_exists", lambda pid: pid == 31337)
    monkeypatch.setattr(collector_module.psutil, "Process", lambda pid: object())
    monkeypatch.setattr(collector_module, "_safe_process_snapshot", lambda proc: new)

    collector._mark_disappeared_processes(set())

    assert 31337 not in collector._seen_processes
    assert _events(collector.sink.path)[-1]["event_type"] == "process.exited"


def test_collector_failure_terminates_owned_workload_and_records_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    collector = _collector(tmp_path)

    def fail_sample(root) -> None:
        raise RuntimeError("synthetic collector failure")

    monkeypatch.setattr(collector, "_sample_process_tree", fail_sample)

    with pytest.raises(RuntimeError, match="synthetic collector failure"):
        collector.run([sys.executable, "-c", "import time; time.sleep(30)"])

    events = _events(collector.sink.path)
    launched = next(event for event in events if event["relation"] == "LAUNCHED")
    finished = events[-1]
    pid = int(launched["target"]["attributes"]["pid"])

    assert finished["event_type"] == "session.finished"
    assert finished["attributes"]["collector_failed"] is True
    assert finished["attributes"]["collector_error_type"] == "RuntimeError"
    assert finished["attributes"]["workload_terminated_due_to_collector_error"] is True
    assert finished["attributes"]["workload_alive_after_cleanup"] is False

    deadline = time.monotonic() + 2.0
    while psutil.pid_exists(pid) and time.monotonic() < deadline:
        time.sleep(0.02)
    assert not psutil.pid_exists(pid)


def test_network_access_denied_is_distinguishable_from_empty_success(tmp_path: Path) -> None:
    collector = _collector(tmp_path, network=True)
    snapshot = _snapshot(100, 1.0)

    class DeniedProcess:
        def net_connections(self, *, kind: str):
            raise psutil.AccessDenied(pid=100)

    class EmptyProcess:
        def net_connections(self, *, kind: str):
            return []

    collector._sample_network(DeniedProcess(), snapshot)
    assert collector._network_collection_status() == "unavailable"
    assert collector._network_sample_attempts == 1
    assert collector._network_sample_successes == 0
    assert collector._network_sample_errors == 1
    assert collector._network_access_denied == 1

    collector._sample_network(EmptyProcess(), snapshot)
    assert collector._network_collection_status() == "degraded"
    assert collector._network_sample_successes == 1


def test_fidelity_surfaces_network_collection_health() -> None:
    report = derive_fidelity(
        [
            {
                "session_id": "s1",
                "event_type": "session.started",
                "attributes": {
                    "backend": "portable",
                    "platform": "test",
                    "network_requested": True,
                    "network_collected": True,
                },
            },
            {
                "session_id": "s1",
                "event_type": "session.finished",
                "attributes": {
                    "backend": "portable",
                    "network_collection_status": "unavailable",
                },
            },
        ]
    )

    assert report["capture_context"]["network_collection_status"] == "unavailable"
    assert any("no process network sample succeeded" in text for text in report["limitations"])


def test_partial_watcher_start_is_torn_down_before_error_propagates(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class PartialObserver:
        instance = None

        def __init__(self) -> None:
            self.unscheduled = False
            self.stopped = False
            self.joined = False
            type(self).instance = self

        def schedule(self, handler, path, recursive=False) -> None:
            return None

        def start(self) -> None:
            raise PermissionError("synthetic start failure")

        def unschedule_all(self) -> None:
            self.unscheduled = True

        def stop(self) -> None:
            self.stopped = True

        def join(self, timeout=None) -> None:
            self.joined = True

    monkeypatch.setattr(filesystem_module, "_prefer_polling_on_linux", lambda root: (False, None))
    monkeypatch.setattr(filesystem_module, "_is_linux_inotify_resource_error", lambda exc: False)
    monkeypatch.setattr(filesystem_module, "Observer", PartialObserver)

    watcher = FileWatcher(
        root=tmp_path,
        session_id="s1",
        session_entity=Entity(type="session", id="session:s1", name="s1"),
        sink=JsonlSink(tmp_path / "watcher.jsonl"),
    )

    with pytest.raises(PermissionError, match="synthetic start failure"):
        watcher.start()

    assert PartialObserver.instance is not None
    assert PartialObserver.instance.unscheduled is True
    assert PartialObserver.instance.stopped is True
    assert PartialObserver.instance.joined is True

    watcher.stop()


def test_finished_conversation_sync_requires_successful_final_fetch() -> None:
    assert "conversationFinishSynchronized=false" in DASHBOARD_HTML
    assert "if(!response.ok)return false" in DASHBOARD_HTML
    assert "return true}catch(_){return false}" in DASHBOARD_HTML
    assert (
        "isFinishedSynchronized:()=>conversationPollingFinished&&conversationFinishSynchronized"
        in DASHBOARD_HTML
    )
    assert "isFinishedSynchronized:()=>conversationPollingFinished};" not in DASHBOARD_HTML
