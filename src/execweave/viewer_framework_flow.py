"""Framework-only communication projection. Provider graphs pass through unchanged."""

FRAMEWORK_FLOW_SCRIPT = r"""
  function execweaveFrameworkMessages(display,raw){
    const a=n=>n?.attributes||{},r=e=>String(e?.relation||'').toUpperCase();
    const agents=new Map((raw?.nodes||[]).filter(n=>n.type==='agent'&&a(n).conversation_scope==='framework_agent').map(n=>[n.id,n]));
    if(!agents.size)return display;
    const groups=new Map();
    for(const e of raw.edges||[]){
      if(!['MESSAGE_SENT','MESSAGE_RECEIVED'].includes(r(e))||!agents.has(e.source)||!agents.has(e.target)||e.source===e.target||e.inferred===true)continue;
      const key=`${e.source}\0${e.target}`;
      if(!groups.has(key))groups.set(key,{source:e.source,target:e.target,edges:[]});
      groups.get(key).edges.push(e);
    }
    if(!groups.size)return display;
    let nodes=display.nodes.map(n=>({...n,attributes:{...a(n)}}));
    const hidden=new Set(),hiddenNodes=new Set(),added=[];
    // Stream-only messages and callback logs remain in their owner's inspector.
    // They are not delivery events and must not create dangling routing branches.
    const providers=new Set([...agents.values()].map(n=>a(n).provider));
    for(const n of raw.nodes||[]){
      if(n.type!=='message'||!providers.has(a(n).provider))continue;
      const anchors=(raw.edges||[]).filter(e=>(e.target===n.id&&agents.has(e.source)&&r(e)==='MESSAGE_SENT')||(e.source===n.id&&r(e)==='OBSERVED_AT_PROCESS'));
      if(!anchors.length)continue;
      for(const e of anchors){
        const owner=nodes.find(x=>x.id===(e.source===n.id?e.target:e.source));
        if(owner)owner.attributes.viewer_message_evidence=[...(a(owner).viewer_message_evidence||[]),{message_id:n.id,routing_status:'recipient_not_recorded',evidence_edge_id:e.id}];
      }
      hiddenNodes.add(n.id);
    }
    nodes=nodes.filter(n=>!hiddenNodes.has(n.id));
    for(const group of groups.values()){
      const id=`viewer:messages:${encodeURIComponent(group.source)}:${encodeURIComponent(group.target)}`;
      const receiver=agents.get(group.target);
      const evidence=group.edges.map(e=>e.id).filter(Boolean);
      for(const eid of evidence)hidden.add(eid);
      nodes.push({id,type:'message',name:`Messages → ${receiver.name||group.target}`,attributes:{
        viewer_only:true,viewer_framework_messages:true,provider:a(receiver).provider,
        sender_agent_id:group.source,recipient_agent_id:group.target,
        viewer_message_observations:group.edges.map(e=>({relation:e.relation,count:e.count||1,first_seen:e.first_seen,last_seen:e.last_seen,evidence_edge_id:e.id})),
        evidence_edge_ids:evidence,
      }});
      const delivery=group.edges.some(e=>r(e)==='MESSAGE_RECEIVED')?'DELIVERED_AGENT_MESSAGE':'ADDRESSED_TO';
      for(const [source,target,relation] of [[group.source,id,'MESSAGE_SENT'],[id,group.target,delivery]]){
        added.push({id:`viewer:${source}--${relation}-->${target}`,source,target,relation,count:1,viewer_only:true,causal:false,inferred:false,
          first_sequence:Math.min(...group.edges.map(e=>e.first_sequence).filter(Number.isInteger)),
          first_seen:group.edges.map(e=>e.first_seen).filter(Boolean).sort()[0],
          attributes:{evidence_edge_ids:evidence,routing_basis:'framework_explicit_participants'}});
      }
    }
    const edges=display.edges.filter(e=>!hidden.has(e.id)&&!hiddenNodes.has(e.source)&&!hiddenNodes.has(e.target)).concat(added);
    return {...display,nodes,edges,node_count:nodes.length,edge_count:edges.length};
  }
"""
