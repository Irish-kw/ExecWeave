from __future__ import annotations

import os
import subprocess
import sys
import time
import venv
from pathlib import Path

import psutil
import pytest

from execweave.collector import RuntimeCollector, _safe_process_snapshot
from execweave.command import resolve_launch_command
from execweave.sink import JsonlSink


def _process_is_live(pid: int) -> bool:
    try:
        process = psutil.Process(pid)
        return process.is_running() and process.status() != psutil.STATUS_ZOMBIE
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return False


def _wait_for(predicate, *, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("condition did not become true before timeout")


@pytest.mark.skipif(os.name == "nt", reason="POSIX virtualenv Python uses launcher symlinks")
def test_explicit_virtualenv_python_keeps_launcher_and_site_prefix(tmp_path: Path) -> None:
    venv_root = tmp_path / ".venv"
    venv.EnvBuilder(with_pip=False, symlinks=True).create(venv_root)
    venv_python = venv_root / "bin" / "python"
    assert venv_python.is_symlink()

    launch = resolve_launch_command(
        [str(venv_python), "-c", "import sys; print(sys.prefix)"]
    )

    assert launch[0] == os.path.abspath(os.fspath(venv_python))
    assert Path(launch[0]).is_symlink()
    completed = subprocess.run(
        launch,
        check=True,
        capture_output=True,
        text=True,
    )
    assert Path(completed.stdout.strip()).resolve() == venv_root.resolve()


def test_live_sibling_sidecar_excludes_entire_internal_output_dir(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "custom-live-output"
    run_dir.mkdir()
    event_path = run_dir / "events.jsonl"
    semantic_path = run_dir / "semantic.jsonl"
    monkeypatch.setenv("EXECWEAVE_SEMANTIC_SIDECAR", str(semantic_path))

    collector = RuntimeCollector(
        session_id="d001",
        sink=JsonlSink(event_path),
        watch_root=tmp_path,
        poll_interval=0.02,
        collect_filesystem=True,
        collect_network=False,
    )

    excluded = collector._filesystem_excluded_roots()
    assert run_dir.resolve() in excluded
    assert event_path.resolve() in excluded


def test_separate_semantic_sidecar_does_not_hide_unrelated_parent_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "runtime-output"
    sidecar_dir = tmp_path / "user-selected-sidecar-dir"
    run_dir.mkdir()
    sidecar_dir.mkdir()
    semantic_path = sidecar_dir / "semantic.jsonl"
    monkeypatch.setenv("EXECWEAVE_SEMANTIC_SIDECAR", str(semantic_path))

    collector = RuntimeCollector(
        session_id="d001-separate",
        sink=JsonlSink(run_dir / "events.jsonl"),
        watch_root=tmp_path,
        poll_interval=0.02,
        collect_filesystem=True,
        collect_network=False,
    )

    excluded = collector._filesystem_excluded_roots()
    assert semantic_path.resolve() in excluded
    assert sidecar_dir.resolve() not in excluded


def test_cleanup_terminates_tracked_child_after_launcher_has_exited(tmp_path: Path) -> None:
    child_pid_path = tmp_path / "child.pid"
    release_parent_path = tmp_path / "release-parent"
    parent_code = r'''
import subprocess
import sys
import time
from pathlib import Path

pid_path = Path(sys.argv[1])
release_path = Path(sys.argv[2])
child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
pid_path.write_text(str(child.pid), encoding="utf-8")
while not release_path.exists():
    time.sleep(0.02)
'''
    parent = subprocess.Popen(
        [
            sys.executable,
            "-c",
            parent_code,
            str(child_pid_path),
            str(release_parent_path),
        ]
    )
    child_pid: int | None = None
    try:
        _wait_for(child_pid_path.exists)
        child_pid = int(child_pid_path.read_text(encoding="utf-8"))
        child = psutil.Process(child_pid)
        snapshot = _safe_process_snapshot(child)
        assert snapshot is not None

        collector = RuntimeCollector(
            session_id="d003",
            sink=JsonlSink(tmp_path / "events.jsonl"),
            watch_root=tmp_path,
            poll_interval=0.02,
            collect_filesystem=False,
            collect_network=False,
        )
        collector._seen_processes[child_pid] = snapshot

        release_parent_path.touch()
        parent.wait(timeout=5)
        assert parent.poll() is not None
        assert _process_is_live(child_pid)

        collector._terminate_process_tree(parent)

        _wait_for(lambda: not _process_is_live(child_pid))
        assert not _process_is_live(child_pid)
    finally:
        if parent.poll() is None:
            parent.kill()
            parent.wait(timeout=5)
        if child_pid is not None and _process_is_live(child_pid):
            try:
                psutil.Process(child_pid).kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
