from __future__ import annotations

from pathlib import Path
from typing import Iterable

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from .schema import Entity, RuntimeEvent
from .sink import JsonlSink


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
        self.observer = Observer()

    def start(self) -> None:
        self.observer.schedule(self.handler, str(self.root), recursive=True)
        self.observer.start()

    def stop(self) -> None:
        self.observer.stop()
        self.observer.join(timeout=5)
