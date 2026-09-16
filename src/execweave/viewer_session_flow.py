"""Session/actor presentation over evidence; never mutates the recorded graph."""

SESSION_FLOW_SCRIPT = r"""
  function execweaveSessionFlow(display,raw){
    const a=n=>n?.attributes||{},r=e=>String(e?.relation||'').toUpperCase();
    const rawNodes=raw?.nodes||[],rawEdges=raw?.edges||[];
    const byId=new Map(rawNodes.map(n=>[n.id,n]));
    const sessions=rawNodes.filter(n=>n.type==='session');
    // A recording can contain multiple roots/sessions. Never choose by array order.
    const roots=rawNodes.filter(n=>n.type==='agent'&&(a(n).agent_role==='root'||a(n).viewer_root===true||a(n).agent_path==='/root'||n.name==='/root'));
    if(!sessions.length||!roots.length)return display;
    let nodes=display.nodes.map(n=>({...n,attributes:{...a(n),...(Number.isFinite(a(n).viewer_flow_rank)&&a(n).viewer_flow_rank>0?{viewer_flow_rank:a(n).viewer_flow_rank+1}:{})}}));
    let edges=display.edges.map(e=>({...e}));
    const observed=e=>e&&e.inferred!==true&&e.viewer_only!==true&&a(e).inferred!==true;
    const unique=items=>{const ids=[...new Set(items.filter(Boolean))];return ids.length===1?ids[0]:null};
    const ownerOf=(id,seen=new Set())=>{
      const n=byId.get(id);if(!n||seen.has(id))return null;
      if(n.type==='agent')return id;
      if(!['provider_session','agent_turn','agent_execution','tool_call','tool_call_observation'].includes(n.type))return null;
      seen=new Set(seen);seen.add(id);
      return unique(rawEdges.filter(e=>e.target===id&&observed(e)).map(e=>ownerOf(e.source,seen)));
    };
    const rootSessions=new Map(),unresolved=[];
    for(const root of roots){
      const direct=rawEdges.filter(e=>e.source===root.id&&sessions.some(s=>s.id===e.target)&&observed(e));
      let sid=unique(direct.map(e=>e.target));
      // The run id is explicit recording membership, not a claim that the provider
      // launched a process. Show that membership with a non-causal display edge.
      if(!sid&&roots.length===1&&sessions.length===1&&sessions[0].id===`session:${raw.session_id}`)sid=sessions[0].id;
      if(!sid){unresolved.push(root.id);continue}
      rootSessions.set(root.id,sid);
      const session=byId.get(sid);
      if(!nodes.some(n=>n.id===sid))nodes.push({...session,attributes:{...a(session)}});
      if(!edges.some(e=>e.source===root.id&&e.target===sid))edges.push({
        id:`viewer:${root.id}--RECORDED_IN_SESSION-->${sid}`,source:root.id,target:sid,
        relation:'RECORDED_IN_SESSION',count:1,viewer_only:true,causal:false,inferred:false,
        attributes:{evidence_node_ids:[root.id,sid],recording_session_id:raw.session_id}
      });
      const sessionNode=nodes.find(n=>n.id===sid);sessionNode.attributes.viewer_flow_rank=1;
      sessionNode.attributes.viewer_owner_agent_id=root.id;
      const rootNode=nodes.find(n=>n.id===root.id);if(rootNode){rootNode.attributes.viewer_flow_rank=0;rootNode.attributes.viewer_session_flow=true}
    }
    if(!rootSessions.size)return display;
    const modelRelations=new Set(['USED_MODEL','INVOKED_MODEL','INVOKES_MODEL','REQUESTED_MODEL','REQUESTS_MODEL_CALL','INFERRED','SWITCHED_MODEL','MODEL_INVOCATION_COMPLETED','MODEL_CALL_RESPONDS']);
    const modelUses=[];
    for(const e of rawEdges){
      if(byId.get(e.target)?.type!=='model'||!modelRelations.has(r(e))||!observed(e))continue;
      const owner=ownerOf(e.source);if(owner)modelUses.push({owner,model:e.target,edge:e});
    }
    const contextByKey=new Map();
    for(const n of nodes)if(a(n).viewer_model_context)contextByKey.set(`${a(n).owner_agent_id}\0${a(n).model_resource_id}`,n.id);
    const ensure=(owner,model)=>{
      const key=`${owner}\0${model}`;let id=contextByKey.get(key);
      const sid=rootSessions.get(owner);if(!sid)return id||null;
      if(!id){
        const resource=byId.get(model);if(!resource)return null;
        id=`viewer:model-context:${encodeURIComponent(owner)}:${encodeURIComponent(model)}`;
        nodes.push({...resource,id,attributes:{...a(resource),viewer_only:true,viewer_model_context:true,owner_agent_id:owner,model_resource_id:model,viewer_flow_rank:2}});
        contextByKey.set(key,id);
      }
      const node=nodes.find(n=>n.id===id);if(node)node.attributes.viewer_flow_rank=2;
      edges=edges.filter(e=>!(e.source===owner&&e.target===id&&r(e)==='MODEL_CONTEXT'));
      if(!edges.some(e=>e.source===sid&&e.target===id))edges.push({
        id:`viewer:${sid}--MODEL_CONTEXT-->${id}`,source:sid,target:id,relation:'MODEL_CONTEXT',
        count:1,viewer_only:true,causal:false,inferred:false,
        attributes:{owner_agent_id:owner,model_resource_id:model,evidence_edge_ids:modelUses.filter(u=>u.owner===owner&&u.model===model).map(u=>u.edge.id)}
      });
      return id;
    };
    for(const use of modelUses)if(rootSessions.has(use.owner))ensure(use.owner,use.model);
    for(const n of [...nodes])if(a(n).viewer_model_context&&rootSessions.has(a(n).owner_agent_id))ensure(a(n).owner_agent_id,a(n).model_resource_id);
    // Replace only the same actor/model's invocation edge. Child usage remains
    // independent; a shared model name cannot steal its owner or session.
    edges=edges.filter(e=>{
      if(!modelRelations.has(r(e)))return true;
      const owner=ownerOf(e.source);
      return !(rootSessions.has(owner)&&contextByKey.has(`${owner}\0${e.target}`));
    });
    const modelAt=(owner,item)=>{
      const hint=a(item).model||a(item).model_name||a(item).codex_model;
      const uses=modelUses.filter(u=>u.owner===owner&&!['MODEL_INVOCATION_COMPLETED','MODEL_CALL_RESPONDS'].includes(r(u.edge)));
      if(hint){const matched=unique(uses.filter(u=>u.model===hint||byId.get(u.model)?.name===hint||a(byId.get(u.model)).model_name===hint).map(u=>u.model));if(matched)return matched;return null}
      const seq=item.first_sequence,stamp=item.first_seen;
      const points=uses.flatMap(u=>[u,...(u.edge.last_sequence!==u.edge.first_sequence||u.edge.last_seen!==u.edge.first_seen?[{...u,edge:{...u.edge,first_sequence:u.edge.last_sequence,first_seen:u.edge.last_seen}}]:[])]);
      // An aggregated model edge may have omitted intervening switches. Without
      // an exact model hint, do not pretend its two endpoints are a complete log.
      if(new Set(uses.map(u=>u.model)).size>1&&uses.some(u=>u.edge.count>2&&(Number.isInteger(seq)?u.edge.first_sequence<seq&&seq<u.edge.last_sequence:u.edge.first_seen<stamp&&stamp<u.edge.last_seen)))return null;
      const timed=points.filter(u=>Number.isInteger(seq)&&Number.isInteger(u.edge.first_sequence)?u.edge.first_sequence<=seq:stamp&&u.edge.first_seen&&u.edge.first_seen<=stamp);
      if(!timed.length)return null;
      timed.sort((x,y)=>Number.isInteger(seq)?(y.edge.first_sequence||0)-(x.edge.first_sequence||0):String(y.edge.first_seen).localeCompare(String(x.edge.first_seen)));
      const best=timed[0].edge;
      return unique(timed.filter(u=>Number.isInteger(seq)?u.edge.first_sequence===best.first_sequence:u.edge.first_seen===best.first_seen).map(u=>u.model));
    };
    // Split call edges by exact occurrence ownership and model. A tool resource
    // can be shared, but its calls must never inherit another actor's model.
    const routedEdges=[];
    for(const e of [...edges]){
      if(!rootSessions.has(e.source)||!['CALLED_TOOL','REQUESTED_TOOL_CALL','REQUESTS_TOOL_CALL','USES_TOOL','PERFORMED_ORCHESTRATION','MESSAGE_SENT'].includes(r(e))){routedEdges.push(e);continue}
      const target=nodes.find(n=>n.id===e.target);if(!target){routedEdges.push(e);continue}
      const occurrences=(e.viewer_tool_call_occurrences||a(target).viewer_tool_call_occurrences||[]).filter(o=>!o.owner_id||o.owner_id===e.source);
      const buckets=new Map();
      for(const item of occurrences.length?occurrences:[null]){
        const native=item&&(item.call_ids||[]).map(id=>byId.get(id)).find(Boolean);
        const model=modelAt(e.source,item?{...item,attributes:a(native)}:{...e,attributes:a(target)});
        if(!buckets.has(model))buckets.set(model,[]);
        if(item)buckets.get(model).push(item);
      }
      for(const [model,items] of buckets){
        const context=model&&ensure(e.source,model);
        const source=context||e.source;
        routedEdges.push({...e,id:context?`viewer:${context}--${r(e)}-->${e.target}:${encodeURIComponent(e.id)}`:e.id,source,
          ...(occurrences.length?{count:items.length,evidence_call_count:items.length,viewer_tool_call_occurrences:items}:{}),
          ...(context?{viewer_only:true,causal:false,viewer_original_edge_id:e.id}:{}),
          attributes:{...a(e),...(context?{model_resource_id:model}: {model_attribution:'not_observed'})}});
      }
    }
    edges=routedEdges;
    // A received message goes back to its actual recipient. The sender's model is
    // a separate invocation, never a substitute destination for the reply.
    for(const n of nodes){
      if(!a(n).viewer_orchestration_action||a(n).orchestration_kind!=='send_input')continue;
      const owner=a(n).owner_agent_id;
      const returns=edges.filter(e=>e.source===n.id&&rootSessions.has(e.target)&&e.target!==owner);
      if(!returns.length)continue;
      edges=edges.map(e=>e.target===n.id&&r(e)==='PERFORMED_ORCHESTRATION'?{...e,source:owner,relation:'SENT_AGENT_MESSAGE',viewer_original_source:e.source}:e);
      n.attributes.viewer_return_message=true;
      delete n.attributes.viewer_flow_rank;
    }
    const usedIds=new Set(edges.flatMap(e=>[e.source,e.target]));
    nodes=nodes.filter(n=>n.type!=='model'||usedIds.has(n.id));
    const known=new Set(nodes.map(n=>n.id));
    edges=edges.filter(e=>known.has(e.source)&&known.has(e.target));
    // Root/session are the forward spine. Return edges remain in the graph but
    // cannot push the root behind its children during layout.
    const ranks=new Map([...rootSessions.keys()].map(id=>[id,0]));
    const queue=[...ranks.keys()];
    while(queue.length){
      const source=queue.shift();
      const outgoing=edges.filter(e=>e.source===source&&!rootSessions.has(e.target));
      outgoing.sort((x,y)=>(r(x)==='MODEL_CONTEXT'?-1:0)-(r(y)==='MODEL_CONTEXT'?-1:0));
      for(const e of outgoing){
        if(ranks.has(e.target))continue;
        ranks.set(e.target,ranks.get(source)+1);queue.push(e.target);
      }
    }
    for(const n of nodes){
      if(ranks.has(n.id))n.attributes.viewer_flow_rank=ranks.get(n.id);
      else if(n.type==='agent')n.attributes.viewer_flow_rank=3;
    }
    return {...display,nodes,edges,node_count:nodes.length,edge_count:edges.length,dashboard_projection:{...display.dashboard_projection,session_flow:true,unresolved_root_sessions:unresolved}};
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
