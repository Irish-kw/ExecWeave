from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import psutil

from . import __version__
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
        self._discovered_processes: dict[int, ProcessSnapshot] = {}
        self._seen_connections: set[tuple[str, str | None, str | None, str]] = set()
        self._network_sample_attempts = 0
        self._network_sample_successes = 0
        self._network_sample_errors = 0
        self._network_access_denied = 0

    def _filesystem_excluded_roots(self) -> list[Path]:
        """Return ExecWeave-owned paths that must never become workload evidence.

        The default ``.execweave`` tree and the runtime event stream were already
        internal. Live mode can also place ``events.jsonl`` and ``semantic.jsonl``
        together in a caller-selected output directory inside the watch root. When
        those files are siblings, exclude their whole run directory so ExecWeave's
        own evidence writes cannot recursively manufacture filesystem evidence.
        A separately configured semantic sidecar remains an exact-file exclusion.
        """
        sink_path = self.sink.path.expanduser().resolve()
        excluded = [(self.watch_root / ".execweave").resolve(), sink_path]
        configured = os.environ.get("EXECWEAVE_SEMANTIC_SIDECAR")
        if not configured:
            return excluded

        semantic_path = Path(configured).expanduser().resolve()
        excluded.append(
            semantic_path.parent if semantic_path.parent == sink_path.parent else semantic_path
        )
        return excluded

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
                "execweave_version": __version__,
            },
        )
        self.sink.emit(
            RuntimeEvent.create(
                session_id=self.session_id,
                event_type="session.started",
                relation="STARTED_SESSION",
                source=agent,
                target=session,
                attributes={
                    "collector_pid": os.getpid(),
                    "backend": self.backend_name,
                    "execweave_version": __version__,
                },
            )
        )

        watcher: FileWatcher | None = None
        if self.collect_filesystem:
            watcher = FileWatcher(
                root=self.watch_root,
                session_id=self.session_id,
                session_entity=session,
                sink=self.sink,
                excluded_roots=self._filesystem_excluded_roots(),
            )

        process: subprocess.Popen[bytes] | None = None
        owned: list[psutil.Process] = []
        return_code = 1
        interrupted = False
        collector_error_type: str | None = None
        workload_terminated_due_to_collector_error = False
        post_command_probe = prepare_post_command_specialized_probe(command)
        try:
            if watcher is not None:
                watcher.start()

            try:
                with auto_specialized_launch(
                    command,
                    server_relay=True,
                ) as launch_environment:
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
            except KeyboardInterrupt:
                interrupted = True
                return_code = 130

            if not interrupted:
                run_post_command_specialized_probe(
                    post_command_probe,
                    return_code=return_code,
                )
            return return_code
        except BaseException as exc:
            collector_error_type = type(exc).__name__
            raise
        finally:
            # A workload exception is a nonzero child exit, not an exception in
            # this collector. Finalize observed descendants on every exit path,
            # including successful launchers that leave reparented children.
            if process is not None:
                owned = self._owned_live_processes(process)
                workload_terminated_due_to_collector_error = (
                    collector_error_type is not None and bool(owned)
                )
                self._terminate_process_tree(process, owned=owned)
            if watcher is not None:
                watcher.stop()
            # A failed termination must not become a false clean result merely
            # because the selected child has since reparented out of the tree.
            workload_alive_after_cleanup = any(
                self._process_is_live(candidate) for candidate in owned
            ) or bool(process is not None and self._owned_live_processes(process))
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
                        "interrupted": interrupted,
                        "collector_failed": collector_error_type is not None,
                        "collector_error_type": collector_error_type,
                        "workload_terminated_due_to_collector_error": (
                            workload_terminated_due_to_collector_error
                        ),
                        "workload_alive_after_cleanup": workload_alive_after_cleanup,
                        "network_collection_status": self._network_collection_status(),
                        "network_sample_attempts": self._network_sample_attempts,
                        "network_sample_successes": self._network_sample_successes,
                        "network_sample_errors": self._network_sample_errors,
                        "network_access_denied": self._network_access_denied,
                        "execweave_version": __version__,
                    },
                )
            )

    @staticmethod
    def _process_is_live(proc: psutil.Process) -> bool:
        try:
            if not proc.is_running():
                return False
            try:
                return proc.status() != psutil.STATUS_ZOMBIE
            except psutil.AccessDenied:
                return True
        except (psutil.NoSuchProcess, psutil.ZombieProcess):
            return False

    def _process_for_snapshot(self, snapshot: ProcessSnapshot) -> psutil.Process | None:
        try:
            process = psutil.Process(snapshot.pid)
            # Cleanup needs identity, not readable exe/name/cmdline metadata.
            # Never treat a reused PID as the process we originally observed.
            if process.create_time() != snapshot.create_time:
                return None
            return process
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            return None

    def _owned_live_processes(
        self,
        process: subprocess.Popen[bytes],
    ) -> list[psutil.Process]:
        """Return live processes still owned by this collector's launched workload.

        A shell or launcher can exit before its children. Relying only on the current
        root process tree then loses those reparented descendants. The collector's
        lifetime-qualified process snapshots preserve enough ownership evidence to
        find and clean them without risking a reused PID.
        """
        owned: dict[int, psutil.Process] = {}

        def add_with_descendants(candidate: psutil.Process) -> None:
            if not self._process_is_live(candidate):
                return
            owned[candidate.pid] = candidate
            try:
                descendants = candidate.children(recursive=True)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                descendants = []
            for child in descendants:
                if self._process_is_live(child):
                    owned[child.pid] = child

        if process.poll() is None:
            try:
                add_with_descendants(psutil.Process(process.pid))
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass

        snapshots = {**self._seen_processes, **self._discovered_processes}
        for snapshot in snapshots.values():
            tracked = self._process_for_snapshot(snapshot)
            if tracked is not None:
                add_with_descendants(tracked)

        return list(owned.values())

    def _terminate_process_tree(
        self,
        process: subprocess.Popen[bytes],
        *,
        owned: list[psutil.Process] | None = None,
    ) -> None:
        # A caller's selection must survive reparenting between discovery and
        # termination. Re-querying here can lose children we just proved owned.
        if owned is None:
            owned = self._owned_live_processes(process)
        # Terminate descendants/tracked orphans before the launcher/root when it is
        # still alive. Holding psutil handles also keeps cleanup robust if a parent
        # exits while the loop is running.
        for candidate in sorted(owned, key=lambda item: item.pid == process.pid):
            try:
                candidate.terminate()
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass

        if owned:
            _, alive = psutil.wait_procs(owned, timeout=2.0)
            for candidate in alive:
                try:
                    candidate.kill()
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass
            if alive:
                psutil.wait_procs(alive, timeout=2.0)

        try:
            process.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            try:
                process.kill()
            except OSError:
                return
            try:
                process.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                pass

    @staticmethod
    def _same_process_lifetime(left: ProcessSnapshot, right: ProcessSnapshot) -> bool:
        return left.entity.id == right.entity.id

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

        # Preserve the complete discovered tree before any event/network callback
        # can raise. _seen_processes only contains successfully registered starts;
        # a root callback can fail after its children have already reparented.
        # Retain only the latest sample here, not an unbounded lifetime history.
        self._discovered_processes = current
        for snapshot in current.values():
            previous = self._seen_processes.get(snapshot.pid)
            if previous is None or not self._same_process_lifetime(previous, snapshot):
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
        previous = self._seen_processes.get(snapshot.pid)
        if previous is not None:
            if self._same_process_lifetime(previous, snapshot):
                return
            self._seen_processes.pop(snapshot.pid, None)
            self._record_process_exit(previous, reason="pid_reused")

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

    def _record_process_exit(self, snapshot: ProcessSnapshot, *, reason: str | None = None) -> None:
        attributes: dict[str, object] = {
            "attribution": "polling",
            "backend": self.backend_name,
        }
        if reason is not None:
            attributes["reason"] = reason
        self.sink.emit(
            RuntimeEvent.create(
                session_id=self.session_id,
                event_type="process.exited",
                relation="EXITED",
                source=snapshot.entity,
                attributes=attributes,
            )
        )

    def _mark_disappeared_processes(self, active_pids: set[int]) -> None:
        for pid in list(self._seen_processes):
            if pid in active_pids:
                continue

            previous = self._seen_processes[pid]
            if psutil.pid_exists(pid):
                try:
                    live_process = psutil.Process(pid)
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    # pid_exists() and Process(pid) are inherently racy. Without a
                    # lifetime snapshot, do not manufacture an EXITED observation.
                    continue
                current = _safe_process_snapshot(live_process)
                if current is None or self._same_process_lifetime(previous, current):
                    continue

            snapshot = self._seen_processes.pop(pid)
            self._record_process_exit(snapshot)

    def _network_collection_status(self) -> str:
        if not self.collect_network:
            return "not_requested"
        if self._network_sample_successes and self._network_sample_errors:
            return "degraded"
        if self._network_sample_successes:
            return "available"
        if self._network_sample_errors:
            return "unavailable"
        return "not_sampled"

    def _sample_network(self, proc: psutil.Process, snapshot: ProcessSnapshot) -> None:
        self._network_sample_attempts += 1
        try:
            getter = getattr(proc, "net_connections", None)
            connections = getter(kind="inet") if getter else proc.connections(kind="inet")
        except psutil.AccessDenied:
            self._network_sample_errors += 1
            self._network_access_denied += 1
            return
        except (psutil.NoSuchProcess, psutil.ZombieProcess):
            return
        except OSError:
            self._network_sample_errors += 1
            return

        self._network_sample_successes += 1
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
