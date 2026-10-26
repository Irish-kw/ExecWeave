"""Nontrivial display-shape fixtures for the final SVG geometry gate."""
from __future__ import annotations

from dashboard_readability_fixture import build_dashboard_readability_graph
from test_graph_arrange_constraints_e2e import _arrange_graph
from test_graph_edge_routing_e2e import _dense_graph

CASES = ('single-agent', '3-agent', '5-agent', '8-agent', 'shared-model', 'shared-tool',
         'many-files', 'process-tree', 'network-endpoints', 'disconnected-components',
         'folded', 'long-label', 'mixed')


def fixture(name: str) -> dict:
    if name == 'shared-tool':
        return build_dashboard_readability_graph()
    if name == 'long-label':
        return _arrange_graph()
    if name == 'mixed':
        return _dense_graph()
    count = {'3-agent': 3, '5-agent': 5, '8-agent': 8, 'shared-model': 8}.get(name, 1)
    nodes, edges = [], []
    def node(identity, kind, label=None, **attrs):
        nodes.append({'id': identity, 'type': kind, 'name': label or identity, 'attributes': attrs})
    def edge(source, target, relation='USES', **attrs):
        edges.append({'id': f'e{len(edges)}', 'source': source, 'target': target, 'relation': relation,
                      'first_sequence': len(edges)+1, 'attributes': attrs})
    node('root', 'agent', '/root', agent_role='root', agent_path='/root')
    for i in range(1, count):
        node(f'a{i}', 'agent', f'/root/worker{i}', agent_path=f'/root/worker{i}')
        edge('root', f'a{i}', 'SPAWNED_AGENT')
    owners = ['root'] + [f'a{i}' for i in range(1, count)]
    if name not in ('many-files', 'folded', 'process-tree', 'network-endpoints', 'disconnected-components'):
        node('model', 'model', 'shared-model')
        for i, owner in enumerate(owners):
            edge(owner, 'model', 'USES_MODEL')
            node(f'f{i}', 'file', f'report-{count-i}.txt')
            edge(owner, f'f{i}', 'WROTE_FILE')
    if name in ('many-files', 'folded'):
        for i in range(36):
            node(f'f{i:02}', 'file', f'artifact-{35-i:02}.txt')
            edge('root', f'f{i:02}', 'WROTE_FILE')
    if name in ('process-tree', 'network-endpoints'):
        for i in range(7):
            node(f'p{i}', 'process', f'worker_{i}_'+'long_command_'*12 if i == 0 else f'python_{i}')
            edge('root' if i == 0 else f'p{(i-1)//2}', f'p{i}', 'LAUNCHED' if i == 0 else 'SPAWNED')
        if name == 'network-endpoints':
            for i in range(12):
                node(f'n{i}', 'network_endpoint', f'127.0.0.1:{12000+i}', host='127.0.0.1', port=12000+i)
                edge(f'p{i%7}', f'n{i}', 'CONNECTED_TO')
    if name == 'disconnected-components':
        for i in range(5):
            node(f'd{i}', 'model', f'orphan-model-{i}')
            node(f'q{i}', 'process', f'orphan-process-{i}')
            edge(f'q{i}', f'd{i}', 'USES_MODEL')
    return {'session_id': f'layout-{name}', 'nodes': nodes, 'edges': edges,
            'node_count': len(nodes), 'edge_count': len(edges), 'event_count': len(edges)}
