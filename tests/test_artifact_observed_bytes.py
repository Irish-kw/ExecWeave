"""Compare actual repeated observations even when metadata reports no change."""
from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from execweave import task_artifacts as artifacts


def freeze_metadata(monkeypatch, path):
    """Model the verifier's coarse metadata, not the local filesystem behavior."""
    info = path.stat()
    fields = ('st_dev', 'st_ino', 'st_mode', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
    fixed = SimpleNamespace(**{k: getattr(info, k) for k in fields})
    original = os.fstat
    monkeypatch.setattr(artifacts.os, 'fstat', lambda fd: (original(fd), fixed)[1])


@pytest.mark.parametrize('boundary', [2, 3], ids=['data-open', 'final-path-open'])
@pytest.mark.parametrize('operation', ['replace', 'rewrite'])
def test_changed_bytes_are_rejected_even_with_equal_metadata(tmp_path, monkeypatch, boundary, operation):
    path = tmp_path / 'selected.bin'
    path.write_bytes(b'old')
    freeze_metadata(monkeypatch, path)
    original = os.open
    opens = []

    def swap(name, flags, *args, **kwargs):
        if os.fspath(name) == str(path):
            opens.append(name)
            if len(opens) == boundary:
                if operation == 'replace':
                    path.unlink()
                path.write_bytes(b'new')
        return original(name, flags, *args, **kwargs)

    monkeypatch.setattr(artifacts.os, 'open', swap)
    with pytest.raises((ValueError, PermissionError)) as rejected:
        artifacts._read_selected(str(path))
    assert len(opens) == boundary
    if isinstance(rejected.value, PermissionError):
        # Some Windows filesystems refuse unlink while the data handle is open.
        # That is a refused operation, not a successful byte-comparison claim.
        assert operation == 'replace' and boundary == 3
        assert path.read_bytes() == b'old'
    else:
        assert 'changed' in str(rejected.value)
        assert path.read_bytes() == b'new'


@pytest.mark.parametrize('payload', [b'', b'abc', b'\x00\xff\r\n\x1a'], ids=['empty', 'text', 'binary'])
def test_equal_repeated_observations_return_original_bytes(tmp_path, monkeypatch, payload):
    path = tmp_path / 'selected.bin'
    path.write_bytes(payload)
    freeze_metadata(monkeypatch, path)
    assert artifacts._read_selected(str(path)) == payload


def test_equal_bytes_do_not_cancel_a_metadata_change(tmp_path, monkeypatch):
    path = tmp_path / 'selected.bin'
    path.write_bytes(b'unchanged bytes')
    original = os.fstat
    calls = []

    def change(fd):
        info = original(fd)
        calls.append(fd)
        if len(calls) == 3:
            fields = ('st_dev', 'st_ino', 'st_mode', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
            return SimpleNamespace(**{k: getattr(info, k) + (k == 'st_mtime_ns') for k in fields})
        return info

    monkeypatch.setattr(artifacts.os, 'fstat', change)
    with pytest.raises(ValueError, match='changed'):
        artifacts._read_selected(str(path))
    for fd in set(calls):
        with pytest.raises(OSError):
            original(fd)


@pytest.mark.parametrize('at', range(1, 8))
def test_every_metadata_failure_closes_all_handles(tmp_path, monkeypatch, at):
    path = tmp_path / 'selected'
    path.write_bytes(b'payload')
    original = os.fstat
    seen = []

    def fail(fd):
        seen.append(fd)
        if len(seen) == at:
            raise OSError('metadata unavailable')
        return original(fd)

    monkeypatch.setattr(artifacts.os, 'fstat', fail)
    with pytest.raises(OSError, match='metadata unavailable'):
        artifacts._read_selected(str(path))
    assert len(seen) == at
    for fd in set(seen):
        with pytest.raises(OSError):
            original(fd)


def test_fdopen_failure_does_not_leak_raw_descriptor(tmp_path, monkeypatch):
    path = tmp_path / 'selected'
    path.write_bytes(b'payload')
    seen = []

    def fail(fd, mode):
        seen.append(fd)
        raise OSError('stream unavailable')

    monkeypatch.setattr(artifacts.os, 'fdopen', fail)
    with pytest.raises(OSError, match='stream unavailable'):
        artifacts._read_selected(str(path))
    assert len(seen) == 1
    with pytest.raises(OSError):
        os.fstat(seen[0])


def test_every_pass_is_bounded_and_only_selected_path_is_read(tmp_path, monkeypatch):
    path = tmp_path / 'selected'
    path.write_bytes(b'payload')
    original = os.fdopen
    reads = []

    class Reader:
        def __init__(self, fd, mode):
            self.handle = original(fd, mode)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self.handle.close()

        def fileno(self):
            return self.handle.fileno()

        def read(self, limit):
            reads.append(limit)
            return self.handle.read(limit)

    monkeypatch.setattr(artifacts.os, 'fdopen', Reader)
    assert artifacts._read_selected(str(path)) == b'payload'
    assert reads == [artifacts.MAX_FILE_BYTES + 1] * 3


def test_read_exception_closes_handle_without_accepting_partial_bytes(tmp_path, monkeypatch):
    path = tmp_path / 'selected'
    path.write_bytes(b'payload')
    original = os.fdopen
    seen = []

    class FailedReader:
        def __init__(self, fd, mode):
            seen.append(fd)
            self.handle = original(fd, mode)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self.handle.close()

        def fileno(self):
            return self.handle.fileno()

        def read(self, limit):
            raise OSError('read unavailable')

    monkeypatch.setattr(artifacts.os, 'fdopen', FailedReader)
    with pytest.raises(OSError, match='read unavailable'):
        artifacts._read_selected(str(path))
    assert len(seen) == 1
    with pytest.raises(OSError):
        os.fstat(seen[0])


@pytest.mark.parametrize('field', ['st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns'])
@pytest.mark.parametrize('at', [5, 6, 7])
def test_final_read_metadata_boundaries_remain_exact(tmp_path, monkeypatch, field, at):
    path = tmp_path / 'selected'
    path.write_bytes(b'payload')
    original = os.fstat
    seen = []

    def change(fd):
        info = original(fd)
        seen.append(fd)
        if len(seen) == at:
            fields = ('st_dev', 'st_ino', 'st_mode', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
            return SimpleNamespace(**{k: getattr(info, k) + (k == field) for k in fields})
        return info

    monkeypatch.setattr(artifacts.os, 'fstat', change)
    with pytest.raises(ValueError, match='changed'):
        artifacts._read_selected(str(path))
    assert len(seen) >= at
    for fd in set(seen):
        with pytest.raises(OSError):
            original(fd)
