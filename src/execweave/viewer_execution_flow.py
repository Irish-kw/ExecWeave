from __future__ import annotations

_STARTUP_SEAM = "applyTheme(initialTheme());applyTransform();poll();"

EXECUTION_FLOW_SCRIPT = r"""
(function(){
  const MODEL_RELATIONS=new Set([
    'USED_MODEL','INVOKED_MODEL','INVOKES_MODEL','INFERRED','SERVED_BY_MODEL',
    'SWITCHED_MODEL','MODEL_INVOCATION_COMPLETED'
  ]);
  const DIRECT_ACTION_RELATIONS=new Map([
    ['SPAWNED_AGENT','spawn_agent'],
    ['SPAWNED_SUBAGENT','spawn_agent'],
    ['ASSIGNED_AGENT_TASK','assign_agent_task'],
    ['REQUESTED_SUBTASK','assign_agent_task'],
    ['SENT_AGENT_MESSAGE','send_input'],
    ['CLOSED_AGENT','close_agent'],
  ]);
  const ACTION_RELATION=new Map([
    ['spawn_agent','SPAWNED_AGENT'],
    ['assign_agent_task','ASSIGNED_AGENT_TASK'],
    ['send_input','SENT_AGENT_MESSAGE'],
    ['wait_agent','WAITED_FOR'],
    ['resume_agent','RESUMED_AGENT'],
    ['close_agent','CLOSED_AGENT'],
  ]);
  const ACTION_ALIASES=new Map([
    ['spawn','spawn_agent'],['spawnagent','spawn_agent'],['spawn_agent','spawn_agent'],
    ['spawn_subagent','spawn_agent'],['create_agent','spawn_agent'],['create_subagent','spawn_agent'],
    ['send','send_input'],['sendinput','send_input'],['send_input','send_input'],
    ['sendmessage','send_input'],['send_message','send_input'],['agent_message','send_input'],
    ['wait','wait_agent'],['waitagent','wait_agent'],['wait_agent','wait_agent'],
    ['wait_for_agent','wait_agent'],['wait_for_agents','wait_agent'],
    ['resume','resume_agent'],['resumeagent','resume_agent'],['resume_agent','resume_agent'],
    ['close','close_agent'],['closeagent','close_agent'],['close_agent','close_agent'],
    ['assign_agent_task','assign_agent_task'],['assign_task','assign_agent_task'],
    ['request_subtask','assign_agent_task'],['subtask','assign_agent_task'],
  ]);
  const attrsOf=node=>node&&typeof node.attributes==='object'&&node.attributes?node.attributes:{};
  const relation=edge=>String(edge?.relation||'').toUpperCase();
  const actionName=value=>{
    const text=String(value||'').trim().toLowerCase().replace(/[\s-]+/g,'_');
    return ACTION_ALIASES.get(text)||null;
  };
  const moment=item=>{
    const attrs=attrsOf(item);
    const sequence=Number.isInteger(item?.first_sequence)?item.first_sequence
      :(Number.isInteger(attrs.first_sequence)?attrs.first_sequence:null);
    const stamp=item?.first_seen||attrs.first_seen||attrs.timestamp||null;
    return{
      sequence:sequence,
      stamp:stamp?String(stamp):null,
      id:String(item?.id||''),
    };
  };
  const momentComparable=(left,right)=>{
    if(!left||!right)return false;
    if(left.sequence!==null&&right.sequence!==null)return true;
    if(left.stamp&&right.stamp)return true;
    return false;
  };
  const momentLE=(left,right)=>{
    // Only compare when both ends share a sequence or a timestamp. Mixing kinds
    // (or comparing id fallbacks) falsely orders early actions against future switches.
    if(!momentComparable(left,right))return false;
    if(left.sequence!==null&&right.sequence!==null)return left.sequence<=right.sequence;
    return String(left.stamp)<=String(right.stamp);
  };
  const momentEqual=(left,right)=>{
    if(!momentComparable(left,right))return false;
    if(left.sequence!==null&&right.sequence!==null)return left.sequence===right.sequence;
    return String(left.stamp)===String(right.stamp);
  };
  const provider=node=>String(attrsOf(node).provider||'unknown').toLowerCase();

  function execweaveExecutionFlowProjection(display,raw){
    if(!display||!Array.isArray(display.nodes)||!Array.isArray(display.edges))return display;
    const rawNodes=Array.isArray(raw?.nodes)?raw.nodes:[],rawEdges=Array.isArray(raw?.edges)?raw.edges:[];
    const rawById=new Map(rawNodes.filter(node=>node?.id).map(node=>[node.id,node]));
    const agents=new Map(rawNodes.filter(node=>node?.type==='agent'&&node.id).map(node=>[node.id,node]));
    if(!agents.size)return display;
    const models=new Map(rawNodes.filter(node=>node?.type==='model'&&node.id).map(node=>[node.id,node]));

    const incoming=new Map(),outgoing=new Map();
    for(const edge of rawEdges){
      if(!edge)continue;
      if(!incoming.has(edge.target))incoming.set(edge.target,[]);
      if(!outgoing.has(edge.source))outgoing.set(edge.source,[]);
      incoming.get(edge.target).push(edge);outgoing.get(edge.source).push(edge);
    }
    const aliasToAgent=new Map();
    const rememberAlias=(alias,id)=>{
      if(alias===undefined||alias===null)return;
      const text=String(alias).trim();
      if(!text)return;
      let bucket=aliasToAgent.get(text);
      if(!bucket){bucket=new Set();aliasToAgent.set(text,bucket)}
      bucket.add(id);
    };
    for(const [id,node] of agents){
      const attrs=attrsOf(node);
      rememberAlias(id,id);
      for(const value of [node.name,attrs.agent_id,attrs.thread_id,attrs.agent_path,attrs.child_agent_path,attrs.nickname]){
        rememberAlias(value,id);
      }
    }
    const resolveAgent=value=>{
      if(value===undefined||value===null)return null;
      const text=String(value);
      // Exact canonical id always wins over alias lookup.
      if(agents.has(text))return text;
      const bucket=aliasToAgent.get(text);
      if(!bucket||!bucket.size)return null;
      if(bucket.size===1)return [...bucket][0];
      // Non-unique alias: abstain rather than last-writer-wins.
      return null;
    };
    const uniqueOwner=candidates=>{
      const ids=[...new Set((candidates||[]).filter(Boolean))];
      return ids.length===1?ids[0]:null;
    };
    const ownerForNode=node=>{
      if(!node?.id)return null;
      const direct=[];
      for(const edge of incoming.get(node.id)||[])if(agents.has(edge.source))direct.push(edge.source);
      const directOwner=uniqueOwner(direct);
      if(directOwner)return directOwner;
      if(direct.length)return null; // ambiguous direct owners
      const viaTurn=[];
      for(const edge of incoming.get(node.id)||[]){
        const parent=rawById.get(edge.source);
        if(parent?.type!=='agent_turn')continue;
        for(const grand of incoming.get(parent.id)||[])if(agents.has(grand.source))viaTurn.push(grand.source);
      }
      const turnOwner=uniqueOwner(viaTurn);
      if(turnOwner)return turnOwner;
      if(viaTurn.length)return null;
      const attrs=attrsOf(node);
      const attrOwners=[];
      for(const key of ['owner_agent_id','agent_id','source_agent_id','thread_id','agent_path']){
        const found=resolveAgent(attrs[key]);if(found)attrOwners.push(found);
      }
      return uniqueOwner(attrOwners);
    };
    const agentForAnchor=id=>{
      if(agents.has(id))return id;
      const node=rawById.get(id);
      if(!node)return null;
      return ownerForNode(node);
    };

    const modelNameIndex=new Map();
    const rememberModelAlias=(alias,id)=>{
      if(alias===undefined||alias===null)return;
      const text=String(alias).trim().toLowerCase();
      if(!text)return;
      let bucket=modelNameIndex.get(text);
      if(!bucket){bucket=new Set();modelNameIndex.set(text,bucket)}
      bucket.add(id);
    };
    for(const [id,node] of models){
      const attrs=attrsOf(node);
      rememberModelAlias(id,id);
      for(const value of [node.name,attrs.model,attrs.model_name,attrs.native_name]){
        rememberModelAlias(value,id);
      }
    }
    const modelHintFor=node=>{
      if(!node)return null;
      const attrs=attrsOf(node);
      for(const key of ['model','model_name','codex_model','default_model','provider_model']){
        const value=attrs[key];
        if(value!==undefined&&value!==null&&String(value).trim())return String(value);
      }
      return null;
    };
    const modelIdFromHint=hint=>{
      if(!hint)return null;
      const lower=String(hint).toLowerCase();
      // Exact canonical id first.
      if(models.has(hint))return hint;
      if(models.has(lower))return lower;
      const bucket=modelNameIndex.get(lower);
      if(!bucket||!bucket.size)return null;
      if(bucket.size===1)return [...bucket][0];
      // Ambiguous model name across resources: abstain (no suffix fuzzy match).
      return null;
    };

    const modelEventsByAgent=new Map();
    const addModelEvent=(owner,modelId,item)=>{
      if(!owner||!modelId||!agents.has(owner)||!models.has(modelId))return;
      if(!modelEventsByAgent.has(owner))modelEventsByAgent.set(owner,[]);
      modelEventsByAgent.get(owner).push({modelId,moment:moment(item||{}),edge:item});
    };
    for(const edge of rawEdges){
      if(!agents.has(edge?.source)||!models.has(edge?.target)||!MODEL_RELATIONS.has(relation(edge)))continue;
      addModelEvent(edge.source,edge.target,edge);
    }
    // Hooks and rollout formats often carry the active model on an agent-owned
    // tool/turn/interaction object even when no direct agent -> model edge exists.
    for(const node of rawNodes){
      const owner=ownerForNode(node);
      if(!owner)continue;
      const modelId=modelIdFromHint(modelHintFor(node));
      if(modelId)addModelEvent(owner,modelId,node);
    }
    for(const list of modelEventsByAgent.values())list.sort((a,b)=>{
      // Prefer sequence when both have it; otherwise timestamp; never cross-rank kinds.
      if(a.moment.sequence!==null&&b.moment.sequence!==null){
        return a.moment.sequence-b.moment.sequence;
      }
      if(a.moment.stamp&&b.moment.stamp){
        return String(a.moment.stamp)<String(b.moment.stamp)?-1:String(a.moment.stamp)>String(b.moment.stamp)?1:0;
      }
      if(a.moment.sequence!==null&&b.moment.sequence===null)return -1;
      if(a.moment.sequence===null&&b.moment.sequence!==null)return 1;
      return String(a.moment.id).localeCompare(String(b.moment.id));
    });

    const resolveModel=(owner,item)=>{
      // Item hint is only for the owner/actor side. Callers that resolve a child
      // must pass null as item so an actor tool-call model cannot pollute lookup.
      const hinted=item?modelIdFromHint(modelHintFor(item)):null;
      if(hinted)return hinted;
      const list=modelEventsByAgent.get(owner)||[];
      if(!list.length)return null;
      const at=moment(item||{});
      const eligible=[];
      for(const event of list){
        if(!momentComparable(event.moment,at))continue;
        if(momentLE(event.moment,at))eligible.push(event);
      }
      if(!eligible.length){
        const unique=[...new Set(list.map(event=>event.modelId))];
        return unique.length===1?unique[0]:null;
      }
      // Prefer the latest comparable event; if several tie at the same moment with
      // conflicting models, abstain instead of taking array order.
      let bestMoment=eligible[0].moment;
      for(const event of eligible){
        if(momentLE(bestMoment,event.moment)&&!momentEqual(bestMoment,event.moment))bestMoment=event.moment;
      }
      const tied=eligible.filter(event=>momentEqual(event.moment,bestMoment));
      const unique=[...new Set(tied.map(event=>event.modelId))];
      return unique.length===1?unique[0]:null;
    };

    const occurrences=[];
    const pushOccurrence=(kind,owner,targets,item,rawNodeIds=[],rawEdgeIds=[])=>{
      if(!kind||!owner||!agents.has(owner))return;
      occurrences.push({
        kind,owner,targets:new Set((targets||[]).filter(id=>agents.has(id)&&id!==owner)),
        item:item||{},modelId:resolveModel(owner,item||{}),
        rawNodeIds:[...rawNodeIds],rawEdgeIds:[...rawEdgeIds],
      });
    };

    for(const node of rawNodes){
      if(node?.type!=='agent_interaction'||!node.id)continue;
      const kind=actionName(attrsOf(node).kind||node.name);
      if(!kind)continue;
      const sources=(incoming.get(node.id)||[]).filter(edge=>relation(edge)==='STARTED_AGENT_INTERACTION');
      const targets=(outgoing.get(node.id)||[]).filter(edge=>relation(edge)==='TARGETED_BY_AGENT_INTERACTION');
      const ownerCandidates=sources.map(edge=>agentForAnchor(edge.source));
      const owner=uniqueOwner(ownerCandidates);
      if(!owner)continue;
      // Unknown endpoints keep the occurrence target-less rather than inventing uniqueness.
      const peerIds=[];
      let peersComplete=true;
      for(const edge of targets){
        const peer=agentForAnchor(edge.target);
        if(!peer){peersComplete=false;continue}
        peerIds.push(peer);
      }
      if(targets.length&&!peersComplete&&!peerIds.length)continue;
      pushOccurrence(kind,owner,peerIds,node,[node.id],[...sources,...targets].map(edge=>edge.id).filter(Boolean));
    }

    for(const node of rawNodes){
      if(node?.type!=='agent_message'||!node.id)continue;
      const sent=(incoming.get(node.id)||[]).filter(edge=>relation(edge)==='SENT_AGENT_MESSAGE');
      const delivered=(outgoing.get(node.id)||[]).filter(edge=>relation(edge)==='DELIVERED_AGENT_MESSAGE');
      const owner=uniqueOwner(sent.map(edge=>agentForAnchor(edge.source)));
      if(!owner)continue;
      const peerIds=[];
      let peersComplete=true;
      for(const edge of delivered){
        const peer=agentForAnchor(edge.target);
        if(!peer){peersComplete=false;continue}
        peerIds.push(peer);
      }
      if(delivered.length&&!peersComplete&&!peerIds.length)continue;
      pushOccurrence('send_input',owner,peerIds,node,[node.id],[...sent,...delivered].map(edge=>edge.id).filter(Boolean));
    }

    for(const edge of rawEdges){
      const kind=DIRECT_ACTION_RELATIONS.get(relation(edge));
      if(!kind)continue;
      const owner=agentForAnchor(edge.source),target=agentForAnchor(edge.target);
      if(owner&&target&&owner!==target)pushOccurrence(kind,owner,[target],edge,[],[edge.id].filter(Boolean));
    }

    for(const call of rawNodes){
      if(!['tool_call','tool_call_observation'].includes(String(call?.type||''))||!call.id)continue;
      let tool=null;
      for(const edge of outgoing.get(call.id)||[]){
        if(relation(edge)!=='USES_TOOL')continue;
        const candidate=rawById.get(edge.target);
        if(candidate?.type==='tool'){tool=candidate;break}
      }
      const kind=actionName(attrsOf(call).tool_name||call.name||attrsOf(tool).native_name||tool?.name);
      if(!kind)continue;
      const owner=ownerForNode(call);
      if(!owner)continue;
      const attrs=attrsOf(call),targets=[];
      for(const key of ['target_agent_id','recipient_agent_id','recipient','agent_id']){
        const found=resolveAgent(attrs[key]);if(found&&found!==owner)targets.push(found);
      }
      for(const key of ['target_agent_ids','recipient_agent_ids','recipients','agent_ids']){
        const values=attrs[key];
        if(Array.isArray(values))for(const value of values){const found=resolveAgent(value);if(found&&found!==owner)targets.push(found)}
      }
      pushOccurrence(kind,owner,targets,call,[call.id],[]);
    }

    if(!occurrences.length&&![...modelEventsByAgent.values()].some(list=>list.length))return display;

    const groups=new Map();
    for(const occurrence of occurrences){
      const key=`${occurrence.owner}\u0000${occurrence.kind}\u0000${occurrence.modelId||''}`;
      let group=groups.get(key);
      if(!group){
        group={owner:occurrence.owner,kind:occurrence.kind,modelId:occurrence.modelId,targets:new Set(),rawNodeIds:new Set(),rawEdgeIds:new Set(),occurrences:[]};
        groups.set(key,group);
      }
      for(const id of occurrence.targets)group.targets.add(id);
      for(const id of occurrence.rawNodeIds)group.rawNodeIds.add(id);
      for(const id of occurrence.rawEdgeIds)group.rawEdgeIds.add(id);
      group.occurrences.push(occurrence);
    }

    const roots=[...agents.values()].filter(node=>{
      const attrs=attrsOf(node);
      return attrs.viewer_root===true||attrs.agent_role==='root'||attrs.agent_path==='/root'||attrs.root_agent_path==='/root'||node.name==='/root';
    }).map(node=>node.id);
    const spawnParents=new Map();
    for(const group of groups.values()){
      if(group.kind!=='spawn_agent')continue;
      for(const child of group.targets)if(!spawnParents.has(child))spawnParents.set(child,group.owner);
    }
    if(!roots.length){
      const candidates=[...agents.keys()].filter(id=>!spawnParents.has(id));
      if(candidates.length)roots.push(...candidates.sort());
    }
    const agentRank=new Map(roots.map(id=>[id,0]));
    for(let pass=0;pass<agents.size+2;pass++){
      let changed=false;
      for(const group of groups.values()){
        if(group.kind!=='spawn_agent'||!agentRank.has(group.owner))continue;
        const modelOffset=group.modelId?1:0,actionRank=agentRank.get(group.owner)+modelOffset+1;
        for(const child of group.targets){
          const wanted=actionRank+1,current=agentRank.get(child);
          if(current===undefined||wanted<current){agentRank.set(child,wanted);changed=true}
        }
      }
      if(!changed)break;
    }
    for(const id of agents.keys())if(!agentRank.has(id))agentRank.set(id,0);

    const addedNodes=[],addedEdges=[],contextIds=new Map(),contextifiedModels=new Set();
    const contextId=(owner,modelId)=>`${owner}\u0000${modelId}`;
    const ensureContext=(owner,modelId)=>{
      if(!modelId||!models.has(modelId))return null;
      const key=contextId(owner,modelId);
      if(contextIds.has(key))return contextIds.get(key);
      const model=models.get(modelId),id=`viewer:model-context:${encodeURIComponent(owner)}:${encodeURIComponent(modelId)}`;
      const rank=(agentRank.get(owner)||0)+1;
      const node={
        id,type:'model',name:model.name||attrsOf(model).model||modelId,
        attributes:{...attrsOf(model),viewer_only:true,viewer_model_context:true,owner_agent_id:owner,model_resource_id:modelId,viewer_flow_rank:rank,provider:attrsOf(model).provider||provider(agents.get(owner))}
      };
      addedNodes.push(node);
      addedEdges.push({
        id:`viewer:${owner}--MODEL_CONTEXT-->${id}`,source:owner,target:id,relation:'MODEL_CONTEXT',
        count:1,viewer_only:true,causal:false,inferred:false,
        attributes:{viewer_only:true,projection:'execution_flow',model_resource_id:modelId}
      });
      contextIds.set(key,id);contextifiedModels.add(modelId);return id;
    };

    for(const [owner,list] of modelEventsByAgent){
      for(const modelId of new Set(list.map(item=>item.modelId)))ensureContext(owner,modelId);
    }

    const consumedRawNodes=new Set(),consumedRawEdges=new Set(),consumedCallIds=new Set();
    const contentRefFromNode=(contentNode,edge,direction)=>{
      const attrs=attrsOf(contentNode);
      const viewer=attrs.viewer_content&&typeof attrs.viewer_content==='object'?attrs.viewer_content:{};
      return{
        content_node_id:contentNode.id,
        raw_node_id:contentNode.id,
        raw_edge_id:edge?.id||null,
        relation:edge?.relation||null,
        direction:direction||null,
        sha256:viewer.sha256||attrs.sha256||attrs.content_sha256||null,
        path:viewer.safe_relative_path||attrs.path||attrs.content_path||null,
        size_bytes:viewer.size_bytes??attrs.size_bytes??attrs.content_size_bytes??null,
        media_type:viewer.media_type||attrs.media_type||attrs.content_media_type||null,
        content_kind:viewer.content_kind||attrs.content_kind||contentNode.name||null,
      };
    };
    for(const group of groups.values()){
      const context=group.modelId?ensureContext(group.owner,group.modelId):null;
      const source=context||group.owner;
      const baseRank=agentRank.get(group.owner)||0;
      const actionRank=baseRank+(context?2:1);
      const id=`viewer:orchestration:${encodeURIComponent(group.owner)}:${encodeURIComponent(group.modelId||'unresolved')}:${group.kind}`;
      const contentRefs=[];
      const toolCallOccurrences=[];
      for(const rawId of group.rawNodeIds){
        const rawNode=rawById.get(rawId);
        if(!rawNode)continue;
        if(String(rawNode.type||'')==='observed_content'){
          contentRefs.push(contentRefFromNode(rawNode,null,'node'));
          continue;
        }
        for(const edge of [...(outgoing.get(rawId)||[]),...(incoming.get(rawId)||[])]){
          const peerId=edge.source===rawId?edge.target:edge.source;
          const peer=rawById.get(peerId);
          if(peer?.type!=='observed_content')continue;
          const direction=edge.source===rawId?'outgoing':'incoming';
          const ref=contentRefFromNode(peer,edge,direction);
          if(!contentRefs.some(item=>item.content_node_id===ref.content_node_id&&item.raw_edge_id===ref.raw_edge_id)){
            contentRefs.push(ref);
          }
        }
        if(['tool_call','tool_call_observation'].includes(String(rawNode?.type||''))){
          consumedCallIds.add(rawId);
          const attrs=attrsOf(rawNode);
          let toolId=null;
          for(const edge of outgoing.get(rawId)||[]){
            if(relation(edge)==='USES_TOOL'||relation(edge)==='RESOLVED_TOOL'){toolId=edge.target;break}
          }
          toolCallOccurrences.push({
            invocation_id:rawId,
            owner_id:group.owner,
            tool_id:toolId,
            call_ids:[rawId],
            first_sequence:Number.isInteger(rawNode.first_sequence)?rawNode.first_sequence:null,
            last_sequence:Number.isInteger(rawNode.last_sequence)?rawNode.last_sequence:null,
            first_seen:rawNode.first_seen||null,
            last_seen:rawNode.last_seen||null,
            input:attrs.arguments??attrs.args??attrs.tool_input??attrs.input??attrs.parameters??attrs.request??null,
            output:attrs.output??attrs.result??attrs.tool_output??attrs.response??null,
            content_references:contentRefs.filter(ref=>ref.raw_edge_id&&[...(outgoing.get(rawId)||[]),...(incoming.get(rawId)||[])].some(edge=>edge.id===ref.raw_edge_id)),
          });
        }
      }
      addedNodes.push({
        id,type:'tool',name:group.kind,
        attributes:{
          viewer_only:true,viewer_orchestration_action:true,orchestration_kind:group.kind,
          owner_agent_id:group.owner,model_context_id:context,model_resource_id:group.modelId,
          viewer_flow_rank:actionRank,provider:provider(agents.get(group.owner)),
          evidence_node_ids:[...group.rawNodeIds].sort(),evidence_edge_ids:[...group.rawEdgeIds].sort(),
          viewer_occurrence_count:group.occurrences.length,
          viewer_model_context_unresolved:!context||undefined,
          viewer_content_references:contentRefs,
          viewer_tool_call_occurrences:toolCallOccurrences,
        }
      });
      addedEdges.push({
        id:`viewer:${source}--PERFORMED_ORCHESTRATION-->${id}`,source,target:id,
        relation:'PERFORMED_ORCHESTRATION',count:group.occurrences.length,viewer_only:true,causal:false,inferred:false,
        attributes:{viewer_only:true,projection:'execution_flow',orchestration_kind:group.kind,evidence_node_ids:[...group.rawNodeIds],evidence_edge_ids:[...group.rawEdgeIds]}
      });
      const targetRelation=ACTION_RELATION.get(group.kind)||'TARGETED_AGENT';
      for(const target of [...group.targets].sort()){
        addedEdges.push({
          id:`viewer:${id}--${targetRelation}-->${target}`,source:id,target,relation:targetRelation,
          count:1,viewer_only:true,causal:false,inferred:false,
          attributes:{viewer_only:true,projection:'execution_flow',evidence_node_ids:[...group.rawNodeIds],evidence_edge_ids:[...group.rawEdgeIds]}
        });
      }
      for(const rawId of group.rawNodeIds)consumedRawNodes.add(rawId);
      for(const rawId of group.rawEdgeIds)consumedRawEdges.add(rawId);
    }

    // Shared tool definitions / model resources stay unless every remaining USES_TOOL
    // into them came from consumed calls. Consuming one owner's call must not wipe the
    // shared definition for other owners or unresolved calls.
    const hideToolDefs=new Set();
    for(const [toolId,node] of [...rawById].filter(([,n])=>n?.type==='tool')){
      const uses=(incoming.get(toolId)||[]).filter(edge=>['USES_TOOL','RESOLVED_TOOL'].includes(relation(edge)));
      if(!uses.length)continue;
      const fromCalls=uses.filter(edge=>{
        const src=rawById.get(edge.source);
        return ['tool_call','tool_call_observation'].includes(String(src?.type||''));
      });
      if(!fromCalls.length)continue;
      if(fromCalls.every(edge=>consumedCallIds.has(edge.source)))hideToolDefs.add(toolId);
    }

    const flowNodes=display.nodes.map(node=>{
      if(node?.type!=='agent'||!agentRank.has(node.id))return node;
      return{...node,attributes:{...attrsOf(node),viewer_flow_rank:agentRank.get(node.id)}};
    });

    const modelRelation=edge=>MODEL_RELATIONS.has(relation(edge))||relation(edge)==='MODEL_CONTEXT';
    const orchestrationRelation=edge=>DIRECT_ACTION_RELATIONS.has(relation(edge));
    let nodes=flowNodes.filter(node=>!consumedRawNodes.has(node.id)&&!hideToolDefs.has(node.id));
    let edges=display.edges.filter(edge=>{
      if(consumedRawEdges.has(edge.id))return false;
      // Keep unconsumed inferred / provider orchestration evidence. Only hide edges
      // that were actually folded into an occurrence (tracked via consumedRawEdges).
      if(orchestrationRelation(edge)&&agents.has(edge.source)&&agents.has(edge.target)){
        return !consumedRawEdges.has(edge.id);
      }
      if(hideToolDefs.has(edge.source)||hideToolDefs.has(edge.target))return false;
      if(contextifiedModels.has(edge.target)&&agents.has(edge.source)&&modelRelation(edge))return false;
      return true;
    });

    for(const modelId of contextifiedModels){
      const remaining=edges.filter(edge=>edge.source===modelId||edge.target===modelId);
      if(!remaining.length)nodes=nodes.filter(node=>node.id!==modelId);
    }

    const known=new Set(nodes.map(node=>node.id));
    for(const node of addedNodes)if(!known.has(node.id)){known.add(node.id);nodes.push(node)}
    const edgeIds=new Set(edges.map(edge=>edge.id));
    for(const edge of addedEdges)if(!edgeIds.has(edge.id)){edgeIds.add(edge.id);edges.push(edge)}

    return{
      ...display,nodes,edges,node_count:nodes.length,edge_count:edges.length,
      dashboard_projection:{
        ...(display.dashboard_projection||{}),
        execution_flow_projection:true,
        model_context_node_count:addedNodes.filter(node=>attrsOf(node).viewer_model_context).length,
        orchestration_action_node_count:addedNodes.filter(node=>attrsOf(node).viewer_orchestration_action).length,
        unique_agent_node_count:nodes.filter(node=>node.type==='agent').length,
      }
    };
  }

  if(typeof execweaveDashboardGraph==='function'){
    const execweaveDashboardGraphBeforeExecutionFlow=execweaveDashboardGraph;
    execweaveDashboardGraph=function(data){
      return execweaveExecutionFlowProjection(execweaveDashboardGraphBeforeExecutionFlow(data),data);
    };
  }

  function execweaveApplyExecutionFlowColumns(topo){
    if(!topo?.spec||typeof nodeById==='undefined')return topo;
    const ranked=[];
    for(const [id,spec] of topo.spec){
      const node=nodeById.get(id),rank=Number(attrsOf(node).viewer_flow_rank);
      if(!node||!Number.isFinite(rank))continue;
      ranked.push({id,spec,rank});
    }
    if(ranked.length<2)return topo;
    const widthByRank=new Map();
    for(const item of ranked)widthByRank.set(item.rank,Math.max(widthByRank.get(item.rank)||160,typeof execweaveWidthOf==='function'?execweaveWidthOf(item.id):160));
    const ranks=[...widthByRank.keys()].sort((a,b)=>a-b);
    const minRank=ranks[0],rootItems=ranked.filter(item=>item.rank===minRank);
    let x=Math.min(...rootItems.map(item=>item.spec.x));
    if(!Number.isFinite(x))x=0;
    const xByRank=new Map();
    for(const rank of ranks){
      xByRank.set(rank,x);
      x+=(widthByRank.get(rank)||160)+72;
    }
    for(const item of ranked){
      item.spec.x=xByRank.get(item.rank);
      item.spec.flowRank=item.rank;
    }
    if(typeof execweaveRecomputePorts==='function')execweaveRecomputePorts(topo);
    return topo;
  }
  window.execweaveApplyExecutionFlowColumns=execweaveApplyExecutionFlowColumns;

  if(typeof execweaveBuildTopology==='function'){
    const execweaveBuildTopologyBeforeExecutionFlow=execweaveBuildTopology;
    execweaveBuildTopology=function(){
      return execweaveApplyExecutionFlowColumns(execweaveBuildTopologyBeforeExecutionFlow());
    };
  }

  window.__execweaveExecutionFlow={
    version:1,
    project:execweaveExecutionFlowProjection,
    applyColumns:execweaveApplyExecutionFlowColumns,
  };
})();
"""


def inject_execution_flow(html: str) -> str:
    """Add provider-neutral model/orchestration/agent presentation without changing evidence."""

    if html.count(_STARTUP_SEAM) != 1:
        raise RuntimeError("execution-flow startup seam changed")
    return html.replace(_STARTUP_SEAM, EXECUTION_FLOW_SCRIPT + "\n" + _STARTUP_SEAM, 1)
