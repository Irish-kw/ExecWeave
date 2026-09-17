from __future__ import annotations

FOLD_STATE_JS = r"""
let selectedFoldNode=null;
// A deterministic namespace hash, not a cryptographic or identity assertion. The
// store contains booleans only; transcript text is never written to browser storage.
function foldHash(value){let a=2166136261,b=3339675911;for(const ch of String(value)){const n=ch.codePointAt(0);a=Math.imul(a^n,16777619);b=Math.imul(b^n,2246822519)}return(a>>>0).toString(16)+(b>>>0).toString(16)}
function foldScope(node){const coreGraph=window.__execweaveCore?.getGraph?.()||{},staticGraph=window.__execweaveStaticGraph||{},identity=String(coreGraph.session_id||staticGraph.session_id||coreGraph.source_path||staticGraph.source_path||'');return identity?`execweave:folds:v1:${foldHash(identity)}:${foldHash(agentKey(node))}`:null}
function foldStateFor(node){
  const scope=foldScope(node),key=`agent:${foldHash(agentKey(node))}`;
  let state=foldStateByAgent.get(key);
  if(state){if(scope)state.__execweaveScope=scope;return state}
  state=new Map();state.__execweaveScope=scope||null;
  if(scope)try{const data=JSON.parse(localStorage.getItem(scope)||'null');if(data&&data.version===1&&Array.isArray(data.folds))for(const pair of data.folds.slice(-4096)){if(Array.isArray(pair)&&typeof pair[0]==='string'&&typeof pair[1]==='boolean')Map.prototype.set.call(state,pair[0],pair[1])}}catch(_){}
  const get=state.get.bind(state),has=state.has.bind(state),set=state.set.bind(state);
  state.get=raw=>get(foldHash(raw));state.has=raw=>has(foldHash(raw));
  state.set=(raw,value)=>{set(foldHash(raw),Boolean(value));while(state.size>4096)state.delete(state.keys().next().value);const activeScope=state.__execweaveScope;if(activeScope)try{localStorage.setItem(activeScope,JSON.stringify({version:1,folds:[...state]}))}catch(_){}return state};
  foldStateByAgent.set(key,state);return state;
}
function bindFold(fold,state,key,defaultOpen=false){
  fold.dataset.foldKey=key;fold.open=state.has(key)?state.get(key):defaultOpen;
  const initial=fold.open;let touched=false;
  fold.addEventListener('click',event=>{if(event.target.closest?.('summary')?.parentElement===fold){touched=true;state.set(key,!fold.open)}});
  fold.__execweaveRemember=()=>{if(fold.isConnected&&(touched||state.has(key)||fold.open!==initial))state.set(key,fold.open)};
  // Detached details can dispatch a queued toggle after a replacement. It must
  // not overwrite the state of the newly rendered copy.
  fold.addEventListener('toggle',fold.__execweaveRemember);return fold;
}
function rememberVisibleFoldState(){for(const fold of details.querySelectorAll('details[data-fold-key]'))fold.__execweaveRemember?.()}
window.addEventListener('pagehide',rememberVisibleFoldState);
""".strip()
