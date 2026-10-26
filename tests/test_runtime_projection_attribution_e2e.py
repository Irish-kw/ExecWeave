"""The final Dashboard must not relabel an ambient runtime as the launched agent."""
from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from execweave.dashboard_shell import render_static_dashboard_html
from execweave.viewer_projection import project_viewer_graph
from test_runtime_projection_attribution import unowned_runtime_fixture
from test_viewer_agent_isolation_e2e import _browser, _launch

pytestmark = pytest.mark.viewer_e2e


def assert_runtime_ownership(page):
    graph = page.evaluate('window.__execweaveCore.getDisplayGraph()')
    assert len(graph['nodes']) == 3
    assert len(graph['edges']) == 1
    loaded = graph['edges'][0]
    assert loaded['relation'] == 'LOADED_MODEL'
    assert loaded['source'] == 'model-runtime:ollama:foreign'
    assert loaded['target'] == 'model:ollama:preexisting:latest'
    assert loaded['causal'] is False
    assert page.locator('.node[data-id="model-runtime:ollama:foreign"]').count() == 1
    assert page.locator('.edge[data-source="agent:Ollama"]').count() == 0
    assert page.locator('.edge[data-source="model-runtime:ollama:foreign"]').count() == 1


@pytest.mark.parametrize('theme', ['dark', 'light'])
@pytest.mark.parametrize('transport', ['http', 'file'])
def test_unowned_model_source_stays_runtime_in_real_viewer(tmp_path, theme, transport):
    raw = unowned_runtime_fixture()
    frozen = json.dumps(raw, sort_keys=True)
    html = render_static_dashboard_html(project_viewer_graph(raw))
    viewer = tmp_path / 'viewer.html'
    viewer.write_text(html, encoding='utf-8')
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_GET(self):
            body = html.encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        manager, executable = _browser()
        with manager as playwright:
            browser = _launch(playwright, executable)
            try:
                page = browser.new_page(viewport={'width': 1600, 'height': 1100})
                errors = []
                page.on('pageerror', lambda e: errors.append(str(e)))
                page.on('console', lambda m: errors.append(m.text) if m.type == 'error' else None)
                url = viewer.as_uri() if transport == 'file' else f'http://127.0.0.1:{server.server_address[1]}/'
                page.goto(url)
                page.wait_for_selector('.node')
                if page.locator('html').get_attribute('data-theme') != theme:
                    page.locator('#theme-toggle').click()
                before = page.evaluate('JSON.stringify(window.__execweaveCore.getGraph())')
                assert_runtime_ownership(page)
                page.locator('#arrange').click()
                page.locator('#fit').click()
                page.wait_for_timeout(250)
                page.locator('.node[data-id="agent:Ollama"]').click()
                assert_runtime_ownership(page)
                assert before == page.evaluate('JSON.stringify(window.__execweaveCore.getGraph())')
                assert frozen == json.dumps(raw, sort_keys=True)
                out = Path(os.environ.get('EXECWEAVE_VISUAL_ARTIFACT_DIR', str(tmp_path))) / f'runtime-attribution-{transport}-{theme}'
                out.mkdir(parents=True, exist_ok=True)
                page.locator('#svg').screenshot(path=str(out / 'dashboard.png'))
                (out / 'graphs.json').write_text(json.dumps({'raw': raw,
                    'display': page.evaluate('window.__execweaveCore.getDisplayGraph()')}), encoding='utf-8')
                assert not errors, errors
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
