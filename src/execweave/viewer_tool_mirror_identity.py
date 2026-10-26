"""Exact invocation witnesses for an otherwise unlinked tool observation.

A mirrored provider observation is not a second invocation. It may corroborate a
proved call only through an explicit scoped native ID or conversation/step/tool
identity. An ambiguous or dangling ownership path is never overridden.
"""

TOOL_MIRROR_SCRIPT = r"""
  function mirrorIdentity(node){
    const identity=scope(node),a=node?.attributes||{};
    if(!identity||!identity.provider)return null;
    const values=keys=>sorted(keys.map(k=>text(a[k])).filter(Boolean));
    const native=values(['tool_use_id','tool_call_id','call_id','provider_call_id','invocation_id']);
    const rawSteps=values(['step_index','antigravity_step_index','stepIdx']);
    if(native.length>1||rawSteps.some(v=>!/^\d+$/.test(v)))return null;
    const steps=sorted(rawSteps.map(v=>String(Number(v))));
    if(steps.length>1||steps.some(v=>!Number.isSafeInteger(Number(v))))return null;
    const toolNames=values(['tool_name','native_name']).map(v=>v.toLowerCase());
    if(new Set(toolNames).size>1)return null;
    const tool=toolNames[0]||text(node?.name).toLowerCase();
    return{identity,native:native[0]||'',step:steps[0]??null,tool};
  }
  function mirrorWitness(observation,anchor){
    const a=mirrorIdentity(observation),b=mirrorIdentity(anchor);
    if(!a||!b||a.identity.provider!==b.identity.provider)return null;
    const identity=joinScope(a.identity,b.identity);if(!identity)return null;
    if(!a.tool||a.tool!==b.tool)return null;
    if(a.native&&b.native&&a.native!==b.native)return null;
    if(a.step!==null&&b.step!==null&&a.step!==b.step)return null;
    const commonScope=['conversation','session','run'].some(k=>a.identity[k]&&a.identity[k]===b.identity[k]);
    if(a.native&&a.native===b.native&&commonScope){
      return{kind:'scoped-native-invocation',identity,native:a.native,tool:a.tool};
    }
    if(a.identity.conversation&&a.identity.conversation===b.identity.conversation&&a.step!==null&&a.step===b.step){
      return{kind:'provider-conversation-step-tool',identity,step:a.step,tool:a.tool};
    }
    return null;
  }
  function proveToolOccurrence(ids,presented,visible,byId,incoming,rawEdges,aliases){
    const proofs=[],anchors=[],pending=[];
    if(!ids.length)return null;
    for(const id of [...ids].sort()){
      const call=byId.get(id);if(!call)return null;
      const leaves=rawEdges.filter(edge=>edge.source===id&&aliases.get(edge.target)===presented.target);
      const candidates=leaves.length?leaves:[{source:id,target:presented.target}];
      let unresolved=false;
      for(const leaf of candidates){
        const proof=supportFor(leaf,visible,byId,incoming,!leaves.length);
        if(!proof.reason&&proof.sources.length===1&&proof.sources[0]===presented.source){proofs.push(proof);continue;}
        if(call.type==='tool_call_observation'&&proof.reason==='unattributed_observation'&&!(incoming.get(id)||[]).length){
          unresolved=true;break;
        }
        return null;
      }
      if(unresolved)pending.push(call);else anchors.push(call);
    }
    if(!proofs.length)return null;
    for(const observation of pending){
      const matches=anchors.map(anchor=>({anchor,witness:mirrorWitness(observation,anchor)})).filter(v=>v.witness);
      if(!matches.length)return null;
      const {anchor,witness}=matches[0];
      const related=rawEdges.filter(e=>e.source===observation.id||e.target===observation.id);
      let identity=witness.identity;
      for(const e of related){identity=joinScope(identity,scope(e));if(!identity)return null;}
      // A contradictory explicit tool target is not a harmless mirror detail.
      if(related.some(e=>e.source===observation.id&&byId.get(e.target)?.type==='tool'&&aliases.get(e.target)!==presented.target))return null;
      const proofIdentity=joinScope(identity,proofs.find(p=>p.nodes.includes(anchor.id))?.identity);
      if(!proofIdentity)return null;
      proofs.push({sources:[presented.source],edges:related,nodes:sorted([observation.id,anchor.id,
        presented.target,...related.flatMap(e=>[e.source,e.target])]),missingSources:[],identity:proofIdentity,reason:'',
        mirror:{observation_id:observation.id,proved_call_id:anchor.id,...witness,viewer_only:true,inferred:true,causal:false}});
    }
    return proofs;
  }
""".strip()
