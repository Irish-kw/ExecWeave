"""Published Codex history keeps middle records; legacy preview budgets stay valid."""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy

import pytest

from execweave.agent_topology import EVIDENCE_CROSS_AGENT_ROUTING
from execweave.codex_conversation import _DerivedThreads, codex_rollout_previews
from execweave.conversation_preview_codex import conversation_preview
from execweave.conversation_records import _merge_conversation_previews


def rollout(tmp_path, count=210, *, child=False):
    identity = {'id': 'thread', 'agent_path': '/root/child' if child else '/root'}
    if child:
        identity.update(parent_thread_id='parent', subagent_history_start_ordinal=100)
    records = [{'type': 'session_meta', 'payload': identity}]
    for i in range(count):
        records.append({'type': 'response_item', 'ordinal': i + 1,
            'payload': {'type': 'message', 'role': 'assistant', 'phase': 'final_answer',
                        'content': [{'type': 'output_text', 'text': f'answer {i}'}]}})
    p = tmp_path / 'rollout-test.jsonl'
    p.write_text('\n'.join(json.dumps(r) for r in records), encoding='utf-8')
    return p


def test_legacy_preview_still_bounded_but_preserved_mode_keeps_middle(tmp_path):
    p = rollout(tmp_path)
    original = p.read_bytes()
    bounded = codex_rollout_previews(p)[0]
    full = codex_rollout_previews(p, preserve_history=True)[0]
    assert len(bounded['messages']) == 80 and bounded['messages_truncated']
    assert len(full['messages']) == 210 and not full['messages_truncated']
    assert full['messages'][83]['text'] == 'answer 83'
    assert p.read_bytes() == original


def test_actual_parser_to_publication_keeps_every_record(tmp_path):
    p = rollout(tmp_path)
    preview = conversation_preview(p, content_kind='codex.conversation_transcript', provider='codex',
        source={'id': 'agent:a', 'type': 'agent', 'attributes': {}})
    entries = [{'source_id': 'agent:a', 'provider': 'codex', 'content_kind': 'codex.conversation_transcript',
                'sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'conversation_preview': preview}]
    _merge_conversation_previews(entries)
    merged = entries[0]['conversation_preview']
    assert merged['message_count'] == len(merged['messages']) == 210
    assert not merged['messages_truncated']
    assert merged['messages'][83]['text'] == 'answer 83'


def test_child_inherited_history_cutoff_still_applies_in_preserved_mode(tmp_path):
    preview = codex_rollout_previews(rollout(tmp_path, child=True), preserve_history=True)[0]
    assert len(preview['messages']) == 111
    assert all(m['ordinal'] >= 100 for m in preview['messages'])
    assert all(m['sender'] == '/root/child' for m in preview['messages'])


def test_routing_only_derived_threads_preserve_scope_and_default_budget():
    derived = _DerivedThreads('parent', '/root')
    derived.delegate('/root/child', 'child')
    for i in range(210):
        derived.add('/root/child', {'ordinal': i, 'text': 'same', 'sender': '/root/child'})
    assert len(derived.previews()[0]['messages']) == 80
    full = derived.previews(preserve_history=True)[0]
    assert len(full['messages']) == 210
    assert full['evidence_scope'] == EVIDENCE_CROSS_AGENT_ROUTING
    assert full['parent_thread_id'] == 'parent'


def raw_entry(source, *, partial=False, child=False, count=410):
    path = '/root/child' if child else '/root'
    messages = [{'ordinal': i, 'kind': 'assistant_message', 'sender': path,
                 'recipient': None, 'text': 'same reply', 'content_state': 'plaintext',
                 'phase': 'final_answer'} for i in range(count)]
    return {'source_id': source, 'provider': 'codex', 'content_kind': 'codex.conversation_transcript',
            'sha256': 'a' * 64, 'conversation_preview': {
            'thread_id': source, 'provider_native_id': source, 'thread_id_source': 'provider_native',
            'agent_path': path, 'is_root': not child, 'messages': messages,
            'message_count': len(messages), 'messages_truncated': partial}}


@pytest.mark.parametrize('count', [0, 1, 80, 81, 210, 410])
def test_publication_budget_does_not_drop_middle_same_text_turns(count):
    records = [raw_entry('agent:a', count=count)]
    _merge_conversation_previews(records)
    result = records[0]['conversation_preview']
    assert len(result['messages']) == count
    assert result['message_count'] == count
    assert not result['messages_truncated']
    assert [m['ordinal'] for m in result['messages']] == list(range(count))


def test_existing_input_truncation_is_not_reported_repaired():
    records = [raw_entry('agent:a', partial=True)]
    _merge_conversation_previews(records)
    assert records[0]['conversation_preview']['messages_truncated'] is True


def test_two_roots_with_same_display_path_do_not_union():
    records = [raw_entry('agent:a'), raw_entry('agent:b')]
    records[1]['conversation_preview']['messages'][83]['text'] = 'only B owns this'
    _merge_conversation_previews(records)
    assert len([e for e in records if 'conversation_preview' in e]) == 2
    for e in records:
        assert len(e['conversation_preview']['messages']) == 410
        assert ('only B owns this' in [m['text'] for m in e['conversation_preview']['messages']]) == (e['source_id'] == 'agent:b')


def test_child_root_user_prompt_filter_still_runs_after_preservation():
    records = [raw_entry('agent:child', child=True)]
    records[0]['conversation_preview']['messages'].insert(50, {
        'ordinal': -1, 'sender': 'user', 'recipient': '/root', 'text': 'parent private request',
        'kind': 'user_message', 'content_state': 'plaintext'})
    _merge_conversation_previews(records)
    messages = records[0]['conversation_preview']['messages']
    assert len(messages) == 410
    assert all(m['text'] != 'parent private request' for m in messages)


def test_repeated_merge_is_idempotent_for_one_preserved_transcript():
    records = [raw_entry('agent:a')]
    _merge_conversation_previews(records)
    before = deepcopy(records)
    _merge_conversation_previews(records)
    assert records == before


def test_reused_derived_thread_alias_does_not_cross_independent_roots():
    from execweave.agent_topology import THREAD_ID_EXECWEAVE_DERIVED
    records = [raw_entry('agent:a'), raw_entry('agent:b')]
    for e in records:
        e['conversation_preview']['thread_id'] = 'codex:root'
        e['conversation_preview']['thread_id_source'] = THREAD_ID_EXECWEAVE_DERIVED
    records[1]['conversation_preview']['messages'][83]['text'] = 'only B owns this'
    _merge_conversation_previews(records)
    first = next(e for e in records if e['source_id'] == 'agent:a')
    assert all(m['text'] != 'only B owns this' for m in first['conversation_preview']['messages'])


def test_conflicting_native_scopes_cannot_join_even_with_same_source_id():
    from execweave.conversation_records_codex import _same_merged_execution
    a, b = raw_entry('agent:a'), raw_entry('agent:a')
    b['conversation_preview']['provider_native_id'] = 'other-execution'
    assert not _same_merged_execution(a, a['conversation_preview'], b, b['conversation_preview'])


def test_native_thread_evidence_can_join_aliases_only_with_same_execution_scope():
    from execweave.agent_topology import THREAD_ID_PROVIDER_NATIVE
    from execweave.conversation_records_codex import _same_merged_execution
    a, b = raw_entry('agent:a'), raw_entry('agent:alias')
    for e in (a, b):
        e['conversation_preview'].update(provider_native_id='native-thread', thread_id='native-thread', thread_id_source=THREAD_ID_PROVIDER_NATIVE)
    a['conversation_preview']['evidence_thread_ids'] = ['native-thread']
    assert _same_merged_execution(a, a['conversation_preview'], b, b['conversation_preview'])
