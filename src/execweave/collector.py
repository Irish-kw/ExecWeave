from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import psutil

from .auto_specialized import (
    auto_specialized_launch,
    auto_specialized_probe,
    prepare_post_command_specialized_probe,
    run_post_command_specialized_probe,
)
from .command import resolve_launch_command
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
    create_time: float

    @property
    def entity(self) -> Entity:
        identity = f"{self.pid}:{int(self.create_time * 1_000_000)}"
        return Entity(
            type="process",
            id=f"process:{identity}",
            name=self.name,
            attributes={
                "pid": self.pid,
                "ppid": self.ppid,
                "cmdline": self.cmdline,
                "exe": self.exe,
                "create_time": self.create_time,
            },
        )


def _safe_process_snapshot(proc: psutil.Process) -> ProcessSnapshot | None:
    try:
        with proc.oneshot():
            try:
                exe = proc.exe()
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                exe = None
            return ProcessSnapshot(
                pid=proc.pid,
                ppid=proc.ppid(),
                name=proc.name(),
                cmdline=proc.cmdline(),
                exe=exe,
                create_time=proc.create_time(),
            )
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
    basename = Path(parts[0]).name
    executable = basename.lower()
    for suffix in (".exe", ".cmd", ".bat", ".ps1"):
        if executable.endswith(suffix):
            executable = executable[: -len(suffix)]
            break
    known = {
        "claude": "Claude Code",
        "codex": "OpenAI Codex",
        "agy": "Antigravity",
        "antigravity": "Antigravity",
        "gemini": "Gemini CLI",
        "cursor": "Cursor",
        "opencode": "OpenCode",
        "ollama": "Ollama",
    }
    return known.get(executable, basename)


class RuntimeCollector:
    """Portable polling collector used on all platforms and as a fallback backend."""

    backend_name = "portable"

    def __init__(
        self,
        *,
        session_id: str,
        sink: JsonlSink,
        watch_root: Path,
        poll_interval: float = 0.10,
        collect_filesystem: bool = True,
        collect_network: bool = True,
    ) -> None:
        self.session_id = session_id
        self.sink = sink
        self.watch_root = watch_root.expanduser().resolve()
        self.poll_interval = max(0.02, poll_interval)
        self.collect_filesystem = collect_filesystem
        self.collect_network = collect_network
        self._seen_processes: dict[int, ProcessSnapshot] = {}
        self._seen_connections: set[tuple[str, str | None, str | None, str]] = set()

    def run(self, command: list[str]) -> int:
        if not command:
            raise ValueError("command must not be empty")

        launch_command = resolve_launch_command(command)
        agent_name = infer_agent_name(command)
        agent = Entity(type="agent", id=f"agent:{agent_name}", name=agent_name)
        session = Entity(
            type="session",
            id=f"session:{self.session_id}",
            name=self.session_id,
            attributes={
                "command": command,
                "cwd": str(self.watch_root),
                "backend": self.backend_name,
            },
        )
        self.sink.emit(
            RuntimeEvent.create(
                session_id=self.session_id,
                event_type="session.started",
                relation="STARTED_SESSION",
                source=agent,
                target=session,
                attributes={"collector_pid": os.getpid(), "backend": self.backend_name},
            )
        )

        watcher: FileWatcher | None = None
        internal_root = self.watch_root / ".execweave"
        if self.collect_filesystem:
            watcher = FileWatcher(
                root=self.watch_root,
                session_id=self.session_id,
                session_entity=session,
                sink=self.sink,
                excluded_roots=[internal_root, self.sink.path],
            )
            watcher.start()

        process: subprocess.Popen[bytes] | None = None
        return_code = 1
        post_command_probe = prepare_post_command_specialized_probe(command)
        try:
            with auto_specialized_launch(command) as launch_environment:
                process = subprocess.Popen(
                    launch_command,
                    cwd=str(self.watch_root),
                    env=launch_environment,
                )
                root = psutil.Process(process.pid)
                snapshot = _safe_process_snapshot(root)
                if snapshot is not None:
                    self._record_process_start(snapshot, parent=session, relation="LAUNCHED")

                with auto_specialized_probe(command):
                    while process.poll() is None:
                        self._sample_process_tree(root)
                        time.sleep(self.poll_interval)

                    self._sample_process_tree(root)
                    self._mark_disappeared_processes(set())
                return_code = int(process.returncode or 0)
            run_post_command_specialized_probe(
                post_command_probe,
                return_code=return_code,
            )
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
                        "backend": self.backend_name,
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
        process_objects: dict[int, psutil.Process] = {}
        for proc in processes:
            snapshot = _safe_process_snapshot(proc)
            if snapshot is None:
                continue
            current[snapshot.pid] = snapshot
            process_objects[snapshot.pid] = proc

        for snapshot in current.values():
            if snapshot.pid not in self._seen_processes:
                parent_snapshot = current.get(snapshot.ppid) or self._seen_processes.get(
                    snapshot.ppid
                )
                parent = (
                    parent_snapshot.entity
                    if parent_snapshot is not None
                    else Entity(
                        type="process_reference",
                        id=f"process-pid:{snapshot.ppid}",
                        name=str(snapshot.ppid),
                        attributes={"pid": snapshot.ppid, "unresolved": True},
                    )
                )
                self._record_process_start(snapshot, parent=parent, relation="SPAWNED")
            if self.collect_network:
                self._sample_network(process_objects[snapshot.pid], snapshot)

        self._mark_disappeared_processes(set(current))

    def _record_process_start(
        self,
        snapshot: ProcessSnapshot,
        *,
        parent: Entity,
        relation: str,
    ) -> None:
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
                attributes={
                    "attribution": "polling",
                    "causal": relation == "LAUNCHED",
                    "backend": self.backend_name,
                },
            )
        )

    def _mark_disappeared_processes(self, active_pids: set[int]) -> None:
        for pid in list(self._seen_processes):
            if pid in active_pids or psutil.pid_exists(pid):
                continue
            snapshot = self._seen_processes.pop(pid)
            self.sink.emit(
                RuntimeEvent.create(
                    session_id=self.session_id,
                    event_type="process.exited",
                    relation="EXITED",
                    source=snapshot.entity,
                    attributes={"attribution": "polling", "backend": self.backend_name},
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
            key = (snapshot.entity.id, local, remote, status)
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
                    attributes={
                        "local_address": local,
                        "remote_address": remote,
                        "status": status,
                        "attribution": "process_polling",
                        "causal": True,
                        "backend": self.backend_name,
                    },
                )
            )
