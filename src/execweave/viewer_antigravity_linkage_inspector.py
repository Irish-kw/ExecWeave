from __future__ import annotations

_ANTIGRAVITY_LINKAGE_CSS = r"""
.antigravity-linkage-inspector{margin:14px 0 4px;border:1px solid var(--border);border-radius:8px;background:var(--panel2);overflow:hidden}.antigravity-linkage-inspector summary{cursor:pointer;padding:9px 10px;font-weight:700;list-style:none}.antigravity-linkage-inspector summary::-webkit-details-marker{display:none}.antigravity-linkage-inspector summary::before{content:'▸';display:inline-block;width:14px;color:var(--muted)}.antigravity-linkage-inspector[open] summary::before{content:'▾'}.antigravity-linkage-body{padding:0 10px 10px}.antigravity-linkage-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px;margin:4px 0 9px}.antigravity-linkage-card{min-width:0;padding:8px;border:1px solid var(--border);border-radius:7px;background:var(--panel)}.antigravity-linkage-card.is-exact{border-color:var(--selected)}.antigravity-linkage-label{color:var(--muted);font-size:9px;font-weight:800;text-transform:uppercase;letter-spacing:.06em}.antigravity-linkage-value{margin-top:3px;font-size:10px;line-height:1.4;overflow-wrap:anywhere}.antigravity-linkage-card.is-exact .antigravity-linkage-value{font-weight:800}.antigravity-linkage-actions{display:flex;gap:5px;flex-wrap:wrap;margin:7px 0}.antigravity-linkage-actions button{padding:3px 6px;font-size:10px}@media(max-width:720px){.antigravity-linkage-grid{grid-template-columns:1fr}}
""".strip()

_ANTIGRAVITY_LINKAGE_JS = r"""
function execweaveAntigravityLinkageCard(label,text,exact=false){const card=document.createElement('div');card.className=`antigravity-linkage-card${exact?' is-exact':''}`;const key=document.createElement('div');key.className='antigravity-linkage-label';key.textContent=label;const value=document.createElement('div');value.className='antigravity-linkage-value';value.textContent=text;card.append(key,value);return card}
function execweaveAppendAntigravityLinkageInspector(kind,value){
  if(kind!=='Node'||!value||value.type!=='subtask'||!value.id||!value.attributes||value.attributes.provider!=='antigravity')return;
  const nodeMap=execweaveAgentNodeMap(),edges=execweaveIncidentEdges(value.id);const assigned=edges.find(edge=>edge&&edge.relation==='ASSIGNED_AGENT_TASK'&&edge.source===value.id);if(!assigned)return;const child=nodeMap.get(assigned.target);if(!child||child.type!=='agent')return;
  const methods=Array.isArray(assigned.identity_methods)?assigned.identity_methods:[];const method=methods.length?methods.join(', '):'Not materialized';const exact=assigned.identity_exact===true;const recordOrderExact=exact&&methods.includes('validated_transcript_record_order_and_provider_ids');const childAttrs=child.attributes||{};const lifecycle=childAttrs.lifecycle_authority==='child_provider_hooks'?'Child hooks authoritative':'Not asserted by parent linkage';
  const panel=document.createElement('details');panel.className='antigravity-linkage-inspector';panel.open=true;const summary=document.createElement('summary');summary.textContent='Antigravity Transcript Linkage';panel.appendChild(summary);const body=document.createElement('div');body.className='antigravity-linkage-body';const grid=document.createElement('div');grid.className='antigravity-linkage-grid';
  grid.append(execweaveAntigravityLinkageCard('Child identity',exact?'Validated transcript identity':'Assignment edge observed',exact),execweaveAntigravityLinkageCard('Identity method',method,recordOrderExact),execweaveAntigravityLinkageCard('Timing join',recordOrderExact?'No timing join':'Not asserted'),execweaveAntigravityLinkageCard('Child lifecycle',lifecycle));body.appendChild(grid);
  const actions=document.createElement('div');actions.className='antigravity-linkage-actions';const button=document.createElement('button');button.type='button';button.textContent='Inspect child';button.addEventListener('click',()=>showDetails('Node',child));actions.appendChild(button);body.appendChild(actions);
  const note=document.createElement('div');note.className='content-note';note.textContent='This is exact identity-correlation evidence only. Validated transcript record order plus provider conversation IDs can establish the subtask → child identity join; the parent transcript does not establish child execution, return, close, or completion lifecycle.';body.appendChild(note);panel.appendChild(body);details.appendChild(panel);
}
""".strip()


def inject_standalone_antigravity_linkage_inspector(html: str) -> str:
    """Surface validated Antigravity child identity without exposing transcript paths."""
    if "function execweaveAppendAntigravityLinkageInspector(" in html:
        return html
    marker = "function showDetails(kind,value){"
    if marker not in html or "function execweaveAppendExecutionInspector(" not in html:
        return html
    visibility_marker = (
        "provider_exposed_reasoning_part:'Provider exposes reasoning part',unknown:'Unknown'"
    )
    visibility_replacement = (
        "provider_exposed_reasoning_part:'Provider exposes reasoning part',"
        "provider_exposed_validated_transcript_child_identity:'Validated transcript child identity',"
        "provider_exposed_request_and_validated_assignment_only:'Request + validated assignment only',"
        "unknown:'Unknown'"
    )
    if visibility_marker not in html:
        raise RuntimeError("standalone viewer visibility mapping seam changed")
    result = html.replace(visibility_marker, visibility_replacement, 1)
    result = result.replace("</style>", _ANTIGRAVITY_LINKAGE_CSS + "\n</style>", 1)
    result = result.replace(marker, _ANTIGRAVITY_LINKAGE_JS + "\n" + marker, 1)
    seam = "execweaveAppendExecutionInspector(kind,value);\n}"
    replacement = (
        "execweaveAppendExecutionInspector(kind,value);"
        "execweaveAppendAntigravityLinkageInspector(kind,value);\n}"
    )
    if seam not in result:
        raise RuntimeError("standalone viewer Antigravity linkage inspector seam changed")
    return result.replace(seam, replacement, 1)
