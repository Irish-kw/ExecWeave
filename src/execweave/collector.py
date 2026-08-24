from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import psutil

from .filesystem import FileWatcher
from .schema import Entity, RuntimeEvent
from .sink import JsonlSink


@dataclass(frozen=True)
class ProcessSnapshot:
    pid: int
    ppid: int
    name: str
    cmdline: list[str]
    exe: str | None

    @property
    def entity(self) -> Entity:
        return Entity(
            type="process",
            id=f"process:{self.pid}",
            name=self.name,
            attributes={
                "pid": self.pid,
                "ppid": self.ppid,
                "cmdline": self.cmdline,
                "exe": self.exe,
            },
        )


def _safe_process_snapshot(proc: psutil.Process) -> ProcessSnapshot | None:
    try:
        with proc.oneshot():
            return ProcessSnapshot(
                pid=proc.pid,
                ppid=proc.ppid(),
                name=proc.name(),
                cmdline=proc.cmdline(),
                exe=_safe_exe(proc),
            )
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return None


def _safe_exe(proc: psutil.Process) -> str | None:
    try:
        return proc.exe()
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return None


def _format_address(address: object) -> str | None:
    if not address:
        return None
    ip = getattr(address, "ip", None)
    port = getattr(address, "port", None)
    if ip is not None and port is not None:
        return f"{ip}:{port}"
    if isinstance(address, tuple) and len(address) >= 2:
        return f"{address[0]}:{address[1]}"
    return str(address)


def infer_agent_name(command: Iterable[str]) -> str:
    parts = list(command)
    if not parts:
        return "unknown-agent"
    executable = Path(parts[0]).name.lower()
    known = {
        "claude": "Claude Code",
        "claude.exe": "Claude Code",
        "codex": "OpenAI Codex",
        "codex.exe": "OpenAI Codex",
        "gemini": "Gemini CLI",
        "gemini.exe": "Gemini CLI",
        "opencode": "OpenCode",
        "opencode.exe": "OpenCode",
    }
    return known.get(executable, Path(parts[0]).name)


class RuntimeCollector:
    """Phase 1 local runtime collector.

    The collector launches one command as an ExecWeave session and observes the
    resulting process tree. Process/network observations are process-attributed.
    Filesystem changes are session-correlated only in this initial polling MVP.
    """

    def __init__(
        self,
        *,
        session_id: str,
        sink: JsonlSink,
        watch_root: Path,
        poll_interval: float = 0.25,
        collect_filesystem: bool = True,
        collect_network: bool = True,
    ) -> None:
        self.session_id = session_id
        self.sink = sink
        self.watch_root = watch_root.expanduser().resolve()
        self.poll_interval = max(0.05, poll_interval)
        self.collect_filesystem = collect_filesystem
        self.collect_network = collect_network
        self._seen_processes: dict[int, ProcessSnapshot] = {}
        self._seen_connections: set[tuple[int, str | None, str | None, str]] = set()

    def run(self, command: list[str]) -> int:
        if not command:
            raise ValueError("command must not be empty")

        agent_name = infer_agent_name(command)
        agent = Entity(type="agent", id=f"agent:{agent_name}", name=agent_name)
        session = Entity(
            type="session",
            id=f"session:{self.session_id}",
            name=self.session_id,
            attributes={"command": command, "cwd": str(self.watch_root)},
        )

        self.sink.emit(
            RuntimeEvent.create(
                session_id=self.session_id,
                event_type="session.started",
                relation="STARTED_SESSION",
                source=agent,
                target=session,
                attributes={"collector_pid": os.getpid()},
            )
        )

        watcher: FileWatcher | None = None
        if self.collect_filesystem:
            watcher = FileWatcher(
                root=self.watch_root,
                session_id=self.session_id,
                session_entity=session,
                sink=self.sink,
                excluded_roots=[self.sink.path.parent.parent],
            )
            watcher.start()

        process: subprocess.Popen[bytes] | None = None
        return_code = 1
        try:
            process = subprocess.Popen(command, cwd=str(self.watch_root))
            root = psutil.Process(process.pid)
            root_snapshot = _safe_process_snapshot(root)
            if root_snapshot is not None:
                self._record_process_start(root_snapshot, parent=session, relation="LAUNCHED")

            while process.poll() is None:
                self._sample_process_tree(root)
                time.sleep(self.poll_interval)

            self._sample_process_tree(root)
            self._mark_disappeared_processes(set())
            return_code = int(process.returncode or 0)
            return return_code
        finally:
            if watcher is not None:
                watcher.stop()
            self.sink.emit(
                RuntimeEvent.create(
                    session_id=self.session_id,
                    event_type="session.finished",
                    relation="FINISHED_SESSION",
                    source=session,
                    attributes={
                        "return_code": return_code,
                        "root_pid": process.pid if process is not None else None,
                    },
                )
            )

    def _sample_process_tree(self, root: psutil.Process) -> None:
        processes: list[psutil.Process] = []
        try:
            processes.append(root)
            processes.extend(root.children(recursive=True))
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass

        current: dict[int, ProcessSnapshot] = {}
        for proc in processes:
            snapshot = _safe_process_snapshot(proc)
            if snapshot is None:
                continue
            current[snapshot.pid] = snapshot
            if snapshot.pid not in self._seen_processes:
                parent_snapshot = self._seen_processes.get(snapshot.ppid)
                parent = (
                    parent_snapshot.entity
                    if parent_snapshot is not None
                    else Entity(type="process", id=f"process:{snapshot.ppid}", name=str(snapshot.ppid))
                )
                self._record_process_start(snapshot, parent=parent, relation="SPAWNED")
            if self.collect_network:
                self._sample_network(proc, snapshot)

        self._mark_disappeared_processes(set(current))

    def _record_process_start(self, snapshot: ProcessSnapshot, *, parent: Entity, relation: str) -> None:
        if snapshot.pid in self._seen_processes:
            return
        self._seen_processes[snapshot.pid] = snapshot
        self.sink.emit(
            RuntimeEvent.create(
                session_id=self.session_id,
                event_type="process.started",
                relation=relation,
                source=parent,
                target=snapshot.entity,
            )
        )

    def _mark_disappeared_processes(self, active_pids: set[int]) -> None:
        for pid in list(self._seen_processes):
            if pid in active_pids:
                continue
            snapshot = self._seen_processes.pop(pid)
            self.sink.emit(
                RuntimeEvent.create(
                    session_id=self.session_id,
                    event_type="process.exited",
                    relation="EXITED",
                    source=snapshot.entity,
                )
            )

    def _sample_network(self, proc: psutil.Process, snapshot: ProcessSnapshot) -> None:
        try:
            getter = getattr(proc, "net_connections", None)
            connections = getter(kind="inet") if getter else proc.connections(kind="inet")
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, OSError):
            return

        for connection in connections:
            remote = _format_address(connection.raddr)
            if remote is None:
                continue
            local = _format_address(connection.laddr)
            status = str(getattr(connection, "status", ""))
            key = (snapshot.pid, local, remote, status)
            if key in self._seen_connections:
                continue
            self._seen_connections.add(key)
            endpoint = Entity(type="network_endpoint", id=f"endpoint:{remote}", name=remote)
            self.sink.emit(
                RuntimeEvent.create(
                    session_id=self.session_id,
                    event_type="network.connection",
                    relation="CONNECTED_TO",
                    source=snapshot.entity,
                    target=endpoint,
                    attributes={"local_address": local, "remote_address": remote, "status": status},
                )
            )
