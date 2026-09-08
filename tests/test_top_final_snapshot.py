"""The terminal UI must reconcile the same final graph as the web Dashboard."""
from __future__ import annotations

from copy import deepcopy

import pytest

import execweave.live as live_module
from execweave.live import _LiveState
from execweave.top import TerminalState
from execweave.viewer_projection import project_viewer_graph
from test_live_final_snapshot import append, event, finalized


def assert_final(client, response, graph):
    client.apply_response(response)
    expected = project_viewer_graph(graph)
    assert client.finished is True
    assert client.connection_status == 'FINISHED'
    assert client.sequence == response['sequence']
    assert client.nodes == {n['id']: n for n in expected['nodes']}
    assert client.edges == {e['id']: e for e in expected['edges']}
    assert client.node_count == expected['node_count']
    assert client.edge_count == expected['edge_count']


@pytest.mark.parametrize('late_poll', [False, True])
def test_top_replaces_provisional_identities_on_terminal_delta(tmp_path, late_poll):
    path = tmp_path / 'events.jsonl'
    append(path, event(1, 'process:provisional'))
    state = _LiveState('s1', path)
    client = TerminalState()
    client.apply_response(state.live_update(-1))
    append(path, event(2, 'file:late.txt', 'file'))
    if late_poll:
        client.apply_response(state.live_update(client.sequence))
    final_path = tmp_path / 'canonical.jsonl'
    append(final_path, event(1, 'process:canonical'))
    append(final_path, event(2, 'file:late.txt', 'file'))
    final = finalized(final_path)
    before = deepcopy(final)
    state.finish(final)
    response = state.live_update(client.sequence)
    assert response['kind'] == 'delta'
    assert_final(client, response, final)
    assert 'process:provisional' not in client.nodes
    assert final == before
    last = deepcopy(client.nodes)
    client.apply_response(state.live_update(client.sequence))
    assert client.nodes == last and client.finished


def test_top_receives_final_metadata_even_when_every_event_was_polled(tmp_path):
    path = tmp_path / 'events.jsonl'
    append(path, event(1, 'process:p'))
    state = _LiveState('s1', path)
    client = TerminalState()
    client.apply_response(state.live_update(-1))
    final = finalized(path)
    final['nodes'][0]['attributes']['canonical_final'] = True
    final['edges'][0]['canonical_final'] = True
    state.finish(final)
    assert_final(client, state.live_update(client.sequence), final)


def test_top_final_compact_payload_removes_stale_entity_details(tmp_path, monkeypatch):
    path = tmp_path / 'events.jsonl'
    append(path, event(1, 'process:p'))
    state = _LiveState('s1', path)
    client = TerminalState()
    client.apply_response(state.live_update(-1))
    assert client.nodes
    monkeypatch.setattr(live_module, 'VIEWER_MAX_NODES', 1)
    state.finish(finalized(path))
    client.apply_response(state.live_update(client.sequence))
    assert client.finished and client.compact
    assert client.node_count == 2
    assert client.nodes == client.edges == {}


def test_top_keeps_legacy_terminal_delta_compatibility():
    client = TerminalState(sequence=1, nodes={'n': {'id': 'n', 'type': 'file'}})
    client.apply_response({'kind': 'delta', 'base_sequence': 1, 'sequence': 2,
        'updates': [{'sequence': 2, 'terminal': True, 'event_count': 1,
                     'node_count': 1, 'edge_count': 0}], 'live_finished': True})
    assert client.finished and client.sequence == 2
    assert client.node_count == 1 and 'n' in client.nodes
