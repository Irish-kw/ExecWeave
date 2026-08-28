from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

_VIEWER_CONTENT_SCHEMA_VERSION = "0.1"
_CONTENT_PATH_RE = re.compile(
    r"^content/sha256/(?P<sha256>[0-9a-f]{64})\.(?P<suffix>json|txt|bin)$"
)


def _content_category(content_kind: str) -> str:
    value = content_kind.lower()
    if "agent_message" in value:
        return "Agent Message Payload"
    if "reasoning.encoded" in value or "encoded_reasoning" in value:
        return "Encoded Reasoning"
    if "reasoning.summary" in value or "reasoning_summary" in value:
        return "Reasoning Summary"
    if "reasoning.text" in value or value.endswith(".reasoning"):
        return "Reasoning Text"
    if "inference_request" in value:
        return "Inference Request"
    if "inference_response" in value:
        return "Inference Response"
    if "terminal.request" in value:
        return "Terminal Request"
    if "terminal.result" in value:
        return "Terminal Result"
    if "code_cell.source" in value:
        return "Code Cell Source"
    if "raw_payload" in value:
        return "Raw Provider Payload"
    if "provider_metadata" in value or "provider_request_config" in value or value.endswith("metadata"):
        return "Provider Metadata"
    if any(token in value for token in ("tool_output", "tool_result", "tool_response", "shell_output")):
        return "Tool Output"
    if any(token in value for token in ("tool_input", "tool_arguments")):
        return "Tool Input"
    if any(
        token in value
        for token in (
            "assistant_response",
            "completed_text",
            "response_object",
            "standard_logging_response",
            ".response",
        )
    ):
        return "Response"
    if any(
        token in value
        for token in (
            "user_prompt",
            "system_prompt",
            "request_messages",
            "model_context",
            "inference_message",
            "request_prompt",
            "request_input",
        )
    ):
        return "Prompt"
    if "file_content" in value or "file_snapshot" in value:
        return "File Content"
    if "shell_command" in value or value.endswith(".command"):
        return "Shell Command"
    if "mcp" in value:
        return "MCP Content"
    if "tool_definition" in value or "tool_schema" in value:
        return "Tool Definition"
    return "Observed Content"


def viewer_content_reference(node: dict[str, Any]) -> dict[str, Any] | None:
    """Return a safe viewer-only projection of an observed-content reference.

    The viewer accepts only ExecWeave content-addressed paths whose filename hash
    exactly matches the node's SHA-256 attribute. This prevents a hand-edited
    graph from turning the inspector into an arbitrary relative-file link.
    """
    if node.get("type") != "observed_content":
        return None
    attributes = node.get("attributes")
    if not isinstance(attributes, dict):
        return None
    path = attributes.get("path")
    sha256 = attributes.get("sha256")
    content_kind = attributes.get("content_kind")
    if not all(isinstance(value, str) and value for value in (path, sha256, content_kind)):
        return None
    match = _CONTENT_PATH_RE.fullmatch(path)
    if match is None or match.group("sha256") != sha256:
        return None
    size_bytes = attributes.get("size_bytes")
    if not isinstance(size_bytes, int) or isinstance(size_bytes, bool) or size_bytes < 0:
        return None
    media_type = attributes.get("media_type")
    representation = attributes.get("representation")
    complete = attributes.get("complete_from_source")
    return {
        "schema_version": _VIEWER_CONTENT_SCHEMA_VERSION,
        "viewer_only": True,
        "category": _content_category(content_kind),
        "safe_relative_path": path,
        "sha256": sha256,
        "suffix": match.group("suffix"),
        "size_bytes": size_bytes,
        "media_type": media_type if isinstance(media_type, str) else None,
        "representation": representation if isinstance(representation, str) else None,
        "content_kind": content_kind,
        "complete_from_source": complete if isinstance(complete, bool) else None,
        "content_embedded_in_viewer": False,
    }


def _node_lists(graph: dict[str, Any]) -> list[list[Any]]:
    result: list[list[Any]] = []
    nodes = graph.get("nodes")
    if isinstance(nodes, list):
        result.append(nodes)
    expansion = graph.get("expansion")
    clusters = expansion.get("clusters") if isinstance(expansion, dict) else None
    if isinstance(clusters, dict):
        for entry in clusters.values():
            members = entry.get("nodes") if isinstance(entry, dict) else None
            if isinstance(members, list):
                result.append(members)
    return result


def decorate_viewer_content_references(graph: dict[str, Any]) -> dict[str, Any]:
    """Add safe display metadata without mutating the canonical graph or content."""
    references = 0
    for nodes in _node_lists(graph):
        for node in nodes:
            if isinstance(node, dict) and viewer_content_reference(node) is not None:
                references += 1
    if references == 0:
        return dict(graph)

    projected = deepcopy(graph)
    decorated = 0
    for nodes in _node_lists(projected):
        for node in nodes:
            if not isinstance(node, dict):
                continue
            reference = viewer_content_reference(node)
            if reference is None:
                continue
            attributes = node.setdefault("attributes", {})
            if not isinstance(attributes, dict):
                continue
            attributes["viewer_content"] = reference
            node["name"] = reference["category"]
            decorated += 1
    projected["viewer_content_projection"] = {
        "schema_version": _VIEWER_CONTENT_SCHEMA_VERSION,
        "viewer_only": True,
        "reference_count": decorated,
        "content_embedded_in_viewer": False,
        "http_content_serving_enabled": False,
    }
    return projected


_INSPECTOR_CSS = r"""
.content-inspector,.agent-inspector,.message-inspector{margin:14px 0 4px;border:1px solid var(--border);border-radius:8px;background:var(--panel2);overflow:hidden}
.content-inspector summary,.agent-inspector summary,.message-inspector summary{cursor:pointer;padding:9px 10px;font-weight:700;list-style:none}.content-inspector summary::-webkit-details-marker,.agent-inspector summary::-webkit-details-marker,.message-inspector summary::-webkit-details-marker{display:none}
.content-inspector summary::before,.agent-inspector summary::before,.message-inspector summary::before{content:'▸';display:inline-block;width:14px;color:var(--muted)}.content-inspector[open] summary::before,.agent-inspector[open] summary::before,.message-inspector[open] summary::before{content:'▾'}
.content-inspector-body,.agent-inspector-body,.message-inspector-body{padding:0 10px 10px}.content-meta{display:grid;grid-template-columns:max-content minmax(0,1fr);gap:4px 8px;margin:2px 0 9px;font:11px/1.4 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}.content-meta dt{color:var(--muted)}.content-meta dd{margin:0;overflow-wrap:anywhere}
.content-note{margin:8px 0;color:var(--muted);font-size:11px}.content-open{display:inline-block;margin:3px 5px 9px 0;padding:5px 8px;border:1px solid var(--border);border-radius:6px;color:var(--text);text-decoration:none}.content-open:hover{border-color:var(--selected)}
.content-frame{display:block;width:100%;min-height:220px;border:1px solid var(--border);border-radius:6px;background:#fff}.content-unavailable{color:var(--muted);font-size:11px}
.agent-visibility{margin:7px 0 10px;padding:8px;border:1px solid var(--border);border-radius:7px;background:var(--panel)}.agent-visibility-head{display:flex;align-items:center;gap:7px;flex-wrap:wrap;margin-bottom:7px}.agent-visibility-title{font-weight:700;font-size:11px}.agent-visibility-provider{color:var(--muted);font:10px/1.3 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}.agent-visibility-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:6px}.agent-visibility-card{min-width:0;padding:7px;border:1px solid var(--border);border-radius:6px;background:var(--panel2)}.agent-visibility-label{color:var(--muted);font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.05em}.agent-visibility-value{margin-top:3px;font-size:10px;line-height:1.35;overflow-wrap:anywhere}.agent-visibility-card.is-gap .agent-visibility-value{font-weight:700}.agent-visibility-note{margin-top:7px;color:var(--muted);font-size:10px;line-height:1.4}
.agent-activity-list{display:grid;gap:7px}.agent-activity{border:1px solid var(--border);border-radius:7px;padding:7px 8px;background:var(--panel)}.agent-activity-head{display:flex;gap:6px;align-items:center;flex-wrap:wrap;font-size:11px}.agent-activity-relation{font-weight:700;color:var(--text)}.agent-activity-direction{color:var(--selected);font-weight:800}.agent-activity-peer{margin-top:3px;color:var(--muted);font:11px/1.4 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;overflow-wrap:anywhere}.agent-activity-meta{margin-left:auto;color:var(--muted);font-size:10px}.agent-activity-actions{display:flex;gap:5px;flex-wrap:wrap;margin-top:6px}.agent-activity-actions button{padding:3px 6px;font-size:10px}.agent-empty{color:var(--muted);font-size:11px}.agent-section-title{margin:9px 0 6px;color:var(--muted);font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.05em}
.message-stage-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:6px;margin:4px 0 9px}.message-stage{min-width:0;padding:7px;border:1px solid var(--border);border-radius:6px;background:var(--panel)}.message-stage-label{color:var(--muted);font-size:9px;font-weight:800;letter-spacing:.06em}.message-stage-value{margin-top:3px;font-size:10px;line-height:1.35}.message-stage.is-observed .message-stage-value{font-weight:800;color:var(--text)}.message-route{display:grid;grid-template-columns:max-content minmax(0,1fr);gap:4px 8px;margin:7px 0 9px;font:10px/1.4 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}.message-route dt{color:var(--muted)}.message-route dd{margin:0;overflow-wrap:anywhere}.message-inferences{display:grid;gap:6px;margin-top:7px}.message-inference{display:flex;align-items:center;gap:7px;padding:6px 7px;border:1px solid var(--border);border-radius:6px;background:var(--panel)}.message-inference-label{min-width:0;flex:1;color:var(--muted);font:10px/1.35 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;overflow-wrap:anywhere}.message-inference button{padding:3px 6px;font-size:10px}
@media(max-width:720px){.agent-visibility-grid,.message-stage-grid{grid-template-columns:1fr}}
""".strip()

_INSPECTOR_JS = r"""
function execweaveFormatBytes(value){const n=Number(value)||0;if(n<1024)return `${n} B`;if(n<1024*1024)return `${(n/1024).toFixed(1)} KiB`;return `${(n/(1024*1024)).toFixed(1)} MiB`}
function execweaveAppendMeta(list,key,value){if(value===null||value===undefined||value==='')return;const dt=document.createElement('dt');dt.textContent=key;const dd=document.createElement('dd');dd.textContent=String(value);list.append(dt,dd)}
function execweaveAppendContentInspector(kind,value){
  if(kind!=='Node'||!value||value.type!=='observed_content')return;
  const ref=value.attributes&&value.attributes.viewer_content;if(!ref||ref.viewer_only!==true)return;
  const panel=document.createElement('details');panel.className='content-inspector';
  const summary=document.createElement('summary');summary.textContent=`${ref.category||'Observed Content'} · ${execweaveFormatBytes(ref.size_bytes)}`;panel.appendChild(summary);
  const body=document.createElement('div');body.className='content-inspector-body';const meta=document.createElement('dl');meta.className='content-meta';
  execweaveAppendMeta(meta,'kind',ref.content_kind);execweaveAppendMeta(meta,'media',ref.media_type);execweaveAppendMeta(meta,'representation',ref.representation);execweaveAppendMeta(meta,'sha256',ref.sha256);execweaveAppendMeta(meta,'path',ref.safe_relative_path);body.appendChild(meta);
  const complete=document.createElement('div');complete.className='content-note';complete.textContent=ref.complete_from_source===true?'Complete from source: the selected integration supplied this complete value. This does not imply visibility into hidden model/provider state.':'Completeness was not asserted by the selected integration point.';body.appendChild(complete);
  if(location.protocol==='file:'){
    const link=document.createElement('a');link.className='content-open';link.href=ref.safe_relative_path;link.target='_blank';link.rel='noreferrer';link.textContent='Open stored content';body.appendChild(link);
    if(ref.suffix==='json'||ref.suffix==='txt'){
      const frame=document.createElement('iframe');frame.className='content-frame';frame.setAttribute('sandbox','');frame.setAttribute('referrerpolicy','no-referrer');frame.loading='lazy';frame.title=`${ref.category||'Observed Content'} stored content`;panel.addEventListener('toggle',()=>{if(panel.open&&!frame.getAttribute('src'))frame.setAttribute('src',ref.safe_relative_path)});body.appendChild(frame);
    }
  }else{
    const unavailable=document.createElement('div');unavailable.className='content-unavailable';unavailable.textContent='Content bytes are not fetched over HTTP by this inspector. Open the persisted viewer.html from the run directory to inspect the local content reference.';body.appendChild(unavailable);
  }
  panel.appendChild(body);details.appendChild(panel);
}
function execweaveActivitySequence(edge){return Number.isInteger(edge.first_sequence)?edge.first_sequence:Number.isInteger(edge.last_sequence)?edge.last_sequence:Number.MAX_SAFE_INTEGER}
function execweaveActivityTime(edge){return edge.first_seen||edge.last_seen||''}
function execweaveAgentNodeMap(){return new Map(possibleNodes.filter(node=>node&&node.id).map(node=>[node.id,node]))}
function execweaveIncidentEdges(nodeId){return possibleEdges.filter(edge=>edge&&(edge.source===nodeId||edge.target===nodeId)).sort((a,b)=>execweaveActivitySequence(a)-execweaveActivitySequence(b)||String(execweaveActivityTime(a)).localeCompare(String(execweaveActivityTime(b)))||String(a.id||'').localeCompare(String(b.id||'')))}
function execweaveAgentTraceCapability(agent,nodeMap){
  const direct=possibleEdges.find(edge=>edge&&edge.relation==='DECLARES_AGENT_TRACE_VISIBILITY'&&edge.source===agent.id&&nodeMap.get(edge.target)&&nodeMap.get(edge.target).type==='agent_trace_capability');if(direct)return nodeMap.get(direct.target);
  const provider=agent.attributes&&agent.attributes.provider;if(!provider)return null;
  return possibleNodes.find(node=>node&&node.type==='agent_trace_capability'&&node.attributes&&node.attributes.provider===provider)||null;
}
function execweaveVisibilityText(value){
  const known={not_exposed_by_source:'Not exposed by provider source',provider_root_only:'Root agent only',provider_exposed_subagent_id:'Provider exposes subagent ID',provider_exposed_lifecycle:'Provider exposes lifecycle',provider_exposed_thread_identity:'Provider exposes thread identity',provider_exposed_rollout_graph:'Provider exposes rollout graph',provider_exposed_plaintext_summary_or_encoded:'Provider exposes text / summary / encoded form',provider_exposed_when_subagent_id_present:'When provider supplies subagent ID',provider_exposed_thinking_text:'Provider exposes thinking text',provider_exposed_session_identity:'Provider exposes session identity',provider_exposed_session_parent_id:'Provider exposes session parent ID',provider_exposed_reasoning_part:'Provider exposes reasoning part',unknown:'Unknown'};if(known[value])return known[value];return String(value||'Unknown').replaceAll('_',' ');
}
function execweaveVisibilityCard(label,value){const card=document.createElement('div');card.className='agent-visibility-card';if(value==='not_exposed_by_source')card.classList.add('is-gap');const key=document.createElement('div');key.className='agent-visibility-label';key.textContent=label;const body=document.createElement('div');body.className='agent-visibility-value';body.textContent=execweaveVisibilityText(value);card.append(key,body);return card}
function execweaveAppendAgentVisibility(body,agent,nodeMap){
  const capability=execweaveAgentTraceCapability(agent,nodeMap);if(!capability)return;const attrs=capability.attributes||{};const panel=document.createElement('div');panel.className='agent-visibility';const head=document.createElement('div');head.className='agent-visibility-head';const title=document.createElement('span');title.className='agent-visibility-title';title.textContent='Provider trace visibility';const provider=document.createElement('span');provider.className='agent-visibility-provider';provider.textContent=String(attrs.provider||'provider');head.append(title,provider);panel.appendChild(head);const grid=document.createElement('div');grid.className='agent-visibility-grid';grid.append(execweaveVisibilityCard('Identity',attrs.agent_identity_visibility),execweaveVisibilityCard('Subagents',attrs.subagent_visibility),execweaveVisibilityCard('Reasoning',attrs.reasoning_visibility));panel.appendChild(grid);const note=document.createElement('div');note.className='agent-visibility-note';note.textContent='This describes what the selected provider integration exposed. “Not exposed” is a source capability boundary, not evidence that ExecWeave dropped an event or that hidden provider state was unavailable internally.';panel.appendChild(note);body.appendChild(panel);
}
function execweavePayloadNodes(nodeId,nodeMap){
  const result=[],seen=new Set();
  possibleEdges.forEach(edge=>{if(!edge||(edge.source!==nodeId&&edge.target!==nodeId))return;const peerId=edge.source===nodeId?edge.target:edge.source;const peer=nodeMap.get(peerId);const ref=peer&&peer.type==='observed_content'&&peer.attributes&&peer.attributes.viewer_content;if(!ref||seen.has(peer.id))return;seen.add(peer.id);result.push(peer)});
  return result;
}
function execweaveAppendPayloadLinks(container,nodeId,nodeMap){
  if(location.protocol!=='file:')return;
  execweavePayloadNodes(nodeId,nodeMap).forEach(node=>{const ref=node.attributes.viewer_content;const link=document.createElement('a');link.className='content-open';link.href=ref.safe_relative_path;link.target='_blank';link.rel='noreferrer';link.textContent=`${ref.category||'Payload'} · ${execweaveFormatBytes(ref.size_bytes)}`;container.appendChild(link)});
}
function execweaveActivityRow(edge,agentId,nodeMap){
  const outbound=edge.source===agentId,peerId=outbound?edge.target:edge.source,peer=nodeMap.get(peerId);const row=document.createElement('div');row.className='agent-activity';
  const head=document.createElement('div');head.className='agent-activity-head';const direction=document.createElement('span');direction.className='agent-activity-direction';direction.textContent=outbound?'OUT':'IN';const relation=document.createElement('span');relation.className='agent-activity-relation';relation.textContent=edge.relation||'UNKNOWN';const meta=document.createElement('span');meta.className='agent-activity-meta';const seq=execweaveActivitySequence(edge);meta.textContent=`${seq===Number.MAX_SAFE_INTEGER?'seq —':`seq ${seq}`}${execweaveActivityTime(edge)?` · ${execweaveActivityTime(edge)}`:''}`;head.append(direction,relation,meta);row.appendChild(head);
  const peerLabel=document.createElement('div');peerLabel.className='agent-activity-peer';peerLabel.textContent=`${peer&&peer.type?peer.type:'node'} · ${peer&&(peer.name||peer.id)?(peer.name||peer.id):peerId}`;row.appendChild(peerLabel);
  const actions=document.createElement('div');actions.className='agent-activity-actions';const inspect=document.createElement('button');inspect.type='button';inspect.textContent='Inspect edge';inspect.addEventListener('click',()=>showDetails('Edge',edge));actions.appendChild(inspect);if(peer){const peerButton=document.createElement('button');peerButton.type='button';peerButton.textContent='Inspect peer';peerButton.addEventListener('click',()=>showDetails('Node',peer));actions.appendChild(peerButton)}row.appendChild(actions);
  execweaveAppendPayloadLinks(row,peerId,nodeMap);return row;
}
function execweaveCommunicationEdges(agentId,nodeMap){
  const communicationRelations=new Set(['SPAWNED_AGENT','ASSIGNED_AGENT_TASK','SENT_AGENT_MESSAGE','DELIVERED_AGENT_MESSAGE','RETURNED_AGENT_RESULT','CLOSED_AGENT','SUBAGENT_STOPPED','HAS_CHILD_AGENT_SESSION','SPAWNED_SUBAGENT','RETURNED_TO','REQUESTED_SUBTASK']);
  return execweaveIncidentEdges(agentId).filter(edge=>{const peerId=edge.source===agentId?edge.target:edge.source,peer=nodeMap.get(peerId);return communicationRelations.has(edge.relation)||(peer&&['agent','agent_message','agent_interaction','subtask'].includes(peer.type))});
}
function execweaveAppendActivitySection(body,title,edges,agentId,nodeMap){const heading=document.createElement('div');heading.className='agent-section-title';heading.textContent=`${title} · ${edges.length}`;body.appendChild(heading);if(!edges.length){const empty=document.createElement('div');empty.className='agent-empty';empty.textContent='No matching evidence in this graph.';body.appendChild(empty);return}const list=document.createElement('div');list.className='agent-activity-list';edges.forEach(edge=>list.appendChild(execweaveActivityRow(edge,agentId,nodeMap)));body.appendChild(list)}
function execweaveAppendAgentActivity(kind,value){
  if(kind!=='Node'||!value||value.type!=='agent'||!value.id)return;
  const nodeMap=execweaveAgentNodeMap(),all=execweaveIncidentEdges(value.id),communications=execweaveCommunicationEdges(value.id,nodeMap);const panel=document.createElement('details');panel.className='agent-inspector';panel.open=true;const summary=document.createElement('summary');summary.textContent=`Agent trace · ${communications.length} communications · ${all.length} activities`;panel.appendChild(summary);const body=document.createElement('div');body.className='agent-inspector-body';execweaveAppendAgentVisibility(body,value,nodeMap);execweaveAppendActivitySection(body,'Agent communications',communications,value.id,nodeMap);execweaveAppendActivitySection(body,'Agent activity',all,value.id,nodeMap);panel.appendChild(body);details.appendChild(panel);
}
function execweaveMessageStageCard(label,relation,edges){const observed=edges.some(edge=>edge&&edge.relation===relation);const card=document.createElement('div');card.className=`message-stage${observed?' is-observed':''}`;const key=document.createElement('div');key.className='message-stage-label';key.textContent=label;const value=document.createElement('div');value.className='message-stage-value';value.textContent=observed?'Observed':'No evidence';card.title=relation;card.append(key,value);return card}
function execweaveAppendMessageInspector(kind,value){
  if(kind!=='Node'||!value||value.type!=='agent_message'||!value.id)return;
  const nodeMap=execweaveAgentNodeMap(),edges=execweaveIncidentEdges(value.id),attrs=value.attributes||{};const panel=document.createElement('details');panel.className='message-inspector';panel.open=true;const summary=document.createElement('summary');summary.textContent='Message Evidence';panel.appendChild(summary);const body=document.createElement('div');body.className='message-inspector-body';const stages=document.createElement('div');stages.className='message-stage-grid';stages.append(execweaveMessageStageCard('SEND','SENT_AGENT_MESSAGE',edges),execweaveMessageStageCard('DELIVER','DELIVERED_AGENT_MESSAGE',edges),execweaveMessageStageCard('CONTEXT','INCLUDED_AGENT_MESSAGE_IN_INFERENCE',edges),execweaveMessageStageCard('CONSUME','CONSUMED_AGENT_MESSAGE',edges));body.appendChild(stages);
  const route=document.createElement('dl');route.className='message-route';execweaveAppendMeta(route,'author',attrs.author);execweaveAppendMeta(route,'recipient',attrs.recipient);execweaveAppendMeta(route,'conversation item',attrs.conversation_item_id);body.appendChild(route);
  const inferenceEdges=edges.filter(edge=>edge&&edge.relation==='INCLUDED_AGENT_MESSAGE_IN_INFERENCE'&&edge.source===value.id);if(inferenceEdges.length){const title=document.createElement('div');title.className='agent-section-title';title.textContent=`Inference context · ${inferenceEdges.length}`;body.appendChild(title);const list=document.createElement('div');list.className='message-inferences';inferenceEdges.forEach(edge=>{const inference=nodeMap.get(edge.target);const row=document.createElement('div');row.className='message-inference';const label=document.createElement('div');label.className='message-inference-label';label.textContent=inference?(inference.name||inference.id):String(edge.target||'inference');row.appendChild(label);if(inference){const button=document.createElement('button');button.type='button';button.textContent='Inspect inference';button.addEventListener('click',()=>showDetails('Node',inference));row.appendChild(button)}list.appendChild(row)});body.appendChild(list)}
  execweaveAppendPayloadLinks(body,value.id,nodeMap);const note=document.createElement('div');note.className='content-note';note.textContent='CONTEXT and CONSUME reflect provider-recorded request-context evidence. They are not proof that the model attended to, read, or semantically used the message. “No evidence” is not a failure state.';body.appendChild(note);panel.appendChild(body);details.appendChild(panel);
}
""".strip()


def inject_standalone_content_inspector(html: str) -> str:
    """Inject reference-only content, agent-activity, and message inspectors.

    Protective-mode HTML is intentionally left untouched. Full content bytes are
    never embedded in the HTML and are never fetched over HTTP by this inspector.
    Agent activity and message stages are derived only from materialized graph evidence.
    """
    marker = "function showDetails(kind,value){"
    if marker not in html:
        return html
    result = html.replace("</style>", _INSPECTOR_CSS + "\n</style>", 1)
    result = result.replace(marker, _INSPECTOR_JS + "\n" + marker, 1)
    detail_end = "  details.append(p);\n}"
    replacement = (
        "  details.append(p);execweaveAppendContentInspector(kind,value);"
        "execweaveAppendAgentActivity(kind,value);"
        "execweaveAppendMessageInspector(kind,value);\n}"
    )
    if detail_end not in result:
        raise RuntimeError("standalone viewer detail seam changed; content inspector not injected")
    return result.replace(detail_end, replacement, 1)
