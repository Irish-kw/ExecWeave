"""Regression tests for descriptor/path metadata differences and exact checks."""
from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from execweave import content_integrity as integrity
from execweave.finalization import record_finalization
from test_content_integrity import archive


def altered(value, **fields):
    names = ('st_dev', 'st_ino', 'st_mode', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
    return SimpleNamespace(**{**{name: getattr(value, name) for name in names}, **fields})


def test_path_stat_time_semantics_do_not_override_consistent_descriptor_metadata(tmp_path, monkeypatch):
    archive(tmp_path)
    original = Path.stat

    def stat_with_different_path_ctime(path, *, follow_symlinks=True):
        value = original(path, follow_symlinks=follow_symlinks)
        if follow_symlinks:
            return altered(value, st_ctime_ns=value.st_ctime_ns + 123456789)
        return value

    monkeypatch.setattr(Path, 'stat', stat_with_different_path_ctime)
    result = record_finalization(tmp_path, state='complete')
    assert result['state'] == 'complete'
    assert result['content_integrity']['verified_file_count'] == 1


@pytest.mark.parametrize('field', ['st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns'])
def test_reopened_handle_still_rejects_even_one_unit_difference(tmp_path, monkeypatch, field):
    ref = archive(tmp_path)
    original = integrity._path_descriptor_stat

    def different(path):
        value = original(path)
        if path.name == Path(ref['path']).name:
            return altered(value, **{field: getattr(value, field) + 1})
        return value

    monkeypatch.setattr(integrity, '_path_descriptor_stat', different)
    result = integrity.audit_content_references(tmp_path)
    assert result['state'] == 'incomplete'
    assert result['verified_file_count'] == 0
    assert any(row['code'] == 'changed_during_read' for row in result['errors'])


def test_additional_handle_is_closed_when_fstat_fails(tmp_path, monkeypatch):
    path = tmp_path / 'file.txt'
    path.write_bytes(b'content')
    descriptor = None
    real_fstat = os.fstat

    def fail(fd):
        nonlocal descriptor
        descriptor = fd
        raise OSError('simulated stat failure')

    monkeypatch.setattr(integrity.os, 'fstat', fail)
    with pytest.raises(OSError, match='simulated stat failure'):
        integrity._path_descriptor_stat(path)
    assert descriptor is not None
    with pytest.raises(OSError):
        real_fstat(descriptor)


def test_reopen_failure_remains_incomplete(tmp_path, monkeypatch):
    archive(tmp_path)

    def denied(path):
        raise PermissionError('simulated reopen denied')

    monkeypatch.setattr(integrity, '_path_descriptor_stat', denied)
    result = integrity.audit_content_references(tmp_path)
    assert result['state'] == 'incomplete'
    assert result['verified_file_count'] == 0
    assert {item['code'] for item in result['errors']} == {'unreadable_or_unsafe_path'}


def test_repeated_real_exports_after_create_then_modify(tmp_path):
    # Runs on each CI OS. The previous comparison mixed descriptor ctime with
    # path-stat ctime; creation and modification need not be the same timestamp.
    ref = archive(tmp_path)
    target = tmp_path / ref['path']
    for _ in range(5):
        original = target.read_bytes()
        target.write_bytes(original)
        result = record_finalization(tmp_path, state='complete')
        assert result['state'] == 'complete', result
        assert result['content_integrity']['verified_file_count'] == 1
