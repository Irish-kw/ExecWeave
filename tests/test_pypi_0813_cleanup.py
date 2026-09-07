"""D003: exercise real run/finalization, not a pre-seeded ownership dictionary."""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path

import psutil
import pytest

import execweave.collector as collector_module
from execweave.collector import RuntimeCollector, _safe_process_snapshot
from execweave.sink import JsonlSink


_LEAF = "import time; time.sleep(60)"
_CHILD = r'''
import json
import os
import subprocess
import sys
import time
from pathlib import Path

leaf = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
Path(sys.argv[1]).write_text(json.dumps([os.getpid(), leaf.pid]), encoding="utf-8")
Path(sys.argv[2]).touch()
time.sleep(60)
'''
_PARENT = r'''
import subprocess
import sys
import time
from pathlib import Path

subprocess.Popen([sys.executable, "-c", sys.argv[1], sys.argv[2], sys.argv[3]])
while not Path(sys.argv[4]).exists():
    time.sleep(0.01)
if sys.argv[5] == "workload_exception":
    raise RuntimeError("D003 workload exception")
sys.exit(int(sys.argv[5]))
'''


def _live(process: psutil.Process) -> bool:
    try:
        return process.is_running() and process.status() != psutil.STATUS_ZOMBIE
    except (psutil.NoSuchProcess, psutil.ZombieProcess):
        return False


def _wait_for(predicate, *, timeout: float = 8.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("D003 fixture did not reach its handshake before timeout")


def _remember(pid: int, owned: list[psutil.Process]) -> psutil.Process:
    process = psutil.Process(pid)
    # Prime the lifetime identity before any wait/reparent/PID-reuse race.
    process.create_time()
    owned.append(process)
    return process


def _cleanup(owned: list[psutil.Process]) -> None:
    # Test teardown uses only retained lifetime-qualified handles, never bare-PID
    # kills, executable-name matching, or a global process sweep.
    for process in reversed(owned):
        try:
            if _live(process):
                process.kill()
        except (psutil.NoSuchProcess, psutil.ZombieProcess):
            pass
    psutil.wait_procs(owned, timeout=2.0)


def _collector(tmp_path: Path, *, network: bool = False) -> RuntimeCollector:
    return RuntimeCollector(
        session_id="d003-run",
        sink=JsonlSink(tmp_path / "events.jsonl"),
        watch_root=tmp_path,
        poll_interval=0.02,
        collect_filesystem=False,
        collect_network=network,
    )


def _command(tmp_path: Path, exit_kind: str) -> list[str]:
    return [
        sys.executable, "-c", _PARENT, _CHILD,
        str(tmp_path / "family.json"), str(tmp_path / "ready"),
        str(tmp_path / "release"), exit_kind,
    ]


@pytest.mark.parametrize("mode", ["0", "17", "workload_exception", "collector_error", "interrupt"])
def test_run_finalizes_reparented_children_and_grandchildren(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str,
) -> None:
    collector = _collector(tmp_path)
    owned: list[psutil.Process] = []
    family: list[psutil.Process] = []
    sentinel = subprocess.Popen([sys.executable, "-c", _LEAF])
    external = _remember(sentinel.pid, owned)
    original_sample = collector._sample_process_tree
    root_seen = False
    released = False

    def sample(root: psutil.Process) -> None:
        nonlocal root_seen, released
        if not root_seen:
            _remember(root.pid, owned)
            root_seen = True
        original_sample(root)
        if released or not (tmp_path / "ready").exists():
            return
        pids = json.loads((tmp_path / "family.json").read_text(encoding="utf-8"))
        if not all(pid in collector._seen_processes for pid in pids):
            return
        family.extend(_remember(pid, owned) for pid in pids)
        released = True
        (tmp_path / "release").touch()
        _wait_for(lambda: not _live(root))
        assert all(_live(process) for process in family)
        if mode == "collector_error":
            raise RuntimeError("D003 collector failure after reparent")
        if mode == "interrupt":
            raise KeyboardInterrupt

    monkeypatch.setattr(collector, "_sample_process_tree", sample)
    exit_kind = mode if mode in {"0", "17", "workload_exception"} else "0"
    try:
        if mode == "collector_error":
            with pytest.raises(RuntimeError, match="D003 collector failure"):
                collector.run(_command(tmp_path, exit_kind))
        else:
            result = collector.run(_command(tmp_path, exit_kind))
            expected = (
                130 if mode == "interrupt"
                else 1 if mode == "workload_exception"
                else int(mode)
            )
            assert result == expected
        assert released and len(family) == 2
        assert not any(_live(process) for process in family), "owned orphan survived run()"
        assert _live(external), "unrelated same-command process was terminated"
        events = [json.loads(line) for line in collector.sink.path.read_text().splitlines()]
        finished = [event for event in events if event["event_type"] == "session.finished"]
        assert len(finished) == 1
        attributes = finished[0]["attributes"]
        assert attributes["workload_alive_after_cleanup"] is False
        assert attributes["collector_failed"] is (mode == "collector_error")
        assert attributes["interrupted"] is (mode == "interrupt")
    finally:
        _cleanup(owned)
        sentinel.wait(timeout=8)


def test_cleanup_retains_discovery_before_a_network_callback_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    collector = _collector(tmp_path, network=True)
    owned: list[psutil.Process] = []
    family: list[psutil.Process] = []
    original_sample = collector._sample_process_tree

    def sample(root: psutil.Process) -> None:
        _remember(root.pid, owned)
        _wait_for((tmp_path / "ready").exists)
        pids = json.loads((tmp_path / "family.json").read_text(encoding="utf-8"))
        family.extend(_remember(pid, owned) for pid in pids)
        original_sample(root)

    def fail_network(root: psutil.Process, snapshot) -> None:
        # The tree has already been discovered, but the first callback fails
        # before descendant process.started events have been emitted.
        assert not any(process.pid in collector._seen_processes for process in family)
        (tmp_path / "release").touch()
        _wait_for(lambda: not _live(root))
        raise RuntimeError("D003 network callback failure")

    monkeypatch.setattr(collector, "_sample_process_tree", sample)
    monkeypatch.setattr(collector, "_sample_network", fail_network)
    try:
        with pytest.raises(RuntimeError, match="D003 network callback failure"):
            collector.run(_command(tmp_path, "0"))
        assert len(family) == 2
        assert not any(_live(process) for process in family), "discovered orphan was forgotten"
        finished = json.loads(collector.sink.path.read_text().splitlines()[-1])
        assert finished["attributes"]["collector_error_type"] == "RuntimeError"
        assert finished["attributes"]["workload_alive_after_cleanup"] is False
        assert finished["attributes"]["workload_terminated_due_to_collector_error"] is True
    finally:
        _cleanup(owned)


def test_snapshot_cleanup_needs_lifetime_not_readable_command_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    collector = _collector(tmp_path)
    snapshot = _safe_process_snapshot(psutil.Process())
    assert snapshot is not None
    monkeypatch.setattr(collector_module, "_safe_process_snapshot", lambda process: None)
    matched = collector._process_for_snapshot(snapshot)
    assert matched is not None and matched.pid == snapshot.pid
    assert collector._process_for_snapshot(replace(snapshot, create_time=snapshot.create_time - 10)) is None


def test_cleanup_is_idempotent_and_rejects_stale_process_identity(tmp_path: Path) -> None:
    collector = _collector(tmp_path)
    owned: list[psutil.Process] = []
    parent = subprocess.Popen(_command(tmp_path, "0"), cwd=tmp_path)
    root = _remember(parent.pid, owned)
    sentinel = subprocess.Popen([sys.executable, "-c", _LEAF])
    external = _remember(sentinel.pid, owned)
    try:
        _wait_for((tmp_path / "ready").exists)
        family = [_remember(pid, owned) for pid in json.loads((tmp_path / "family.json").read_text())]
        collector._sample_process_tree(root)
        stale = _safe_process_snapshot(external)
        assert stale is not None
        collector._seen_processes[external.pid] = replace(stale, create_time=stale.create_time - 10)
        (tmp_path / "release").touch()
        parent.wait(timeout=8)
        collector._terminate_process_tree(parent)
        collector._terminate_process_tree(parent)
        assert not any(_live(process) for process in family)
        assert _live(external)
    finally:
        _cleanup(owned)
        parent.wait(timeout=8)
        sentinel.wait(timeout=8)


@pytest.mark.skipif(os.name == "nt", reason="POSIX signals; not a Windows console acceptance")
def test_real_sigint_cleans_the_owned_tree(tmp_path: Path) -> None:
    owned: list[psutil.Process] = []
    env = dict(os.environ)
    source_root = str(Path(collector_module.__file__).resolve().parents[1])
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [source_root, env.get("PYTHONPATH")]))
    runner_code = r'''
import sys
from pathlib import Path
from execweave.collector import RuntimeCollector
from execweave.sink import JsonlSink
root = Path(sys.argv[1])
collector = RuntimeCollector(
    session_id="d003-sigint", sink=JsonlSink(root / "events.jsonl"),
    watch_root=root, poll_interval=0.02, collect_filesystem=False, collect_network=False,
)
sys.exit(collector.run(sys.argv[2:]))
'''
    runner = subprocess.Popen(
        [sys.executable, "-c", runner_code, str(tmp_path), *_command(tmp_path, "0")], env=env,
    )
    monitor = _remember(runner.pid, owned)
    sentinel = subprocess.Popen([sys.executable, "-c", _LEAF])
    external = _remember(sentinel.pid, owned)
    try:
        _wait_for((tmp_path / "ready").exists)
        family = [_remember(pid, owned) for pid in json.loads((tmp_path / "family.json").read_text())]
        roots = monitor.children()
        assert len(roots) == 1
        root = _remember(roots[0].pid, owned)
        runner.send_signal(signal.SIGINT)
        assert runner.wait(timeout=15) == 130
        assert not any(_live(process) for process in [root, *family])
        assert _live(external)
        finished = json.loads((tmp_path / "events.jsonl").read_text().splitlines()[-1])
        assert finished["attributes"]["interrupted"] is True
        assert finished["attributes"]["workload_alive_after_cleanup"] is False
    finally:
        _cleanup(owned)
        runner.wait(timeout=8)
        sentinel.wait(timeout=8)


@pytest.mark.skipif(os.name == "nt", reason="Windows TerminateProcess does not deliver POSIX SIGTERM")
def test_cleanup_escalates_an_ignored_sigterm(tmp_path: Path) -> None:
    ready = tmp_path / "ignoring-sigterm"
    code = (
        "import signal,time; from pathlib import Path; "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        f"Path({str(ready)!r}).touch(); time.sleep(60)"
    )
    parent = subprocess.Popen([sys.executable, "-c", code])
    owned: list[psutil.Process] = []
    process = _remember(parent.pid, owned)
    try:
        _wait_for(ready.exists)
        collector = _collector(tmp_path)
        collector._sample_process_tree(process)
        collector._terminate_process_tree(parent)
        # psutil.wait_procs may reap the root before Popen.wait; do not infer
        # its signal from Popen's ECHILD fallback return code.
        assert not _live(process)
        parent.wait(timeout=8)
        collector._terminate_process_tree(parent)
    finally:
        _cleanup(owned)
        parent.wait(timeout=8)
