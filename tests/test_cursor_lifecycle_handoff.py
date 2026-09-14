"""Deterministic tests for Cursor launcher-to-GUI attribution."""

from __future__ import annotations

import json
import sys
from execweave.collector import RuntimeCollector
from execweave.sink import JsonlSink

from types import SimpleNamespace

from execweave import cursor_lifecycle


def _snapshot(pid: int, ppid: int, exe: str, create_time: float):
    return SimpleNamespace(
        pid=pid,
        ppid=ppid,
        exe=exe,
        create_time=create_time,
    )


class _LiveProcess:
    def __init__(self, pid: int) -> None:
        self.pid = pid

    def is_running(self) -> bool:
        return True

    def status(self) -> str:
        return "sleeping"


def test_preexisting_cursor_is_excluded(monkeypatch):
    executable = r"C:\Program Files\Cursor\Cursor.exe"
    root = _snapshot(100, 1, executable, 100.0)
    preexisting = _snapshot(200, 1, executable, 50.0)
    monkeypatch.setattr(cursor_lifecycle.psutil, "Process", _LiveProcess)

    result = cursor_lifecycle.select_handoff_candidate(
        [root, preexisting],
        root=root,
        executable=executable,
        baseline={(200, 50.0)},
    )

    assert result.status == "no_attributed_candidate"


def test_exactly_one_new_descendant_is_handed_off(monkeypatch):
    executable = r"C:\Program Files\Cursor\Cursor.exe"
    root = _snapshot(100, 1, executable, 100.0)
    gui = _snapshot(300, 100, executable, 101.0)
    monkeypatch.setattr(cursor_lifecycle.psutil, "Process", _LiveProcess)

    result = cursor_lifecycle.select_handoff_candidate(
        [root, gui],
        root=root,
        executable=executable,
        baseline=set(),
    )

    assert result.status == "handoff"
    assert result.snapshot is gui
    assert result.process is not None
    assert result.process.pid == 300


def test_observed_ancestry_survives_reparenting(monkeypatch):
    executable = r"C:\Program Files\Cursor\Cursor.exe"
    root = _snapshot(100, 1, executable, 100.0)
    bridge = _snapshot(200, 100, r"C:\Windows\system32\helper.exe", 100.5)
    gui_latest = _snapshot(300, 200, executable, 101.0)
    monkeypatch.setattr(cursor_lifecycle.psutil, "Process", _LiveProcess)

    result = cursor_lifecycle.select_handoff_candidate(
        [root, bridge, gui_latest],
        root=root,
        executable=executable,
        baseline=set(),
    )

    assert result.status == "handoff"


def test_ambiguous_new_descendants_abstain(monkeypatch):
    executable = r"C:\Program Files\Cursor\Cursor.exe"
    root = _snapshot(100, 1, executable, 100.0)
    first = _snapshot(300, 100, executable, 101.0)
    second = _snapshot(400, 100, executable, 102.0)
    monkeypatch.setattr(cursor_lifecycle.psutil, "Process", _LiveProcess)

    result = cursor_lifecycle.select_handoff_candidate(
        [root, first, second],
        root=root,
        executable=executable,
        baseline=set(),
    )

    assert result.status == "ambiguous_candidates"


def test_cursor_invocation_only_matches_cursor_executable():
    assert cursor_lifecycle.is_cursor_invocation([r"C:\Cursor\Cursor.exe", "--wait"])
    assert not cursor_lifecycle.is_cursor_invocation([r"C:\Cursor\cursor-helper.exe"])
    assert not cursor_lifecycle.is_cursor_invocation([])
def test_fake_cursor_launcher_hands_off_to_unique_gui_process(tmp_path, monkeypatch):
    launch_code = (
        "import subprocess, sys, time; "
        "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(0.5)']); time.sleep(0.15)"
    )
    monkeypatch.setattr(
        "execweave.collector.resolve_launch_command",
        lambda _command: [sys.executable, "-c", launch_code],
    )
    output = tmp_path / "events.jsonl"
    collector = RuntimeCollector(
        session_id="cursor-fake",
        sink=JsonlSink(output),
        watch_root=tmp_path,
        poll_interval=0.03,
        collect_filesystem=False,
        collect_network=False,
    )

    assert collector.run(["cursor"]) == 0
    events = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    finished = next(event for event in events if event["event_type"] == "session.finished")
    attributes = finished["attributes"]
    assert attributes["cursor_lifecycle_handoff"] == "launcher"
    assert attributes["cursor_handoff_status"] == "completed"
    assert isinstance(attributes["cursor_handoff_pid"], int)
