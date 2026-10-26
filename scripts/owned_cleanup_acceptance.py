#!/usr/bin/env python3
"""Formal acceptance for bounded cleanup of harness-owned process descendants."""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

from acceptance.processes import OwnedProcessTracker, identity_for_pid, identity_is_alive
from acceptance.reporting import FEATURES, Result, Status, write_report

_PROVIDER = "owned-cleanup-fixture"


def _wait_until(predicate, timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


def _stop_process(process: subprocess.Popen[str] | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2)


def _run(output_dir: Path) -> Result:
    marker = "EW-CLEANUP-" + uuid4().hex[:10].upper()
    run_root = output_dir / marker.lower()
    run_root.mkdir(parents=True, exist_ok=True)
    result = Result(_PROVIDER, "owned-cleanup", marker, platform.system().lower())
    result.artifacts = str(run_root)
    started_at = time.monotonic()

    tracker = OwnedProcessTracker(poll_interval=0.02)
    sentinel: subprocess.Popen[str] | None = None
    parent: subprocess.Popen[str] | None = None
    child_pid: int | None = None
    try:
        sentinel = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            text=True,
        )
        sentinel_identity = identity_for_pid(sentinel.pid)
        if sentinel_identity is None:
            raise RuntimeError("unrelated sentinel identity unavailable")

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
        tracker.track_pid(parent.pid)
        tracker.start()
        result.check(
            "Launch",
            True,
            "Harness launched an explicitly owned root plus an unrelated sentinel",
        )

        assert parent.stdout is not None
        child_pid = int(parent.stdout.readline().strip())
        if not _wait_until(lambda: tracker.is_tracked(child_pid)):
            raise RuntimeError("owned descendant was not observed before root exit")
        child_identity = identity_for_pid(child_pid)
        if child_identity is None:
            raise RuntimeError("owned child identity unavailable")

        exit_code = parent.wait(timeout=5)
        if exit_code != 0:
            stderr = parent.stderr.read() if parent.stderr is not None else ""
            raise RuntimeError(f"fixture root exited {exit_code}: {stderr[:400]}")
        if not identity_is_alive(child_identity):
            raise RuntimeError("fixture child did not outlive its launched root")

        report = tracker.cleanup(
            grace_seconds=0.05,
            terminate_timeout=2.0,
            kill_timeout=2.0,
        )
        cleanup_ok = (
            not report.remaining
            and not identity_is_alive(child_identity)
            and identity_is_alive(sentinel_identity)
        )
        result.check(
            "Cleanup",
            cleanup_ok,
            "Orphaned owned descendant stopped within bounded cleanup; unrelated sentinel survived",
            f"tracked={len(tracker.identities())}",
            f"terminated={len(report.terminated)}",
            f"forced_kills={len(report.killed)}",
        )
    except Exception as exc:
        reason = f"{type(exc).__name__}: {exc}"
        if "Launch" not in result.checks:
            result.check("Launch", False, reason)
        if "Cleanup" not in result.checks:
            result.check("Cleanup", False, reason)
    finally:
        tracker.cleanup(
            grace_seconds=0,
            terminate_timeout=0.5,
            kill_timeout=0.5,
        )
        # The tracker retains the observed child identity after root exit.
        # Never reacquire and kill a bare PID here: it may already be reused.
        _stop_process(parent)
        _stop_process(sentinel)
        for feature in FEATURES:
            if feature not in result.checks:
                result.skip(feature, "Not exercised by the owned-process cleanup scenario")
        result.runtime_seconds = time.monotonic() - started_at
    return result


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/dashboard-acceptance/owned-cleanup"),
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    result = _run(args.output_dir)
    run_root = Path(result.artifacts)
    summary = write_report(run_root, [result], {_PROVIDER})
    print(
        json.dumps(
            {"output": str(run_root), **summary},
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )
    return 0 if summary["status"] == Status.PASS.value else 1


if __name__ == "__main__":
    raise SystemExit(main())
