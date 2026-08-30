from __future__ import annotations

import json
from typing import Any

_STANDALONE_CSS = r"""
.execweave-conversation-panel{margin:8px 0 14px}.execweave-conversation-summary{color:var(--muted);font-size:11px;margin:0 0 7px}.execweave-conversation-list{display:grid;gap:7px}.execweave-conversation-row{padding:8px;border:1px solid var(--border);border-radius:8px;background:var(--panel2)}.execweave-conversation-meta{display:flex;gap:6px;flex-wrap:wrap;color:var(--muted);font-size:9px;margin-bottom:5px}.execweave-conversation-title{font-size:11px;font-weight:700;color:var(--text)}.execweave-conversation-link{display:inline-block;color:var(--selected);font-size:9px;text-decoration:none;margin-top:5px;overflow-wrap:anywhere}.execweave-conversation-link:hover{filter:brightness(1.15)}.execweave-conversation-messages{display:grid;gap:5px;margin-top:7px}.execweave-conversation-message{padding:6px 7px;border-left:2px solid var(--border);background:rgba(0,0,0,.12);border-radius:0 6px 6px 0}.execweave-conversation-message.final{border-left-color:var(--selected)}.execweave-conversation-message.encrypted{border-left-style:dashed}.execweave-conversation-message-meta{font-size:9px;color:var(--muted);margin-bottom:3px}.execweave-conversation-message-body{font-size:11px;color:var(--text);white-space:pre-wrap;overflow-wrap:anywhere}.execweave-conversation-message.encrypted .execweave-conversation-message-body{color:var(--muted);font-style:italic}.execweave-conversation-index{display:inline-block;margin-top:8px;font-size:10px;color:var(--selected);text-decoration:none}
""".strip()

_STANDALONE_MARKUP = r"""
<h3>Conversation records</h3>
<div id="execweave-conversation-panel" class="execweave-conversation-panel"><div class="execweave-conversation-summary">No conversation records exposed yet.</div></div>
""".strip()

_STANDALONE_JS = r"""
function execweaveConversationKind(kind){const value=String(kind||'').toLowerCase(),tokens=['conversation_transcript','conversation_item','agent_message','user_message','user_prompt','assistant_display','assistant_response','assistant_final_response','completed_text','subtask_prompt','subtask_description','subagent_task','subagent_description','subagent_summary','subagent_final_response','prompt_submission_candidate','inference_message','model_context_messages'];return tokens.some(token=>value.includes(token))}
function execweaveConversationReference(node){if(!node||node.type!=='observed_content')return null;const attrs=node.attributes||{},ref=attrs.viewer_content||{},kind=String(ref.content_kind||attrs.content_kind||''),path=String(ref.safe_relative_path||attrs.path||''),sha=String(ref.sha256||attrs.sha256||'');if(!execweaveConversationKind(kind))return null;const match=/^content\/sha256\/([0-9a-f]{64})\.(json|txt|bin)$/.exec(path);if(!match||match[1]!==sha)return null;return{kind,path,size:Number(ref.size_bytes??attrs.size_bytes)||0,category:String(ref.category||'Conversation content')}}
function execweaveConversationHref(path){if(location.protocol==='file:')return path;const token=String(window.__execweaveToken||'');return `/${path}${token?`?t=${encodeURIComponent(token)}`:''}`}
function execweaveEmbeddedConversationEntries(){const element=document.getElementById('execweave-conversation-data');if(!element)return[];try{const payload=JSON.parse(element.textContent||'{}');return Array.isArray(payload.entries)?payload.entries:[]}catch(_){return[]}}
function execweaveLatestConversationThreads(entries){const latest=new Map();for(const entry of entries){const preview=entry&&entry.conversation_preview;if(!preview||!Array.isArray(preview.messages))continue;const key=String(preview.thread_id||entry.source_id||entry.path||'unknown'),existing=latest.get(key);if(!existing){latest.set(key,entry);continue}const a=Number.isInteger(existing.last_sequence)?existing.last_sequence:-1,b=Number.isInteger(entry.last_sequence)?entry.last_sequence:-1;if(b>a||(b===a&&Number(entry.size_bytes||0)>Number(existing.size_bytes||0)))latest.set(key,entry)}return[...latest.values()].sort((a,b)=>String(a.conversation_preview?.agent_path||a.source_name||'').localeCompare(String(b.conversation_preview?.agent_path||b.source_name||'')))}
function execweaveAppendConversationMessage(container,message,fallbackSource){const row=document.createElement('div');row.className='execweave-conversation-message';if(message?.phase==='final_answer')row.classList.add('final');if(message?.content_state==='provider_encrypted')row.classList.add('encrypted');const meta=document.createElement('div');meta.className='execweave-conversation-message-meta';const sender=String(message?.sender||fallbackSource||'agent'),recipient=message?.recipient?` → ${message.recipient}`:'',kind=String(message?.kind||'message'),phase=message?.phase?` · ${message.phase}`:'';meta.textContent=`${sender}${recipient} · ${kind}${phase}`;const body=document.createElement('div');body.className='execweave-conversation-message-body';body.textContent=message?.content_state==='provider_encrypted'?'Provider-encrypted payload — plaintext is not exposed by the Codex rollout.':String(message?.text||'(no plaintext body exposed)');row.append(meta,body);container.appendChild(row)}
function execweaveRenderRichConversationRecords(panel,entries){const threads=execweaveLatestConversationThreads(entries);if(!threads.length)return false;panel.replaceChildren();const messageCount=threads.reduce((total,entry)=>total+((entry.conversation_preview?.messages||[]).length),0),summary=document.createElement('div');summary.className='execweave-conversation-summary';summary.textContent=`${threads.length} agent conversation${threads.length===1?'':'s'} · ${messageCount} visible item${messageCount===1?'':'s'} · run-local evidence`;panel.appendChild(summary);const list=document.createElement('div');list.className='execweave-conversation-list';for(const entry of threads){const preview=entry.conversation_preview||{},row=document.createElement('div');row.className='execweave-conversation-row';const title=document.createElement('div');title.className='execweave-conversation-title';const source=String(preview.agent_path||entry.source_name||entry.source_id||'Codex conversation'),nickname=preview.agent_nickname?` · ${preview.agent_nickname}`:'';title.textContent=`${source}${nickname}`;const meta=document.createElement('div');meta.className='execweave-conversation-meta';meta.textContent=`${entry.provider||'provider'} · ${entry.relation||'conversation'} · ${entry.size_bytes||0} bytes`;const messages=document.createElement('div');messages.className='execweave-conversation-messages';for(const message of (preview.messages||[]).slice(-40))execweaveAppendConversationMessage(messages,message,source);const raw=document.createElement('a');raw.className='execweave-conversation-link';raw.href=execweaveConversationHref(String(entry.path||''));raw.target='_blank';raw.rel='noreferrer';raw.textContent='Open run-local raw rollout evidence';row.append(title,meta,messages,raw);list.appendChild(row)}panel.appendChild(list);const index=document.createElement('a');index.className='execweave-conversation-index';index.href=location.protocol==='file:'?'conversations.md':`/conversations.md${window.__execweaveToken?`?t=${encodeURIComponent(window.__execweaveToken)}`:''}`;index.target='_blank';index.rel='noreferrer';index.textContent='Open complete conversation index';panel.appendChild(index);return true}
function execweaveRenderConversationRecords(){const panel=document.getElementById('execweave-conversation-panel');if(!panel)return;const embedded=execweaveEmbeddedConversationEntries();if(execweaveRenderRichConversationRecords(panel,embedded))return;panel.replaceChildren();const summary=document.createElement('div');summary.className='execweave-conversation-summary';summary.textContent='No agent conversation was projected from this run \u00b7 each agent shows only its own conversation';panel.appendChild(summary)}
function execweavePreferAgentView(){const agents=possibleNodes.filter(node=>node&&node.type==='agent'&&node.id!=='agent:Codex'),ids=new Set(agents.map(node=>node.id)),linked=possibleEdges.some(edge=>ids.has(edge?.source)&&ids.has(edge?.target));if(agents.length>=2&&linked&&typeFilter.value==='')typeFilter.value='agent'}
""".strip()

_LIVE_CSS = r"""
#conversation-records{max-height:360px;overflow:auto}.conversation-live-summary{color:var(--muted);font-size:11px;margin-bottom:7px}.conversation-live-list{display:grid;gap:7px}.conversation-live-row{padding:8px;border:1px solid var(--border);border-radius:7px;background:var(--panel2)}.conversation-live-title{font-size:11px;font-weight:700;color:var(--text)}.conversation-live-meta{color:var(--muted);font-size:9px;margin:3px 0}.conversation-live-messages{display:grid;gap:5px;margin-top:6px}.conversation-live-message{padding:6px 7px;border-left:2px solid var(--border);background:rgba(0,0,0,.12);border-radius:0 6px 6px 0}.conversation-live-message.final{border-left-color:var(--accent)}.conversation-live-message.encrypted{border-left-style:dashed}.conversation-live-message-meta{color:var(--muted);font-size:9px;margin-bottom:2px}.conversation-live-message-body{font-size:11px;color:var(--text);white-space:pre-wrap;overflow-wrap:anywhere}.conversation-live-message.encrypted .conversation-live-message-body{color:var(--muted);font-style:italic}.conversation-live-link{display:inline-block;color:var(--accent);font-size:9px;text-decoration:none;margin-top:5px;overflow-wrap:anywhere}.conversation-live-index{display:inline-block;margin-top:8px;color:var(--accent);font-size:10px;text-decoration:none}
""".strip()

_LIVE_MARKUP = r"""
<div class="inspector-section"><div class="eyebrow">Conversation records</div><div id="conversation-records"><div class="conversation-live-summary">Waiting for provider-supplied conversation evidence…</div></div></div>
""".strip()

_LIVE_JS = r"""
<script>
(()=>{const core=window.__execweaveCore,dashboard=window.__execweaveDashboard||{},panel=document.getElementById('conversation-records');if(!core||!panel)return;let finished=false,indexEntries=null,indexLoading=false,indexAttempts=0,indexLoadedAt=0;const oldPayload=typeof dashboard.onPayload==='function'?dashboard.onPayload.bind(dashboard):null,oldFinished=typeof dashboard.onFinished==='function'?dashboard.onFinished.bind(dashboard):null;
function isConversation(kind){const value=String(kind||'').toLowerCase(),tokens=['conversation_transcript','conversation_item','agent_message','user_message','user_prompt','assistant_display','assistant_response','assistant_final_response','completed_text','subtask_prompt','subtask_description','subagent_task','subagent_description','subagent_summary','subagent_final_response','prompt_submission_candidate','inference_message','model_context_messages'];return tokens.some(token=>value.includes(token))}
function ref(node){if(!node||node.type!=='observed_content')return null;const attrs=node.attributes||{},viewer=attrs.viewer_content||{},kind=String(viewer.content_kind||attrs.content_kind||''),path=String(viewer.safe_relative_path||attrs.path||''),sha=String(viewer.sha256||attrs.sha256||'');if(!isConversation(kind))return null;const match=/^content\/sha256\/([0-9a-f]{64})\.(json|txt|bin)$/.exec(path);if(!match||match[1]!==sha)return null;return{kind,path,size:Number(viewer.size_bytes??attrs.size_bytes)||0,category:String(viewer.category||'Conversation content')}}
function href(path){const token=String(window.__execweaveToken||'');return `/${path}${token?`?t=${encodeURIComponent(token)}`:''}`}
function latestThreads(entries){const latest=new Map();for(const entry of entries||[]){const preview=entry?.conversation_preview;if(!preview||!Array.isArray(preview.messages))continue;const key=String(preview.thread_id||entry.source_id||entry.path||'unknown'),existing=latest.get(key);if(!existing){latest.set(key,entry);continue}const a=Number.isInteger(existing.last_sequence)?existing.last_sequence:-1,b=Number.isInteger(entry.last_sequence)?entry.last_sequence:-1;if(b>a||(b===a&&Number(entry.size_bytes||0)>Number(existing.size_bytes||0)))latest.set(key,entry)}return[...latest.values()]}
function appendMessage(container,message,fallback){const row=document.createElement('div');row.className='conversation-live-message';if(message?.phase==='final_answer')row.classList.add('final');if(message?.content_state==='provider_encrypted')row.classList.add('encrypted');const meta=document.createElement('div');meta.className='conversation-live-message-meta';meta.textContent=`${message?.sender||fallback||'agent'}${message?.recipient?` → ${message.recipient}`:''} · ${message?.kind||'message'}${message?.phase?` · ${message.phase}`:''}`;const body=document.createElement('div');body.className='conversation-live-message-body';body.textContent=message?.content_state==='provider_encrypted'?'Provider-encrypted payload — plaintext is not exposed by the Codex rollout.':String(message?.text||'(no plaintext body exposed)');row.append(meta,body);container.appendChild(row)}
function renderRich(entries){const threads=latestThreads(entries);if(!threads.length)return false;panel.replaceChildren();const count=threads.reduce((n,e)=>n+((e.conversation_preview?.messages||[]).length),0),summary=document.createElement('div');summary.className='conversation-live-summary';summary.textContent=`${threads.length} agent conversation${threads.length===1?'':'s'} · ${count} visible item${count===1?'':'s'} · run-local record`;panel.appendChild(summary);const list=document.createElement('div');list.className='conversation-live-list';for(const entry of threads){const preview=entry.conversation_preview||{},row=document.createElement('div');row.className='conversation-live-row';const source=String(preview.agent_path||entry.source_name||entry.source_id||'Codex conversation'),title=document.createElement('div');title.className='conversation-live-title';title.textContent=`${source}${preview.agent_nickname?` · ${preview.agent_nickname}`:''}`;const meta=document.createElement('div');meta.className='conversation-live-meta';meta.textContent=`${entry.provider||'provider'} · ${entry.relation||'conversation'} · ${entry.size_bytes||0} bytes`;const messages=document.createElement('div');messages.className='conversation-live-messages';for(const message of (preview.messages||[]).slice(-40))appendMessage(messages,message,source);const raw=document.createElement('a');raw.className='conversation-live-link';raw.href=href(String(entry.path||''));raw.target='_blank';raw.rel='noreferrer';raw.textContent='Open run-local raw rollout evidence';row.append(title,meta,messages,raw);list.appendChild(row)}panel.appendChild(list);const index=document.createElement('a');index.className='conversation-live-index';index.href=`/conversations.md${window.__execweaveToken?`?t=${encodeURIComponent(window.__execweaveToken)}`:''}`;index.target='_blank';index.rel='noreferrer';index.textContent='Open complete conversation index';panel.appendChild(index);return true}
async function loadIndex(){if(indexLoading)return;if(indexEntries!==null&&(finished||Date.now()-indexLoadedAt<1500))return;indexLoading=true;indexAttempts+=1;try{const token=String(window.__execweaveToken||''),response=await fetch(`/conversations.json${token?`?t=${encodeURIComponent(token)}`:''}`,{cache:'no-store'});if(!response.ok)throw new Error(String(response.status));const payload=await response.json();indexEntries=Array.isArray(payload.entries)?payload.entries:[];indexLoadedAt=Date.now();render()}catch(_){if(finished&&indexAttempts<6)setTimeout(()=>{indexLoading=false;loadIndex()},350)}finally{indexLoading=false}}
function render(){if(indexEntries!==null&&renderRich(indexEntries))return;loadIndex();panel.replaceChildren();const summary=document.createElement('div');summary.className='conversation-live-summary';summary.textContent=finished?'No agent conversation was projected from this run.':'Waiting for an agent conversation to be projected from this run \u00b7 each agent shows only its own conversation';panel.appendChild(summary);if(finished){const index=document.createElement('a');index.className='conversation-live-index';index.href=`/conversations.md${window.__execweaveToken?`?t=${encodeURIComponent(window.__execweaveToken)}`:''}`;index.target='_blank';index.rel='noreferrer';index.textContent='Open complete conversation index';panel.appendChild(index)}}
window.__execweaveDashboard={...dashboard,onPayload(data){oldPayload?.(data);render()},onFinished(){oldFinished?.();finished=true;render();loadIndex()}};render()})();
</script>
""".strip()


def _safe_embedded_json(entries: list[dict[str, Any]]) -> str:
    return (
        json.dumps({"entries": entries}, ensure_ascii=False, separators=(",", ":"))
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


def inject_standalone_conversation_panel(
    html: str,
    *,
    entries: list[dict[str, Any]] | None = None,
) -> str:
    """Add direct run-local conversation timelines to the final standalone dashboard."""
    if 'id="execweave-conversation-panel"' in html:
        return html
    marker = "function showDetails(kind,value){"
    init = "renderCorrelationSummary();loadPresets();applyGraphFilters();"
    if marker not in html or init not in html or "<h3>Saved views</h3>" not in html:
        return html
    data = ""
    if entries is not None:
        data = (
            '<script type="application/json" id="execweave-conversation-data">'
            + _safe_embedded_json(entries)
            + "</script>\n"
        )
    result = html.replace("</style>", _STANDALONE_CSS + "\n</style>", 1)
    result = result.replace(
        "<h3>Saved views</h3>",
        _STANDALONE_MARKUP + "\n" + data + "  <h3>Saved views</h3>",
        1,
    )
    result = result.replace(marker, _STANDALONE_JS + "\n" + marker, 1)
    replacement = (
        "renderCorrelationSummary();loadPresets();execweavePreferAgentView();"
        "applyGraphFilters();execweaveRenderConversationRecords();"
    )
    return result.replace(init, replacement, 1)


def inject_live_conversation_panel(html: str) -> str:
    """Add live timelines backed only by ExecWeave's authenticated run-local server."""
    if 'id="conversation-records"' in html:
        return html
    if "</aside>" not in html or "</body>" not in html:
        return html
    result = html.replace("</style>", _LIVE_CSS + "\n</style>", 1)
    result = result.replace("</aside>", _LIVE_MARKUP + "\n</aside>", 1)
    return result.replace("</body>", _LIVE_JS + "\n</body>", 1)
