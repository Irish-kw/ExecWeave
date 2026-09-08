"""Actual HTTP polling must apply the final graph before FINISHED stops polling."""
from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import threading
from urllib.parse import urlsplit

import pytest

from execweave.dashboard_shell import render_static_dashboard_html
from execweave.live import _LiveState, _LocalThreadingHTTPServer, _handler_factory
from execweave.viewer_projection import project_viewer_graph
from test_live_final_snapshot import append, event, finalized
from test_viewer_agent_isolation_e2e import _browser, _launch

pytestmark = pytest.mark.viewer_e2e


def test_final_graph_is_applied_before_polling_stops_and_matches_reopened_viewer(tmp_path):
    path = tmp_path / 'events.jsonl'
    append(path, event(1, 'process:p'))
    responses, requests = [], []

    class ObservedState(_LiveState):
        def live_update(self, after):
            payload = super().live_update(after)
            responses.append(deepcopy(payload))
            return payload

    state = ObservedState('s1', path)
    token = 'final-snapshot-regression'
    handler = _handler_factory(state, token)

    class ObservedHandler(handler):
        def do_GET(self):
            requests.append(urlsplit(self.path).path)
            super().do_GET()

    server = _LocalThreadingHTTPServer(('127.0.0.1', 0), ObservedHandler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    manager, executable = _browser()
    try:
        with manager as playwright:
            browser = _launch(playwright, executable)
            try:
                page = browser.new_page(viewport={'width': 1440, 'height': 1000})
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.on('console', lambda msg: errors.append(msg.text) if msg.type == 'error' else None)
                page.goto(f'http://127.0.0.1:{server.server_port}/?t={token}')
                page.wait_for_function("window.__execweaveCore?.getGraph().nodes?.length===2")
                page.locator('#zoom-in').click()
                page.wait_for_timeout(250)
                page.locator('.node[data-id="process:p"]').click()
                camera = page.locator('#viewport').get_attribute('transform')
                first = page.evaluate('window.__execweaveCore.getGraph()')
                for i in range(2, 8):
                    append(path, event(i, f'file:{i}.txt', 'file'))
                final = finalized(path)
                # Final-only metadata makes this deterministic even if a poll
                # happens to read the last runtime batch before finish().
                final['final_artifact_marker'] = 'authoritative-after-materialization'
                expected = project_viewer_graph(final)
                viewer = tmp_path / 'viewer.html'
                viewer.write_text(render_static_dashboard_html(expected), encoding='utf-8')
                state.finish(final, final_html=viewer.read_text(encoding='utf-8'))
                page.wait_for_function("document.getElementById('status').textContent==='FINISHED'")
                completed = page.evaluate('window.__execweaveCore.getGraph()')
                display = page.evaluate('window.__execweaveCore.getDisplayGraph()')
                assert completed == expected, 'FINISHED exposed a graph older than the saved artifact'
                assert first['node_count'] < completed['node_count']
                assert page.locator('#viewport').get_attribute('transform') == camera
                assert page.locator('.node.selected').get_attribute('data-id') == 'process:p'
                assert not page.locator('#finished-actions').is_hidden()
                poll_count = requests.count('/live.json')
                page.wait_for_timeout(1200)
                assert requests.count('/live.json') == poll_count, 'polling continued after FINISHED'
                assert '/final' not in requests
                assert any(
                    data.get('live_finished') and (
                        data['kind'] == 'snapshot' or any('final_graph' in u for u in data.get('updates', []))
                    ) for data in responses
                )
                out = Path(os.environ.get('EXECWEAVE_VISUAL_ARTIFACT_DIR', str(tmp_path))) / 'final-snapshot'
                out.mkdir(parents=True, exist_ok=True)
                page.locator('#svg').screenshot(path=str(out / 'completed-live.png'))
                page.goto(viewer.as_uri())
                page.wait_for_selector('.node')
                reopened = page.evaluate('window.__execweaveCore.getGraph()')
                assert reopened == completed
                reopened_display = page.evaluate('window.__execweaveCore.getDisplayGraph()')
                assert reopened_display == display
                assert not errors, errors
                page.locator('#svg').screenshot(path=str(out / 'reopened.png'))
                (out / 'protocol.json').write_text(json.dumps({
                    'initial': first, 'final': completed, 'reopened': reopened,
                    'responses': responses, 'request_paths': requests, 'js_errors': errors,
                }, indent=2), encoding='utf-8')
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
