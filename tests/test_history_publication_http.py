"""Real authenticated HTTP publication with synthetic history, no provider calls."""
from __future__ import annotations

import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from execweave import live, live_core
from test_observed_history import entry, graph, message


@pytest.fixture
def history_server(tmp_path):
    event_path = tmp_path / 'events.jsonl'
    event_path.write_text('', encoding='utf-8')
    records = [entry('agent:a', [message(i) for i in range(210)])]
    (tmp_path / 'conversations.json').write_text(json.dumps({'entries': records}), encoding='utf-8')
    state = live._LiveState('run-one', event_path)
    state.finish(graph())
    server = live_core._LocalThreadingHTTPServer(
        ('127.0.0.1', 0), live._handler_factory(state, 'synthetic-history-token'))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_address[1]}', records
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


@pytest.mark.parametrize('token', [None, 'wrong-token'])
def test_history_index_requires_native_server_authentication(history_server, token):
    base, _ = history_server
    headers = {'X-ExecWeave-Token': token} if token else {}
    with pytest.raises(HTTPError) as denied:
        urlopen(Request(base + '/conversations.json', headers=headers), timeout=5)
    assert denied.value.code == 401
    denied.value.close()


def test_authenticated_history_publication_keeps_middle_and_final_records(history_server):
    base, records = history_server
    request = Request(base + '/conversations.json', headers={'X-ExecWeave-Token': 'synthetic-history-token'})
    with urlopen(request, timeout=5) as response:
        assert response.status == 200
        assert response.headers['Cache-Control'] == 'no-store'
        assert json.load(response)['entries'] == records
    assert records[0]['conversation_preview']['messages'][83]['text'] == 'record 83'
    assert records[0]['conversation_preview']['messages'][-1]['text'] == 'record 209'
