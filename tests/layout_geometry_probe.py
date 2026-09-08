"""Independent measurements of boxes and actual final SVG paths in Chromium."""
from __future__ import annotations

import math
import re
from typing import Any

READ_SVG = r"""() => {
  const svg=document.getElementById('svg'),viewport=document.getElementById('viewport');
  const nodes=[...svg.querySelectorAll('.node')].map(g=>{
    const r=g.querySelector('rect'),m=g.transform.baseVal.consolidate().matrix;
    return{id:g.dataset.id,lane:g.dataset.layoutLane,x:m.e,y:m.f,w:+r.getAttribute('width'),h:+r.getAttribute('height')};
  });
  const edges=[...svg.querySelectorAll('.edge')].map(p=>{
    const d=p.getAttribute('d'),length=p.getTotalLength(),steps=Math.max(24,Math.min(192,Math.ceil(length/8)));
    const sampled=[];for(let i=0;i<=steps;i++){const q=p.getPointAtLength(length*i/steps);sampled.push([q.x,q.y])}
    return{id:p.dataset.edgeId,source:p.dataset.source,target:p.dataset.target,d,kind:p.dataset.routeKind,
      geometry:p.dataset.geometryKind,length,sampled};
  });
  return{nodes,edges,fit_scale:viewport.transform.baseVal.consolidate().matrix.a};
}"""


def polyline(edge: dict) -> list[tuple[float, float]]:
    """Parse exact M/L/H/V vertices; curves use Chromium's own arc-length samples."""
    if re.search('[CQASTZcqastz]', edge['d']):
        return [tuple(p) for p in edge['sampled']]
    tokens = re.findall(r'[MLHV]|[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?', edge['d'])
    result = []
    i = 0
    x = y = 0.0
    while i < len(tokens):
        op = tokens[i]
        i += 1
        if op in ('M', 'L'):
            x, y = float(tokens[i]), float(tokens[i + 1])
            i += 2
        elif op == 'H':
            x = float(tokens[i])
            i += 1
        elif op == 'V':
            y = float(tokens[i])
            i += 1
        else:
            raise AssertionError(f'Unrecognized path command: {op}')
        result.append((x, y))
    return result


def side(a, b, c):
    return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])


def crossed(a, b, c, d):
    def opposite(p, q):
        return p > 1e-6 and q < -1e-6 or q > 1e-6 and p < -1e-6
    return opposite(side(a, b, c), side(a, b, d)) and opposite(side(c, d, a), side(c, d, b))


def cuts_box(a, b, box):
    # Independent slab intersection, excluding tangent/boundary contact.
    low, high = 0.0, 1.0
    for index, lower, upper in ((0, box['x'] + 1e-6, box['x'] + box['w'] - 1e-6),
                                (1, box['y'] + 1e-6, box['y'] + box['h'] - 1e-6)):
        delta = b[index] - a[index]
        if abs(delta) < 1e-6:
            if not lower <= a[index] <= upper:
                return False
        else:
            t1, t2 = (lower - a[index])/delta, (upper - a[index])/delta
            low, high = max(low, min(t1, t2)), min(high, max(t1, t2))
            if low >= high:
                return False
    return low < high


def measure(snapshot: dict[str, Any]) -> dict[str, Any]:
    nodes, edges = snapshot['nodes'], snapshot['edges']
    paths = [polyline(e) for e in edges]
    overlap_pairs, crossing_pairs, intersection_pairs = [], [], []
    for i, node in enumerate(nodes):
        assert all(math.isfinite(node[k]) for k in ('x', 'y', 'w', 'h'))
        for other in nodes[:i]:
            if (min(node['x']+node['w'], other['x']+other['w'])-max(node['x'], other['x']) > 1e-6
                    and min(node['y']+node['h'], other['y']+other['h'])-max(node['y'], other['y']) > 1e-6):
                overlap_pairs.append([node['id'], other['id']])
    for i, path in enumerate(paths):
        for j, other in enumerate(paths[:i]):
            if any(crossed(a,b,c,d) for a,b in zip(path,path[1:]) for c,d in zip(other,other[1:])):
                crossing_pairs.append([edges[i]['id'], edges[j]['id']])
        for node in nodes:
            if node['id'] in (edges[i]['source'], edges[i]['target']):
                continue
            if any(cuts_box(a,b,node) for a,b in zip(path,path[1:])):
                intersection_pairs.append([edges[i]['id'], node['id']])
    lengths = sorted(e['length'] for e in edges)
    all_x = [v for n in nodes for v in (n['x'], n['x']+n['w'])] + [p[0] for path in paths for p in path]
    all_y = [v for n in nodes for v in (n['y'], n['y']+n['h'])] + [p[1] for path in paths for p in path]
    adjacent = {n['id']: set() for n in nodes}
    for edge in edges:
        assert edge['source'] in adjacent and edge['target'] in adjacent
        adjacent[edge['source']].add(edge['target'])
        adjacent[edge['target']].add(edge['source'])
    seen, components = set(), 0
    for start in adjacent:
        if start in seen:
            continue
        components += 1
        queue = [start]
        while queue:
            item = queue.pop()
            if item not in seen:
                seen.add(item)
                queue.extend(adjacent[item]-seen)
    return {
        'EDGE_CROSSINGS': len(crossing_pairs), 'NODE_OVERLAPS': len(overlap_pairs),
        'EDGE_NODE_INTERSECTIONS': len(intersection_pairs),
        'MAX_EDGE_LENGTH': max(lengths, default=0),
        'P95_EDGE_LENGTH': lengths[max(0, math.ceil(len(lengths)*.95)-1)] if lengths else 0,
        'GRAPH_WIDTH': max(all_x, default=0)-min(all_x, default=0),
        'GRAPH_HEIGHT': max(all_y, default=0)-min(all_y, default=0),
        'FIT_SCALE': snapshot['fit_scale'], 'VISIBLE_NODE_COUNT': len(nodes),
        'VISIBLE_EDGE_COUNT': len(edges), 'SECONDARY_COMPONENT_COUNT': max(0, components-1),
        'overlap_pairs': overlap_pairs, 'crossing_pairs': crossing_pairs,
        'intersection_pairs': intersection_pairs,
    }
