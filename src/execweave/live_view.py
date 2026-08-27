from __future__ import annotations

import re

from .live_view_extra_style import LIVE_EXTRA_STYLE
from .live_view_markup import LIVE_MARKUP
from .live_view_script_a import LIVE_SCRIPT_A
from .live_view_script_b import LIVE_SCRIPT_B
from .live_view_script_c import LIVE_SCRIPT_C
from .live_view_script_d import LIVE_SCRIPT_D
from .live_view_style import LIVE_STYLE


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
    """Preserve the established live-view safety contracts after modular assembly."""
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

    old_open_final = (
        "function openFinal(){if(!finalHtmlCache)return;document.open();"
        "document.write(finalHtmlCache);document.close()}"
    )
    new_open_final = (
        "function openFinal(){if(!finalHtmlCache)return;"
        "const finalWindow=window.open('about:blank','_blank');"
        "if(!finalWindow){window.alert('Allow pop-ups to open the final graph.');return}"
        "finalWindow.document.open();finalWindow.document.write(finalHtmlCache);"
        "finalWindow.document.close();try{finalWindow.opener=null}catch(_){}}"
    )
    if old_open_final not in html:
        raise RuntimeError("final graph navigation patch target not found")
    html = html.replace(old_open_final, new_open_final, 1)
    return html


LIVE_HTML = _restore_live_safety_contracts(
    f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ExecWeave Live</title>
<style>
{LIVE_STYLE}
{LIVE_EXTRA_STYLE}
</style>
</head>
<body>
{LIVE_MARKUP}
<script>
{LIVE_SCRIPT_A}{LIVE_SCRIPT_B}{LIVE_SCRIPT_C}{LIVE_SCRIPT_D}
</script>
</body>
</html>"""
)
