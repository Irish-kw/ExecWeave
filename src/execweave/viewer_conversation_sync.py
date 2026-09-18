"""Explicit, run-scoped state for the existing final conversation synchronization."""
from __future__ import annotations

SYNC_STATE_JS = """let selectedNode=null,refreshing=false,conversationPollingFinished=false,conversationFinishSynchronized=false,conversationFinishing=false,conversationRefreshController=null,conversationRefreshTimer=null,conversationRefreshPromise=Promise.resolve(false),conversationFinishPromise=Promise.resolve(false),selectedConversationSignature='',conversationScopeKey=null,conversationSyncGeneration=0,conversationResponseScoped=false;"""

SYNC_REFRESH_JS = r"""
function conversationScope(){
  const g=window.__execweaveCore?.getGraph?.()||window.__execweaveStaticGraph||{};
  return {session_id:g.session_id||null,source_path:g.source_path||null};
}
function synchronizationStatus(){
  const scope=conversationScope(),stale=conversationScopeKey!==null&&conversationScopeKey!==JSON.stringify(scope);
  return {...scope,state:stale?'unknown':window.__execweaveStaticMode?'embedded':
    conversationFinishing?'syncing':conversationPollingFinished?
      (conversationFinishSynchronized?'synced':'failed'):'live',
    response_session_checked:!stale&&conversationResponseScoped};
}
function notifyConversationSync(){
  window.dispatchEvent(new CustomEvent('execweave:conversation-sync'));
}
function ensureConversationScope(){
  const next=JSON.stringify(conversationScope());
  if(conversationScopeKey===null){conversationScopeKey=next;return}
  if(next===conversationScopeKey)return;
  conversationScopeKey=next;conversationSyncGeneration++;
  conversationRefreshController?.abort();conversationRefreshController=null;
  refreshing=false;conversationPollingFinished=false;conversationFinishSynchronized=false;
  conversationFinishing=false;conversationResponseScoped=false;
  conversationRefreshPromise=Promise.resolve(false);conversationFinishPromise=Promise.resolve(false);
  document.getElementById('conversation-sync-status')?.remove();setEntries([]);
  if(!window.__execweaveStaticMode&&conversationRefreshTimer===null){
    conversationRefreshTimer=setInterval(()=>{if(selectedNode&&!conversationFinishing&&!conversationPollingFinished)refresh()},800);
  }
  notifyConversationSync();
}
async function refresh({allowDuringFinish=false}={}){
  ensureConversationScope();
  if(window.__execweaveStaticMode||(conversationPollingFinished&&!allowDuringFinish)||
     (conversationFinishing&&!allowDuringFinish))return false;
  if(refreshing)return conversationRefreshPromise;
  refreshing=true;const epoch=conversationSyncGeneration,scope=conversationScopeKey;
  const controller=new AbortController();conversationRefreshController=controller;
  const timeout=setTimeout(()=>controller.abort(),5000);
  const task=(async()=>{try{
    const headers={};if(window.__execweaveToken)headers['X-ExecWeave-Token']=window.__execweaveToken;
    const response=await fetch('/conversations.json',{cache:'no-store',headers,signal:controller.signal});
    if(!response.ok||(response.status!==undefined&&response.status!==200))return false;
    const payload=await response.json();
    if(controller.signal.aborted||epoch!==conversationSyncGeneration||scope!==JSON.stringify(conversationScope()))return false;
    if(!Array.isArray(payload?.entries)||payload.entries.some(e=>!e||typeof e!=='object'||Array.isArray(e)))return false;
    const session=conversationScope().session_id;
    if(payload.session_id!==undefined&&payload.session_id!==session)return false;
    if(payload.source_path!==undefined&&(payload.source_path||null)!==conversationScope().source_path)return false;
    conversationResponseScoped=typeof session==='string'&&payload.session_id===session;
    setEntries(payload.entries);return true;
  }catch(_){return false}finally{
    clearTimeout(timeout);
    if(conversationRefreshController===controller){conversationRefreshController=null;refreshing=false}
  }})();conversationRefreshPromise=task;return await task;
}
""".strip()

SYNC_LIFECYCLE_JS = r"""
function reportFinalConversationSync(ok){
  let notice=document.getElementById('conversation-sync-status');
  if(ok){notice?.remove();return}if(notice)return;
  notice=document.createElement('div');notice.id='conversation-sync-status';notice.setAttribute('role','status');
  notice.style.cssText='position:fixed;right:18px;bottom:18px;z-index:100;max-width:360px;padding:12px;background:#2b2118;color:#fff;border:1px solid #e5ad63;border-radius:8px';
  notice.append(document.createTextNode('Conversation history may be incomplete. Final synchronization failed. '));
  const retry=document.createElement('button');retry.type='button';retry.textContent='Retry sync';
  retry.onclick=async()=>{retry.disabled=true;try{await finishConversationPolling()}finally{retry.disabled=false}};
  notice.append(retry);document.body.append(notice);
}
async function finishConversationPolling(){
  ensureConversationScope();
  if(conversationPollingFinished&&conversationFinishSynchronized)return true;
  if(conversationFinishing)return conversationFinishPromise;
  const epoch=conversationSyncGeneration,scope=conversationScopeKey;
  conversationFinishing=true;notifyConversationSync();
  if(conversationRefreshTimer!==null){clearInterval(conversationRefreshTimer);conversationRefreshTimer=null}
  conversationFinishPromise=(async()=>{
    await conversationRefreshPromise;
    if(epoch!==conversationSyncGeneration||scope!==JSON.stringify(conversationScope()))return false;
    if(window.__execweaveStaticMode)return true;
    return await refresh({allowDuringFinish:true});
  })().catch(()=>false).then(synchronized=>{
    if(epoch!==conversationSyncGeneration||scope!==JSON.stringify(conversationScope()))return false;
    conversationFinishSynchronized=Boolean(synchronized);reportFinalConversationSync(conversationFinishSynchronized);
    return conversationFinishSynchronized;
  }).finally(()=>{
    if(epoch!==conversationSyncGeneration||scope!==JSON.stringify(conversationScope()))return;
    conversationPollingFinished=true;conversationFinishing=false;
    if(conversationRefreshController!==null){conversationRefreshController.abort();conversationRefreshController=null}
    notifyConversationSync();
  });return await conversationFinishPromise;
}
const stopConversationPolling=finishConversationPolling;
const previous=window.__execweaveDashboard||{};
window.__execweaveDashboard={...previous,
  onPayload(data){previous.onPayload?.(data);ensureConversationScope();if(selectedNode&&!data?.live_finished&&!conversationFinishing&&!conversationPollingFinished)refresh()},
  onFinished(){previous.onFinished?.();void finishConversationPolling()}
};
""".strip()
