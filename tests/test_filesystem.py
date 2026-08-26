import errno
from pathlib import Path

import pytest

import execweave.filesystem as filesystem
from execweave.schema import Entity
from execweave.sink import JsonlSink


class _FakeObserver:
    instances = []

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.scheduled = []
        self.started = False
        self.stopped = False
        self.joined = False
        self.unscheduled = False
        type(self).instances.append(self)

    def schedule(self, handler, path: str, *, recursive: bool = False):
        self.scheduled.append((handler, path, recursive))
        return object()

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True

    def join(self, timeout: float | None = None) -> None:
        self.joined = True

    def unschedule_all(self) -> None:
        self.unscheduled = True


def _make_watcher(tmp_path: Path) -> filesystem.FileWatcher:
    return filesystem.FileWatcher(
        root=tmp_path,
        session_id="test-session",
        session_entity=Entity(type="session", id="session:test", name="test"),
        sink=JsonlSink(tmp_path / "events.jsonl"),
    )


@pytest.mark.parametrize(
    ("error_number", "message"),
    [
        (errno.ENOSPC, "inotify watch limit reached"),
        (errno.EMFILE, "inotify instance limit reached"),
    ],
)
def test_file_watcher_falls_back_when_inotify_resources_are_exhausted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error_number: int,
    message: str,
) -> None:
    class ExhaustedObserver(_FakeObserver):
        instances = []

        def start(self) -> None:
            raise OSError(error_number, message)

    class FakePollingObserver(_FakeObserver):
        instances = []

    monkeypatch.setattr(filesystem, "Observer", ExhaustedObserver)
    monkeypatch.setattr(filesystem, "PollingObserver", FakePollingObserver)

    watcher = _make_watcher(tmp_path)
    watcher.start()

    native = ExhaustedObserver.instances[-1]
    polling = FakePollingObserver.instances[-1]
    assert native.unscheduled is True
    assert watcher.observer is polling
    assert watcher.observer_backend == "polling"
    assert polling.kwargs == {"timeout": filesystem._POLLING_FALLBACK_INTERVAL}
    assert polling.started is True
    assert polling.scheduled[0][1:] == (str(tmp_path.resolve()), True)

    watcher.stop()
    assert polling.stopped is True
    assert polling.joined is True


def test_file_watcher_does_not_hide_unrelated_observer_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingObserver(_FakeObserver):
        instances = []

        def start(self) -> None:
            raise OSError(errno.EACCES, "permission denied")

    class FakePollingObserver(_FakeObserver):
        instances = []

    monkeypatch.setattr(filesystem, "Observer", FailingObserver)
    monkeypatch.setattr(filesystem, "PollingObserver", FakePollingObserver)

    watcher = _make_watcher(tmp_path)
    with pytest.raises(OSError, match="permission denied"):
        watcher.start()

    assert FakePollingObserver.instances == []
