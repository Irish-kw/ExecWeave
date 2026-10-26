"""Keep exact open-handle checks without comparing unlike stat providers."""
from __future__ import annotations

import hashlib
import os
from types import SimpleNamespace

import pytest

from execweave import task_artifacts as artifacts
from test_task_validation_reports import receipt


def altered(value, **changes):
    fields = ('st_dev', 'st_ino', 'st_mode', 'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_file_attributes')
    return SimpleNamespace(**{**{k: getattr(value, k, 0) for k in fields}, **changes})


@pytest.mark.parametrize('field', ['st_mtime_ns', 'st_ctime_ns'])
def test_path_timestamps_do_not_override_consistent_handles(tmp_path, monkeypatch, field):
    path = tmp_path / 'selected.bin'
    payload = b'\x00\xff\r\n\x1aunaltered bytes'
    path.write_bytes(payload)
    lstat = os.lstat

    def different_stat(name, *args, **kwargs):
        info = lstat(name, *args, **kwargs)
        if os.fspath(name) == str(path):
            return altered(info, **{field: getattr(info, field) + 1})
        return info

    monkeypatch.setattr(artifacts.os, 'lstat', different_stat)
    result = artifacts.bind_artifacts(receipt(), [f'file.bin={path}'])
    assert result['artifacts']['entries'][0] == {
        'path': 'file.bin', 'size_bytes': len(payload),
        'sha256': hashlib.sha256(payload).hexdigest(),
    }
    assert path.read_bytes() == payload


@pytest.mark.parametrize('field', ['st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns'])
@pytest.mark.parametrize('stage', ['open', 'read', 'reopen'])
def test_single_unit_handle_difference_is_rejected(tmp_path, monkeypatch, field, stage):
    path = tmp_path / 'selected'
    path.write_bytes(b'original bytes')
    original = os.fstat
    calls = []
    # Baseline metadata handle, data handle before/after read, final path handle.
    change_at = {'open': 2, 'read': 3, 'reopen': 4}[stage]

    def changed(fd):
        info = original(fd)
        calls.append(fd)
        if len(calls) == change_at:
            return altered(info, **{field: getattr(info, field) + 1})
        return info

    monkeypatch.setattr(artifacts.os, 'fstat', changed)
    with pytest.raises(ValueError, match='changed'):
        artifacts._read_selected(str(path))
    assert len(calls) >= change_at
    for fd in set(calls):
        with pytest.raises(OSError):
            original(fd)


@pytest.mark.parametrize('at', [1, 2, 3, 4])
def test_metadata_failure_closes_all_opened_handles(tmp_path, monkeypatch, at):
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


def test_repeated_real_create_modify_and_binary_reads(tmp_path):
    path = tmp_path / 'artifact'
    for payload in (b'abc', b'def', b'\x00\xff\r\n\x1aafter', b''):
        path.write_bytes(payload)
        result = artifacts.bind_artifacts(receipt(), [f'a.bin={path}'])
        item = result['artifacts']['entries'][0]
        assert item['size_bytes'] == len(payload)
        assert item['sha256'] == hashlib.sha256(payload).hexdigest()


def test_changed_path_during_data_open_is_not_accepted(tmp_path, monkeypatch):
    path = tmp_path / 'selected'
    path.write_bytes(b'old')
    original = os.open
    calls = 0

    def replace_at_open(name, flags, *args, **kwargs):
        nonlocal calls
        if os.fspath(name) == str(path):
            calls += 1
            if calls == 2:
                path.unlink()
                path.write_bytes(b'new')
        return original(name, flags, *args, **kwargs)

    monkeypatch.setattr(artifacts.os, 'open', replace_at_open)
    with pytest.raises(ValueError, match='changed'):
        artifacts._read_selected(str(path))


def test_reparse_path_is_refused_before_open(tmp_path, monkeypatch):
    path = tmp_path / 'selected'
    path.write_bytes(b'payload')
    original = os.lstat
    calls = []

    def reparse(name, *args, **kwargs):
        info = original(name, *args, **kwargs)
        return altered(info, st_file_attributes=0x400) if os.fspath(name) == str(path) else info

    def must_not_open(*args, **kwargs):
        calls.append(args)
        raise AssertionError('reparse target opened')

    monkeypatch.setattr(artifacts.os, 'lstat', reparse)
    monkeypatch.setattr(artifacts.os, 'open', must_not_open)
    with pytest.raises(ValueError):
        artifacts._read_selected(str(path))
    assert not calls
