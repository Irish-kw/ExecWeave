"""Session/actor presentation over evidence; never mutates the recorded graph."""

SESSION_FLOW_SCRIPT = r"""
  function execweaveSessionFlow(display,raw){
    const a=n=>n?.attributes||{},r=e=>String(e?.relation||'').toUpperCase(),enc=encodeURIComponent;
    if(!display||!Array.isArray(display.nodes)||!Array.isArray(display.edges))return display;
    const rawNodes=raw?.nodes||[],rawEdges=raw?.edges||[],sid=raw?.session_id;
    const byId=new Map(rawNodes.map(n=>[n.id,n])),rawEdgeById=new Map(rawEdges.map(e=>[e.id,e]));
    const rawSessions=rawNodes.filter(n=>n.type==='session');
    // The recording session is the run being viewed. Never choose one by array order.
    const R=byId.get(`session:${sid}`)?.type==='session'?`session:${sid}`:(rawSessions.length===1?rawSessions[0].id:null);
    if(!R)return display;
    const recordingId=sid!=null&&sid!==''?String(sid):String(R).replace(/^session:/,'');
    let nodes=display.nodes.map(n=>({...n,attributes:{...a(n)}}));
    let edges=display.edges.map(e=>({...e,attributes:{...a(e)}}));
    const observed=e=>!!e&&e.inferred!==true&&e.viewer_only!==true&&a(e).inferred!==true;
    const unique=items=>{const ids=[...new Set(items.filter(x=>x!=null&&x!==''))];return ids.length===1?ids[0]:null};
    const group=(list,key)=>{const m=new Map();for(const x of list){const k=key(x);if(!m.has(k))m.set(k,[]);m.get(k).push(x)}return m};
    const inRaw=group(rawEdges,e=>e.target),outRaw=group(rawEdges,e=>e.source);
    const incoming=id=>inRaw.get(id)||[],outgoing=id=>outRaw.get(id)||[];
    const OWNED=new Set(['provider_session','agent_turn','agent_execution','tool_call','tool_call_observation']);
    const ownerWalk=(id,seen)=>{
      const n=byId.get(id);if(!n||seen.has(id))return null;
      if(n.type==='agent')return id;
      if(!OWNED.has(n.type))return null;
      seen.add(id);const owner=unique(incoming(id).filter(observed).map(e=>ownerWalk(e.source,seen)));seen.delete(id);
      return owner;
    };
    const owners=new Map(),ownerOf=id=>{if(!owners.has(id))owners.set(id,ownerWalk(id,new Set()));return owners.get(id)};
    let shown=new Map(nodes.map(n=>[n.id,n]));
    const refresh=()=>{shown=new Map(nodes.map(n=>[n.id,n]))};
    const info=id=>({...a(byId.get(id)),...a(shown.get(id))}),typeOf=id=>(shown.get(id)||byId.get(id))?.type;
    const CHILD=new Set(['SPAWNED_AGENT','HAS_CHILD_AGENT_SESSION']);
    const childTargets=new Set([...rawEdges,...edges].filter(e=>CHILD.has(r(e))).map(e=>e.target));
    const isChild=id=>childTargets.has(id)||!!String(info(id).parent_agent_path||'').trim()||['subagent','child'].includes(String(info(id).agent_role||'').toLowerCase());
    const isCarrier=id=>['provider_session_id','provider_conversation_id'].includes(String(info(id).identity_semantics||''));
    const named=(id,name)=>byId.get(id)?.name===name||shown.get(id)?.name===name;
    const rootMarked=id=>{const x=info(id);return x.agent_role==='root'||x.viewer_root===true||x.agent_path==='/root'||(x.root_agent_path==='/root'&&!isChild(id))||named(id,'/root')};
    const eligible=id=>typeOf(id)==='agent'&&rootMarked(id)&&!isCarrier(id)&&!isChild(id);
    const ALIAS={'claude code':'claude','openai codex':'codex','cursor agent':'cursor','cursor-agent':'cursor','agy':'antigravity'};
    const tokens=id=>new Set([a(byId.get(id)).provider,byId.get(id)?.name,a(shown.get(id)).provider].map(x=>String(x||'').trim().toLowerCase()).filter(x=>x&&x!=='/root'&&x!=='root').map(x=>ALIAS[x]||x));
    const sameProduct=(x,y)=>{const t=tokens(y);return [...tokens(x)].some(v=>t.has(v))};
    const rawAgents=rawNodes.filter(n=>n.type==='agent').map(n=>n.id);
    // The launcher of the recording session is its root actor unless the same
    // product exposes an explicit root agent of its own.
    const starts=incoming(R).filter(e=>r(e)==='STARTED_SESSION'&&byId.get(e.source)?.type==='agent');
    const L=unique(starts.filter(observed).map(e=>e.source))||unique(starts.map(e=>e.source));
    const root=L?(unique(rawAgents.filter(id=>id!==L&&eligible(id)&&sameProduct(id,L)))||L):(rawSessions.length===1?unique(rawAgents.filter(eligible)):null);
    if(!root)return display;
    // Without the run id, a lone session joins the flow only on observed membership
    // evidence from the root itself, as before; a session that merely owns it does not.
    if(R!==`session:${sid}`&&!rawEdges.some(e=>e.source===root&&e.target===R&&observed(e)))return display;
    const PROVIDER_ROOTS=new Set(['agent:Claude Code','agent:OpenAI Codex','agent:Codex','agent:Cursor','agent:OpenCode','agent:Antigravity','agent:Ollama','agent:ollama']);
    const ofRoot=id=>sameProduct(id,root)||(!!L&&sameProduct(id,L));
    let D=null;
    if(shown.has(root))D=root;
    else{
      const alias=unique(nodes.filter(n=>n.type==='agent'&&n.name==='/root'&&isCarrier(n.id)&&!isChild(n.id)&&ofRoot(n.id)).map(n=>n.id));
      if(alias)D=alias;
      else{
        const source=byId.get(root);
        nodes.push({...source,name:PROVIDER_ROOTS.has(root)||rootMarked(root)?'/root':source.name,attributes:{...a(source)}});
        D=root;refresh();
      }
    }
    // One actor: the root, its display alias, the launcher and the provider
    // session/conversation carriers of the same product. Children stay separate.
    const members=new Set([root,D,L].filter(Boolean));
    for(const n of rawNodes)if(n.type==='agent'&&isCarrier(n.id)&&!isChild(n.id)&&ofRoot(n.id))members.add(n.id);
    const psIds=new Set();
    for(const m of members)for(const e of outgoing(m))if(byId.get(e.target)?.type==='provider_session')psIds.add(e.target);
    const ownsPs=id=>outgoing(id).some(e=>psIds.has(e.target));
    const unitIds=[...psIds,...[...members].filter(id=>byId.has(id)&&isCarrier(id)&&!ownsPs(id))];
    const pointOf=(x,last)=>({seq:last?(x?.last_sequence??x?.first_sequence):x?.first_sequence,stamp:last?(x?.last_seen||x?.first_seen):x?.first_seen});
    const cmp=(p,q)=>Number.isInteger(p.seq)&&Number.isInteger(q.seq)?p.seq-q.seq:String(p.stamp||'').localeCompare(String(q.stamp||''));
    const startOf=id=>{
      const items=[byId.get(id),...incoming(id),...outgoing(id)].filter(Boolean);
      const seqs=items.map(x=>x.first_sequence).filter(Number.isInteger),stamps=items.map(x=>x.first_seen).filter(Boolean).map(String).sort();
      return {seq:seqs.length?Math.min(...seqs):undefined,stamp:stamps[0]};
    };
    const psidOf=id=>{const n=byId.get(id),x=a(n);return String(x.session_id||x.conversation_id||x.provider_session_id||String(id).split(':').pop()||n?.name||'')};
    const units=unitIds.map(id=>({id,start:startOf(id),psid:psidOf(id)})).sort((p,q)=>cmp(p.start,q.start)||String(p.id).localeCompare(String(q.id)));
    const unitIndex=new Map(units.map((u,k)=>[u.id,k]));
    const carrierUnits=new Map([...members].map(m=>[m,[...new Set([m,...outgoing(m).map(e=>e.target)].filter(id=>unitIndex.has(id)).map(id=>unitIndex.get(id)))]]));
    const nativeUnit=(id,seen=new Set())=>{
      if(id==null||seen.has(id))return null;
      if(unitIndex.has(id))return unitIndex.get(id);
      if(carrierUnits.get(id)?.length===1)return carrierUnits.get(id)[0];
      seen.add(id);let k=null;
      const e=rawEdgeById.get(id);
      if(e){k=nativeUnit(e.source,seen);if(k==null&&OWNED.has(byId.get(e.target)?.type))k=nativeUnit(e.target,seen)}
      else if(OWNED.has(byId.get(id)?.type)){const ks=[...new Set(incoming(id).filter(observed).map(x=>nativeUnit(x.source,seen)).filter(x=>x!=null))];k=ks.length===1?ks[0]:null}
      seen.delete(id);return k;
    };
    const BASIS=['single_session','provider_session_evidence','provider_session_id','session_start_time','sequence_window','unresolved'];
    const TIMED=new Set(['session_start_time','sequence_window','unresolved']);
    const better=(x,y)=>BASIS.indexOf(x)<=BASIS.indexOf(y)?x:y;
    // Which provider session an item belongs to: exact provider evidence first,
    // then the provider session id, and only then the observed time window.
    const unitOf=(point,ids=[])=>{
      if(units.length<=1)return {k:0,basis:'single_session'};
      const ks=[...new Set(ids.map(id=>nativeUnit(id)).filter(k=>k!=null))];
      if(ks.length===1)return {k:ks[0],basis:'provider_session_evidence'};
      const segments=new Set(ids.filter(id=>byId.has(id)||rawEdgeById.has(id)).flatMap(id=>String(id).split(':')));
      const hits=units.map((u,k)=>u.psid&&segments.has(u.psid)?k:null).filter(k=>k!=null);
      if(hits.length===1)return {k:hits[0],basis:'provider_session_id'};
      if(!Number.isInteger(point?.seq)&&!point?.stamp)return null;
      const exact=units.map((u,k)=>u.start.stamp&&u.start.stamp===point.stamp?k:null).filter(k=>k!=null);
      if(exact.length===1)return {k:exact[0],basis:'session_start_time'};
      let k=0;units.forEach((u,i)=>{if(cmp(u.start,point)<=0)k=i});
      return {k,basis:'sequence_window'};
    };
    const sessionIds=units.length?units.map((u,k)=>k===0?R:`viewer:session:${enc(u.id)}`):[R];
    const sessionSet=new Set(sessionIds);
    const USE=new Set(['SERVED_BY_MODEL','INVOKES_MODEL','INVOKED_MODEL','USED_MODEL','REQUESTED_MODEL','ROUTED_TO_MODEL','INFERRED','REQUESTS_MODEL_CALL']);
    const DONE=new Set(['MODEL_INVOCATION_COMPLETED','MODEL_CALL_RESPONDS','MODEL_CALL_FAILED']);
    const isCtx=id=>!!a(shown.get(id)).viewer_model_context;
    const isModel=id=>typeOf(id)==='model'&&!isCtx(id);
    const usesModel=e=>USE.has(r(e))||DONE.has(r(e))||(r(e)==='SWITCHED_MODEL'&&typeOf(e.source)!=='model');
    const uses=new Map(),seenUse=new Set();
    const addUse=e=>{
      const key=`${e.target}\0${e.first_sequence}\0${e.first_seen}\0${r(e)}`;
      if(uses.has(e.id)||seenUse.has(key))return;
      seenUse.add(key);
      uses.set(e.id,{model:e.target,edge:e,done:DONE.has(r(e)),ids:[e.id,...(e.viewer_hidden_bridge_sources||[]),e.source],inferred:!observed(e)});
    };
    for(const e of rawEdges)if(usesModel(e)&&byId.get(e.target)?.type==='model'&&members.has(ownerOf(e.source)))addUse(e);
    for(const e of edges)if(usesModel(e)&&isModel(e.target)&&(e.source===D||members.has(e.source)||psIds.has(e.source)))addUse(e);
    // Framework agents that run inside the recorded program itself are the root's
    // own work: the process it launched hosts them, or the run has no other actor.
    // Their model calls are the root's model contexts, and a framework report and
    // the wire call it caused, under the same model name, are one context.
    const isFramework=id=>typeOf(id)==='agent'&&info(id).conversation_scope==='framework_agent';
    const launched=new Set(outgoing(R).filter(e=>r(e)==='LAUNCHED'&&byId.get(e.target)?.type==='process').map(e=>e.target));
    const hostOf=id=>unique(outgoing(id).filter(e=>r(e)==='CORRELATED_WITH_PROCESS'&&byId.get(e.target)?.type==='process').map(e=>e.target));
    const programOnly=root===L&&!psIds.size&&rawAgents.every(id=>id===L||isFramework(id));
    const hosted=id=>isFramework(id)&&(programOnly||launched.has(hostOf(id)));
    const nameOf=id=>{const n=shown.get(id)||byId.get(id);return String(info(id).model_name||n?.name||'').trim().toLowerCase().replace(/:latest$/,'')};
    const frameworkUses=edges.filter(e=>usesModel(e)&&isFramework(e.source)&&isModel(e.target));
    const wire=[...new Set([...uses.values()].map(u=>u.model))],sameModel=new Map();
    for(const e of frameworkUses){
      if(!hosted(e.source))continue;
      const m=e.target,same=nameOf(m)?unique(wire.filter(w=>w!==m&&nameOf(w)===nameOf(m))):null;
      if(same)sameModel.set(m,same);else addUse(e);
    }
    for(const n of nodes){
      const m=a(n).model_resource_id;
      if(!a(n).viewer_model_context||!members.has(a(n).owner_agent_id)||!m||[...uses.values()].some(u=>u.model===m))continue;
      uses.set(n.id,{model:m,edge:{id:n.id,first_sequence:n.first_sequence,first_seen:n.first_seen,last_sequence:n.last_sequence,last_seen:n.last_seen},done:false,pseudo:true,ids:[n.id],inferred:a(n).inferred===true||n.inferred===true});
    }
    const allUses=[...uses.values()];
    for(const u of allUses){
      u.basis=new Map();
      for(const p of [pointOf(u.edge),pointOf(u.edge,true)]){
        const x=unitOf(p,u.ids)||{k:0,basis:'unresolved'};
        u.basis.set(x.k,u.basis.has(x.k)?better(u.basis.get(x.k),x.basis):x.basis);
      }
      u.units=[...u.basis.keys()];
    }
    // Fold the root's aliases and provider sessions into the root and its sessions.
    const remap=new Map();
    for(const m of members)if(m!==D)remap.set(m,D);
    for(const [id,k] of unitIndex)if(psIds.has(id))remap.set(id,sessionIds[k]);
    const ctxByModel=new Map();
    const memberCtx=nodes.filter(n=>a(n).viewer_model_context&&members.has(a(n).owner_agent_id)&&a(n).model_resource_id);
    for(const [model,list] of group(memberCtx,n=>a(n).model_resource_id)){
      let keep=list.find(n=>a(n).owner_agent_id===D);
      if(!keep){
        const id=`viewer:model-context:${enc(D)}:${enc(model)}`;
        keep=nodes.find(n=>n.id===id);
        if(!keep){keep={...list[0],id,attributes:{...a(list[0])}};nodes.push(keep)}
      }
      keep.attributes.owner_agent_id=D;
      for(const n of list)if(n.id!==keep.id)remap.set(n.id,keep.id);
      ctxByModel.set(model,keep.id);
    }
    const moved=new Set();
    edges=edges.flatMap(e=>{
      const source=remap.get(e.source)??e.source,target=remap.get(e.target)??e.target;
      if(source===e.source&&target===e.target)return [e];
      if(source===target)return [];
      moved.add(e.id);
      return [{...e,source,target,viewer_original_source:e.viewer_original_source??e.source,viewer_original_target:e.viewer_original_target??e.target,...(r(e)==='STARTED_SESSION'?{causal:false}:{})}];
    });
    const merged=new Set(),list=items=>[...new Set(items.flatMap(x=>Array.isArray(x)?x:[]))];
    for(const same of group(edges,e=>`${e.source}\0${r(e)}\0${e.target}`).values()){
      if(same.length<2||!same.some(e=>moved.has(e.id)))continue;
      const base=same.find(e=>!moved.has(e.id))||same[0],rest=same.filter(e=>e!==base),all=[base,...rest];
      const firsts=all.map(e=>pointOf(e)).sort(cmp),lasts=all.map(e=>pointOf(e,true)).sort(cmp);
      Object.assign(base,{
        count:all.reduce((n,e)=>n+(Number(e.count)||1),0),
        ...(all.some(e=>e.evidence_call_count!=null)?{evidence_call_count:all.reduce((n,e)=>n+(Number(e.evidence_call_count)||0),0)}:{}),
        ...(all.some(e=>Array.isArray(e.viewer_tool_call_occurrences))?{viewer_tool_call_occurrences:all.flatMap(e=>e.viewer_tool_call_occurrences||[])}:{}),
        ...(all.some(e=>Array.isArray(e.event_ids))?{event_ids:list(all.map(e=>e.event_ids))}:{}),
        ...(all.some(e=>Array.isArray(e.evidence_ids))?{evidence_ids:list(all.map(e=>e.evidence_ids))}:{}),
        first_sequence:firsts[0].seq??base.first_sequence,first_seen:firsts[0].stamp??base.first_seen,
        last_sequence:lasts.at(-1).seq??base.last_sequence,last_seen:lasts.at(-1).stamp??base.last_seen,
        inferred:all.every(e=>e.inferred===true),viewer_only:all.every(e=>e.viewer_only===true),
        viewer_merged_edge_ids:list([base.viewer_merged_edge_ids||[],rest.map(e=>e.id)]),
      });
      for(const e of rest)merged.add(e);
    }
    edges=edges.filter(e=>!merged.has(e));
    nodes=nodes.filter(n=>!remap.has(n.id)||remap.get(n.id)===n.id);
    for(const n of nodes)for(const key of ['owner_agent_id','model_context_id'])if(remap.has(n.attributes[key]))n.attributes[key]=remap.get(n.attributes[key]);
    const rootNode=nodes.find(n=>n.id===D);
    rootNode.attributes.viewer_agent_member_ids=[...new Set([...(rootNode.attributes.viewer_agent_member_ids||[]),...members])].filter(id=>id!==D);
    rootNode.attributes.viewer_merged_agent_ids=[...members].filter(id=>id!==D&&shown.has(id));
    // Sessions: the recording session holds the first provider session; each later
    // provider session the root opened becomes its own session node.
    if(!nodes.some(n=>n.id===R)){const s=byId.get(R);nodes.push({...s,attributes:{...a(s)}})}
    units.forEach((u,k)=>{
      if(k===0)return;
      const ps=byId.get(u.id);
      nodes.push({id:sessionIds[k],type:'session',name:'Session',first_sequence:u.start.seq,first_seen:u.start.stamp,viewer_only:true,
        attributes:{...a(ps),viewer_only:true,viewer_session_unit_id:u.id}});
    });
    sessionIds.forEach((id,k)=>{
      const n=nodes.find(x=>x.id===id),u=units[k];
      n.name=sessionIds.length===1?'Session':`Session ${k+1}`;
      Object.assign(n.attributes,{viewer_flow_session:true,recording_session_id:recordingId,viewer_owner_agent_id:D,
        ...(u?{provider_session_id:u.psid,viewer_session_unit_id:u.id,viewer_agent_member_ids:[...new Set([...(n.attributes.viewer_agent_member_ids||[]),u.id])]}:{})});
    });
    refresh();
    // Root -> model context -> session. A model switch adds a context from the
    // root that returns to the same session; a new provider session adds a session.
    const firstPoint=list=>list.map(u=>pointOf(u.edge)).sort(cmp)[0]||{};
    const models=[...group(allUses,u=>u.model)].sort(([,x],[,y])=>cmp(firstPoint(x),firstPoint(y))).map(([m])=>m);
    const ctxFor=model=>{
      if(ctxByModel.has(model))return ctxByModel.get(model);
      const resource=shown.get(model)||byId.get(model);if(!resource)return null;
      const id=`viewer:model-context:${enc(D)}:${enc(model)}`;
      if(!shown.has(id)){
        const {viewer_flow_rank,...attributes}=a(resource);
        nodes.push({...resource,id,attributes:{...attributes,viewer_only:true,viewer_model_context:true,owner_agent_id:D,model_resource_id:model}});
      }
      ctxByModel.set(model,id);refresh();return id;
    };
    for(const model of models){
      const ctx=ctxFor(model);if(!ctx)continue;
      const mine=allUses.filter(u=>u.model===model),real=mine.filter(u=>!u.pseudo),first=firstPoint(mine);
      const id=`viewer:${D}--MODEL_CONTEXT-->${ctx}`;
      const old=edges.filter(e=>e.target===ctx&&r(e)==='MODEL_CONTEXT');
      edges=edges.filter(e=>!old.includes(e));
      edges.push({id,source:D,target:ctx,relation:'MODEL_CONTEXT',count:1,viewer_only:true,causal:false,inferred:mine.every(u=>u.inferred),
        first_sequence:first.seq,first_seen:first.stamp,
        attributes:{...Object.assign({},...old.map(a)),owner_agent_id:D,model_resource_id:model,evidence_edge_ids:real.map(u=>u.edge.id)}});
      for(const k of [...new Set(mine.flatMap(u=>u.units))].sort((x,y)=>x-y)){
        const here=mine.filter(u=>u.units.includes(k)),basis=here.map(u=>u.basis.get(k)).reduce(better,'unresolved');
        const calls=here.filter(u=>!u.pseudo&&!u.done).length||here.filter(u=>!u.pseudo).length||1,at=firstPoint(here);
        edges.push({id:`viewer:${ctx}--USED_IN_SESSION-->${sessionIds[k]}`,source:ctx,target:sessionIds[k],relation:'USED_IN_SESSION',
          count:calls,viewer_only:true,causal:false,inferred:TIMED.has(basis),first_sequence:at.seq,first_seen:at.stamp,
          attributes:{model_resource_id:model,recording_session_id:recordingId,...(units[k]?{provider_session_id:units[k].psid}:{}),
            evidence_edge_ids:here.filter(u=>!u.pseudo).map(u=>u.edge.id),viewer_session_attribution:basis}});
      }
    }
    for(const e of edges){
      if(r(e)!=='SWITCHED_MODEL'||!ctxByModel.has(e.target)||!ctxByModel.has(e.source))continue;
      const n=shown.get(ctxByModel.get(e.target));
      n.attributes.viewer_switched_from=[...new Set([...(n.attributes.viewer_switched_from||[]),e.source])];
    }
    edges=edges.filter(e=>!(r(e)==='SWITCHED_MODEL'&&ctxByModel.has(e.target)&&ctxByModel.has(e.source)));
    // One framework agent's requests, responses and failures for one model are one
    // display edge. A root context serves the agent; any other model is called by it.
    const folded=new Set(),counted=xs=>xs.reduce((k,e)=>k+(Number(e.count)||1),0);
    const modelOf=e=>hosted(e.source)&&sameModel.get(e.target)||e.target;
    for(const list of group(frameworkUses,e=>`${e.source}\0${modelOf(e)}`).values()){
      const agent=list[0].source,model=modelOf(list[0]),ctx=hosted(agent)&&ctxByModel.get(model);
      const source=ctx||agent,target=ctx?agent:model,relation=ctx?'USED_BY_AGENT':'CALLED_MODEL';
      const asked=list.filter(e=>!DONE.has(r(e))),failed=list.filter(e=>r(e)==='MODEL_CALL_FAILED'),done=list.filter(e=>DONE.has(r(e))&&!failed.includes(e));
      const firsts=list.map(e=>pointOf(e)).sort(cmp),lasts=list.map(e=>pointOf(e,true)).sort(cmp);
      edges.push({id:`viewer:${source}--${relation}-->${target}`,source,target,relation,count:counted(asked)||counted(done)+counted(failed)||1,
        viewer_only:true,causal:false,inferred:list.every(e=>!observed(e)),
        first_sequence:firsts[0].seq,first_seen:firsts[0].stamp,last_sequence:lasts.at(-1).seq,last_seen:lasts.at(-1).stamp,
        viewer_merged_edge_ids:list.map(e=>e.id),
        attributes:{model_resource_id:model,framework_model_ids:[...new Set(list.map(e=>e.target))],request_count:counted(asked),
          response_count:counted(done),failure_count:counted(failed),evidence_edge_ids:list.map(e=>e.id)}});
      for(const e of list)folded.add(e.id);
    }
    edges=edges.filter(e=>!folded.has(e.id));
    for(const [m,w] of sameModel)if(ctxByModel.has(w)){
      edges=edges.map(e=>e.source===m||e.target===m?{...e,source:e.source===m?ctxByModel.get(w):e.source,target:e.target===m?ctxByModel.get(w):e.target,
        viewer_original_source:e.viewer_original_source??e.source,viewer_original_target:e.viewer_original_target??e.target}:e);
      const ctx=shown.get(ctxByModel.get(w));
      ctx.attributes.viewer_framework_model_ids=[...new Set([...(ctx.attributes.viewer_framework_model_ids||[]),m])];
    }
    edges=edges.filter(e=>!(usesModel(e)&&ctxByModel.has(e.target)&&(e.source===D||sessionSet.has(e.source))));
    for(const [model,ctx] of ctxByModel){
      if(!edges.some(e=>e.source===model))continue;
      const kept=edges.some(e=>e.target===model);
      edges=edges.flatMap(e=>{
        if(e.source!==model)return [e];
        const copy={...e,source:ctx,viewer_original_source:e.viewer_original_source??model};
        return kept?[e,{...copy,id:`viewer:${ctx}--${r(e)}-->${e.target}:${enc(e.id)}`,viewer_only:true,causal:false,viewer_original_edge_id:e.id}]:[copy];
      });
    }
    for(const s of sessionIds){
      const direct=edges.filter(e=>e.source===D&&e.target===s);
      if(edges.some(e=>e.target===s&&r(e)==='USED_IN_SESSION')){
        if(direct.length){
          const n=shown.get(s);n.attributes.viewer_start_edge_ids=[...new Set([...(n.attributes.viewer_start_edge_ids||[]),...direct.map(e=>e.id)])];
          edges=edges.filter(e=>!direct.includes(e));
        }
      }else if(!direct.length)edges.push({
        id:`viewer:${D}--RECORDED_IN_SESSION-->${s}`,source:D,target:s,relation:'RECORDED_IN_SESSION',count:1,
        viewer_only:true,causal:false,inferred:false,
        attributes:{evidence_node_ids:[D,s],recording_session_id:recordingId,model_attribution:'not_observed'}});
    }
    // Tool calls and orchestration hang off the model context that was active at
    // that moment in that provider session. A tool resource may be shared, but a
    // call never inherits another actor's or another session's model.
    const WORK=new Set(['CALLED_TOOL','REQUESTED_TOOL_CALL','REQUESTS_TOOL_CALL','USES_TOOL','PERFORMED_ORCHESTRATION','MESSAGE_SENT']);
    const ownersOk=new Set([...members,...psIds,D]);
    const workUses=allUses.filter(u=>!u.done&&!u.pseudo);
    const modelAt=(k,item)=>{
      const pool=units.length<=1||k==null?workUses:workUses.filter(u=>u.units.includes(k));
      const hint=a(item).model||a(item).model_name||a(item).codex_model;
      if(hint){
        const match=list=>unique(list.filter(u=>u.model===hint||byId.get(u.model)?.name===hint||a(byId.get(u.model)).model_name===hint).map(u=>u.model));
        return match(pool)||match(workUses);
      }
      const at=pointOf(item);
      if(!Number.isInteger(at.seq)&&!at.stamp)return null;
      // An aggregated model edge may have omitted intervening switches. Without
      // an exact model hint, do not pretend its two endpoints are a complete log.
      if(new Set(pool.map(u=>u.model)).size>1&&pool.some(u=>(Number(u.edge.count)||1)>2&&cmp(pointOf(u.edge),at)<0&&cmp(at,pointOf(u.edge,true))<0))return null;
      const points=pool.flatMap(u=>{const f=pointOf(u.edge),l=pointOf(u.edge,true);return cmp(f,l)===0?[[u,f]]:[[u,f],[u,l]]}).filter(([,p])=>cmp(p,at)<=0);
      if(!points.length)return null;
      const best=points.reduce((b,[,p])=>!b||cmp(p,b)>0?p:b,null);
      return unique(points.filter(([,p])=>cmp(p,best)===0).map(([u])=>u.model));
    };
    const routed=[];
    for(const e of edges){
      if(!WORK.has(r(e))||!(e.source===D||sessionSet.has(e.source))){routed.push(e);continue}
      const target=shown.get(e.target);if(!target){routed.push(e);continue}
      const occurrences=(e.viewer_tool_call_occurrences||a(target).viewer_tool_call_occurrences||[]).filter(o=>!o.owner_id||ownersOk.has(o.owner_id));
      const buckets=new Map();
      for(const item of occurrences.length?occurrences:[null]){
        const native=item&&(item.call_ids||[]).map(id=>byId.get(id)).find(Boolean);
        const probe=item?{...item,attributes:a(native)}:{...e,attributes:a(target)};
        const ids=item?[...((item.call_ids||[]).length?item.call_ids:[e.id]),item.owner_id]:[e.id,...(e.viewer_hidden_bridge_sources||[])];
        const model=modelAt(unitOf(pointOf(probe),ids)?.k??null,probe);
        if(!buckets.has(model))buckets.set(model,[]);
        if(item)buckets.get(model).push(item);
      }
      for(const [model,items] of buckets){
        const ctx=model!=null&&ctxByModel.get(model);
        const split=occurrences.length?{count:items.length,evidence_call_count:items.length,viewer_tool_call_occurrences:items}:{};
        routed.push(ctx?{...e,...split,id:`viewer:${ctx}--${r(e)}-->${e.target}:${enc(e.id)}`,source:ctx,viewer_only:true,causal:false,
          viewer_original_edge_id:e.id,viewer_original_source:e.viewer_original_source??e.source,attributes:{...a(e),model_resource_id:model}}
          :{...e,...split,attributes:{...a(e),model_attribution:'not_observed'}});
      }
    }
    edges=routed;
    // Runtime work (processes, files, network, warnings) observed through the
    // session belongs to that session, not directly to the root actor.
    const SESSION_WORK=new Set(['process','file','directory','network_endpoint','observation_warning']);
    const sessionSources=new Set([R,...psIds]);
    edges=edges.map(e=>{
      if(!SESSION_WORK.has(typeOf(e.target))||r(e)==='CORRELATED_WITH_PROCESS')return e;
      const bridged=e.source===D&&!observed(e)&&e.viewer_hidden_bridge===true&&(e.viewer_hidden_bridge_sources||[]).some(id=>sessionSources.has(id));
      if(!bridged&&!(e.source===R&&units.length>1))return e;
      const unit=unitOf(pointOf(e),[e.id,...(e.viewer_hidden_bridge_sources||[])]),basis=unit?.basis||'unresolved',s=sessionIds[unit?.k??0];
      if(s===e.source)return e;
      return {...e,id:`viewer:${s}--${r(e)}-->${e.target}:${enc(e.id)}`,source:s,viewer_original_source:e.viewer_original_source??e.source,
        viewer_original_edge_id:e.id,inferred:e.inferred===true||TIMED.has(basis),attributes:{...a(e),viewer_session_attribution:basis}};
    });
    // A framework agent runs inside its process: the process hosts the agent. A
    // child hosted by its parent's process is already reached through its parent.
    const hostEdges=edges.filter(e=>r(e)==='CORRELATED_WITH_PROCESS'&&isFramework(e.source)&&typeOf(e.target)==='process');
    const hostsOf=group(hostEdges,e=>e.source),parentsOf=group(edges.filter(e=>r(e)==='PARENT_AGENT'),e=>e.target);
    edges=edges.filter(e=>!hostEdges.includes(e));
    for(const [agent,list] of hostsOf){
      const n=shown.get(agent);
      if(n)Object.assign(n.attributes,{viewer_host_process_ids:[...new Set(list.map(e=>e.target))],viewer_host_edge_ids:list.map(e=>e.id)});
      for(const e of list){
        if((parentsOf.get(agent)||[]).some(p=>(hostsOf.get(p.source)||[]).some(x=>x.target===e.target)))continue;
        edges.push({...e,id:`viewer:${e.target}--HOSTS_AGENT-->${agent}`,source:e.target,target:agent,relation:'HOSTS_AGENT',viewer_only:true,causal:false,
          viewer_original_edge_id:e.id,viewer_original_source:e.source,viewer_original_target:e.target,
          attributes:{...a(e),correlation_kind:'logical_agent_to_process',viewer_original_edge_ids:[e.id]}});
      }
    }
    // A framework agent's tool request, its result and its failure are one call edge.
    const TOOL_CALL=new Set(['REQUESTS_TOOL_CALL','TOOL_CALL_RETURNS','TOOL_CALL_FAILED']);
    const toolEdges=edges.filter(e=>TOOL_CALL.has(r(e))&&isFramework(e.source)&&typeOf(e.target)==='tool');
    for(const list of group(toolEdges,e=>`${e.source}\0${e.target}`).values()){
      const {source,target}=list[0],of=rel=>counted(list.filter(e=>r(e)===rel));
      const firsts=list.map(e=>pointOf(e)).sort(cmp),lasts=list.map(e=>pointOf(e,true)).sort(cmp);
      edges.push({id:`viewer:${source}--CALLED_TOOL-->${target}`,source,target,relation:'CALLED_TOOL',
        count:of('REQUESTS_TOOL_CALL')||of('TOOL_CALL_RETURNS')+of('TOOL_CALL_FAILED')||1,viewer_only:true,causal:false,inferred:list.every(e=>!observed(e)),
        first_sequence:firsts[0].seq,first_seen:firsts[0].stamp,last_sequence:lasts.at(-1).seq,last_seen:lasts.at(-1).stamp,
        viewer_merged_edge_ids:list.map(e=>e.id),
        attributes:{request_count:of('REQUESTS_TOOL_CALL'),result_count:of('TOOL_CALL_RETURNS'),failure_count:of('TOOL_CALL_FAILED'),evidence_edge_ids:list.map(e=>e.id)}});
    }
    edges=edges.filter(e=>!toolEdges.includes(e));
    const spawned=new Set(edges.filter(e=>r(e)==='SPAWNED_AGENT').map(e=>e.target));
    edges=edges.filter(e=>!(e.source===D&&r(e)==='HAS_CHILD_AGENT_SESSION'&&spawned.has(e.target)));
    // A received message goes back to its actual recipient. The sender's model is
    // a separate invocation, never a substitute destination for the reply.
    for(const n of nodes){
      if(!a(n).viewer_orchestration_action||a(n).orchestration_kind!=='send_input')continue;
      const owner=a(n).owner_agent_id;
      const returns=edges.filter(e=>e.source===n.id&&e.target===D&&e.target!==owner);
      if(!returns.length)continue;
      edges=edges.map(e=>e.target===n.id&&r(e)==='PERFORMED_ORCHESTRATION'?{...e,source:owner,relation:'SENT_AGENT_MESSAGE',viewer_original_source:e.source}:e);
      n.attributes.viewer_return_message=true;
    }
    const usedIds=new Set(edges.flatMap(e=>[e.source,e.target]));
    nodes=nodes.filter(n=>n.type!=='model'||usedIds.has(n.id));
    nodes=[...new Map(nodes.map(n=>[n.id,n])).values()];refresh();
    edges=[...new Map(edges.filter(e=>shown.has(e.source)&&shown.has(e.target)).map(e=>[e.id,e])).values()];
    // Nothing floats: whatever the root cannot reach is attached to the session it
    // was observed in, as a non-causal membership edge.
    const INFRA=new Set(['model','model_runtime','inference_api','inference_gateway','inference_provider','network_endpoint','network_endpoint_cluster']);
    for(;;){
      const out=group(edges,e=>e.source),reached=new Set([D]),queue=[D];
      while(queue.length)for(const e of out.get(queue.shift())||[])if(!reached.has(e.target)){reached.add(e.target);queue.push(e.target)}
      const left=nodes.filter(n=>!reached.has(n.id));
      if(!left.length)break;
      const targets=new Set(edges.map(e=>e.target));
      let heads=left.filter(n=>!targets.has(n.id));
      if(!heads.length){
        // A closed loop (actors messaging each other): enter it at the actor that
        // was observed first, never at a derived message or resource node.
        const touching=group(edges.flatMap(e=>[[e.source,e],[e.target,e]]),([id])=>id);
        const when=n=>[pointOf(n),...(touching.get(n.id)||[]).map(([,e])=>pointOf(e))].filter(p=>Number.isInteger(p.seq)||p.stamp).sort(cmp)[0];
        const pool=left.some(n=>n.type==='agent')?left.filter(n=>n.type==='agent'):left;
        heads=[[...pool].sort((x,y)=>{const p=when(x),q=when(y);return (!p-!q)||(p&&q?cmp(p,q):0)||String(x.id).localeCompare(String(y.id))})[0]];
      }
      for(const n of heads){
        const unit=unitOf(pointOf(n),[n.id]),basis=unit?.basis||'unresolved',source=sessionIds[unit?.k??0]===n.id?D:sessionIds[unit?.k??0];
        const relation=n.type==='agent'?'SESSION_AGENT':INFRA.has(n.type)?'OBSERVED_INFRASTRUCTURE':'OBSERVED_IN_SESSION';
        edges.push({id:`viewer:${source}--${relation}-->${n.id}`,source,target:n.id,relation,count:1,viewer_only:true,causal:false,
          inferred:TIMED.has(basis),first_sequence:n.first_sequence,first_seen:n.first_seen,
          attributes:{recording_session_id:recordingId,viewer_session_attribution:basis}});
      }
    }
    // Root, contexts and sessions are the forward spine. Return edges stay in the
    // graph as feedback and cannot push the root behind its children in layout.
    const ownCtx=new Set(ctxByModel.values()),feedback=new Set();
    for(const e of edges)if(e.target===D||r(e)==='SUBAGENT_STOPPED'||(sessionSet.has(e.target)&&e.source!==D&&!ownCtx.has(e.source)))feedback.add(e.id);
    // Structure is walked before traffic, so a cycle closes on the message or call
    // that returns to an agent rather than on the edge that placed the agent.
    const SPINE=new Set(['MODEL_CONTEXT','USED_IN_SESSION','RECORDED_IN_SESSION','LAUNCHED','HOSTS_AGENT','PARENT_AGENT',
      'SPAWNED_AGENT','HAS_CHILD_AGENT_SESSION','SESSION_AGENT','SPAWNED']);
    const forward=group(edges.filter(e=>!feedback.has(e.id)),e=>e.source);
    for(const list of forward.values())list.sort((x,y)=>(SPINE.has(r(y))-SPINE.has(r(x)))||cmp(pointOf(x),pointOf(y))||String(x.id).localeCompare(String(y.id)));
    const state=new Map([[D,1]]),stack=[[D,0]];
    while(stack.length){
      const top=stack.at(-1),next=(forward.get(top[0])||[])[top[1]++];
      if(!next){state.set(top[0],2);stack.pop();continue}
      if(state.get(next.target)===1){feedback.add(next.id);continue}
      if(!state.has(next.target)){state.set(next.target,1);stack.push([next.target,0])}
    }
    const sessionRank=ownCtx.size?2:1;
    const floor=id=>id===D?0:ownCtx.has(id)?1:sessionSet.has(id)?sessionRank:sessionRank+1;
    const ranks=new Map(nodes.map(n=>[n.id,floor(n.id)])),indegree=new Map(nodes.map(n=>[n.id,0]));
    const kept=edges.filter(e=>!feedback.has(e.id)&&e.source!==e.target);
    for(const e of kept)indegree.set(e.target,indegree.get(e.target)+1);
    const after=group(kept,e=>e.source),ready=nodes.filter(n=>!indegree.get(n.id)).map(n=>n.id);
    while(ready.length){
      const id=ready.shift();
      for(const e of after.get(id)||[]){
        ranks.set(e.target,Math.max(ranks.get(e.target),ranks.get(id)+1));
        indegree.set(e.target,indegree.get(e.target)-1);
        if(!indegree.get(e.target))ready.push(e.target);
      }
    }
    edges=edges.map(e=>feedback.has(e.id)?{...e,viewer_flow_feedback:true}:e);
    for(const n of nodes){
      n.attributes.viewer_flow_rank=ranks.get(n.id);
      if(n.id===D)n.attributes.viewer_session_flow=true;else delete n.attributes.viewer_session_flow;
    }
    return {...display,nodes,edges,node_count:nodes.length,edge_count:edges.length,
      dashboard_projection:{...display.dashboard_projection,session_flow:true,unresolved_root_sessions:[],viewer_session_root:D}};
  }
  function execweaveExecutionFlowProjection(display,raw){
    return execweaveSessionFlow(execweaveFrameworkMessages(execweaveExecutionFlowBeforeSession(display,raw),raw),raw);
  }
"""


def inject_session_flow(script: str) -> str:
    from .viewer_framework_flow import FRAMEWORK_FLOW_SCRIPT

    seam = "  function execweaveExecutionFlowProjection(display,raw){"
    anchor = "  if(typeof execweaveDashboardGraph==='function'){"
    if script.count(seam) != 1 or script.count(anchor) != 1:
        raise RuntimeError("session flow projection seam changed")
    script = script.replace(seam, "  function execweaveExecutionFlowBeforeSession(display,raw){", 1)
    return script.replace(anchor, FRAMEWORK_FLOW_SCRIPT + SESSION_FLOW_SCRIPT + "\n" + anchor, 1)
