"""Attribution-safe Cursor GUI launcher hand-off helpers."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import psutil


@dataclass(frozen=True)
class CursorHandoff:
    status: str
    snapshot: Any | None = None
    process: psutil.Process | None = None


def is_cursor_invocation(command: Iterable[str]) -> bool:
    values = list(command)
    if not values:
        return False
    name = Path(values[0]).name.lower()
    for suffix in (".exe", ".cmd", ".bat", ".ps1"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    return name == "cursor"


def normalized_executable(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return os.path.normcase(str(Path(value).expanduser().resolve(strict=False)))
    except (OSError, RuntimeError, ValueError):
        return os.path.normcase(str(value))


def process_identity(snapshot: Any) -> tuple[int, float]:
    return snapshot.pid, snapshot.create_time


def process_baseline(executable: str | None) -> set[tuple[int, float]]:
    """Return exact PID/create-time identities already using this executable."""
    target = normalized_executable(executable)
    if target is None:
        return set()
    identities: set[tuple[int, float]] = set()
    try:
        processes = psutil.process_iter(["pid", "create_time", "exe"])
    except (OSError, RuntimeError):
        return identities
    for process in processes:
        try:
            info = process.info
            if normalized_executable(info.get("exe")) == target:
                create_time = info.get("create_time")
                if isinstance(create_time, (int, float)):
                    identities.add((int(info["pid"]), float(create_time)))
        except (KeyError, OSError, psutil.Error):
            continue
    return identities


def _descends_from(snapshot: Any, root_pid: int, snapshots: dict[int, Any]) -> bool:
    current = snapshot
    visited: set[int] = set()
    while current.ppid > 0 and current.ppid not in visited:
        if current.ppid == root_pid:
            return True
        visited.add(current.ppid)
        parent = snapshots.get(current.ppid)
        if parent is None:
            return False
        current = parent
    return False


def select_handoff_candidate(
    snapshots: Iterable[Any],
    *,
    root: Any,
    executable: str | None,
    baseline: set[tuple[int, float]],
) -> CursorHandoff:
    """Select exactly one newly-created descendant of the launcher.

    The function intentionally abstains when process ancestry or identity is
    ambiguous. It never searches by the string ``Cursor.exe`` alone.
    """
    target = normalized_executable(executable)
    if target is None:
        return CursorHandoff("unattributed_no_executable")
    snapshot_map = {snapshot.pid: snapshot for snapshot in snapshots}
    candidates = []
    for snapshot in snapshot_map.values():
        identity = process_identity(snapshot)
        if identity == process_identity(root) or identity in baseline:
            continue
        if normalized_executable(snapshot.exe) != target:
            continue
        if snapshot.create_time < root.create_time:
            continue
        if not _descends_from(snapshot, root.pid, snapshot_map):
            continue
        try:
            process = psutil.Process(snapshot.pid)
            if process.is_running() and process.status() != psutil.STATUS_ZOMBIE:
                candidates.append((snapshot, process))
        except psutil.Error:
            continue
    if not candidates:
        return CursorHandoff("no_attributed_candidate")
    if len(candidates) != 1:
        return CursorHandoff("ambiguous_candidates")
    snapshot, process = candidates[0]
    return CursorHandoff("handoff", snapshot=snapshot, process=process)


def run_cursor_handoff(
    collector: Any,
    *,
    root_snapshot: Any,
    executable: str,
    baseline: set[tuple[int, float]],
) -> None:
    """Keep Live attached to one identity-safe GUI successor until it exits."""
    snapshots = [
        *collector._seen_processes.values(),
        *collector._discovered_processes.values(),
        root_snapshot,
    ]
    handoff = select_handoff_candidate(
        snapshots,
        root=root_snapshot,
        executable=executable,
        baseline=baseline,
    )
    collector._cursor_handoff_info["cursor_handoff_status"] = handoff.status
    if handoff.status != "handoff" or handoff.process is None or handoff.snapshot is None:
        return

    collector._preserved_processes.add((handoff.snapshot.pid, handoff.snapshot.create_time))
    collector._cursor_handoff_info.update(
        {
            "cursor_handoff_pid": handoff.snapshot.pid,
            "cursor_handoff_create_time": handoff.snapshot.create_time,
            "cursor_handoff_status": "active",
        }
    )
    while collector._process_is_live(handoff.process):
        collector._sample_process_tree(handoff.process)
        time.sleep(collector.poll_interval)
    collector._sample_process_tree(handoff.process)
    collector._mark_disappeared_processes(set())
    collector._cursor_handoff_info["cursor_handoff_status"] = "completed"
