"""Finish must reconcile the last polled graph with the authoritative saved graph."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

import execweave.live as live_module
from execweave.graph import GraphAccumulator
from execweave.live import _LiveState
from execweave.viewer_projection import project_viewer_graph


def event(sequence: int, identity: str, kind: str = 'process') -> dict:
    return {
        'schema_version': '0.2', 'session_id': 's1', 'event_id': f'ev-{sequence}',
        'sequence': sequence, 'timestamp': f'2026-09-08T00:00:{sequence:02d}Z',
        'event_type': 'file.modified' if kind == 'file' else 'process.started',
        'relation': 'OBSERVED_FILE_CHANGE' if kind == 'file' else 'LAUNCHED',
        'source': {'id': 'session:s1', 'type': 'session', 'name': 's1'},
        'target': {'id': identity, 'type': kind, 'name': identity},
        'attributes': {'backend': 'portable', 'causal': kind != 'file'},
    }


def append(path: Path, record: dict) -> None:
    with path.open('a', encoding='utf-8') as handle:
        handle.write(json.dumps(record) + '\n')


def finalized(path: Path) -> dict:
    accumulator = GraphAccumulator(session_id='s1', source_path=path)
    for line in path.read_text(encoding='utf-8').splitlines():
        accumulator.apply(json.loads(line))
    return accumulator.to_dict()


def consume(previous: dict, payload: dict) -> dict:
    """An independent protocol client, including authoritative terminal replacement."""
    if payload['kind'] == 'snapshot':
        return payload['graph']
    nodes = {n['id']: n for n in previous['nodes']}
    edges = {e['id']: e for e in previous['edges']}
    for update in payload.get('updates', []):
        if update.get('terminal') and 'final_graph' in update:
            return update['final_graph']
        nodes.update((n['id'], n) for n in update['nodes_added'] + update['nodes_updated'])
        edges.update((e['id'], e) for e in update['edges_added'] + update['edges_updated'])
    return {**previous, 'nodes': list(nodes.values()), 'edges': list(edges.values())}


@pytest.mark.parametrize('last_poll', [0, 1, 4, 7])
def test_final_reconciliation_does_not_depend_on_last_poll(tmp_path, last_poll):
    path = tmp_path / 'events.jsonl'
    path.touch()
    state = _LiveState('s1', path)
    initial = state.live_update(-1)
    for sequence in range(1, 8):
        append(path, event(sequence, 'process:p' if sequence == 1 else f'file:{sequence}.txt',
                           'process' if sequence == 1 else 'file'))
        if sequence == last_poll:
            initial = state.live_update(-1)
    final = finalized(path)
    unchanged = deepcopy(final)
    state.finish(final)
    response = state.live_update(initial['sequence'])
    received = consume(initial['graph'], response)
    assert received == project_viewer_graph(final)
    assert response['live_finished'] is True
    assert response['live_evidence_counts']['os_runtime'] == 7
    assert [row['event']['event_id'] for row in state.snapshot()['raw_events']] == [
        f'ev-{i}' for i in range(1, 8)
    ]
    assert final == unchanged, 'finalization must not rewrite raw evidence'
    repeat = state.live_update(response['sequence'])
    assert repeat['kind'] == 'noop'
    assert repeat['sequence'] == response['sequence']
    assert state.live_update(-1)['graph'] == received


def test_terminal_replaces_provisional_identities_and_updated_metadata(tmp_path):
    path = tmp_path / 'events.jsonl'
    append(path, event(1, 'process:provisional'))
    state = _LiveState('s1', path)
    initial = state.live_update(-1)
    # A canonical materialization can replace provisional identities and metadata,
    # so draining the event tail or upserting new nodes alone is insufficient.
    canonical_path = tmp_path / 'canonical.jsonl'
    append(canonical_path, event(1, 'process:canonical'))
    final = finalized(canonical_path)
    final['nodes'][0]['attributes']['canonical_final'] = True
    state.finish(final)
    received = consume(initial['graph'], state.live_update(initial['sequence']))
    assert received == project_viewer_graph(final)
    assert 'process:provisional' not in {n['id'] for n in received['nodes']}
    assert received['source_path'] == final['source_path']


def test_terminal_snapshot_honors_payload_budget(tmp_path, monkeypatch):
    monkeypatch.setattr(live_module, 'VIEWER_MAX_NODES', 1)
    path = tmp_path / 'events.jsonl'
    append(path, event(1, 'process:p'))
    state = _LiveState('s1', path)
    initial = state.live_update(-1)
    state.finish(finalized(path))
    received = consume(initial['graph'], state.live_update(initial['sequence']))
    assert received['live_payload_compact'] is True
    assert received['node_count'] == 2
    assert received['nodes'] == received['edges'] == []
