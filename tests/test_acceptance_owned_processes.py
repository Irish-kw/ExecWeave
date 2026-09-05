from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from acceptance.processes import (  # noqa: E402
    OwnedProcessTracker,
    ProcessIdentity,
    identity_for_pid,
    identity_is_alive,
)


def _stop_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2)


def _wait_until(predicate, timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


def test_owned_cleanup_tracks_orphaned_child_and_preserves_unrelated_process():
    sentinel = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        text=True,
    )
    parent_code = (
        "import subprocess,sys,time\n"
        "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'])\n"
        "print(child.pid, flush=True)\n"
        "time.sleep(1.5)\n"
    )
    parent = subprocess.Popen(
        [sys.executable, "-c", parent_code],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    tracker = OwnedProcessTracker(poll_interval=0.02)
    child_pid: int | None = None
    try:
        sentinel_identity = identity_for_pid(sentinel.pid)
        assert sentinel_identity is not None
        tracker.track_pid(parent.pid)
        tracker.start()

        assert parent.stdout is not None
        child_pid = int(parent.stdout.readline().strip())
        assert _wait_until(lambda: tracker.is_tracked(child_pid))
        child_identity = identity_for_pid(child_pid)
        assert child_identity is not None

        assert parent.wait(timeout=5) == 0
        assert identity_is_alive(child_identity), "fixture child did not outlive its root"

        report = tracker.cleanup(
            grace_seconds=0.05,
            terminate_timeout=2.0,
            kill_timeout=2.0,
        )
        assert not report.remaining
        assert not identity_is_alive(child_identity)
        assert identity_is_alive(sentinel_identity), (
            "owned cleanup touched an unrelated process"
        )
    finally:
        tracker.cleanup(
            grace_seconds=0,
            terminate_timeout=0.5,
            kill_timeout=0.5,
        )
        # Cleanup must use the saved identities even on assertion failure.
        _stop_process(parent)
        _stop_process(sentinel)


def test_create_time_mismatch_never_grants_ownership():
    sentinel = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        text=True,
    )
    tracker = OwnedProcessTracker()
    try:
        actual = identity_for_pid(sentinel.pid)
        assert actual is not None
        tracker.track_identity(ProcessIdentity(actual.pid, actual.create_time + 1000.0))
        report = tracker.cleanup(
            grace_seconds=0,
            terminate_timeout=0.1,
            kill_timeout=0.1,
        )
        assert not report.terminated
        assert not report.killed
        assert not report.remaining
        assert identity_is_alive(actual), "PID reuse guard terminated the live process"
    finally:
        _stop_process(sentinel)
