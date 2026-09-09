from __future__ import annotations


_EXACT_SUBTASK_ACTION = """      const evidenceEdges=[...requests,...assignments,...childSessionEdges];
      pushOccurrence(
        'assign_agent_task',owner,[target],assignmentSeed,[subtask.id],
        evidenceEdges.map(edge=>edge.id).filter(Boolean)
      );"""
_EXACT_SUBTASK_ACTION_NORMALIZED = """      const evidenceEdges=[...requests,...assignments,...childSessionEdges];
      const matchingSpawn=occurrences.find(occurrence=>
        occurrence.kind==='spawn_agent'&&occurrence.owner===owner&&occurrence.targets.has(target)
      );
      if(matchingSpawn){
        if(!matchingSpawn.rawNodeIds.includes(subtask.id))matchingSpawn.rawNodeIds.push(subtask.id);
        for(const edgeIdValue of evidenceEdges.map(edge=>edge.id).filter(Boolean)){
          if(!matchingSpawn.rawEdgeIds.includes(edgeIdValue))matchingSpawn.rawEdgeIds.push(edgeIdValue);
        }
      }else{
        pushOccurrence(
          'assign_agent_task',owner,[target],assignmentSeed,[subtask.id],
          evidenceEdges.map(edge=>edge.id).filter(Boolean)
        );
      }"""

_ACTION_TARGET_END = """      for(const target of [...group.targets].sort()){
        addedEdges.push({
          id:`viewer:${id}--${targetRelation}-->${target}`,source:id,target,relation:targetRelation,
          count:1,viewer_only:true,causal:false,inferred:false,
          attributes:{viewer_only:true,projection:'execution_flow',evidence_node_ids:[...group.rawNodeIds],evidence_edge_ids:[...group.rawEdgeIds]}
        });
      }
      for(const rawId of group.rawNodeIds)consumedRawNodes.add(rawId);"""
_ACTION_TARGET_WITH_PAYLOADS = """      for(const target of [...group.targets].sort()){
        addedEdges.push({
          id:`viewer:${id}--${targetRelation}-->${target}`,source:id,target,relation:targetRelation,
          count:1,viewer_only:true,causal:false,inferred:false,
          attributes:{viewer_only:true,projection:'execution_flow',evidence_node_ids:[...group.rawNodeIds],evidence_edge_ids:[...group.rawEdgeIds]}
        });
      }
      // Retarget visible detail edges onto the replacement action, but never onto
      // peers that other flow groups also consume (prevents dangling action ->
      // consumed interaction anchors in Codex reduced-state replay).
      const peerConsumedRawNodeIds=new Set();
      for(const other of groups.values())for(const rawId of other.rawNodeIds)peerConsumedRawNodeIds.add(rawId);
      const detailRelations=new Set([
        'HAS_SUBTASK_PROMPT','HAS_SUBTASK_DESCRIPTION','TARGETS_AGENT_PROFILE',
        'HAS_COMMAND','HAS_WORKING_DIRECTORY','USES_PROFILE','READS_FILE','WRITES_FILE',
        'HAS_FILE','OBSERVED_CONTENT','HAS_TOOL_INPUT','HAS_TOOL_OUTPUT'
      ]);
      for(const rawId of group.rawNodeIds){
        for(const rawEdge of outgoing.get(rawId)||[]){
          const payloadRelation=relation(rawEdge);
          if(!detailRelations.has(payloadRelation))continue;
          const detailTarget=rawEdge.target;
          // Skip retargeting into another group's consumed anchors.
          if(peerConsumedRawNodeIds.has(detailTarget)&&!group.rawNodeIds.has(detailTarget))continue;
          if(!display.nodes.some(node=>node?.id===detailTarget)&&!rawById.has(detailTarget))continue;
          // Do not paint observed_content back onto the canvas; content stays hidden
          // and is exposed via viewer_content_references on the action instead.
          const targetNode=rawById.get(detailTarget)||display.nodes.find(node=>node?.id===detailTarget);
          if(targetNode?.type==='observed_content')continue;
          if(targetNode?.type==='agent_interaction')continue;
          addedEdges.push({
            id:`viewer:${id}--${payloadRelation}-->${detailTarget}:evidence:${encodeURIComponent(rawEdge.id||rawId)}`,
            source:id,target:detailTarget,relation:rawEdge.relation||payloadRelation,
            count:Number.isFinite(rawEdge.count)?rawEdge.count:1,viewer_only:true,causal:false,inferred:false,
            attributes:{viewer_only:true,projection:'execution_flow',evidence_node_ids:[rawId],evidence_edge_ids:[rawEdge.id].filter(Boolean)}
          });
          if(rawEdge.id)consumedRawEdges.add(rawEdge.id);
        }
      }
      for(const rawId of group.rawNodeIds)consumedRawNodes.add(rawId);"""

_EDGE_FILTER = "      if(consumedRawEdges.has(edge.id))return false;"
_EDGE_FILTER_NO_DANGLING = """      if(consumedRawEdges.has(edge.id))return false;
      // Drop edges that still point at consumed presentation nodes, but never use
      // this as a blanket cover for lost evidence — detail retargeting above must
      // have preserved reachable payloads onto the replacement action first.
      if(consumedRawNodes.has(edge.source)||consumedRawNodes.has(edge.target))return false;"""


def normalize_provider_execution_flow(html: str) -> str:
    """Normalize equivalent exact delegation encodings without weakening evidence gates.

    Cursor may report both a direct child-start lifecycle edge and an exact subtask
    assignment for the same child. Those are two observations of one delegation, not two
    orchestration actions. The exact subtask evidence is folded into the existing spawn
    occurrence when both owner and child already match. Providers without a direct spawn
    (for example the validated Antigravity assignment path) keep the assignment action.

    Superseded task/tool-call nodes are presentation-only removals. Any provider-observed
    task prompt/description remains reachable from the replacement orchestration action,
    and no display edge is allowed to reference a consumed node. The raw graph is never
    mutated by this normalizer.
    """
    seams = (
        (_EXACT_SUBTASK_ACTION, _EXACT_SUBTASK_ACTION_NORMALIZED, "exact-subtask fold"),
        (_ACTION_TARGET_END, _ACTION_TARGET_WITH_PAYLOADS, "delegation payload preservation"),
        (_EDGE_FILTER, _EDGE_FILTER_NO_DANGLING, "consumed-node edge filter"),
    )
    for needle, replacement, label in seams:
        if html.count(needle) != 1:
            raise RuntimeError(f"execution-flow provider normalization seam changed: {label}")
        html = html.replace(needle, replacement, 1)
    return html
