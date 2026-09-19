"""A reversible workflow-first projection over the existing display graph.

The raw graph, identity policy, layout solver and source evidence are unchanged.
Only visible membership is narrowed; no path is contracted into a new edge.
"""
from __future__ import annotations

WORKFLOW_JS = r"""
// Installed inside the core closure after the existing projection wrappers.
const workflowTypes=new Set(['agent','session','task','agent_task','subtask','message','artifact','model','tool']);
let workflowChoice='auto',workflowScope=null,workflowInventory=null;
const workflowBaseProjection=execweaveDashboardGraph;
const workflowToolbar=document.createElement('div');workflowToolbar.id='execweave-workflow-controls';
workflowToolbar.setAttribute('role','group');workflowToolbar.setAttribute('aria-label','Graph view');
const workflowSelect=document.createElement('select');workflowSelect.setAttribute('aria-label','Graph view');
for(const [value,label] of [['auto','Automatic view'],['workflow','Workflow overview'],['all','All execution evidence']]){
  const option=document.createElement('option');option.value=value;option.textContent=label;workflowSelect.append(option);
}
const workflowSummary=document.createElement('span');workflowSummary.id='execweave-workflow-summary';workflowSummary.setAttribute('role','status');
workflowToolbar.append(workflowSelect,workflowSummary);document.querySelector('#graph-panel .panel-bar')?.after(workflowToolbar);
function workflowFailed(node){
  const a=node?.attributes||{};
  return a.provider_reported_error===true||a.success===false||
    ['failed','error','interrupted','cancelled'].includes(a.status)||
    (Number.isSafeInteger(a.return_code)&&a.return_code!==0)||
    (typeof a.error==='string'&&a.error.length>0);
}
function workflowProject(data,display,choice,selected,selectedEdge){
  const nodes=Array.isArray(display?.nodes)?display.nodes:[],edges=Array.isArray(display?.edges)?display.edges:[];
  const seen=new Set();let ambiguous=false;
  for(const node of nodes){if(!node||typeof node.id!=='string'||seen.has(node.id)){ambiguous=true;break}seen.add(node.id)}
  const agentCount=nodes.filter(n=>n?.type==='agent').length;
  const mode=choice==='auto'?(agentCount>1?'workflow':'all'):choice;
  if(mode!=='workflow'||!agentCount||ambiguous||data?.live_payload_compact){
    return {display,mode:'all',total:nodes.length,shown:nodes.length,hidden:0,ambiguous,agentCount};
  }
  const selectedEnds=new Set(edges.filter(e=>edgeId(e)===selectedEdge).flatMap(e=>[e.source,e.target]));
  const snapshots=new Set((Array.isArray(data.edges)?data.edges:[])
    .filter(e=>e?.relation==='OBSERVED_FILE_CONTENT_BEFORE_READ').map(e=>e.source));
  const kept=nodes.filter(n=>workflowTypes.has(n.type)||n.attributes?.viewer_framework_messages||
    n.attributes?.viewer_orchestration_action||n.attributes?.viewer_folded||snapshots.has(n.id)||workflowFailed(n)||n.id===selected||selectedEnds.has(n.id)||
    (Array.isArray(n.attributes?.viewer_folded_members)&&n.attributes.viewer_folded_members.some(m=>workflowTypes.has(m?.type)||workflowFailed(m))));
  const ids=new Set(kept.map(n=>n.id));
  const shownEdges=edges.filter(e=>ids.has(e.source)&&ids.has(e.target));
  return {display:{...display,nodes:kept,edges:shownEdges,node_count:kept.length,edge_count:shownEdges.length},
    mode,agentCount,total:nodes.length,shown:kept.length,hidden:nodes.length-kept.length,ambiguous:false};
}
// Bundle rails in the filtered view follow actual visible rows, not stale
// full-graph preferred row numbers. Unchanged positions must keep the same rail.
function execweaveWorkflowRailOrder(id){
  if(workflowInventory?.mode!=='workflow')return null;
  const at=positions.get(id);if(!at)return null;
  let order=0;
  for(const [other,p] of positions)if(nodeById.has(other)&&Math.abs(p.x-at.x)<.5&&
    (p.y<at.y||(p.y===at.y&&String(other).localeCompare(String(id))<0)))order++;
  return order;
}
function workflowUpdate(){
  workflowSelect.value=workflowChoice;workflowSelect.disabled=protectedMode;
  const s=workflowInventory;
  workflowSummary.textContent=protectedMode?'Large-graph protection is active. View switching cannot redraw a stale snapshot.':
    !s?'Waiting for a published graph.':s.ambiguous?'Ambiguous display identities; the full evidence view is retained.':
    `${s.mode==='workflow'?'Workflow':'All evidence'}: ${s.shown}/${s.total} displayable nodes. `+
    (s.hidden?`${s.hidden} infrastructure/detail nodes are hidden, not deleted. Choose All execution evidence or Runtime evidence to inspect them.`:
      'Existing file/folding limits still apply; raw evidence is unchanged.');
  workflowToolbar.dataset.mode=s?.mode||'all';
}
execweaveDashboardGraph=function(data){
  const key=JSON.stringify([data?.run_id??null,data?.session_id??null,data?.source_path??null]);
  if(key!==workflowScope){workflowScope=key;workflowChoice='auto'}
  const display=workflowBaseProjection(data);
  workflowInventory=workflowProject(data,display,workflowChoice,selectedNodeId,selectedEdgeId);
  workflowUpdate();return workflowInventory.display;
};
function workflowSetMode(mode){
  if(!['auto','workflow','all'].includes(mode))return false;
  if(protectedMode){workflowUpdate();return false}
  workflowChoice=mode;
  if(typeof execweaveFlowInvalidate==='function')execweaveFlowInvalidate();
  setSnapshot(graph);restoreSelectionFocus();
  // An explicit view change should settle the active Fit camera before the
  // next interaction, not leave a delayed fit that appears to come from Arrange.
  if(cameraMode==='fit'){clearTimeout(cameraTimer);cameraTimer=null;stopAnimation();fit(false)}
  workflowUpdate();return true;
}
workflowSelect.addEventListener('change',()=>workflowSetMode(workflowSelect.value));
// A direct request for an exact hidden display node opens the full evidence
// view. No same-name, ancestry, or shared-resource identity substitution.
function workflowReveal(id){
  if(typeof id!=='string'||protectedMode)return false;
  if(nodeById.has(id))return true;
  const matches=(workflowBaseProjection(graph).nodes||[]).filter(n=>n?.id===id);
  if(matches.length!==1)return false;
  return workflowSetMode('all')&&nodeById.has(id);
}
const workflowSelectNode=window.__execweaveCore.selectNode;
window.__execweaveCore.selectNode=(id,...args)=>{if(!nodeById.has(id))workflowReveal(id);return workflowSelectNode(id,...args)};
const workflowProtection=enterProtectiveMode;
enterProtectiveMode=function(data){workflowProtection(data);workflowUpdate()};
const workflowLeaveProtection=leaveProtectiveMode;
leaveProtectiveMode=function(){workflowLeaveProtection();workflowUpdate()};
window.__execweaveWorkflow={setMode:workflowSetMode,reveal:workflowReveal,project:workflowProject,
  status:()=>workflowInventory?{mode:workflowInventory.mode,total:workflowInventory.total,shown:workflowInventory.shown,hidden:workflowInventory.hidden}:null};
""".strip()

WORKFLOW_CSS = """
#graph-panel{grid-template-rows:46px auto minmax(0,1fr)}
#execweave-explore-run,#execweave-runtime-launcher{font-size:12px;white-space:nowrap;line-height:1.4;padding:7px 9px;background:var(--panel2);color:var(--text);border:1px solid var(--border);border-radius:6px}
#execweave-health-dialog button,#execweave-health-dialog select,#execweave-share-dialog button{background:var(--panel2);color:var(--text);border:1px solid var(--border);border-radius:6px}
#execweave-health-dialog button:disabled,#execweave-share-dialog button:disabled{opacity:.5;cursor:not-allowed}
#execweave-workflow-controls button{font:inherit;font-size:12px;padding:6px 10px;cursor:pointer;background:var(--panel2);color:var(--text);border:1px solid var(--border);border-radius:6px}
#execweave-workflow-controls{display:flex;align-items:center;gap:10px;flex-wrap:wrap;padding:6px 12px;background:var(--panel);border-bottom:1px solid var(--border);flex-shrink:0}
#execweave-workflow-controls select{font:inherit;font-size:12px;background:var(--panel);color:var(--text);padding:5px;border:1px solid var(--border);border-radius:6px}
#execweave-workflow-summary{font-size:12px;line-height:1.4;flex:1;min-width:140px;color:var(--muted)}
""".strip()


def inject_workflow_mode(html: str) -> str:
    if 'id="execweave-workflow-style"' in html:
        return html
    startup = "applyTheme(initialTheme());applyTransform();poll();"
    if html.count(startup) != 1 or "</head>" not in html:
        raise RuntimeError("workflow startup seam changed")
    return html.replace("</head>", '<style id="execweave-workflow-style">' + WORKFLOW_CSS + "</style></head>", 1).replace(startup, WORKFLOW_JS + "\n" + startup, 1)
