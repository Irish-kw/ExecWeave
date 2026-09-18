"""Archive integrity tests use real temporary files, not provider recordings."""
from __future__ import annotations

import hashlib
import json
import os
from contextlib import contextmanager

import pytest

from execweave import content_integrity as integrity
from execweave import finalization


def archive(root, payload=b'hello', *, extension='txt'):
    digest = hashlib.sha256(payload).hexdigest()
    ref = {'path': f'content/sha256/{digest}.{extension}', 'sha256': digest,
           'size_bytes': len(payload), 'content_kind': 'test.tool_output',
           'complete_from_source': True}
    target = root / ref['path']
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    write_indexes(root, [ref], [ref])
    return ref


def write_indexes(root, refs, entries=()):
    (root / 'graph.json').write_text(json.dumps({'nodes': [
        {'id': f'content:{index}', 'type': 'observed_content', 'attributes': ref}
        for index, ref in enumerate(refs)]}), encoding='utf-8')
    (root / 'conversations.json').write_text(json.dumps({'entries': list(entries)}), encoding='utf-8')
    (root / 'viewer.html').write_text('<html>synthetic viewer</html>', encoding='utf-8')


def errors(report):
    return {item['code'] for item in report['errors']}


@pytest.mark.parametrize('payload', [b'', b'null', b'false', b'0', '中文'.encode(), b'\x00\xff\xfe', b'x' * (integrity.CHUNK + 17)])
def test_all_captured_bytes_and_duplicate_refs_are_verified_once(tmp_path, payload):
    ref = archive(tmp_path, payload, extension='bin')
    report = integrity.audit_content_references(tmp_path)
    assert report['state'] == 'complete'
    assert report['reference_count'] == 2
    assert report['unique_file_count'] == report['verified_file_count'] == 1
    assert report['completed_read_bytes'] == len(payload)
    assert report['verified_files'][ref['path']] == {'sha256': ref['sha256'], 'size_bytes': len(payload)}


def test_empty_valid_indexes_are_explicitly_scoped_not_provider_recall(tmp_path):
    write_indexes(tmp_path, [])
    report = integrity.audit_content_references(tmp_path)
    assert report['state'] == 'complete' and report['reference_count'] == 0
    assert report['scope'] == 'declared_graph_and_conversation_content'
    assert 'provider_recall' not in report


@pytest.mark.parametrize('operation,expected', [('delete', 'missing_file'), ('tamper', 'hash_mismatch'), ('size', 'size_mismatch')])
def test_broken_archive_never_passes(tmp_path, operation, expected):
    ref = archive(tmp_path)
    if operation == 'delete':
        (tmp_path / ref['path']).unlink()
    elif operation == 'tamper':
        (tmp_path / ref['path']).write_bytes(b'HELLO')
    else:
        ref['size_bytes'] = 99
        write_indexes(tmp_path, [ref], [ref])
    report = integrity.audit_content_references(tmp_path)
    assert report['state'] == 'incomplete' and expected in errors(report)
    assert report['verified_file_count'] == 0


@pytest.mark.parametrize('patch', [
    {'path': '../secret'}, {'path': '/etc/passwd'}, {'path': 'C:\\secret'},
    {'path': 'file:///secret'}, {'path': 'https://example.invalid/secret'},
    {'path': 'content/sha256/' + 'a' * 64 + '.txt\n'},
    {'path': 'content\\sha256\\' + 'a' * 64 + '.txt'},
    {'path': 'content/sha256/' + 'a' * 64 + '.txt?key=1'},
    {'sha256': 'f' * 64}, {'sha256': None}, {'size_bytes': True},
    {'size_bytes': -1}, {'size_bytes': 1.5}, {'size_bytes': None},
])
def test_invalid_registered_reference_is_rejected_before_open(tmp_path, monkeypatch, patch):
    ref = archive(tmp_path)
    ref.update(patch)
    write_indexes(tmp_path, [ref])
    original = integrity._open_regular
    opened = []

    @contextmanager
    def tracked(root, relative):
        opened.append(relative)
        with original(root, relative) as handle:
            yield handle

    monkeypatch.setattr(integrity, '_open_regular', tracked)
    report = integrity.audit_content_references(tmp_path)
    assert report['state'] == 'incomplete' and 'invalid_reference' in errors(report)
    assert opened == ['graph.json', 'conversations.json']


def test_legacy_missing_size_is_not_zero_and_source_partial_is_orthogonal(tmp_path):
    ref = archive(tmp_path)
    del ref['size_bytes']
    ref['complete_from_source'] = False
    write_indexes(tmp_path, [ref], [ref])
    report = integrity.audit_content_references(tmp_path)
    assert report['state'] == 'complete' and report['completed_read_bytes'] == 5


def test_conflicting_sizes_cannot_be_erased_by_a_later_reference(tmp_path):
    ref = archive(tmp_path)
    write_indexes(tmp_path, [ref, {**ref, 'size_bytes': 10}, ref])
    report = integrity.audit_content_references(tmp_path)
    assert report['state'] == 'incomplete' and 'conflicting_reference' in errors(report)
    assert report['verified_file_count'] == 0


@pytest.mark.parametrize('raw', [b'', b'artifact', b'{"nodes":[]', b'[]', b'{}', b'{"nodes":null}',
                                  b'{"nodes":[],"nodes":[]}', b'{"nodes":[],"n":NaN}', b'\xff'])
def test_invalid_index_is_not_a_successful_zero_reference_archive(tmp_path, raw):
    archive(tmp_path)
    (tmp_path / 'graph.json').write_bytes(raw)
    report = integrity.audit_content_references(tmp_path)
    assert report['state'] == 'incomplete' and 'invalid_index' in errors(report)


def test_bad_conversation_entry_does_not_silently_disappear(tmp_path):
    write_indexes(tmp_path, [], [{'conversation_preview': {'messages': []}}, None])
    report = integrity.audit_content_references(tmp_path)
    assert {'invalid_reference', 'invalid_index_entry'} <= errors(report)


def test_provider_payload_dictionaries_are_not_filesystem_instructions(tmp_path, monkeypatch):
    ref = archive(tmp_path, json.dumps({'path': '/etc/passwd', 'sha256': 'f' * 64}).encode())
    graph = {'nodes': [{'id': 'agent:a', 'type': 'agent', 'attributes': {
        'message': {'path': '/etc/passwd', 'sha256': 'f' * 64}}}]}
    (tmp_path / 'graph.json').write_text(json.dumps(graph))
    entry = {**ref, 'conversation_preview': {'messages': [{'path': '/etc/passwd', 'sha256': 'f' * 64}]}}
    (tmp_path / 'conversations.json').write_text(json.dumps({'entries': [entry]}))
    report = integrity.audit_content_references(tmp_path)
    assert report['state'] == 'complete' and report['reference_count'] == 1


def test_hidden_expansion_content_is_still_verified(tmp_path):
    ref = archive(tmp_path)
    graph = {'nodes': [], 'expansion': {'clusters': {'hidden': {'nodes': [
        {'type': 'observed_content', 'attributes': ref}]}}}}
    (tmp_path / 'graph.json').write_text(json.dumps(graph))
    (tmp_path / ref['path']).unlink()
    report = integrity.audit_content_references(tmp_path)
    assert report['state'] == 'incomplete' and report['reference_count'] == 2


@pytest.mark.parametrize('kwargs,code', [
    ({'max_index_bytes': 2}, 'verification_limit'),
    ({'max_content_bytes': 2}, 'verification_limit'),
    ({'max_references': 0}, 'reference_limit'),
])
def test_limits_are_explicit_incomplete_results(tmp_path, kwargs, code):
    archive(tmp_path)
    report = integrity.audit_content_references(tmp_path, **kwargs)
    assert report['state'] == 'incomplete' and code in errors(report)


@pytest.mark.parametrize('limit', [-1, True, 1.5, None])
def test_invalid_budget_parameters_raise(tmp_path, limit):
    with pytest.raises(ValueError):
        integrity.audit_content_references(tmp_path, max_content_bytes=limit)


def test_bounded_error_details_preserve_total_error_count(tmp_path):
    write_indexes(tmp_path, [{} for _ in range(130)])
    report = integrity.audit_content_references(tmp_path)
    assert report['error_count'] == 130
    assert len(report['errors']) == 100 and report['errors_truncated']


@pytest.mark.parametrize('target_kind', ['file', 'directory'])
def test_symlinked_content_is_not_followed(tmp_path, target_kind):
    root = tmp_path / 'run'
    root.mkdir()
    ref = archive(root)
    blob = root / ref['path']
    outside = tmp_path / 'outside'
    if target_kind == 'file':
        outside.write_bytes(blob.read_bytes())
        blob.unlink()
        link = blob
    else:
        (root / 'content').rename(outside)
        link = root / 'content'
    try:
        link.symlink_to(outside, target_is_directory=target_kind == 'directory')
    except OSError:
        pytest.skip('OS account lacks permission to create a symlink')
    report = integrity.audit_content_references(root)
    assert report['state'] == 'incomplete' and report['verified_file_count'] == 0
    assert errors(report) & {'unsafe_path', 'unreadable_or_unsafe_path'}


@pytest.mark.skipif(os.name == 'nt', reason='POSIX named pipes only')
def test_named_pipe_does_not_block_integrity_check(tmp_path):
    ref = archive(tmp_path)
    blob = tmp_path / ref['path']
    blob.unlink()
    os.mkfifo(blob)
    report = integrity.audit_content_references(tmp_path)
    assert report['state'] == 'incomplete' and 'not_regular_file' in errors(report)


def test_file_modified_during_read_is_rejected(tmp_path, monkeypatch):
    ref = archive(tmp_path)
    original = integrity._open_regular

    @contextmanager
    def changing(root, relative):
        with original(root, relative) as handle:
            yield handle
            if relative == ref['path']:
                (root / relative).write_bytes(b'changed')

    monkeypatch.setattr(integrity, '_open_regular', changing)
    report = integrity.audit_content_references(tmp_path)
    assert 'changed_during_read' in errors(report) and report['verified_file_count'] == 0


def test_finalization_checks_content_and_writes_diagnostic_before_raising(tmp_path):
    ref = archive(tmp_path)
    (tmp_path / ref['path']).unlink()
    with pytest.raises(RuntimeError, match='incomplete'):
        finalization.record_finalization(tmp_path, state='complete')
    report = json.loads((tmp_path / 'finalization.json').read_text())
    assert report['state'] == 'incomplete' and report['missing'] == []
    assert 'missing_file' in errors(report['content_integrity'])


def test_valid_export_can_coexist_with_collector_failure(tmp_path):
    archive(tmp_path)
    error = RuntimeError('collector failure')
    report = finalization.record_finalization(tmp_path, state='complete', error=error)
    assert report['state'] == 'complete' and report['error_type'] == 'RuntimeError'
    assert report['content_integrity']['state'] == 'complete'


def test_missing_export_and_content_do_not_replace_collector_error(tmp_path):
    ref = archive(tmp_path)
    (tmp_path / ref['path']).unlink()
    error = RuntimeError('collector failure')
    report = finalization.record_finalization(tmp_path, state='complete', error=error)
    assert report['state'] == 'incomplete' and report['error_type'] == 'RuntimeError'


def test_recording_does_not_claim_an_integrity_pass(tmp_path, monkeypatch):
    def unexpected(*args, **kwargs):
        raise AssertionError('recording must not scan content')
    monkeypatch.setattr(finalization, 'audit_content_references', unexpected)
    report = finalization.record_finalization(tmp_path, state='recording')
    assert report['state'] == 'recording' and report['content_integrity']['state'] == 'not_checked'


def test_export_changed_between_primary_hash_and_audit_cannot_pass(tmp_path, monkeypatch):
    archive(tmp_path)
    original = finalization.audit_content_references

    def changed(root):
        (root / 'conversations.json').write_text('{"entries":[]}')
        return original(root)

    monkeypatch.setattr(finalization, 'audit_content_references', changed)
    with pytest.raises(RuntimeError, match='incomplete'):
        finalization.record_finalization(tmp_path, state='complete')
    report = json.loads((tmp_path / 'finalization.json').read_text())
    assert report['artifact_errors']['conversations.json'] == 'changed_during_finalization'


def test_content_and_exports_are_not_modified_by_verification(tmp_path):
    ref = archive(tmp_path)
    names = [*finalization.REQUIRED_EXPORTS, ref['path']]
    before = {name: (tmp_path / name).read_bytes() for name in names}
    report = finalization.record_finalization(tmp_path, state='complete')
    assert report['state'] == 'complete'
    assert before == {name: (tmp_path / name).read_bytes() for name in names}
    assert report['content_integrity']['index_files']['graph.json'] == report['artifacts']['graph.json']


def test_reference_limit_count_is_marked_as_lower_bound(tmp_path):
    ref = archive(tmp_path)
    write_indexes(tmp_path, [ref] * 20)
    report = integrity.audit_content_references(tmp_path, max_references=2)
    assert report['reference_count'] == 3 and report['reference_count_truncated']
    assert report['state'] == 'incomplete'


def test_known_cross_run_indexes_cannot_be_declared_complete(tmp_path):
    archive(tmp_path)
    for name, session in [('graph.json', 'one'), ('conversations.json', 'two')]:
        data = json.loads((tmp_path / name).read_text())
        data['session_id'] = session
        (tmp_path / name).write_text(json.dumps(data))
    report = integrity.audit_content_references(tmp_path)
    assert report['state'] == 'incomplete' and 'index_session_mismatch' in errors(report)


def test_unreferenced_workspace_files_are_not_opened(tmp_path):
    archive(tmp_path)
    (tmp_path / 'workspace-secret.txt').write_text('not part of declared content')
    report = integrity.audit_content_references(tmp_path)
    assert report['state'] == 'complete'
    assert 'workspace-secret' not in json.dumps(report)


def test_complete_then_missing_archive_is_rechecked_not_cached(tmp_path):
    ref = archive(tmp_path)
    assert finalization.record_finalization(tmp_path, state='complete')['state'] == 'complete'
    (tmp_path / ref['path']).unlink()
    with pytest.raises(RuntimeError, match='incomplete'):
        finalization.record_finalization(tmp_path, state='complete')
    assert json.loads((tmp_path / 'finalization.json').read_text())['state'] == 'incomplete'
