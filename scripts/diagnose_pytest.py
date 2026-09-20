"""Opt-in, single-process pytest diagnostics; never an acceptance substitute.

The parent preserves partial progress before its own deadline, so a cancelled
CI job need not be the only evidence. No tests are selected, reordered or edited
by the journal. A deadline terminates only this diagnostic's process tree and
returns 124, not a passing pytest result. No environment/command-line process
inventory or frame locals are recorded.
"""
from __future__ import annotations

import argparse
import faulthandler
import json
import math
from pathlib import Path
import subprocess
import sys
import time

import psutil


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")


class Progress:
    """Observe pytest's public reporting hooks without changing test outcomes."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.stream = (root / "progress.jsonl").open("x", encoding="utf-8", buffering=1)
        self.started = time.monotonic()

    def emit(self, event: str, **values: object) -> None:
        self.stream.write(json.dumps({"event": event, "elapsed": time.monotonic() - self.started,
                                      **values}, ensure_ascii=True) + "\n")
        self.stream.flush()

    def pytest_collection_finish(self, session) -> None:
        write_json(self.root / "collection.json", [item.nodeid for item in session.items])
        self.emit("collection", count=len(session.items))

    def pytest_runtest_logstart(self, nodeid, location) -> None:
        self.emit("start", nodeid=nodeid)

    def pytest_runtest_logreport(self, report) -> None:
        self.emit("phase", nodeid=report.nodeid, phase=report.when,
                  outcome=report.outcome, duration=report.duration)

    def pytest_runtest_logfinish(self, nodeid, location) -> None:
        self.emit("finish", nodeid=nodeid)

    def pytest_sessionfinish(self, session, exitstatus) -> None:
        self.emit("sessionfinish", exitstatus=int(exitstatus))


def worker(root: Path, stack_interval: float, pytest_args: list[str]) -> int:
    import pytest

    progress = Progress(root)
    with (root / "stacks.txt").open("x", encoding="utf-8") as stacks:
        faulthandler.dump_traceback_later(stack_interval, repeat=True, file=stacks)
        try:
            code = int(pytest.main(["-q", "--junitxml=" + str(root / "pytest.xml"),
                                    *pytest_args], plugins=[progress]))
            write_json(root / "worker-result.json", {"exit_code": code})
            return code
        finally:
            faulthandler.cancel_dump_traceback_later()
            progress.stream.close()


def snapshot(process: psutil.Process) -> tuple[list[psutil.Process], list[dict]]:
    """Only the owned worker and its descendants, never unrelated host processes."""
    try:
        candidates = [process, *process.children(recursive=True)]
    except psutil.NoSuchProcess:
        return [], []
    rows, handles = [], []
    for item in candidates:
        try:
            rows.append({"pid": item.pid, "ppid": item.ppid(), "name": item.name(),
                         "status": item.status(), "created": item.create_time()})
            handles.append(item)
        except psutil.NoSuchProcess:
            continue
        except psutil.AccessDenied:
            rows.append({"pid": item.pid, "state": "access_denied"})
            handles.append(item)
    return handles, rows


def stop_owned(handles: list[psutil.Process]) -> list[int]:
    for item in reversed(handles):
        try:
            item.terminate()
        except psutil.NoSuchProcess:
            pass
        except psutil.AccessDenied:
            continue
    _, alive = psutil.wait_procs(handles, timeout=3)
    for item in alive:
        try:
            item.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    _, alive = psutil.wait_procs(alive, timeout=3)
    return [item.pid for item in alive if item.is_running()]


def journal_summary(path: Path) -> dict:
    result = {"last_started": None, "last_finished": None, "last_phase": None,
              "finished_records": 0, "session_exit_code": None, "invalid_lines": 0}
    if path.exists():
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                try:
                    event = json.loads(line)
                    if not isinstance(event, dict):
                        raise ValueError("not an event")
                except (ValueError, TypeError):
                    result["invalid_lines"] += 1
                    continue
                if event.get("event") == "start":
                    result["last_started"] = event.get("nodeid")
                elif event.get("event") == "finish":
                    result["last_finished"] = event.get("nodeid")
                    result["finished_records"] += 1
                elif event.get("event") == "phase":
                    result["last_phase"] = event
                elif event.get("event") == "sessionfinish":
                    result["session_exit_code"] = event.get("exitstatus")
    return result


def supervise(root: Path, budget: float, stack_interval: float, pytest_args: list[str]) -> int:
    root.mkdir(parents=True, exist_ok=False)  # Never overwrite an earlier diagnostic.
    command = [sys.executable, "-u", str(Path(__file__).resolve()), "--worker",
               "--output", str(root), "--stack-interval", str(stack_interval), "--", *pytest_args]
    started = time.monotonic()
    write_json(root / "invocation.json", {"python": sys.version, "platform": sys.platform,
               "cwd": str(Path.cwd()), "budget_seconds": budget, "pytest_args": pytest_args,
               "acceptance": False})
    timed_out = False
    with (root / "pytest.log").open("xb") as output:
        child = subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT)
        process = psutil.Process(child.pid)
        try:
            child.wait(timeout=budget)
        except subprocess.TimeoutExpired:
            timed_out = True
            handles, rows = snapshot(process)
            write_json(root / "processes-at-deadline.json", rows)
            survivors = stop_owned(handles)
            write_json(root / "cleanup.json", {"surviving_owned_pids": survivors})
            try:
                child.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass
        finally:
            if child.poll() is None:
                # Also bound cleanup when the supervising command is interrupted.
                handles, _ = snapshot(process)
                stop_owned(handles)
    summary = journal_summary(root / "progress.jsonl")
    code = 124 if timed_out else child.returncode
    completed = not timed_out and code == 0 and summary["session_exit_code"] == 0
    summary.update({"state": "deadline" if timed_out else "completed" if completed else "failed",
                    "exit_code": code, "elapsed": time.monotonic() - started, "acceptance": False})
    write_json(root / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=True), flush=True)
    return code if isinstance(code, int) and code != 0 else (0 if completed else 2)


def positive(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("must be finite and positive")
    return number


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--budget", type=positive, default=1500.0)
    parser.add_argument("--stack-interval", type=positive, default=120.0)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("pytest_args", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    rest = args.pytest_args[1:] if args.pytest_args[:1] == ["--"] else args.pytest_args
    root = args.output.resolve()
    if args.worker:
        return worker(root, args.stack_interval, rest)
    return supervise(root, args.budget, args.stack_interval, rest)


if __name__ == "__main__":
    raise SystemExit(main())
