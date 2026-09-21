"""Read published agent-local history without changing round or ownership policy.

The existing inspector keeps its compact round summaries. This on-demand reader
uses exact source IDs (and explicit projection members), paginates DOM nodes, and
pins the open snapshot until the reader explicitly refreshes it. It never fetches
new files, reconstructs hidden reasoning, or declares task success from text.
"""
from __future__ import annotations

HISTORY_BROWSER_CSS = r"""
.execweave-history-entry{display:flex;align-items:center;flex-wrap:wrap;gap:8px;margin:0 0 12px}
.execweave-history-entry button{font:inherit;padding:7px 10px;cursor:pointer}
.execweave-history-entry small{color:var(--muted)}
#execweave-history-dialog{width:min(1000px,92vw);max-height:88vh;box-sizing:border-box;border:1px solid var(--border,#888);border-radius:10px;background:var(--panel,#fff);color:var(--text,#111);padding:16px}
#execweave-history-dialog::backdrop{background:rgba(0,0,0,.4)}
#execweave-history-dialog header,.execweave-history-controls{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin-bottom:10px}
#execweave-history-title{flex:1;font-size:18px;margin:0}
#execweave-history-dialog button,#execweave-history-dialog input,#execweave-history-dialog select{font:inherit;padding:6px}
#execweave-history-search{flex:1;min-width:180px}
#execweave-history-status,#execweave-history-boundary,#execweave-history-updates{font-size:13px;overflow-wrap:anywhere}
#execweave-history-list{overflow:auto;max-height:52vh;overscroll-behavior:contain}
#execweave-history-list details{border:1px solid var(--border,#888);border-radius:8px;margin:8px 0}
#execweave-history-list summary{cursor:pointer;padding:10px;font-size:14px;overflow-wrap:anywhere}
#execweave-history-list .history-provenance{padding:0 10px;font-size:12px;overflow-wrap:anywhere;color:var(--muted)}
#execweave-history-list pre{padding:10px;margin:0;white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.5 ui-monospace,monospace}
#execweave-history-list .history-body-controls{padding:8px 10px;font-size:12px}
""".strip()

HISTORY_BROWSER_JS = r"""
function execweaveCreateHistoryBrowser(getGraph,getEntries){
  const PAGE=25,TEXT_PAGE=16384,states=new Map();
  let dialog=null,title,search,filter,status,boundary,updates,refreshButton,items,prev,next;
  let active=null,published=null,currentState=null,runScope=null,viewKey=null;
  const STORE='execweave.history.view.v1',STORE_LIMIT=131072;
  const filters=new Set(['all','input','message','marker','encrypted','context']);
  const list=value=>Array.isArray(value)?value:[];
  const str=value=>typeof value==='string'?value:'';
  const scope=()=>{const g=getGraph()||{};return JSON.stringify([g.run_id??null,g.session_id??null,g.source_path??null])};
  const make=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n};
  const button=(text,action)=>{const b=make('button',text);b.type='button';b.onclick=action;return b};
  function recordsFor(node){
    const ids=new Set([str(node?.id)]);
    if(node?.type==='agent')for(const id of list(node.attributes?.viewer_agent_member_ids))if(typeof id==='string')ids.add(id);
    ids.delete('');
    const candidates=list(getEntries()).filter(e=>ids.has(e?.source_id)&&e?.conversation_preview&&typeof e.conversation_preview==='object');
    const scopes=new Map();
    for(const e of candidates){
      const p=e.conversation_preview;
      if(!['provider_native','execweave_derived'].includes(p.thread_id_source)||!str(p.provider_native_id))continue;
      if(!scopes.has(e.source_id))scopes.set(e.source_id,new Set());
      scopes.get(e.source_id).add(JSON.stringify([str(e.provider).toLowerCase(),p.provider_native_id]));
    }
    const ambiguous=new Set([...scopes].filter(([,values])=>values.size>1).map(([id])=>id));
    return {records:candidates.filter(e=>!ambiguous.has(e.source_id)),ambiguous:ambiguous.size};
  }
  function persistenceKey(node){
    const g=getGraph()||{};
    // A filename or display label alone does not identify an execution.
    if(![g.run_id,g.session_id].some(v=>typeof v==='string'&&v.length>0&&v.length<=4096))return null;
    const selected=recordsFor(node);if(selected.ambiguous)return null;
    const identities=selected.records.map(e=>[e.source_id,str(e.provider),str(e.conversation_preview.thread_id),str(e.conversation_preview.provider_native_id)]);
    identities.sort((a,b)=>JSON.stringify(a).localeCompare(JSON.stringify(b)));
    const key=JSON.stringify([scope(),node.id,identities]);return key.length<=8192?key:null;
  }
  function validView(v){
    return v&&typeof v==='object'&&!Array.isArray(v)&&filters.has(v.filter)&&
      Number.isSafeInteger(v.page)&&v.page>=0&&v.page<=100000&&Array.isArray(v.open)&&v.open.length<=64&&
      v.open.every(x=>typeof x==='string'&&x.length<=2048);
  }
  function storedViews(){
    try{
      const text=window.sessionStorage.getItem(STORE);if(!text||text.length>STORE_LIMIT)return [];
      const data=JSON.parse(text);if(data?.version!==1||!Array.isArray(data.views)||data.views.length>32)return [];
      return data.views.filter(v=>Array.isArray(v)&&v.length===2&&typeof v[0]==='string'&&v[0].length<=8192&&validView(v[1])).map(([key,v])=>[key,{filter:v.filter,page:v.page,open:v.open}]);
    }catch{return []}
  }
  function restoreView(key){
    const saved=key?storedViews().find(v=>v[0]===key)?.[1]:null;
    return {query:'',filter:saved?.filter||'all',page:saved?.page||0,open:new Set(saved?.open||[])};
  }
  function saveView(){
    if(!viewKey||!currentState)return;
    // Store presentation state and record identifiers only. Never serialize a
    // transcript, message body, search term, URL token, or graph attributes.
    const view={filter:currentState.filter,page:currentState.query?0:currentState.page,
      open:[...currentState.open].filter(k=>k.length<=2048).slice(-64)};
    if(!validView(view))return;
    const views=storedViews().filter(v=>v[0]!==viewKey);views.push([viewKey,view]);
    while(views.length>32)views.shift();
    let text=JSON.stringify({version:1,views});
    while(text.length>STORE_LIMIT&&views.length){views.shift();text=JSON.stringify({version:1,views})}
    try{window.sessionStorage.setItem(STORE,text)}catch{/* Disabled/quota-limited storage must not break reading. */}
  }
  function category(m){
    if(m.content_state==='provider_encrypted')return 'encrypted';
    if(m.content_role==='shared_injected_context')return 'context';
    if(m.sender==='user'||m.kind==='user_message')return 'input';
    // Text matching is a presentation hint, never protocol or success evidence.
    if(m.text_truncated!==true&&['assistant_message','assistant_response','subagent_final_response','agent_result','final_answer'].includes(m.kind)&&
       ['TERMINATE','<CAMEL_TASK_DONE>'].includes(str(m.text).trim()))return 'marker';
    return 'message';
  }
  function snapshot(node){
    const selection=recordsFor(node),records=selection.records,rows=[];let partial=false,routing=false;
    records.forEach((e,ei)=>{
      const p=e.conversation_preview,messages=list(p.messages);
      partial=partial||p.messages_truncated===true||(Number.isSafeInteger(p.message_count)&&p.message_count>messages.length);
      routing=routing||p.conversation_completeness==='routing_only'||['cross_agent_routing','provider_cross_agent_routing_record'].includes(p.evidence_scope);
      messages.forEach((m,mi)=>{
        if(!m||typeof m!=='object'||Array.isArray(m))return;
        const row={};
        for(const key of ['timestamp','ordinal','kind','phase','sender','recipient','text','content_state','content_role','occurrence_id','message_id','text_truncated'])row[key]=m[key]??null;
        row.source_id=e.source_id;row.record_index=ei;row.message_index=mi;row.category=category(row);
        // Never deduplicate by text. Already-normalized records remain separate.
        row.key=JSON.stringify([e.source_id,p.thread_id,ei,m.occurrence_id,m.message_id,m.ordinal,mi,m.kind,m.sender,m.recipient]);
        rows.push(row);
      });
    });
    return {rows,partial,routing,recordCount:records.length,ambiguous:selection.ambiguous};
  }
  function equal(a,b){return a&&a.ambiguous===b.ambiguous&&a.partial===b.partial&&a.routing===b.routing&&a.recordCount===b.recordCount&&a.rows.length===b.rows.length&&a.rows.every((r,i)=>Object.keys(r).every(k=>r[k]===b.rows[i][k]))}
  function clear(){
    saveView();viewKey=null;
    if(dialog){dialog.close();items.replaceChildren();search.value='';status.textContent='';boundary.textContent='';updates.textContent='';title.textContent='Observed history'}
    active=null;published=null;currentState=null;
  }
  function checkRun(){const now=scope();if(now!==runScope){clear();states.clear();runScope=now;return false}return true}
  function ensure(){
    if(dialog)return;
    dialog=make('dialog');dialog.id='execweave-history-dialog';dialog.setAttribute('aria-labelledby','execweave-history-title');
    const head=make('header');title=make('h2','Observed history');title.id='execweave-history-title';head.append(title,button('Close history',clear));
    boundary=make('p');boundary.id='execweave-history-boundary';
    const controls=make('form');controls.className='execweave-history-controls';
    search=make('input');search.type='search';search.id='execweave-history-search';search.placeholder='Search loaded message text, sender, recipient, or kind';search.setAttribute('aria-label','Search observed history');
    filter=make('select');filter.id='execweave-history-filter';filter.setAttribute('aria-label','History message category');
    for(const [value,label] of [['all','All records'],['input','User inputs'],['message','Other messages'],['marker','Termination markers (text match)'],['encrypted','Encrypted records'],['context','Injected context']]){const o=make('option',label);o.value=value;filter.append(o)}
    controls.onsubmit=e=>{e.preventDefault();if(!checkRun()||!active)return;currentState.query=search.value;currentState.filter=filter.value;currentState.page=0;draw()};
    filter.onchange=()=>controls.requestSubmit();const find=button('Search',()=>controls.requestSubmit());controls.append(search,filter,find);
    const pageControls=make('div');pageControls.className='execweave-history-controls';
    prev=button('Previous records',()=>{if(checkRun()&&active){currentState.page--;draw()}});
    next=button('Next records',()=>{if(checkRun()&&active){currentState.page++;draw()}});
    refreshButton=button('Refresh history',()=>{if(!checkRun()||!active)return;published=snapshot(active);updates.textContent='';draw()});
    pageControls.append(prev,next,refreshButton);
    status=make('p');status.id='execweave-history-status';status.setAttribute('role','status');
    updates=make('p');updates.id='execweave-history-updates';updates.setAttribute('role','status');
    items=make('div');items.id='execweave-history-list';
    dialog.append(head,boundary,controls,pageControls,status,updates,items);
    dialog.addEventListener('cancel',e=>{e.preventDefault();clear()});document.body.append(dialog);
  }
  function draw(){
    if(!active||!checkRun())return;
    const query=currentState.query.toLocaleLowerCase(),kind=currentState.filter;
    const rows=published.rows.filter(r=>(kind==='all'||r.category===kind)&&(!query||[r.category==='encrypted'?'':str(r.text),str(r.sender),str(r.recipient),str(r.kind),str(r.phase)].some(t=>t.toLocaleLowerCase().includes(query))));
    const pages=Math.max(1,Math.ceil(rows.length/PAGE));currentState.page=Math.max(0,Math.min(currentState.page,pages-1));
    prev.disabled=currentState.page===0;next.disabled=currentState.page===pages-1;
    boundary.textContent='Published, normalized message records for this exact agent. Search covers the loaded text only, not every archived payload. Individual text may be a provider preview; use Recorded source content for captured bodies. Task success, message delivery, and hidden reasoning are not inferred.'+
      (published.ambiguous?' Conflicting native execution identities were recorded for the same source ID; their histories are withheld rather than combined.':'')+
      (published.partial?' This published history is truncated or has missing records; it is not a complete transcript.':'')+
      (published.routing?' Routing-only evidence is present; it does not establish the recipient\'s own transcript or consumption.':'');
    boundary.textContent+=' Page, category, and expanded records can be restored within this tab for the exact run and agent; message text and search terms are never stored. Browser storage may be unavailable.';
    status.textContent=`${rows.length} matching / ${published.rows.length} loaded records. Page ${currentState.page+1}/${pages}.`;
    if(!published.recordCount)status.textContent+=' No exact-source conversation record is available; no root or sibling content was substituted.';
    items.replaceChildren();items.scrollTop=0;
    for(const row of rows.slice(currentState.page*PAGE,(currentState.page+1)*PAGE)){
      const fold=make('details');fold.className='execweave-history-message';fold.dataset.historyKey=row.key;
      const head=make('summary');
      const label=row.category==='marker'?'Termination marker (text match)':row.category==='encrypted'?'Encrypted record':str(row.kind)||'Message';
      const preview=row.category==='encrypted'?'Plaintext not exposed':str(row.text).replace(/\s+/g,' ').slice(0,100);
      head.textContent=[`#${row.message_index+1}`,str(row.timestamp),label,`${str(row.sender)||'Unknown sender'} → ${str(row.recipient)||'Recipient not recorded'}`,preview].filter(Boolean).join(' · ');
      const meta=make('p',[`Source: ${row.source_id}`,row.occurrence_id?`Occurrence: ${row.occurrence_id}`:'',row.ordinal!==null?`Ordinal: ${row.ordinal}`:'',str(row.phase),str(row.content_state),str(row.content_role)].filter(Boolean).join(' · '));meta.className='history-provenance';
      const content=make('pre');content.className='history-message-text';
      const paging=make('div');paging.className='history-body-controls';let offset=0;
      function showText(){
        let text=row.category==='encrypted'?'Observed record; plaintext was not exposed by the provider.':typeof row.text==='string'?row.text:'No text supplied in this normalized record.';
        const count=Math.max(1,Math.ceil(text.length/TEXT_PAGE));offset=Math.max(0,Math.min(offset,count-1));
        let start=offset*TEXT_PAGE,end=Math.min(text.length,start+TEXT_PAGE);
        if(start>0&&/[\uDC00-\uDFFF]/.test(text[start]))start--;
        if(end<text.length&&/[\uD800-\uDBFF]/.test(text[end-1]))end--;
        content.textContent=text.slice(start,end);paging.replaceChildren();
        if(row.text==='')paging.append(make('span','The recorded text is an empty string. '));
        if(row.text_truncated===true)paging.append(make('span','This record contains truncated text. '));
        if(row.category==='marker')paging.append(make('span','Text matches a termination marker. This is not verified task completion. '));
        if(count>1){const back=button('Previous text',()=>{offset--;showText()}),more=button('Next text',()=>{offset++;showText()});back.disabled=offset===0;more.disabled=offset===count-1;paging.append(make('span',`Loaded text page ${offset+1}/${count}. `),back,more)}
      }
      fold.append(head,meta,content,paging);let ready=false;
      fold.open=currentState.open.has(row.key);
      if(fold.open){showText();ready=true}
      fold.addEventListener('toggle',()=>{
        if(!fold.isConnected||!active||!checkRun())return;
        if(fold.open){currentState.open.add(row.key);if(!ready){showText();ready=true}}else currentState.open.delete(row.key);
        saveView();
      });
      // Toggle is queued. Preserve the reader's intent even when refresh follows
      // the same click before the queued event has fired.
      head.addEventListener('click',()=>{if(fold.open)currentState.open.delete(row.key);else{currentState.open.add(row.key);if(!ready){showText();ready=true}while(currentState.open.size>4096)currentState.open.delete(currentState.open.values().next().value)}saveView()});
      items.append(fold);
    }
    saveView();
  }
  function open(node){
    if(node?.type!=='agent'||!str(node.id))return;
    checkRun();saveView();ensure();active={id:node.id,type:'agent',name:node.name,attributes:{viewer_agent_member_ids:[...list(node.attributes?.viewer_agent_member_ids)]}};
    viewKey=persistenceKey(active);
    const key=viewKey||JSON.stringify([runScope,node.id]);
    if(!states.has(key))states.set(key,restoreView(viewKey));
    currentState=states.get(key);if(states.size>32)states.delete(states.keys().next().value);
    published=snapshot(active);title.textContent=`Observed history · ${node.name||node.id}`;
    search.value=currentState.query;filter.value=currentState.filter;updates.textContent='';draw();
    if(!dialog.open)dialog.showModal();
  }
  function changed(){if(checkRun()&&active&&dialog?.open&&!equal(published,snapshot(active)))updates.textContent='Updated history is available. The current page and expanded records are pinned until Refresh history is selected.'}
  function nodeChanged(node){checkRun();if(active&&active.id!==node?.id)clear()}
  function buttonFor(node){
    const box=make('section');box.className='execweave-history-entry';
    const count=recordsFor(node).records.reduce((n,e)=>n+list(e.conversation_preview.messages).length,0);
    box.append(button('Browse observed history',()=>open(node)),make('small',`${count} loaded message records; summaries below are not the full history.`));return box;
  }
  window.addEventListener('pagehide',()=>{clear();states.clear()});
  return {buttonFor,nodeChanged,changed,close:clear,open};
}
const historyBrowser=execweaveCreateHistoryBrowser(
  ()=>window.__execweaveCore?.getGraph?.()||window.__execweaveStaticGraph||{},()=>entries
);
window.__execweaveHistoryBrowser=historyBrowser;
""".strip()
