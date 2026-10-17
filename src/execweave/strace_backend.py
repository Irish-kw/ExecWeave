from __future__ import annotations

import ast
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .auto_specialized import auto_specialized_launch
from .collector import infer_agent_name
from .command_privacy import public_command
from .schema import Entity, RuntimeEvent
from .private_io import write_private_text
from .sink import JsonlSink, _protect_git_run_directory

_TIMESTAMP_RE = re.compile(r"^(?P<ts>\d+(?:\.\d+)?)\s+(?P<body>.*)$")
_SYSCALL_RE = re.compile(r"^(?P<name>[a-zA-Z0-9_]+)\((?P<args>.*)\)\s+=\s+(?P<result>.*)$")
_CLONE_RESULT_RE = re.compile(r"^(?P<pid>\d+)(?:\s|$)")
_CLONE_THREAD_RE = re.compile(r"\bCLONE_THREAD\b")
_CONNECT_ERROR_RE = re.compile(r"^-1\s+(?P<errno>[A-Z0-9_]+)(?:\s|$)")
_EXIT_RE = re.compile(r"^\+\+\+ exited with (?P<code>-?\d+) \+\+\+$")
_KILLED_RE = re.compile(r"^\+\+\+ killed by (?P<signal>[A-Z0-9]+).*$")
_QUOTED_RE = re.compile(r'"((?:\\.|[^"\\])*)"')
_IPV4_RE = re.compile(
    r'sin_port=htons\((?P<port>\d+)\).*sin_addr=inet_addr\("(?P<host>[^"]+)"\)'
)
_IPV6_RE = re.compile(
    r'sin6_port=htons\((?P<port>\d+)\).*inet_pton\(AF_INET6, "(?P<host>[^"]+)"'
)
_UNIX_RE = re.compile(r'sun_path="(?P<path>[^"]+)"')
_DIRFD_RE = re.compile(r"^[^,]*<(?P<path>/[^>]*)>")


@dataclass(frozen=True)
class TraceRecord:
    timestamp: float
    pid: int
    body: str


def strace_available() -> bool:
    return sys.platform.startswith("linux") and shutil.which("strace") is not None


def _iso_timestamp(value: float) -> str:
    return datetime.fromtimestamp(value, timezone.utc).isoformat().replace("+00:00", "Z")


def _decode_quoted(value: str) -> str:
    # Synthetic Windows traces carry native drive paths with single
    # backslashes (for example ``C:\\tmp``).  Treating those as Python string
    # escapes turns ``\\t`` into a tab and corrupts the observed path.  Real
    # Linux strace paths still use the normal C-style decoding below.
    if re.match(r"^[A-Za-z]:[\\/]", value):
        return value.replace(r'\"', '"').replace(r"\\", "\\")
    try:
        return str(ast.literal_eval(f'"{value}"'))
    except (SyntaxError, ValueError):
        return value


def _quoted_arguments(args: str) -> list[str]:
    return [_decode_quoted(match.group(1)) for match in _QUOTED_RE.finditer(args)]


def _pid_from_trace_path(path: Path) -> int | None:
    suffix = path.name.rsplit(".", 1)[-1]
    try:
        return int(suffix)
    except ValueError:
        return None


def _merge_unfinished(lines: Iterable[str]) -> list[str]:
    merged: list[str] = []
    pending: dict[str, str] = {}
    for raw_line in lines:
        line = raw_line.rstrip("\n")
        timestamp_match = _TIMESTAMP_RE.match(line)
        if timestamp_match is None:
            merged.append(line)
            continue
        body = timestamp_match.group("body")
        if body.endswith("<unfinished ...>"):
            prefix = body[: -len("<unfinished ...>")].rstrip()
            syscall = prefix.split("(", 1)[0]
            pending[syscall] = f"{timestamp_match.group('ts')} {prefix}"
            continue
        resumed = re.match(
            r"^<\.\.\. (?P<name>[a-zA-Z0-9_]+) resumed>(?P<rest>.*)$",
            body,
        )
        if resumed is not None and resumed.group("name") in pending:
            original = pending.pop(resumed.group("name"))
            merged.append(original + resumed.group("rest"))
            continue
        merged.append(line)
    merged.extend(pending.values())
    return merged


def read_trace_records(trace_dir: Path, prefix: str = "trace") -> list[TraceRecord]:
    records: list[TraceRecord] = []
    for path in sorted(trace_dir.glob(f"{prefix}.*")):
        pid = _pid_from_trace_path(path)
        if pid is None:
            continue
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        for line in _merge_unfinished(lines):
            match = _TIMESTAMP_RE.match(line)
            if match is None:
                continue
            records.append(TraceRecord(float(match.group("ts")), pid, match.group("body")))
    records.sort(key=lambda record: (record.timestamp, record.pid))
    return records


class StraceParser:
    """Convert Linux strace output into graph-ready runtime events.

    This backend uses syscall evidence and therefore can attribute process creation,
    file-open/mutation operations, and outbound connect() calls to a concrete PID.
    """

    def __init__(
        self,
        *,
        session_id: str,
        sink: JsonlSink,
        watch_root: Path,
        command: list[str],
    ) -> None:
        self.session_id = session_id
        self.sink = sink
        self.watch_root = watch_root.expanduser().resolve()
        self.command = command
        self.session = Entity(
            type="session",
            id=f"session:{session_id}",
            name=session_id,
            attributes={
                "command": public_command(command),
                "argv_redacted": True,
                "cwd": str(self.watch_root),
                "backend": "strace",
            },
        )
        self._known_processes: set[int] = set()
        # Derive only the executable basename from execve; do not persist argv,
        # which may contain passwords or tokens in ordinary agent commands.
        self._executable_by_pid: dict[int, str] = {}
        self._cwd_by_pid: dict[int, Path] = {}
        self._parent_by_pid: dict[int, int] = {}
        # strace -ff uses TIDs as trace-file suffixes; CLONE_THREAD does not
        # create another process. Keep thread identity distinct from process.
        self._thread_leader_by_tid: dict[int, int] = {}
        self._spawn_origin_tid: dict[int, int] = {}

    def _process_pid(self, tid: int) -> int:
        """Map a traced thread to the native thread-group leader (TGID)."""
        seen: set[int] = set()
        while tid in self._thread_leader_by_tid and tid not in seen:
            seen.add(tid)
            tid = self._thread_leader_by_tid[tid]
        return tid

    @staticmethod
    def _is_thread_clone(name: str, args: str) -> bool:
        # An unrecognized/numeric clone flag is *not* assumed to be a thread.
        return name in {"clone", "clone3"} and _CLONE_THREAD_RE.search(args) is not None

    def _thread_entity(self, tid: int) -> Entity:
        leader = self._process_pid(tid)
        return Entity(
            type="thread", id=f"thread:{self.session_id}:{tid}", name=str(tid),
            attributes={"tid": tid, "tgid": leader, "backend": "strace"},
        )

    def process_entity(self, pid: int) -> Entity:
        pid = self._process_pid(pid)
        return Entity(
            type="process",
            id=f"process:{self.session_id}:{pid}",
            name=(f"{self._executable_by_pid[pid]} · {pid}"
                  if pid in self._executable_by_pid else str(pid)),
            attributes={
                "pid": pid,
                "identity_scope": "session",
                "backend": "strace",
            },
        )

    def parse(self, records: Iterable[TraceRecord]) -> None:
        materialized = list(records)
        self._index_process_parents(materialized)
        for record in materialized:
            self._parse_record(record)

    def _index_process_parents(self, records: Iterable[TraceRecord]) -> None:
        """Index fork/clone relationships before emitting events.

        strace timestamps can tie across per-PID trace files. Without a pre-pass,
        a child record that sorts before its parent's clone() record can be mistaken
        for a session root. The parent index makes process identity independent of
        cross-file ordering at equal timestamps.
        """
        for record in records:
            syscall = _SYSCALL_RE.match(record.body)
            if syscall is None or syscall.group("name") not in {"clone", "clone3", "fork", "vfork"}:
                continue
            child_match = _CLONE_RESULT_RE.match(syscall.group("result"))
            if child_match is None:
                continue
            child = int(child_match.group("pid"))
            if self._is_thread_clone(syscall.group("name"), syscall.group("args")):
                self._thread_leader_by_tid[child] = self._process_pid(record.pid)
            else:
                self._parent_by_pid[child] = self._process_pid(record.pid)
                self._spawn_origin_tid[child] = record.pid

    def _ensure_process(
        self,
        pid: int,
        timestamp: float,
        *,
        parent_pid: int | None = None,
        relation: str | None = None,
    ) -> None:
        pid = self._process_pid(pid)
        if parent_pid is not None:
            parent_pid = self._process_pid(parent_pid)
        if pid in self._known_processes:
            return
        if parent_pid is None:
            parent_pid = self._parent_by_pid.get(pid)
        self._known_processes.add(pid)
        if parent_pid is not None:
            self._cwd_by_pid[pid] = self._cwd_by_pid.get(parent_pid, self.watch_root)
        else:
            self._cwd_by_pid.setdefault(pid, self.watch_root)
        source = self.session if parent_pid is None else self.process_entity(parent_pid)
        relation = relation or ("LAUNCHED" if parent_pid is None else "SPAWNED")
        self.sink.emit(
            RuntimeEvent.create(
                session_id=self.session_id,
                event_type="process.started",
                relation=relation,
                source=source,
                target=self.process_entity(pid),
                timestamp=_iso_timestamp(timestamp),
                attributes={
                    "attribution": "syscall",
                    "causal": True,
                    "backend": "strace",
                    "spawn_origin_tid": self._spawn_origin_tid.get(pid),
                },
            )
        )

    def _parse_record(self, record: TraceRecord) -> None:
        exit_match = _EXIT_RE.match(record.body)
        if exit_match is not None:
            if record.pid in self._thread_leader_by_tid:
                self._emit_thread_exit(record, exit_code=int(exit_match.group("code")))
                return
            self._ensure_process(record.pid, record.timestamp)
            self.sink.emit(
                RuntimeEvent.create(
                    session_id=self.session_id,
                    event_type="process.exited",
                    relation="EXITED",
                    source=self.process_entity(record.pid),
                    timestamp=_iso_timestamp(record.timestamp),
                    attributes={
                        "exit_code": int(exit_match.group("code")),
                        "backend": "strace",
                    },
                )
            )
            return

        killed_match = _KILLED_RE.match(record.body)
        if killed_match is not None:
            if record.pid in self._thread_leader_by_tid:
                self._emit_thread_exit(record, signal=killed_match.group("signal"))
                return
            self._ensure_process(record.pid, record.timestamp)
            self.sink.emit(
                RuntimeEvent.create(
                    session_id=self.session_id,
                    event_type="process.exited",
                    relation="KILLED_BY",
                    source=self.process_entity(record.pid),
                    timestamp=_iso_timestamp(record.timestamp),
                    attributes={
                        "signal": killed_match.group("signal"),
                        "backend": "strace",
                    },
                )
            )
            return

        syscall = _SYSCALL_RE.match(record.body)
        if syscall is None:
            return
        name = syscall.group("name")
        args = syscall.group("args")
        result = syscall.group("result")
        self._ensure_process(record.pid, record.timestamp)

        if name in {"clone", "clone3", "fork", "vfork"}:
            self._parse_process_spawn(record, name, args, result)
        elif name in {"execve", "execveat"}:
            self._parse_exec(record, name, args, result)
        elif name == "chdir":
            self._parse_chdir(record, args, result)
        elif name in {"open", "openat", "openat2", "creat"}:
            self._parse_open(record, name, args, result)
        elif name in {"unlink", "unlinkat", "rmdir"}:
            self._parse_delete(record, name, args, result)
        elif name in {"mkdir", "mkdirat"}:
            self._parse_mkdir(record, name, args, result)
        elif name in {"rename", "renameat", "renameat2"}:
            self._parse_rename(record, name, args, result)
        elif name == "connect":
            self._parse_connect(record, args, result)

    def _emit_thread_exit(
        self, record: TraceRecord, *, exit_code: int | None = None,
        signal: str | None = None,
    ) -> None:
        self.sink.emit(RuntimeEvent.create(
            session_id=self.session_id, event_type="thread.exited",
            relation="EXITED_THREAD" if signal is None else "THREAD_KILLED_BY",
            source=self._thread_entity(record.pid),
            timestamp=_iso_timestamp(record.timestamp),
            attributes={"exit_code": exit_code, "signal": signal,
                        "attribution": "syscall", "backend": "strace"},
        ))

    def _parse_process_spawn(
        self, record: TraceRecord, name: str, args: str, result: str
    ) -> None:
        child_match = _CLONE_RESULT_RE.match(result)
        if child_match is None:
            return
        child_pid = int(child_match.group("pid"))
        if self._is_thread_clone(name, args):
            # CLONE_THREAD creates a task/TID in the same thread group, not a
            # new process. Retain the observed thread without inventing SPAWNED.
            self.sink.emit(RuntimeEvent.create(
                session_id=self.session_id, event_type="thread.started",
                relation="STARTED_THREAD",
                source=self.process_entity(record.pid),
                target=self._thread_entity(child_pid),
                timestamp=_iso_timestamp(record.timestamp),
                attributes={"syscall": name, "attribution": "syscall",
                            "causal": True, "backend": "strace"},
            ))
            return
        self._ensure_process(
            child_pid,
            record.timestamp,
            parent_pid=self._process_pid(record.pid),
            relation="SPAWNED",
        )

    def _parse_exec(self, record: TraceRecord, name: str, args: str, result: str) -> None:
        if not result.startswith("0"):
            return
        quoted = _quoted_arguments(args)
        if not quoted:
            return
        executable = quoted[0]
        target_path = self._resolve_path(record.pid, executable)
        self._executable_by_pid[self._process_pid(record.pid)] = target_path.name
        target = Entity(
            type="executable",
            id=f"executable:{target_path}",
            name=target_path.name,
        )
        self.sink.emit(
            RuntimeEvent.create(
                session_id=self.session_id,
                event_type="process.exec",
                relation="EXECUTED",
                source=self.process_entity(record.pid),
                target=target,
                timestamp=_iso_timestamp(record.timestamp),
                attributes={
                    "syscall": name,
                    "argument_count": max(0, len(quoted) - 1),
                    "backend": "strace",
                    "attribution": "syscall",
                    "causal": True,
                },
            )
        )

    def _parse_chdir(self, record: TraceRecord, args: str, result: str) -> None:
        if not result.startswith("0"):
            return
        quoted = _quoted_arguments(args)
        if not quoted:
            return
        new_cwd = self._resolve_path(record.pid, quoted[0])
        self._cwd_by_pid[self._process_pid(record.pid)] = new_cwd
        target = Entity(
            type="directory",
            id=f"directory:{new_cwd}",
            name=new_cwd.name,
        )
        self.sink.emit(
            RuntimeEvent.create(
                session_id=self.session_id,
                event_type="filesystem.chdir",
                relation="CHANGED_CWD_TO",
                source=self.process_entity(record.pid),
                target=target,
                timestamp=_iso_timestamp(record.timestamp),
                attributes={
                    "attribution": "syscall",
                    "causal": True,
                    "backend": "strace",
                },
            )
        )

    def _parse_open(self, record: TraceRecord, name: str, args: str, result: str) -> None:
        if result.startswith("-1"):
            return
        quoted = _quoted_arguments(args)
        if not quoted:
            return
        raw_path = quoted[0]
        path = self._resolve_open_path(record.pid, name, args, raw_path)
        flags = self._open_flags(name, args)
        relation = self._open_relation(flags, name)
        entity_type = "directory" if "O_DIRECTORY" in flags else "file"
        target = Entity(
            type=entity_type,
            id=f"{entity_type}:{path}",
            name=path.name,
        )
        self.sink.emit(
            RuntimeEvent.create(
                session_id=self.session_id,
                event_type="filesystem.open",
                relation=relation,
                source=self.process_entity(record.pid),
                target=target,
                timestamp=_iso_timestamp(record.timestamp),
                attributes={
                    "syscall": name,
                    "flags": flags,
                    "raw_path": raw_path,
                    "within_watch_root": self._within_watch_root(path),
                    "attribution": "syscall",
                    "causal": True,
                    "backend": "strace",
                },
            )
        )

    def _parse_delete(self, record: TraceRecord, name: str, args: str, result: str) -> None:
        if not result.startswith("0"):
            return
        quoted = _quoted_arguments(args)
        if not quoted:
            return
        path = self._resolve_open_path(record.pid, name, args, quoted[0])
        entity_type = "directory" if name == "rmdir" else "file"
        target = Entity(
            type=entity_type,
            id=f"{entity_type}:{path}",
            name=path.name,
        )
        self.sink.emit(
            RuntimeEvent.create(
                session_id=self.session_id,
                event_type="filesystem.delete",
                relation="DELETED",
                source=self.process_entity(record.pid),
                target=target,
                timestamp=_iso_timestamp(record.timestamp),
                attributes={
                    "syscall": name,
                    "within_watch_root": self._within_watch_root(path),
                    "attribution": "syscall",
                    "causal": True,
                    "backend": "strace",
                },
            )
        )

    def _parse_mkdir(self, record: TraceRecord, name: str, args: str, result: str) -> None:
        if not result.startswith("0"):
            return
        quoted = _quoted_arguments(args)
        if not quoted:
            return
        path = self._resolve_open_path(record.pid, name, args, quoted[0])
        target = Entity(
            type="directory",
            id=f"directory:{path}",
            name=path.name,
        )
        self.sink.emit(
            RuntimeEvent.create(
                session_id=self.session_id,
                event_type="filesystem.create",
                relation="CREATED",
                source=self.process_entity(record.pid),
                target=target,
                timestamp=_iso_timestamp(record.timestamp),
                attributes={
                    "syscall": name,
                    "within_watch_root": self._within_watch_root(path),
                    "attribution": "syscall",
                    "causal": True,
                    "backend": "strace",
                },
            )
        )

    def _parse_rename(self, record: TraceRecord, name: str, args: str, result: str) -> None:
        if not result.startswith("0"):
            return
        quoted = _quoted_arguments(args)
        if len(quoted) < 2:
            return
        source_path = self._resolve_path(record.pid, quoted[-2])
        destination_path = self._resolve_path(record.pid, quoted[-1])
        target = Entity(
            type="file",
            id=f"file:{destination_path}",
            name=destination_path.name,
        )
        self.sink.emit(
            RuntimeEvent.create(
                session_id=self.session_id,
                event_type="filesystem.rename",
                relation="RENAMED_TO",
                source=self.process_entity(record.pid),
                target=target,
                timestamp=_iso_timestamp(record.timestamp),
                attributes={
                    "syscall": name,
                    "source_path": str(source_path),
                    "destination_path": str(destination_path),
                    "within_watch_root": self._within_watch_root(destination_path),
                    "attribution": "syscall",
                    "causal": True,
                    "backend": "strace",
                },
            )
        )

    def _parse_connect(self, record: TraceRecord, args: str, result: str) -> None:
        family: str | None = None
        endpoint: str | None = None
        ipv4 = _IPV4_RE.search(args)
        if ipv4 is not None:
            family = "AF_INET"
            endpoint = f"{ipv4.group('host')}:{ipv4.group('port')}"
        else:
            ipv6 = _IPV6_RE.search(args)
            if ipv6 is not None:
                family = "AF_INET6"
                endpoint = f"[{ipv6.group('host')}]:{ipv6.group('port')}"
            else:
                unix = _UNIX_RE.search(args)
                if unix is not None:
                    family = "AF_UNIX"
                    endpoint = unix.group("path")
        if endpoint is None:
            return

        error_match = _CONNECT_ERROR_RE.match(result)
        connected = error_match is None and not result.startswith("-1")
        relation = "CONNECTED_TO" if connected else "CONNECT_ATTEMPTED"
        event_type = "network.connection" if connected else "network.connection_attempt"
        errno = error_match.group("errno") if error_match is not None else None

        target_type = "unix_socket" if family == "AF_UNIX" else "network_endpoint"
        target = Entity(
            type=target_type,
            id=f"{target_type}:{endpoint}",
            name=endpoint,
        )
        self.sink.emit(
            RuntimeEvent.create(
                session_id=self.session_id,
                event_type=event_type,
                relation=relation,
                source=self.process_entity(record.pid),
                target=target,
                timestamp=_iso_timestamp(record.timestamp),
                attributes={
                    "family": family,
                    "endpoint": endpoint,
                    "syscall": "connect",
                    "result": result,
                    "errno": errno,
                    "connected": connected,
                    "attribution": "syscall",
                    "causal": True,
                    "backend": "strace",
                },
            )
        )

    def _resolve_open_path(self, pid: int, syscall: str, args: str, raw_path: str) -> Path:
        path = Path(raw_path).expanduser()
        if path.is_absolute():
            return path.resolve(strict=False)
        if syscall in {"openat", "openat2", "unlinkat", "mkdirat"}:
            dirfd_match = _DIRFD_RE.search(args)
            if dirfd_match is not None:
                return (Path(dirfd_match.group("path")) / path).resolve(strict=False)
        return self._resolve_path(pid, raw_path)

    def _resolve_path(self, pid: int, raw_path: str) -> Path:
        path = Path(raw_path).expanduser()
        if path.is_absolute():
            return path.resolve(strict=False)
        cwd = self._cwd_by_pid.get(self._process_pid(pid), self.watch_root)
        return (cwd / path).resolve(strict=False)

    def _within_watch_root(self, path: Path) -> bool:
        return path == self.watch_root or self.watch_root in path.parents

    @staticmethod
    def _open_flags(syscall: str, args: str) -> str:
        if syscall == "creat":
            return "O_WRONLY|O_CREAT|O_TRUNC"
        quoted = list(_QUOTED_RE.finditer(args))
        if not quoted:
            return ""
        after_path = args[quoted[0].end() :].lstrip(", ")
        return after_path.split(",", 1)[0].strip()

    @staticmethod
    def _open_relation(flags: str, syscall: str) -> str:
        if syscall == "creat" or "O_CREAT" in flags:
            return "OPENED_WRITE"
        if "O_RDWR" in flags:
            return "OPENED_READ_WRITE"
        if any(flag in flags for flag in ("O_WRONLY", "O_TRUNC", "O_APPEND")):
            return "OPENED_WRITE"
        return "OPENED_READ"


class StraceRuntimeCollector:
    """Linux reference backend with syscall-attributed runtime evidence."""

    backend_name = "strace"

    def __init__(
        self,
        *,
        session_id: str,
        sink: JsonlSink,
        watch_root: Path,
        collect_filesystem: bool = True,
        collect_network: bool = True,
        trace_root: Path | None = None,
        keep_raw_trace: bool = False,
    ) -> None:
        self.session_id = session_id
        self.sink = sink
        self.watch_root = watch_root.expanduser().resolve()
        self.collect_filesystem = collect_filesystem
        self.collect_network = collect_network
        self.trace_root = (
            trace_root or (self.watch_root / ".execweave" / "traces" / session_id)
        ).resolve()
        self.keep_raw_trace = keep_raw_trace

    def _prepare_trace_directory(self) -> None:
        """Guard private, potentially secret-bearing native trace evidence."""
        # Native syscall traces can include entire execve argv and are much more
        # sensitive than projected event/graph evidence. Protect the dedicated
        # directory even when the caller sends graph output elsewhere.
        self.trace_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.trace_root.chmod(0o700)
        _protect_git_run_directory(self.trace_root / "trace")
        raw_ignore = self.trace_root / ".gitignore"
        try:
            write_private_text(raw_ignore, "*\n")
        except FileExistsError:
            # A custom ignore file that does not protect the raw trace is
            # insufficient: fail closed rather than retaining stageable argv.
            if raw_ignore.read_text(encoding="utf-8") != "*\n":
                raise ValueError("native strace directory must ignore all raw traces")

    def run(self, command: list[str]) -> int:
        if not command:
            raise ValueError("command must not be empty")
        executable = shutil.which("strace")
        if not sys.platform.startswith("linux") or executable is None:
            raise RuntimeError("The strace backend requires Linux and the strace executable")

        self._prepare_trace_directory()
        trace_prefix = self.trace_root / "trace"
        agent_name = infer_agent_name(command)
        agent = Entity(type="agent", id=f"agent:{agent_name}", name=agent_name)
        session = Entity(
            type="session",
            id=f"session:{self.session_id}",
            name=self.session_id,
            attributes={
                "command": public_command(command),
                "argv_redacted": True,
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

        trace_expression = "%process"
        if self.collect_filesystem:
            trace_expression += ",%file"
        if self.collect_network:
            trace_expression += ",%network"
        strace_command = [
            executable,
            "-ff",
            "-ttt",
            "-T",
            "-yy",
            "-s",
            "256",
            "-o",
            str(trace_prefix),
            "-e",
            f"trace={trace_expression}",
            "--",
            *command,
        ]
        return_code = 1
        try:
            with auto_specialized_launch(
                command,
                server_relay=True,
            ) as launch_environment:
                completed = subprocess.run(
                    strace_command,
                    cwd=str(self.watch_root),
                    env=launch_environment,
                    check=False,
                    umask=0o077,  # strace creates raw trace files mode 0600
                )
            return_code = int(completed.returncode)
            records = read_trace_records(self.trace_root)
            parser = StraceParser(
                session_id=self.session_id,
                sink=self.sink,
                watch_root=self.watch_root,
                command=command,
            )
            parser.parse(records)
            return return_code
        finally:
            if not self.keep_raw_trace:
                shutil.rmtree(self.trace_root, ignore_errors=True)
            self.sink.emit(
                RuntimeEvent.create(
                    session_id=self.session_id,
                    event_type="session.finished",
                    relation="FINISHED_SESSION",
                    source=session,
                    attributes={
                        "return_code": return_code,
                        "backend": self.backend_name,
                        "raw_trace_kept": self.keep_raw_trace,
                        "trace_directory": str(self.trace_root) if self.keep_raw_trace else None,
                    },
                )
            )
