from __future__ import annotations

from . import _dashboard_shell_base as _base
from . import viewer_projection_base as _viewer_projection_base
from .viewer_semantic_projection import project_provider_neutral_viewer_graph


def _route_bundle_edges_on_ordered_rails(html: str) -> str:
    """Spread bundle members onto deterministic rails instead of one shared trunk.

    The aggregate bundle semantics stay unchanged: members retain the same bundle key,
    representative label, styling, and M-H-V-H route family. Only the vertical rail X
    coordinate differs by source row and target slot, which keeps dense multi-agent
    traffic traceable and prevents stacked trunks from turning into a visual braid.
    """
    needle = "trunkX=Math.max(sx+54,tx-82-(bundle.groupIndex%6)*24);"
    replacement = (
        "sourceRail=Math.max(0,Number(sourceSpec.order)||0),"
        "targetRail=Math.max(0,(Number(targetSpec.rank)||0)-(Number(sourceSpec.rank)||0)-1)"
        "+Math.max(0,Number(targetSpec.order)||0),"
        "railDistance=20+sourceRail*25+targetRail*10,"
        "trunkX=tx>=sx?Math.min(tx,sx+railDistance):Math.max(tx,sx-railDistance);"
    )
    if needle not in html:
        raise RuntimeError("bundle routing seam changed")
    return html.replace(needle, replacement, 1)


def _start_in_fit_camera_mode(html: str) -> str:
    """Follow live graph growth until the user explicitly takes the camera.

    A live run can first render a tiny process-only snapshot and add file/network nodes
    later. If that first automatic fit is followed by Manual mode, the tiny-snapshot
    transform is frozen and later nodes can land under the inspector. Starting in Fit
    keeps incremental growth in the graph viewport; existing pan/zoom handling still
    switches to Manual on the user's first camera action.
    """
    seams = (
        (
            "protectedMode=false,cameraMode='manual',latestNodeId=null",
            "protectedMode=false,cameraMode='fit',latestNodeId=null",
            "camera mode state seam changed",
        ),
        (
            '<button type="button" data-camera="manual" class="active">Manual</button><button type="button" data-camera="fit">Fit graph</button>',
            '<button type="button" data-camera="manual">Manual</button><button type="button" data-camera="fit" class="active">Fit graph</button>',
            "camera control markup seam changed",
        ),
        (
            '<strong id="camera-label">Manual</strong>',
            '<strong id="camera-label">Fit graph</strong>',
            "camera label seam changed",
        ),
    )
    for old, new, error in seams:
        if html.count(old) != 1:
            raise RuntimeError(error)
        html = html.replace(old, new, 1)
    return html


def _avoid_camera_fit_starvation(html: str) -> str:
    """Guarantee a Fit pass during a dense live-delta burst.

    The base scheduler debounces every delta by clearing the pending camera timer.
    Native Windows telemetry can arrive faster than the 180 ms delay for long enough
    that the fit never executes, leaving newly added endpoint nodes underneath the
    inspector. Ordinary deltas now keep the first pending timer. Explicit force
    scheduling can still replace it, preserving resize/resync behavior.
    """
    needle = (
        "function scheduleCamera(force=false){clearTimeout(cameraTimer);"
        "cameraTimer=setTimeout(()=>{if(cameraMode==='fit')fit(true);"
        "else if(cameraMode==='follow')followLatest(force);updateJumpLatest()},180)}"
    )
    replacement = (
        "function scheduleCamera(force=false){if(cameraTimer!==null){"
        "if(!force)return;clearTimeout(cameraTimer)}cameraTimer=setTimeout(()=>{"
        "cameraTimer=null;if(cameraMode==='fit')fit(true);"
        "else if(cameraMode==='follow')followLatest(force);updateJumpLatest()},180)}"
    )
    if html.count(needle) != 1:
        raise RuntimeError("camera scheduler seam changed")
    return html.replace(needle, replacement, 1)


def _defer_camera_takeover_until_node_drag(html: str) -> str:
    """Do not freeze Fit mode merely because a node was clicked.

    The drag affordance historically called ``userTookCamera`` on pointer-down, before
    it knew whether the reader intended to drag. A normal click could therefore switch
    Fit to Manual and stop an in-flight fit animation. Fast native Windows telemetry
    exposed the race: Process/File inspection could freeze the graph before a Network
    endpoint had moved clear of the inspector. Keep pointer capture on press, but only
    take the camera and move the node after the existing 3 px drag threshold is crossed.
    """
    pointer_down = """    event.stopPropagation();userTookCamera();stopAnimation();const point=execweaveGraphPoint(event);
    execweaveNodeDrag={id:node.id,pointerId:event.pointerId,dx:point.x-current.x,dy:point.y-current.y,startX:event.clientX,startY:event.clientY,moved:false};
    group.classList.add('dragging');try{group.setPointerCapture(event.pointerId)}catch(_){}"""
    pointer_down_replacement = """    event.stopPropagation();
    execweaveNodeDrag={id:node.id,pointerId:event.pointerId,originX:current.x,originY:current.y,startX:event.clientX,startY:event.clientY,moved:false};
    try{group.setPointerCapture(event.pointerId)}catch(_){}"""
    pointer_move = """    if(Math.abs(event.clientX-drag.startX)>3||Math.abs(event.clientY-drag.startY)>3)drag.moved=true;
    const point=execweaveGraphPoint(event),next={x:point.x-drag.dx,y:point.y-drag.dy};positions.set(node.id,next);group.setAttribute('transform',`translate(${next.x} ${next.y})`);execweaveRefreshIncidentEdges(node.id);updateJumpLatest();"""
    pointer_move_replacement = """    if(!drag.moved){
      if(Math.abs(event.clientX-drag.startX)<=3&&Math.abs(event.clientY-drag.startY)<=3)return;
      drag.moved=true;userTookCamera();stopAnimation();group.classList.add('dragging');
    }
    const scale=Math.max(.0001,Number(transform.scale)||1),next={x:drag.originX+(event.clientX-drag.startX)/scale,y:drag.originY+(event.clientY-drag.startY)/scale};positions.set(node.id,next);group.setAttribute('transform',`translate(${next.x} ${next.y})`);execweaveRefreshIncidentEdges(node.id);updateJumpLatest();"""
    if html.count(pointer_down) != 1:
        raise RuntimeError("node drag pointer-down seam changed")
    if html.count(pointer_move) != 1:
        raise RuntimeError("node drag pointer-move seam changed")
    html = html.replace(pointer_down, pointer_down_replacement, 1)
    return html.replace(pointer_move, pointer_move_replacement, 1)


def _preserve_readable_initial_camera(html: str) -> str:
    """Keep first paint readable without changing the explicit whole-graph Fit action.

    The initial snapshot historically called the same whole-graph ``fit`` routine as
    the user-facing Fit button. Dense graphs can therefore arrive below readable
    screen-space size even though the camera is otherwise in manual mode. Give only
    the automatic first fit a 0.5 scale floor; an explicit Fit still defaults to the
    established 0.07 floor so the full graph remains available as an overview.
    """
    signature = "function fit(animate=true){"
    if html.count(signature) != 1:
        raise RuntimeError("camera fit signature seam changed")
    html = html.replace(signature, "function fit(animate=true,minScale=.07){", 1)

    scale = (
        "scale=Math.min(1.2,Math.max(.07,Math.min((box.width-72)/w,"
        "(box.height-72)/h))),next="
    )
    scale_with_floor = (
        "fitFloor=Math.min(1.2,Math.max(.07,Number(minScale)||.07)),"
        "scale=Math.min(1.2,Math.max(fitFloor,Math.min((box.width-72)/w,"
        "(box.height-72)/h))),next="
    )
    if html.count(scale) != 1:
        raise RuntimeError("camera fit scale seam changed")
    html = html.replace(scale, scale_with_floor, 1)

    initial_fit = "if(!hasFitted&&positions.size){fit(false);hasFitted=true}"
    if html.count(initial_fit) != 2:
        raise RuntimeError("initial camera fit seams changed")
    return html.replace(
        initial_fit,
        "if(!hasFitted&&positions.size){fit(false,.5);hasFitted=true}",
    )


def _surface_provider_neutral_clusters(html: str) -> str:
    """Expose collapsed files and model-call chronology in the shared inspector."""
    helper_seam = "function nodeCards(node){"
    if html.count(helper_seam) != 1:
        raise RuntimeError("agent panel nodeCards seam changed")
    helper = r"""
function execweaveInferenceHistory(a){
  const rows=Array.isArray(a.viewer_inference_occurrences)?a.viewer_inference_occurrences:[];
  return rows.slice().sort((x,y)=>String(x?.first_seen||'').localeCompare(String(y?.first_seen||''))).map((item,index)=>{
    const messages=Array.isArray(item?.messages)?item.messages:[];
    const user=messages.find(message=>String(message?.sender||'')==='user'||/user|request|prompt/i.test(String(message?.kind||'')));
    const answers=messages.filter(message=>String(message?.phase||'')==='final_answer'||String(message?.sender||'')==='assistant'||/assistant|response|final/i.test(String(message?.kind||'')));
    const answer=answers.length?answers[answers.length-1]:null;
    const refs=Array.isArray(item?.content_references)?item.content_references:[];
    const when=moment(item?.first_seen||item?.last_seen);
    const head=[when,`call ${index+1}`].filter(Boolean).join(' · ');
    const lines=[head];
    if(user?.text)lines.push(`Prompt: ${user.text}`);
    if(answer?.text)lines.push(`Answer: ${answer.text}`);
    if(!user?.text&&!answer?.text&&refs.length)lines.push(`Evidence: ${refs.map(ref=>ref?.content_kind||ref?.relation||ref?.id).filter(Boolean).join(', ')}`);
    return lines.join('\n');
  }).join('\n\n');
}
function execweaveFileClusterHistory(a){
  const rows=Array.isArray(a.entries)?a.entries:[];
  return rows.slice().sort((x,y)=>String(x?.path||'').localeCompare(String(y?.path||''))).map(item=>{
    const when=moment(item?.last_seen||item?.first_seen),kind=String(item?.type||'file');
    return [when,kind,item?.path||item?.name||item?.id].filter(Boolean).join(' · ');
  }).join('\n');
}
""" + helper_seam
    html = html.replace(helper_seam, helper, 1)

    branch_seam = """  }else if(kind==='file'){
    add('Path',node?.name);
    add('Observed',fileHistory(String(node?.id||'')));
  }else if(kind==='tool_call'){"""
    branch_replacement = """  }else if(kind==='file'){
    add('Path',node?.name);
    add('Observed',fileHistory(String(node?.id||'')));
  }else if(kind==='file_cluster'){
    add('Files / directories',`${Number(a.member_count||0)} collapsed entries`);
    add('Observed',execweaveFileClusterHistory(a));
  }else if(kind==='model'){
    add('Model',node?.name);
    add('Provider',a.provider||a.provider_name);
    add('Inference calls',a.viewer_inference_count);
    add('Inference history',execweaveInferenceHistory(a));
  }else if(kind==='tool_call'){"""
    if html.count(branch_seam) != 1:
        raise RuntimeError("agent panel file/model branch seam changed")
    return html.replace(branch_seam, branch_replacement, 1)


def _stop_conversation_polling_after_finish(html: str) -> str:
    """Freeze polling only after one authoritative finished conversation sync.

    The live graph announces ``live_finished`` while its HTTP server is still alive.
    Older code stopped the interval and aborted the conversation request immediately
    from ``onFinished``. That fixed a teardown reset, but it could also abort the
    refresh kicked off by the terminal payload itself, leaving the selected live agent
    panel one response behind the finalized standalone viewer. Stop periodic polling
    immediately, wait for any in-flight refresh, perform exactly one final fetch from
    the now-finished raw graph, then mark the panel synchronized. No request is issued
    after that point, so HTTP teardown cannot race the browser.
    """

    seams = (
        (
            "let selectedNode=null,refreshing=false,selectedConversationSignature='';",
            "let selectedNode=null,refreshing=false,conversationPollingFinished=false,conversationFinishing=false,conversationRefreshController=null,conversationRefreshTimer=null,conversationRefreshPromise=Promise.resolve(),conversationFinishPromise=Promise.resolve(),selectedConversationSignature='';",
            "agent conversation polling state seam changed",
        ),
        (
            "async function refresh(){if(window.__execweaveStaticMode||refreshing)return;refreshing=true;try{const headers={};if(window.__execweaveToken)headers['X-ExecWeave-Token']=window.__execweaveToken;const response=await fetch('/conversations.json',{cache:'no-store',headers});if(response.ok){const payload=await response.json();setEntries(payload?.entries)}}catch(_){}finally{refreshing=false}}",
            "async function refresh({allowDuringFinish=false}={}){if(window.__execweaveStaticMode||conversationPollingFinished||(conversationFinishing&&!allowDuringFinish))return;if(refreshing)return conversationRefreshPromise;refreshing=true;const controller=new AbortController();conversationRefreshController=controller;const task=(async()=>{try{const headers={};if(window.__execweaveToken)headers['X-ExecWeave-Token']=window.__execweaveToken;const response=await fetch('/conversations.json',{cache:'no-store',headers,signal:controller.signal});if(response.ok){const payload=await response.json();setEntries(payload?.entries)}}catch(_){}finally{if(conversationRefreshController===controller)conversationRefreshController=null;refreshing=false}})();conversationRefreshPromise=task;await task}",
            "agent conversation refresh seam changed",
        ),
        (
            "if(!window.__execweaveStaticMode)setInterval(()=>{if(selectedNode)refresh()},800);",
            "if(!window.__execweaveStaticMode)conversationRefreshTimer=setInterval(()=>{if(selectedNode&&!conversationFinishing&&!conversationPollingFinished)refresh()},800);",
            "agent conversation interval seam changed",
        ),
        (
            "const previous=window.__execweaveDashboard||{};window.__execweaveDashboard={...previous,onPayload(data){previous.onPayload?.(data);if(selectedNode)refresh()},onFinished(){previous.onFinished?.();if(selectedNode)refresh()}};",
            "async function finishConversationPolling(){if(conversationPollingFinished)return;if(conversationFinishing)return conversationFinishPromise;conversationFinishing=true;if(conversationRefreshTimer!==null){clearInterval(conversationRefreshTimer);conversationRefreshTimer=null}conversationFinishPromise=(async()=>{await conversationRefreshPromise;if(selectedNode&&!window.__execweaveStaticMode)await refresh({allowDuringFinish:true})})().finally(()=>{conversationPollingFinished=true;conversationFinishing=false;if(conversationRefreshController!==null){conversationRefreshController.abort();conversationRefreshController=null}});await conversationFinishPromise}\nconst stopConversationPolling=finishConversationPolling;\nconst previous=window.__execweaveDashboard||{};window.__execweaveDashboard={...previous,onPayload(data){previous.onPayload?.(data);if(selectedNode&&!data?.live_finished&&!conversationFinishing&&!conversationPollingFinished)refresh()},onFinished(){previous.onFinished?.();void finishConversationPolling()}};",
            "agent conversation lifecycle seam changed",
        ),
        (
            "window.__execweaveAgentPanel={render,setEntries,refresh};",
            "window.__execweaveAgentPanel={render,setEntries,refresh,finishConversationPolling,stopConversationPolling,whenFinished:()=>conversationFinishPromise,isFinishedSynchronized:()=>conversationPollingFinished};",
            "agent conversation export seam changed",
        ),
    )
    for old, new, error in seams:
        if html.count(old) != 1:
            raise RuntimeError(error)
        html = html.replace(old, new, 1)
    return html


_viewer_projection_base.project_viewer_graph = project_provider_neutral_viewer_graph

_base.DASHBOARD_HTML = _stop_conversation_polling_after_finish(
    _surface_provider_neutral_clusters(
        _defer_camera_takeover_until_node_drag(
            _preserve_readable_initial_camera(
                _avoid_camera_fit_starvation(
                    _start_in_fit_camera_mode(
                        _route_bundle_edges_on_ordered_rails(_base.DASHBOARD_HTML)
                    )
                )
            )
        )
    )
)
DASHBOARD_HTML = _base.DASHBOARD_HTML
render_static_dashboard_html = _base.render_static_dashboard_html


def __getattr__(name: str):
    """Preserve access to internal helpers while this acceptance shim is isolated."""
    return getattr(_base, name)
