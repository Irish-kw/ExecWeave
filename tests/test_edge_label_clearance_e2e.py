"""Measure visible SVG text against real node boxes, independently of route metrics."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from test_layout_pipeline_geometry_e2e import _open
from test_viewer_agent_isolation_e2e import _browser, _launch

pytestmark = pytest.mark.viewer_e2e


def hidden_path_fixture():
    def node(identity, kind, **attrs):
        return {'id': identity, 'type': kind, 'name': identity, 'attributes': attrs}
    triples = [('a', 'b', 'SPAWNED_AGENT'), ('a', 'sa', 'OBSERVED_PROVIDER_SESSION'),
               ('b', 'sb', 'OBSERVED_PROVIDER_SESSION'), ('sa', 'm', 'INVOKES_MODEL'),
               ('sb', 'm', 'INVOKES_MODEL'), ('sa', 'fa', 'OBSERVED_FILE_CHANGE'),
               ('sb', 'fb', 'OBSERVED_FILE_CHANGE')]
    return {'session_id': 'label-clearance', 'nodes': [
        node('a', 'agent', agent_role='root', agent_path='/root'),
        node('b', 'agent', agent_path='/root/b'), node('sa', 'provider_session'),
        node('sb', 'provider_session'), node('m', 'model'),
        node('fa', 'file', path='/tmp/a.txt'), node('fb', 'file', path='/tmp/b.txt'),
        node('orphan', 'model')], 'edges': [
            {'id': f'e{i}', 'source': a, 'target': b, 'relation': r, 'first_sequence': i+1,
             'causal': False, 'attributes': {}} for i, (a, b, r) in enumerate(triples)]}


READ_LABELS = """() => {
 const nodes=[...document.querySelectorAll('.node')].map(n=>({id:n.dataset.id,box:n.querySelector('rect').getBoundingClientRect()}));
 const labels=[...document.querySelectorAll('#svg text.label')];
 const overlaps=[], positions=[];
 for(const label of labels){
   const style=getComputedStyle(label);if(style.display==='none'||style.visibility==='hidden'||Number(style.opacity)===0)continue;
   const box=label.getBoundingClientRect();if(box.width<=0||box.height<=0)continue;
   positions.push({id:label.dataset.edgeId,x:label.getAttribute('x'),y:label.getAttribute('y'),text:label.textContent});
   for(const node of nodes){
     const w=Math.min(box.right,node.box.right)-Math.max(box.left,node.box.left);
     const h=Math.min(box.bottom,node.box.bottom)-Math.max(box.top,node.box.top);
     if(w>0.1&&h>0.1)overlaps.push({edge:label.dataset.edgeId,node:node.id,area:w*h,text:label.textContent});
   }
 }
 return {node_count:nodes.length,label_count:labels.length,positions,overlaps};
}"""


@pytest.mark.parametrize('theme', ['dark', 'light'])
def test_hidden_path_labels_remain_readable_after_arrange_and_focus(tmp_path, theme):
    manager, executable = _browser()
    with manager as playwright:
        browser = _launch(playwright, executable)
        try:
            page = _open(browser, hidden_path_fixture(), theme)
            page.locator('#file-graph-filter').select_option('all')
            page.locator('#arrange').click()
            initial = page.evaluate(READ_LABELS)
            # Guard against a vacuous zero from querying a nonexistent CSS class.
            assert initial['node_count'] == 6 and initial['label_count'] == 5
            assert len(initial['positions']) == 5
            assert initial['overlaps'] == [], initial['overlaps']
            raw = page.evaluate('JSON.stringify(window.__execweaveCore.getGraph())')
            before = page.locator('#svg .edge').evaluate_all("es=>es.map(e=>e.getAttribute('d'))")
            page.locator('#arrange').click()
            assert initial['positions'] == page.evaluate(READ_LABELS)['positions']
            assert before == page.locator('#svg .edge').evaluate_all("es=>es.map(e=>e.getAttribute('d'))")
            page.locator('.node[data-id="b"]').click()
            assert page.evaluate(READ_LABELS)['overlaps'] == []
            assert raw == page.evaluate('JSON.stringify(window.__execweaveCore.getGraph())')
            assert not page._execweave_errors
            out = Path(os.environ.get('EXECWEAVE_VISUAL_ARTIFACT_DIR', str(tmp_path)))/f'label-clearance-{theme}'
            out.mkdir(parents=True, exist_ok=True)
            (out/'geometry.json').write_text(json.dumps(initial, indent=2), encoding='utf-8')
            page.locator('#svg').screenshot(path=str(out/'focused.png'))
        finally:
            browser.close()
