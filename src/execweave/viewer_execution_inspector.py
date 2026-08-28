from __future__ import annotations

_EXECUTION_CSS = r"""
.execution-inspector{margin:14px 0 4px;border:1px solid var(--border);border-radius:8px;background:var(--panel2);overflow:hidden}
.execution-inspector summary{cursor:pointer;padding:9px 10px;font-weight:700;list-style:none}.execution-inspector summary::-webkit-details-marker{display:none}.execution-inspector summary::before{content:'▸';display:inline-block;width:14px;color:var(--muted)}.execution-inspector[open] summary::before{content:'▾'}
.execution-inspector-body{padding:0 10px 10px}.execution-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:6px;margin:4px 0 9px}.execution-card{min-width:0;padding:8px;border:1px solid var(--border);border-radius:7px;background:var(--panel)}.execution-card.is-observed{border-color:var(--selected)}.execution-label{color:var(--muted);font-size:9px;font-weight:800;text-transform:uppercase;letter-spacing:.06em}.execution-value{margin-top:3px;font-size:10px;line-height:1.4;overflow-wrap:anywhere}.execution-card.is-observed .execution-value{font-weight:800}.execution-payloads{display:flex;gap:5px;flex-wrap:wrap;margin:7px 0}.execution-payloads button{padding:3px 6px;font-size:10px}.execution-note{margin:8px 0;color:var(--muted);font-size:10px;line-height:1.4}
@media(max-width:720px){.execution-grid{grid-template-columns:1fr}}
""".strip()

_EXECUTION_JS = r"""
function execweaveExecutionCard(label,text,observed=false){const card=document.createElement('div');card.className=`execution-card${observed?' is-observed':''}`;const key=document.createElement('div');key.className='execution-label';key.textContent=label;const value=document.createElement('div');value.className='execution-value';value.textContent=text;card.append(key,value);return card}
function execweaveAppendExecutionInspector(kind,value){
  if(kind!=='Node'||!value||value.type!=='agent_execution'||!value.id)return;
  const nodeMap=execweaveAgentNodeMap(),edges=execweaveIncidentEdges(value.id),attrs=value.attributes||{};
  const stopEdges=edges.filter(edge=>edge&&edge.relation==='OBSERVED_EXECUTION_STOP'&&edge.target===value.id);
  const errorEdges=edges.filter(edge=>edge&&edge.relation==='OBSERVED_EXECUTION_ERROR'&&edge.target===value.id);
  const payloadEdges=edges.filter(edge=>edge&&edge.relation==='OBSERVED_EXECUTION_ERROR_CONTENT'&&edge.source===value.id);
  const panel=document.createElement('details');panel.className='execution-inspector';panel.open=true;const summary=document.createElement('summary');summary.textContent='Execution Evidence';panel.appendChild(summary);const body=document.createElement('div');body.className='execution-inspector-body';const grid=document.createElement('div');grid.className='execution-grid';
  const executionNumber=Number.isInteger(attrs.execution_num)?String(attrs.execution_num):'Not exposed';const termination=typeof attrs.termination_reason==='string'&&attrs.termination_reason?attrs.termination_reason:'Not exposed';const fullyIdle=typeof attrs.fully_idle==='boolean'?(attrs.fully_idle?'Yes':'No'):'Not exposed';const errorObserved=errorEdges.length>0;
  grid.append(execweaveExecutionCard('Execution #',executionNumber,Number.isInteger(attrs.execution_num)),execweaveExecutionCard('Termination',termination,stopEdges.length>0),execweaveExecutionCard('Fully idle',fullyIdle,typeof attrs.fully_idle==='boolean'),execweaveExecutionCard('Error',errorObserved?'Observed':'No evidence',errorObserved));body.appendChild(grid);
  if(payloadEdges.length){const title=document.createElement('div');title.className='agent-section-title';title.textContent=`Stored error payload · ${payloadEdges.length}`;body.appendChild(title);const payloads=document.createElement('div');payloads.className='execution-payloads';payloadEdges.forEach(edge=>{const node=nodeMap.get(edge.target);if(!node||node.type!=='observed_content')return;const ref=node.attributes&&node.attributes.viewer_content;if(location.protocol==='file:'&&ref&&ref.safe_relative_path){const link=document.createElement('a');link.className='content-open';link.href=ref.safe_relative_path;link.target='_blank';link.rel='noreferrer';link.textContent=`Stored error · ${execweaveFormatBytes(ref.size_bytes)}`;payloads.appendChild(link)}const inspect=document.createElement('button');inspect.type='button';inspect.textContent='Inspect error payload';inspect.addEventListener('click',()=>showDetails('Node',node));payloads.appendChild(inspect)});if(payloads.childElementCount)body.appendChild(payloads)}
  const note=document.createElement('div');note.className='execution-note';note.textContent='Execution stop is provider-observed execution-loop evidence. It is not a provider session or conversation end unless a separate session-end event exists. Error payloads are linked only by exact agent_execution → observed_content evidence; no timing or execution-number join is performed in the viewer.';body.appendChild(note);panel.appendChild(body);details.appendChild(panel);
}
""".strip()


def inject_standalone_execution_inspector(html: str) -> str:
    """Inject a viewer-only execution inspector after the existing evidence inspector."""
    if "function execweaveAppendExecutionInspector(" in html:
        return html
    marker = "function showDetails(kind,value){"
    if marker not in html:
        return html
    result = html.replace("</style>", _EXECUTION_CSS + "\n</style>", 1)
    result = result.replace(marker, _EXECUTION_JS + "\n" + marker, 1)
    seam = "execweaveAppendDelegationInspector(kind,value);\n}"
    replacement = (
        "execweaveAppendDelegationInspector(kind,value);"
        "execweaveAppendExecutionInspector(kind,value);\n}"
    )
    if seam not in result:
        raise RuntimeError("standalone viewer execution inspector seam changed")
    return result.replace(seam, replacement, 1)
