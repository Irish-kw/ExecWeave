from __future__ import annotations

_STANDALONE_CSS = r"""
.execweave-conversation-panel{margin:8px 0 14px}.execweave-conversation-summary{color:var(--muted);font-size:11px;margin:0 0 7px}.execweave-conversation-list{display:grid;gap:6px}.execweave-conversation-row{padding:7px 8px;border:1px solid var(--border);border-radius:7px;background:var(--panel2)}.execweave-conversation-meta{display:flex;gap:6px;flex-wrap:wrap;color:var(--muted);font-size:9px;margin-bottom:4px}.execweave-conversation-link{display:block;color:var(--text);font-size:11px;text-decoration:none;overflow-wrap:anywhere}.execweave-conversation-link:hover{color:var(--selected)}.execweave-conversation-index{display:inline-block;margin-top:8px;font-size:10px;color:var(--selected);text-decoration:none}
""".strip()

_STANDALONE_MARKUP = r"""
<h3>Conversation records</h3>
<div id="execweave-conversation-panel" class="execweave-conversation-panel"><div class="execweave-conversation-summary">No conversation records exposed yet.</div></div>
""".strip()

_STANDALONE_JS = r"""
function execweaveConversationKind(kind){const value=String(kind||'').toLowerCase(),tokens=['conversation_transcript','conversation_item','agent_message','user_message','user_prompt','assistant_display','assistant_response','assistant_final_response','completed_text','subtask_prompt','subtask_description','subagent_task','subagent_description','subagent_summary','subagent_final_response','prompt_submission_candidate','inference_message','model_context_messages'];return tokens.some(token=>value.includes(token))}
function execweaveConversationReference(node){if(!node||node.type!=='observed_content')return null;const attrs=node.attributes||{},ref=attrs.viewer_content||{},kind=String(ref.content_kind||attrs.content_kind||''),path=String(ref.safe_relative_path||attrs.path||''),sha=String(ref.sha256||attrs.sha256||'');if(!execweaveConversationKind(kind))return null;const match=/^content\/sha256\/([0-9a-f]{64})\.(json|txt|bin)$/.exec(path);if(!match||match[1]!==sha)return null;return{kind,path,size:Number(ref.size_bytes??attrs.size_bytes)||0,category:String(ref.category||'Conversation content')}}
function execweaveConversationHref(path){if(location.protocol==='file:')return path;const token=String(window.__execweaveToken||'');return `/${path}${token?`?t=${encodeURIComponent(token)}`:''}`}
function execweaveRenderConversationRecords(){const panel=document.getElementById('execweave-conversation-panel');if(!panel)return;const nodeMap=new Map(possibleNodes.filter(node=>node&&node.id).map(node=>[node.id,node])),rows=[];possibleNodes.forEach(node=>{const ref=execweaveConversationReference(node);if(!ref)return;const edge=possibleEdges.find(candidate=>candidate&&candidate.target===node.id),source=edge?nodeMap.get(edge.source):null,provider=String(source?.attributes?.provider||ref.kind.split('.',1)[0]||'provider');rows.push({node,ref,edge,source,provider})});rows.sort((a,b)=>{const sa=Number.isInteger(a.edge?.first_sequence)?a.edge.first_sequence:Number.MAX_SAFE_INTEGER,sb=Number.isInteger(b.edge?.first_sequence)?b.edge.first_sequence:Number.MAX_SAFE_INTEGER;return sa-sb||String(a.node.first_seen||'').localeCompare(String(b.node.first_seen||''))});panel.replaceChildren();const summary=document.createElement('div');summary.className='execweave-conversation-summary';summary.textContent=rows.length?`${rows.length} run-local conversation record${rows.length===1?'':'s'} · newest ${Math.min(rows.length,80)} shown`:'No conversation content was exposed by the selected integrations for this run.';panel.appendChild(summary);if(rows.length){const list=document.createElement('div');list.className='execweave-conversation-list';rows.slice(-80).forEach(item=>{const row=document.createElement('div');row.className='execweave-conversation-row';const meta=document.createElement('div');meta.className='execweave-conversation-meta';meta.textContent=`${item.provider} · ${item.edge?.relation||'CONTENT'} · ${item.ref.size} bytes`;const link=document.createElement('a');link.className='execweave-conversation-link';link.href=execweaveConversationHref(item.ref.path);link.target='_blank';link.rel='noreferrer';link.textContent=`${item.source?.name||item.source?.id||'Conversation'} · ${item.ref.category}`;row.append(meta,link);list.appendChild(row)});panel.appendChild(list);const index=document.createElement('a');index.className='execweave-conversation-index';index.href=location.protocol==='file:'?'conversations.md':`/conversations.md${window.__execweaveToken?`?t=${encodeURIComponent(window.__execweaveToken)}`:''}`;index.target='_blank';index.rel='noreferrer';index.textContent='Open complete conversation index';panel.appendChild(index)}}
""".strip()

_LIVE_CSS = r"""
#conversation-records{max-height:280px;overflow:auto}.conversation-live-summary{color:var(--muted);font-size:11px;margin-bottom:7px}.conversation-live-list{display:grid;gap:6px}.conversation-live-row{padding:7px;border:1px solid var(--border);border-radius:7px;background:var(--panel2)}.conversation-live-meta{color:var(--muted);font-size:9px;margin-bottom:3px}.conversation-live-link{display:block;color:var(--text);font-size:11px;text-decoration:none;overflow-wrap:anywhere}.conversation-live-link:hover{color:var(--accent)}.conversation-live-index{display:inline-block;margin-top:8px;color:var(--accent);font-size:10px;text-decoration:none}
""".strip()

_LIVE_MARKUP = r"""
<div class="inspector-section"><div class="eyebrow">Conversation records</div><div id="conversation-records"><div class="conversation-live-summary">Waiting for provider-supplied conversation evidence…</div></div></div>
""".strip()

_LIVE_JS = r"""
<script>
(()=>{const core=window.__execweaveCore,dashboard=window.__execweaveDashboard||{},panel=document.getElementById('conversation-records');if(!core||!panel)return;let finished=false;const oldPayload=typeof dashboard.onPayload==='function'?dashboard.onPayload.bind(dashboard):null,oldFinished=typeof dashboard.onFinished==='function'?dashboard.onFinished.bind(dashboard):null;
function isConversation(kind){const value=String(kind||'').toLowerCase(),tokens=['conversation_transcript','conversation_item','agent_message','user_message','user_prompt','assistant_display','assistant_response','assistant_final_response','completed_text','subtask_prompt','subtask_description','subagent_task','subagent_description','subagent_summary','subagent_final_response','prompt_submission_candidate','inference_message','model_context_messages'];return tokens.some(token=>value.includes(token))}
function ref(node){if(!node||node.type!=='observed_content')return null;const attrs=node.attributes||{},viewer=attrs.viewer_content||{},kind=String(viewer.content_kind||attrs.content_kind||''),path=String(viewer.safe_relative_path||attrs.path||''),sha=String(viewer.sha256||attrs.sha256||'');if(!isConversation(kind))return null;const match=/^content\/sha256\/([0-9a-f]{64})\.(json|txt|bin)$/.exec(path);if(!match||match[1]!==sha)return null;return{kind,path,size:Number(viewer.size_bytes??attrs.size_bytes)||0,category:String(viewer.category||'Conversation content')}}
function href(path){const token=String(window.__execweaveToken||'');return `/${path}${token?`?t=${encodeURIComponent(token)}`:''}`}
function render(){const graph=core.getGraph()||{},nodes=graph.nodes||[],edges=graph.edges||[],nodeMap=new Map(nodes.filter(node=>node&&node.id).map(node=>[node.id,node])),rows=[];for(const node of nodes){const stored=ref(node);if(!stored)continue;const edge=edges.find(candidate=>candidate&&candidate.target===node.id),source=edge?nodeMap.get(edge.source):null,provider=String(source?.attributes?.provider||stored.kind.split('.',1)[0]||'provider');rows.push({node,stored,edge,source,provider})}rows.sort((a,b)=>String(a.node.last_seen||'').localeCompare(String(b.node.last_seen||'')));panel.replaceChildren();const summary=document.createElement('div');summary.className='conversation-live-summary';summary.textContent=rows.length?`${rows.length} run-local record${rows.length===1?'':'s'} · latest ${Math.min(rows.length,50)} shown`:'No provider-supplied conversation content observed yet.';panel.appendChild(summary);if(rows.length){const list=document.createElement('div');list.className='conversation-live-list';for(const item of rows.slice(-50)){const row=document.createElement('div');row.className='conversation-live-row';const meta=document.createElement('div');meta.className='conversation-live-meta';meta.textContent=`${item.provider} · ${item.edge?.relation||'CONTENT'} · ${item.stored.size} bytes`;const link=document.createElement('a');link.className='conversation-live-link';link.href=href(item.stored.path);link.target='_blank';link.rel='noreferrer';link.textContent=`${item.source?.name||item.source?.id||'Conversation'} · ${item.stored.category}`;row.append(meta,link);list.appendChild(row)}panel.appendChild(list)}if(finished){const index=document.createElement('a');index.className='conversation-live-index';index.href=`/conversations.md${window.__execweaveToken?`?t=${encodeURIComponent(window.__execweaveToken)}`:''}`;index.target='_blank';index.rel='noreferrer';index.textContent='Open complete conversation index';panel.appendChild(index)}}
window.__execweaveDashboard={...dashboard,onPayload(data){oldPayload?.(data);render()},onFinished(){oldFinished?.();finished=true;render()}};render()})();
</script>
""".strip()


def inject_standalone_conversation_panel(html: str) -> str:
    """Add run-local conversation links to the final standalone dashboard."""
    if 'id="execweave-conversation-panel"' in html:
        return html
    marker = "function showDetails(kind,value){"
    init = "renderCorrelationSummary();loadPresets();applyGraphFilters();"
    if marker not in html or init not in html or "<h3>Saved views</h3>" not in html:
        return html
    result = html.replace("</style>", _STANDALONE_CSS + "\n</style>", 1)
    result = result.replace(
        "<h3>Saved views</h3>",
        _STANDALONE_MARKUP + "\n  <h3>Saved views</h3>",
        1,
    )
    result = result.replace(marker, _STANDALONE_JS + "\n" + marker, 1)
    return result.replace(init, init + "execweaveRenderConversationRecords();", 1)


def inject_live_conversation_panel(html: str) -> str:
    """Add live links backed only by ExecWeave's authenticated run-local content server."""
    if 'id="conversation-records"' in html:
        return html
    if "</aside>" not in html or "</body>" not in html:
        return html
    result = html.replace("</style>", _LIVE_CSS + "\n</style>", 1)
    result = result.replace("</aside>", _LIVE_MARKUP + "\n</aside>", 1)
    return result.replace("</body>", _LIVE_JS + "\n</body>", 1)
