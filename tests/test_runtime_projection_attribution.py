"""A provider-shaped root ID is not proof that it is an endpoint-scoped runtime."""
from __future__ import annotations

import json
import shutil
import subprocess

import pytest
from execweave.viewer_dashboard_focus import _FOCUS_JS


def unowned_runtime_fixture(root='agent:Ollama'):
    return {'session_id': 'failed-launch', 'nodes': [
        {'id': root, 'type': 'agent', 'name': 'Ollama', 'attributes': {}},
        {'id': 'model-runtime:ollama:foreign', 'type': 'model_runtime', 'name': 'ollama',
         'attributes': {'provider': 'ollama', 'endpoint': 'http://127.0.0.1:40343'}},
        {'id': 'model:ollama:preexisting:latest', 'type': 'model', 'name': 'preexisting:latest',
         'attributes': {'provider': 'ollama'}}],
        'edges': [{'id': 'loaded', 'source': 'model-runtime:ollama:foreign',
                   'target': 'model:ollama:preexisting:latest', 'relation': 'LOADED_MODEL',
                   'causal': False, 'inferred': None}]}


def project_focus(graph):
    executable = shutil.which('node')
    assert executable, 'Node is required for the actual projection contract'
    source = 'let execweaveDashboardGraph=data=>data;\n' + _FOCUS_JS
    source += '\nconst raw=' + json.dumps(graph) + ';const before=JSON.stringify(raw);'
    source += 'const out=execweaveDashboardGraph(raw);if(before!==JSON.stringify(raw))throw Error("raw mutated");'
    source += 'process.stdout.write(JSON.stringify(out));'
    done = subprocess.run([executable, '-'], input=source, text=True, encoding='utf-8',
                          capture_output=True, check=True, timeout=30)
    return json.loads(done.stdout)


@pytest.mark.parametrize('root', ['agent:Ollama', 'agent:ollama'])
def test_single_runtime_and_single_root_are_not_same_identity(root):
    graph = unowned_runtime_fixture(root)
    display = project_focus(graph)
    assert {n['id'] for n in display['nodes']} == {n['id'] for n in graph['nodes']}
    loaded = next(e for e in display['edges'] if e['relation'] == 'LOADED_MODEL')
    assert loaded['source'] == 'model-runtime:ollama:foreign'
    assert loaded['causal'] is False and loaded['inferred'] is None
    assert not loaded.get('viewer_canonicalized')


def test_actual_runtime_observation_is_preserved_without_a_launch():
    graph = unowned_runtime_fixture()
    graph['nodes'] = graph['nodes'][1:]
    display = project_focus(graph)
    assert len(display['nodes']) == 2
    assert display['edges'][0]['source'] == 'model-runtime:ollama:foreign'


def test_explicit_root_runtime_relation_is_not_an_identity_alias():
    graph = unowned_runtime_fixture()
    graph['edges'].insert(0, {'id': 'ownership', 'source': 'agent:Ollama',
        'target': 'model-runtime:ollama:foreign', 'relation': 'OBSERVED_RUNTIME',
        'causal': False, 'inferred': True})
    display = project_focus(graph)
    assert len(display['nodes']) == 3
    assert {(e['source'], e['relation'], e['target']) for e in display['edges']} == {
        (e['source'], e['relation'], e['target']) for e in graph['edges']}
