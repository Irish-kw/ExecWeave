from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import psutil
import pytest

from execweave.collector import RuntimeCollector
from execweave.sink import JsonlSink


_SLEEP = "import time; time.sleep(60)"


def _live_pid(pid: int) -> bool:
    try:
        process = psutil.Process(pid)
        return process.is_running() and process.status() != psutil.STATUS_ZOMBIE
    except (psutil.NoSuchProcess, psutil.ZombieProcess):
        return False


def _wait_for(predicate, *, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("fast-reparent fixture did not reach its handshake")


def _collector(tmp_path: Path) -> RuntimeCollector:
    return RuntimeCollector(
        session_id="d003-fast-reparent",
        sink=JsonlSink(tmp_path / "events.jsonl"),
        watch_root=tmp_path,
        poll_interval=0.02,
        collect_filesystem=False,
        collect_network=False,
    )


def _detaching_command(pid_file: Path) -> list[str]:
    code = (
        "import subprocess,sys; "
        "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'], "
        "start_new_session=True); "
        "open(sys.argv[1],'w',encoding='utf-8').write(str(child.pid))"
    )
    return [sys.executable, "-c", code, str(pid_file)]


def _miss_short_lived_tree(
    monkeypatch: pytest.MonkeyPatch,
    collector: RuntimeCollector,
    pid_file: Path,
) -> None:
    def miss_tree(root: psutil.Process) -> None:
        _wait_for(pid_file.exists)
        # Deliberately simulate the polling blind spot from issue #9: the launcher
        # exits after spawning a detached child before a descendant sample lands.
        time.sleep(0.05)

    monkeypatch.setattr(collector, "_sample_process_tree", miss_tree)


def _non_linux_guard() -> bool:
    if sys.platform.startswith("linux"):
        return False
    # Fast detached-child recovery in this regression is a Linux subreaper path.
    # On other platforms the implementation must remain disabled rather than
    # silently attempting Linux prctl semantics.
    assert RuntimeCollector._linux_child_subreaper_state() is None
    assert RuntimeCollector._set_linux_child_subreaper(True) is False
    return True


def test_run_cleans_detached_child_even_when_polling_never_observed_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if _non_linux_guard():
        return

    collector = _collector(tmp_path)
    pid_file = tmp_path / "detached.pid"
    sentinel = subprocess.Popen([sys.executable, "-c", _SLEEP])
    try:
        _miss_short_lived_tree(monkeypatch, collector, pid_file)
        assert collector.run(_detaching_command(pid_file)) == 0
        child_pid = int(pid_file.read_text(encoding="utf-8"))
        _wait_for(lambda: not _live_pid(child_pid))
        assert _live_pid(sentinel.pid), "cleanup killed a pre-existing unrelated child"

        finished = json.loads((tmp_path / "events.jsonl").read_text().splitlines()[-1])
        assert finished["event_type"] == "session.finished"
        assert finished["attributes"]["workload_alive_after_cleanup"] is False
    finally:
        if _live_pid(sentinel.pid):
            sentinel.kill()
        sentinel.wait(timeout=5)


def test_fast_detached_survivor_is_reported_if_cleanup_does_not_terminate_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if _non_linux_guard():
        return

    collector = _collector(tmp_path)
    pid_file = tmp_path / "detached.pid"
    _miss_short_lived_tree(monkeypatch, collector, pid_file)
    monkeypatch.setattr(collector, "_terminate_process_tree", lambda process, *, owned=None: None)

    child_pid: int | None = None
    try:
        assert collector.run(_detaching_command(pid_file)) == 0
        child_pid = int(pid_file.read_text(encoding="utf-8"))
        assert _live_pid(child_pid)
        finished = json.loads((tmp_path / "events.jsonl").read_text().splitlines()[-1])
        assert finished["attributes"]["workload_alive_after_cleanup"] is True
    finally:
        if child_pid is not None and _live_pid(child_pid):
            process = psutil.Process(child_pid)
            process.kill()
            try:
                process.wait(timeout=5)
            except psutil.TimeoutExpired:
                pass
