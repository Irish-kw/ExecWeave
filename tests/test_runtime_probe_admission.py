"""Real loopback endpoints must not become evidence for an unrelated launch."""
from __future__ import annotations

import json
import socket
import sys

import pytest

import execweave.auto_specialized as auto_module
import execweave.collector as collector_module
from execweave.live import run_live
from test_auto_specialized import _start_models_server, _start_ollama_server, _stop_server


@pytest.mark.parametrize('runtime', ['ollama', 'llamacpp', 'vllm'])
@pytest.mark.parametrize('delay', [0.20, 0.55])
def test_delayed_failed_launch_never_claims_preexisting_catalog(monkeypatch, tmp_path, runtime, delay):
    payload = ({'models': [{'name': 'foreign:latest'}]} if runtime == 'ollama'
               else {'data': [{'id': 'foreign:latest', 'owned_by': 'local'}]})
    start = _start_ollama_server if runtime == 'ollama' else _start_models_server
    server, thread = start(payload)
    port = server.server_address[1]
    monkeypatch.setenv('OLLAMA_HOST', f'http://127.0.0.1:{port}')
    command = (['ollama', 'serve'] if runtime == 'ollama' else
               ['llama-server', '--port', str(port)] if runtime == 'llamacpp' else
               ['vllm', 'serve', 'unstarted', '--port', str(port)])
    # No grace override: the launch survives the production grace, then fails.
    monkeypatch.setattr(collector_module, 'resolve_launch_command', lambda _: [
        sys.executable, '-c', f'import time; time.sleep({delay}); raise SystemExit(2)'])
    try:
        result = run_live(command, watch_root=tmp_path, output_dir=tmp_path / runtime,
                          collect_filesystem=False, collect_network=False,
                          poll_interval=.02, port=0, open_browser=False, linger_seconds=0)
        assert result.return_code == 2
        assert result.materialized_event_stream == result.event_stream
        assert not result.semantic_sidecar.exists() or result.semantic_sidecar.stat().st_size == 0
        graph = json.loads(result.graph.read_text(encoding='utf-8'))
        assert not any(n.get('type') == 'model' for n in graph['nodes'])
        assert not any(e['relation'] in ('LOADED_MODEL', 'SERVES_MODEL') for e in graph['edges'])
        assert thread.is_alive(), 'an unrelated server must never be stopped by cleanup'
    finally:
        _stop_server(server, thread)


def test_occupied_non_http_endpoint_is_not_admitted(monkeypatch, tmp_path):
    monkeypatch.setenv('EXECWEAVE_SEMANTIC_SIDECAR', str(tmp_path / 'semantic.jsonl'))
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        listener.listen()
        admission = auto_module.prepare_live_specialized_probe(
            ['llama-server', '--port', str(listener.getsockname()[1])])
        assert admission.spec is None


def test_uncertain_endpoint_does_not_authorize_a_probe(monkeypatch, tmp_path):
    monkeypatch.setenv('EXECWEAVE_SEMANTIC_SIDECAR', str(tmp_path / 'semantic.jsonl'))
    def denied(*args, **kwargs):
        raise PermissionError('no socket access')
    monkeypatch.setattr(auto_module.socket, 'create_connection', denied)
    assert auto_module.prepare_live_specialized_probe(['ollama', 'serve']).spec is None


def test_admission_does_not_probe_without_run_sidecar(monkeypatch):
    monkeypatch.delenv('EXECWEAVE_SEMANTIC_SIDECAR', raising=False)
    def forbidden(*args, **kwargs):
        raise AssertionError('inactive integration must not inspect the endpoint')
    monkeypatch.setattr(auto_module.socket, 'create_connection', forbidden)
    assert auto_module.prepare_live_specialized_probe(['ollama', 'serve']).spec is None


def test_preexisting_successful_noop_does_not_claim_catalog(monkeypatch, tmp_path):
    server, thread = _start_ollama_server({'models': [{'name': 'foreign:latest'}]})
    monkeypatch.setenv('OLLAMA_HOST', f'http://127.0.0.1:{server.server_address[1]}')
    monkeypatch.setattr(collector_module, 'resolve_launch_command', lambda _: [
        sys.executable, '-c', 'import time; time.sleep(.2)'])
    try:
        result = run_live(['ollama', 'serve'], watch_root=tmp_path, output_dir=tmp_path / 'noop',
                          collect_filesystem=False, collect_network=False,
                          port=0, open_browser=False, linger_seconds=0)
        assert result.return_code == 0
        assert not result.semantic_sidecar.exists() or result.semantic_sidecar.stat().st_size == 0
    finally:
        _stop_server(server, thread)
