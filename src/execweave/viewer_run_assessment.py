"""One run-level assessment panel shared by Live and static Dashboards."""
from __future__ import annotations

from .viewer_delivery_status import delivery_scripts
from .viewer_task_validation import inject_task_reports
from .viewer_controlled_checks import inject_controlled_checks

RUN_ASSESSMENT_JS = r"""
(()=>{
'use strict';
if(window.__execweaveRunAssessment)return;
const host=document.getElementById('inspector');if(!host)return;
const make=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=String(text);return n};
const object=value=>value&&typeof value==='object'&&!Array.isArray(value)?value:{};
const count=value=>Number.isSafeInteger(value)&&value>=0?String(value):'unknown';
let lastSignature='',currentKey='',latest=null;
const panel=make('section');panel.id='execweave-run-assessment';panel.className='run-assessment-section';
panel.setAttribute('aria-label','Run assessment');
// Preserve the historical first/second inspector-section CSS contracts.
const selectionHost=document.getElementById('details')?.closest('.inspector-section');
if(selectionHost?.parentElement===host)selectionHost.prepend(panel);else host.append(panel);
function graphNow(){return window.__execweaveCore?.getGraph?.()||window.__execweaveStaticGraph||{}}
function compatible(value,graph){
  return value?.schema_version==='0.1'&&value.scope==='published_graph_metadata'&&
    typeof graph.session_id==='string'&&value.session_id===graph.session_id&&
    (value.source_path||null)===(graph.source_path||null);
}
function card(key,title,state,label,description){
  const n=make('div');n.className='run-assessment-card';n.dataset.axis=key;n.dataset.state=state;
  n.append(make('h3',title),make('strong',label),make('p',description));panel.append(n);return n;
}
function render(value){
  const next=JSON.stringify(value);if(next===lastSignature)return;lastSignature=next;
  // Keep disclosure choice while updating facts; do not replace the selection inspector.
  const selected=document.getElementById('details'),anchor=selected?.getBoundingClientRect().top,scroll=host.scrollTop;
  const expanded=panel.querySelector('details')?.open||false;panel.replaceChildren();
  panel.append(make('h2','Run assessment'));
  const execution=object(value?.execution),task=object(value?.task_validation),content=object(value?.content);
  const labels={succeeded:'Process exited successfully',failed:'Process failed',interrupted:'Interrupted',collector_failed:'Collector failed',unknown:'Terminal result unknown'};
  const state=Object.hasOwn(labels,execution.state)?execution.state:'unknown';
  const exit=Number.isSafeInteger(execution.return_code)?`Recorded exit code: ${execution.return_code}.`:'Exit code unavailable.';
  card('execution','Execution',state,labels[state],
    exit+' Task outcome is assessed separately.');
  card('task','Task verification','unverified','Not independently verified',
    `Recorded task reports: ${count(task.reported_completed)} completed; ${count(task.reported_failed)} failed. These are not test results.`);
  if(Number.isSafeInteger(task.both_reported)&&task.both_reported>0){
    panel.lastElementChild.append(make('p',`${task.both_reported} task(s) have both completion and failure reports; neither report is discarded.`));
  }
  const gaps=content.state==='declared_gaps';
  card('content','Recorded content',gaps?'declared_gaps':'not_verified',gaps?'Declared content gaps':'Bytes not verified in this view',
    `${count(content.declared)} content record(s); ${count(content.invalid_references)} invalid reference(s); `+
    `${count(content.source_partial)} source-incomplete; ${count(content.source_completeness_unknown)} with unknown source completeness.`);
  const details=make('details');details.open=expanded;
  details.append(make('summary','Evidence scope and limitations'));
  if(execution.event_id)details.append(make('p','Source event: '+execution.event_id));
  if(execution.reason)details.append(make('p','Terminal evidence status: '+execution.reason));
  details.append(make('p','FINISHED only describes recording/view state. Native completion reports, termination text, and exit code 0 do not establish task quality or independent validation.'));
  details.append(make('p',`${count(content.unique_declared_files)} unique declared content file(s); `+
    `${count(content.opaque)} opaque record(s); ${count(content.redacted)} explicitly redacted record(s). `+
    'These are metadata counts, not readable-body coverage or end-to-end recall.'));
  details.append(make('p','The content inventory above does not verify bytes. The separate delivery checks distinguish recorded export verification, current folder verification, and final history synchronization.'));
  const inspection=object(value?.inspection);
  if(!value||inspection.state!=='declared_graph'){
    const warning=make('p','Inventory is partial or unavailable. Hidden, malformed, ambiguous, or uninspected records are not counted as absent.');
    warning.dataset.warning='partial';details.append(warning);
  }
  if(inspection.limit_reached)details.append(make('p','Metadata inspection reached its safety budget. Counts are lower bounds, not a complete inventory.'));
  details.append(make('p',`Ambiguous node IDs: ${count(inspection.ambiguous_node_ids)}; malformed records: ${count(inspection.invalid_records)}.`));
  for(const report of (Array.isArray(task.reports)?task.reports:[]).slice(0,20)){
    details.append(make('p',[report.relation,report.task_id,report.edge_id].filter(v=>typeof v==='string').join(' · ')));
  }
  panel.append(details);
  if(scroll>0&&selected&&Number.isFinite(anchor))host.scrollTop+=selected.getBoundingClientRect().top-anchor;
}
function refresh(packet){
  const graph=graphNow(),key=JSON.stringify([graph.session_id||null,graph.source_path||null]);
  if(key!==currentKey){currentKey=key;latest=null;lastSignature='';panel.querySelector('details')?.remove()}
  const candidate=object(packet).run_assessment||object(object(packet).graph).run_assessment;
  if(candidate){latest=compatible(candidate,graph)?candidate:null}
  else if(!latest){
    const embedded=graph.run_assessment||window.__execweaveStaticRunAssessment;
    if(compatible(embedded,graph))latest=embedded;
  }
  // Never infer success from a legacy label, absent fields, or a completed viewer.
  window.__execweaveDeliveryStatus?.accept(packet);
  render(latest);
  window.__execweaveDeliveryStatus?.mount(panel);
}
const previous=window.__execweaveDashboard||{};
window.__execweaveDashboard={...previous,
  onPayload(data){previous.onPayload?.(data);refresh(data)},
  onFinished(...args){previous.onFinished?.(...args);refresh()}
};
window.__execweaveRunAssessment={refresh};refresh();
})();
""".strip()

RUN_ASSESSMENT_CSS = r"""
#execweave-run-assessment{overflow-wrap:anywhere;margin-bottom:16px;padding-bottom:12px;border-bottom:1px solid var(--border,#888)}
#execweave-delivery-status{overflow-wrap:anywhere;margin:-8px 0 16px}
#execweave-run-assessment h2{font-size:15px;margin:0 0 10px}
:is(#execweave-run-assessment,#execweave-delivery-status) h3{font-size:12px;text-transform:uppercase;letter-spacing:.04em;margin:0 0 5px;color:var(--muted)}
:is(#execweave-run-assessment,#execweave-delivery-status) .run-assessment-card{border:1px solid var(--border,#888);border-radius:8px;padding:8px;margin:6px 0}
:is(#execweave-run-assessment,#execweave-delivery-status) strong{font-size:14px}
:is(#execweave-run-assessment,#execweave-delivery-status) p{font-size:12px;line-height:1.5;margin:5px 0}
:is(#execweave-run-assessment,#execweave-delivery-status) details{font-size:12px;margin-top:8px}
:is(#execweave-run-assessment,#execweave-delivery-status) summary{cursor:pointer}
:is(#execweave-run-assessment,#execweave-delivery-status) [data-state="failed"],:is(#execweave-run-assessment,#execweave-delivery-status) [data-state="collector_failed"]{border-left:4px solid var(--danger,#c2414f)}
:is(#execweave-run-assessment,#execweave-delivery-status) [data-state="incomplete"],:is(#execweave-run-assessment,#execweave-delivery-status) [data-state="not_verified"],:is(#execweave-run-assessment,#execweave-delivery-status) [data-state="declared_gaps"]{border-left:4px solid var(--noncausal,#b56a16)}
""".strip()


def inject_run_assessment(html: str) -> str:
    if 'id="execweave-run-assessment-script"' in html:
        return html
    if "</body>" not in html:
        raise RuntimeError("run assessment requires a dashboard body")
    return inject_controlled_checks(inject_task_reports(html.replace("</body>", "<style>" + RUN_ASSESSMENT_CSS + "</style>"
                        + delivery_scripts() + '<script id="execweave-run-assessment-script">' + RUN_ASSESSMENT_JS
                        + "</script>\n</body>", 1)))
