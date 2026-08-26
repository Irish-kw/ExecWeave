from __future__ import annotations

import errno
import os
import sys
import warnings
from pathlib import Path
from typing import Iterable

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.polling import PollingObserver

from .schema import Entity, RuntimeEvent
from .sink import JsonlSink

LINUX_INOTIFY_MIN_SAFE_DIRS = 2048
LINUX_INOTIFY_MAX_SAFE_DIRS = 32768
_LINUX_INOTIFY_LIMIT = Path("/proc/sys/fs/inotify/max_user_watches")
_INOTIFY_RESOURCE_ERRNOS = {errno.ENOSPC, errno.EMFILE}


def _linux_inotify_directory_budget() -> int | None:
    """Return a conservative per-session directory budget on Linux.

    watchdog's recursive inotify observer consumes approximately one kernel watch
    per directory. ExecWeave does not know how many watches editors, language
    servers, containers, or other processes already consume, so it deliberately
    reserves most of the kernel limit for the rest of the system. The returned
    budget never exceeds one quarter of the configured per-user watch limit.
    """

    if not sys.platform.startswith("linux"):
        return None
    try:
        configured = int(_LINUX_INOTIFY_LIMIT.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        configured = 32768

    quarter = max(1, configured // 4)
    if quarter < LINUX_INOTIFY_MIN_SAFE_DIRS:
        return quarter
    return min(LINUX_INOTIFY_MAX_SAFE_DIRS, quarter)


def _tree_exceeds_directory_budget(root: Path, budget: int) -> bool:
    """Boundedly count directories without following symlinks.

    Count the tree watchdog's recursive native observer would have to watch,
    including directories whose *events* are later filtered. This intentionally
    avoids underestimating kernel pressure from large internal/cache trees.
    Traversal stops as soon as the budget is exceeded.
    """

    count = 1
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            iterator = os.scandir(current)
        except OSError:
            continue
        with iterator:
            for entry in iterator:
                try:
                    is_directory = entry.is_dir(follow_symlinks=False)
                except OSError:
                    continue
                if not is_directory:
                    continue
                count += 1
                if count > budget:
                    return True
                stack.append(Path(entry.path))
    return False


def _prefer_polling_on_linux(root: Path) -> tuple[bool, int | None]:
    budget = _linux_inotify_directory_budget()
    if budget is None:
        return False, None
    return _tree_exceeds_directory_budget(root, budget), budget


def _is_linux_inotify_resource_error(exc: OSError) -> bool:
    """Return whether watchdog failed because Linux inotify resources are exhausted."""

    return sys.platform.startswith("linux") and exc.errno in _INOTIFY_RESOURCE_ERRNOS


class SessionFileEventHandler(FileSystemEventHandler):
    """Record filesystem changes observed inside a watched session directory.

    Phase 1 intentionally records these as session-level observations. A filesystem
    change is not attributed to a specific process until a lower-level collector
    (for example eBPF/ETW) can prove that relationship.
    """

    def __init__(
        self,
        *,
        session_id: str,
        session_entity: Entity,
        sink: JsonlSink,
        excluded_roots: Iterable[Path] = (),
    ) -> None:
        super().__init__()
        self.session_id = session_id
        self.session_entity = session_entity
        self.sink = sink
        self.excluded_roots = tuple(path.resolve() for path in excluded_roots)

    def _excluded(self, path: str) -> bool:
        candidate = Path(path).expanduser().resolve()
        return any(candidate == root or root in candidate.parents for root in self.excluded_roots)

    def _emit(self, event: FileSystemEvent) -> None:
        if self._excluded(event.src_path):
            return

        src = Path(event.src_path).expanduser().resolve()
        target_path = src
        attributes: dict[str, object] = {
            "filesystem_event": event.event_type,
            "is_directory": event.is_directory,
            "attribution": "session_observation",
            "causal": False,
        }

        destination = getattr(event, "dest_path", None)
        if destination:
            dest = Path(destination).expanduser().resolve()
            if self._excluded(str(dest)):
                return
            attributes["source_path"] = str(src)
            attributes["destination_path"] = str(dest)
            target_path = dest

        entity_type = "directory" if event.is_directory else "file"
        target = Entity(type=entity_type, id=f"{entity_type}:{target_path}", name=target_path.name)
        self.sink.emit(
            RuntimeEvent.create(
                session_id=self.session_id,
                event_type=f"filesystem.{event.event_type}",
                relation="OBSERVED_FILE_CHANGE",
                source=self.session_entity,
                target=target,
                attributes=attributes,
            )
        )

    def on_any_event(self, event: FileSystemEvent) -> None:
        self._emit(event)


class FileWatcher:
    """Filesystem observation with resource-safe Linux fallbacks.

    Native OS notifications remain the default. On Linux, large recursive trees
    are preflighted before allocating inotify watches. If a tree exceeds the
    conservative session budget, or if the kernel still returns ENOSPC/EMFILE
    because other programs already consumed the watch/instance pool, ExecWeave
    falls back to watchdog's polling observer instead of aborting the run.

    The observation semantics stay session-level and non-causal. Only the
    collection mechanism and detection latency change.
    """

    def __init__(
        self,
        *,
        root: Path,
        session_id: str,
        session_entity: Entity,
        sink: JsonlSink,
        excluded_roots: Iterable[Path] = (),
    ) -> None:
        self.root = root.expanduser().resolve()
        self.handler = SessionFileEventHandler(
            session_id=session_id,
            session_entity=session_entity,
            sink=sink,
            excluded_roots=excluded_roots,
        )
        prefer_polling, budget = _prefer_polling_on_linux(self.root)
        self.observer_kind = "polling" if prefer_polling else "native"
        self.observer = PollingObserver(timeout=1.0) if prefer_polling else Observer()
        self.fallback_reason: str | None = None
        self._started = False
        if prefer_polling:
            self.fallback_reason = (
                "ExecWeave selected polling filesystem observation because this Linux "
                f"workspace exceeds the conservative recursive inotify budget ({budget} "
                "directories). File-change semantics are preserved, but detection may "
                "be less immediate."
            )

    def _schedule_and_start(self) -> None:
        self.observer.schedule(self.handler, str(self.root), recursive=True)
        self.observer.start()
        self._started = True

    def _shutdown_observer(self, timeout: float) -> None:
        try:
            self.observer.unschedule_all()
        except (AttributeError, RuntimeError):
            pass
        try:
            self.observer.stop()
        except RuntimeError:
            pass
        try:
            self.observer.join(timeout=timeout)
        except RuntimeError:
            pass
        self._started = False

    def start(self) -> None:
        if self.fallback_reason is not None:
            warnings.warn(self.fallback_reason, RuntimeWarning, stacklevel=2)
        try:
            self._schedule_and_start()
        except OSError as exc:
            if not _is_linux_inotify_resource_error(exc) or self.observer_kind == "polling":
                raise
            self._shutdown_observer(timeout=1)
            self.fallback_reason = (
                "Linux inotify watch or instance capacity was exhausted; ExecWeave is "
                "using polling filesystem observation for this session. File-change "
                "semantics are preserved, but detection may be less immediate."
            )
            warnings.warn(self.fallback_reason, RuntimeWarning, stacklevel=2)
            self.observer_kind = "polling"
            self.observer = PollingObserver(timeout=1.0)
            self._schedule_and_start()

    def stop(self) -> None:
        if not self._started:
            return
        self._shutdown_observer(timeout=5)
