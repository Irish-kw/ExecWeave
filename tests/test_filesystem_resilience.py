from __future__ import annotations

import errno
import json
import sys
import warnings
from pathlib import Path

import pytest
from watchdog.events import FileModifiedEvent

import execweave.collector as collector_module
import execweave.filesystem as filesystem_module
from execweave.collector import RuntimeCollector
from execweave.filesystem import FileWatcher, SessionFileEventHandler
from execweave.schema import Entity
from execweave.sink import JsonlSink


class _CaptureSink:
    def __init__(self) -> None:
        self.events = []

    def emit(self, event) -> None:
        self.events.append(event)


class _ObserverBase:
    instances = []

    def __init__(self, *args, **kwargs) -> None:
        self.scheduled = []
        self.started = False
        self.stopped = False
        self.unscheduled = False
        type(self).instances.append(self)

    def schedule(self, handler, path, recursive=False):
        self.scheduled.append((handler, path, recursive))

    def start(self) -> None:
        self.started = True

    def unschedule_all(self) -> None:
        self.unscheduled = True

    def stop(self) -> None:
        self.stopped = True

    def join(self, timeout=None) -> None:
        return None


class _PollingObserver(_ObserverBase):
    instances = []


def _session() -> Entity:
    return Entity(type="session", id="session:s1", name="s1")


def _watcher(tmp_path: Path) -> FileWatcher:
    return FileWatcher(
        root=tmp_path,
        session_id="s1",
        session_entity=_session(),
        sink=_CaptureSink(),
    )


def test_linux_inotify_budget_respects_small_kernel_limit(monkeypatch, tmp_path: Path) -> None:
    limit = tmp_path / "max_user_watches"
    limit.write_text("4096\n", encoding="utf-8")
    monkeypatch.setattr(filesystem_module.sys, "platform", "linux")
    monkeypatch.setattr(filesystem_module, "_LINUX_INOTIFY_LIMIT", limit)

    assert filesystem_module._linux_inotify_directory_budget() == 1024


@pytest.mark.parametrize("error_number", [errno.ENOSPC, errno.EMFILE])
def test_inotify_resource_exhaustion_during_start_falls_back_to_polling(
    monkeypatch,
    tmp_path: Path,
    error_number: int,
) -> None:
    class _ExhaustedObserver(_ObserverBase):
        instances = []

        def start(self) -> None:
            raise OSError(error_number, "inotify resource limit reached")

    _PollingObserver.instances = []
    monkeypatch.setattr(filesystem_module, "_prefer_polling_on_linux", lambda root: (False, 2048))
    monkeypatch.setattr(filesystem_module, "_is_linux_inotify_resource_error", lambda exc: exc.errno in {errno.ENOSPC, errno.EMFILE})
    monkeypatch.setattr(filesystem_module, "Observer", _ExhaustedObserver)
    monkeypatch.setattr(filesystem_module, "PollingObserver", _PollingObserver)

    watcher = _watcher(tmp_path)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        watcher.start()

    assert watcher.observer_kind == "polling"
    assert watcher._started is True
    assert watcher.fallback_reason is not None
    assert "watch or instance capacity was exhausted" in watcher.fallback_reason
    assert _ExhaustedObserver.instances[-1].unscheduled is True
    assert _PollingObserver.instances[-1].started is True
    assert caught
    watcher.stop()


@pytest.mark.parametrize("error_number", [errno.ENOSPC, errno.EMFILE])
def test_inotify_resource_exhaustion_during_schedule_falls_back_to_polling(
    monkeypatch,
    tmp_path: Path,
    error_number: int,
) -> None:
    class _ScheduleExhaustedObserver(_ObserverBase):
        instances = []

        def schedule(self, handler, path, recursive=False):
            raise OSError(error_number, "inotify resource limit reached")

    _PollingObserver.instances = []
    monkeypatch.setattr(filesystem_module, "_prefer_polling_on_linux", lambda root: (False, 2048))
    monkeypatch.setattr(filesystem_module, "_is_linux_inotify_resource_error", lambda exc: exc.errno in {errno.ENOSPC, errno.EMFILE})
    monkeypatch.setattr(filesystem_module, "Observer", _ScheduleExhaustedObserver)
    monkeypatch.setattr(filesystem_module, "PollingObserver", _PollingObserver)

    watcher = _watcher(tmp_path)
    watcher.start()

    assert watcher.observer_kind == "polling"
    assert watcher._started is True
    assert _ScheduleExhaustedObserver.instances[-1].unscheduled is True
    assert _PollingObserver.instances[-1].scheduled[0][1:] == (str(tmp_path.resolve()), True)
    watcher.stop()


def test_unrelated_observer_error_is_not_hidden(monkeypatch, tmp_path: Path) -> None:
    class _FailingObserver(_ObserverBase):
        instances = []

        def start(self) -> None:
            raise OSError(errno.EACCES, "permission denied")

    _PollingObserver.instances = []
    monkeypatch.setattr(filesystem_module, "_prefer_polling_on_linux", lambda root: (False, 2048))
    monkeypatch.setattr(filesystem_module, "Observer", _FailingObserver)
    monkeypatch.setattr(filesystem_module, "PollingObserver", _PollingObserver)

    watcher = _watcher(tmp_path)
    with pytest.raises(OSError, match="permission denied"):
        watcher.start()
    assert _PollingObserver.instances == []


def test_large_linux_scope_preflights_directly_to_polling(monkeypatch, tmp_path: Path) -> None:
    _PollingObserver.instances = []
    monkeypatch.setattr(filesystem_module, "_prefer_polling_on_linux", lambda root: (True, 4096))
    monkeypatch.setattr(filesystem_module, "PollingObserver", _PollingObserver)

    def _unexpected_native_observer():
        raise AssertionError("native observer should not be allocated for an oversized scope")

    monkeypatch.setattr(filesystem_module, "Observer", _unexpected_native_observer)
    watcher = _watcher(tmp_path)
    assert watcher.observer_kind == "polling"
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        watcher.start()
    assert caught
    assert "conservative recursive inotify budget" in str(caught[0].message)
    watcher.stop()


def test_native_watcher_starts_and_stops_normally(monkeypatch, tmp_path: Path) -> None:
    class _NativeObserver(_ObserverBase):
        instances = []

    monkeypatch.setattr(filesystem_module, "_prefer_polling_on_linux", lambda root: (False, 2048))
    monkeypatch.setattr(filesystem_module, "Observer", _NativeObserver)

    watcher = _watcher(tmp_path)
    watcher.start()
    assert watcher.observer_kind == "native"
    assert watcher._started is True
    assert _NativeObserver.instances[-1].scheduled[0][1:] == (str(tmp_path.resolve()), True)
    watcher.stop()
    assert _NativeObserver.instances[-1].stopped is True


def test_excluded_internal_paths_do_not_emit_file_events(tmp_path: Path) -> None:
    internal = tmp_path / ".execweave"
    internal.mkdir()
    visible = tmp_path / "visible.txt"
    hidden = internal / "events.jsonl"
    sink = _CaptureSink()
    handler = SessionFileEventHandler(
        session_id="s1",
        session_entity=_session(),
        sink=sink,
        excluded_roots=[internal],
    )

    handler.on_any_event(FileModifiedEvent(str(hidden)))
    assert sink.events == []

    handler.on_any_event(FileModifiedEvent(str(visible)))
    assert len(sink.events) == 1
    assert sink.events[0].relation == "OBSERVED_FILE_CHANGE"
    assert sink.events[0].attributes["causal"] is False


def test_no_files_never_constructs_a_file_watcher(monkeypatch, tmp_path: Path) -> None:
    def _unexpected_file_watcher(*args, **kwargs):
        raise AssertionError("FileWatcher must not be constructed when collect_filesystem=False")

    monkeypatch.setattr(collector_module, "FileWatcher", _unexpected_file_watcher)
    sink = JsonlSink(tmp_path / "events.jsonl")
    collector = RuntimeCollector(
        session_id="s1",
        sink=sink,
        watch_root=tmp_path,
        poll_interval=0.02,
        collect_filesystem=False,
        collect_network=False,
    )
    return_code = collector.run([sys.executable, "-c", "pass"])
    assert return_code == 0

    events = [json.loads(line) for line in sink.path.read_text(encoding="utf-8").splitlines()]
    assert events
    assert not any(str(event.get("event_type", "")).startswith("filesystem.") for event in events)
