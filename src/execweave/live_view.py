from __future__ import annotations

import re

from .live_view_extra_style import LIVE_EXTRA_STYLE
from .live_view_markup import LIVE_MARKUP
from .live_view_readability import LIVE_READABILITY_SCRIPT, LIVE_READABILITY_STYLE
from .live_view_script_a import LIVE_SCRIPT_A
from .live_view_script_b import LIVE_SCRIPT_B
from .live_view_script_c import LIVE_SCRIPT_C
from .live_view_script_d import LIVE_SCRIPT_D
from .live_view_style import LIVE_STYLE
from .viewer_agent_panel import inject_agent_panel


_SAFE_GIF_LZW = (
    "function lzw(indices,minCodeSize=8){"
    "const clear=1<<minCodeSize,end=clear+1,out=[];"
    "let buffer=0,bits=0;const codeSize=minCodeSize+1;"
    "const chunk=Math.max(1,(1<<codeSize)-clear-8);"
    "const emit=code=>{buffer|=code<<bits;bits+=codeSize;"
    "while(bits>=8){out.push(buffer&255);buffer>>>=8;bits-=8}};"
    "if(!indices.length)emit(clear);"
    "for(let start=0;start<indices.length;start+=chunk){"
    "emit(clear);const stop=Math.min(indices.length,start+chunk);"
    "for(let i=start;i<stop;i++)emit(indices[i])}"
    "emit(end);if(bits>0)out.push(buffer&255);return out}"
)


def _restore_live_safety_contracts(html: str) -> str:
    """Preserve live-view safety contracts while retiring legacy final-page swapping."""
    html = html.replace(
        "activityFilter='all',cameraTimer=null,animationFrame=null,activitySerial=0;",
        "activityFilter='all',cameraTimer=null,animationFrame=null,activitySerial=0,"
        "lastSignature='';",
        1,
    )
    html = html.replace(
        "evidence.innerHTML=`OS <strong>${runtime}</strong> · specialized "
        "<strong>${specialized}</strong>${provisional?' · provisional':''}`;",
        "evidence.innerHTML=`OS <strong>${runtime}</strong> · specialized "
        "<strong>${specialized}</strong>${provisional?' · provisional':''}`;"
        "evidence.setAttribute('aria-label',`OS ${runtime} · specialized ${specialized}"
        "${provisional?' · provisional':''}`);",
        1,
    )
    html = html.replace(
        "for(const n of nodeById.values())createNodeElement(n);applySearch()}",
        "for(const n of nodeById.values())createNodeElement(n);applySearch();"
        "refreshEdgeLabels()}\n"
        "function refreshEdgeLabels(){for(const e of edgeById.values())updateEdgeElement(e)}",
        1,
    )
    html = html.replace(
        "function setSnapshot(data){graph=data;",
        "function setSnapshot(data){const signature=`${data.node_count||0}:"
        "${data.edge_count||0}`;lastSignature=signature;graph=data;",
        1,
    )

    html, lzw_count = re.subn(
        r"function lzw\(indices,minCodeSize=8\)\{.*?\}\nfunction appendBlocks",
        _SAFE_GIF_LZW + "\nfunction appendBlocks",
        html,
        count=1,
        flags=re.DOTALL,
    )
    if lzw_count != 1:
        raise RuntimeError("live GIF encoder patch target not found")

    open_final_button = '<button id="open-final" type="button">Open final graph</button>'
    if open_final_button not in html:
        raise RuntimeError("legacy final action patch target not found")
    html = html.replace(open_final_button, "", 1)
    html = html.replace(
        ",openFinalButton=document.getElementById('open-final')",
        "",
        1,
    )
    html = html.replace(
        "let rawEntries=[],logMode='structured',finishedShown=false,"
        "finalHtmlCache=null,replaying=false;",
        "let rawEntries=[],logMode='structured',finishedShown=false,replaying=false;",
        1,
    )
    old_final_flow = (
        "async function prepareFinalView(){try{const response=await fetch('/final',"
        "{cache:'no-store'});if(!response.ok)throw new Error(String(response.status));"
        "finalHtmlCache=await response.text()}catch(_){finalHtmlCache=null}}\n"
        "function openFinal(){if(!finalHtmlCache)return;document.open();"
        "document.write(finalHtmlCache);document.close()}\n"
        "function onFinished(){if(finishedShown)return;finishedShown=true;"
        "finishedActions.hidden=false;prepareFinalView()}\n"
        "replayButton.onclick=replayRun;gifButton.onclick=downloadGif;"
        "openFinalButton.onclick=openFinal;"
    )
    new_final_flow = (
        "function onFinished(){if(finishedShown)return;finishedShown=true;"
        "finishedActions.hidden=false}\n"
        "replayButton.onclick=replayRun;gifButton.onclick=downloadGif;"
    )
    if old_final_flow not in html:
        raise RuntimeError("legacy final renderer patch target not found")
    return html.replace(old_final_flow, new_final_flow, 1)


LIVE_HTML = inject_agent_panel(
    _restore_live_safety_contracts(
        f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ExecWeave Live</title>
<style>
{LIVE_STYLE}
{LIVE_EXTRA_STYLE}
{LIVE_READABILITY_STYLE}
</style>
</head>
<body>
{LIVE_MARKUP}
<script>
{LIVE_SCRIPT_A}{LIVE_READABILITY_SCRIPT}{LIVE_SCRIPT_B}{LIVE_SCRIPT_C}{LIVE_SCRIPT_D}
</script>
</body>
</html>"""
    )
)
