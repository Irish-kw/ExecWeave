from __future__ import annotations

from .live_view_extra_style import LIVE_EXTRA_STYLE
from .live_view_markup import LIVE_MARKUP
from .live_view_script_a import LIVE_SCRIPT_A
from .live_view_script_b import LIVE_SCRIPT_B
from .live_view_script_c import LIVE_SCRIPT_C
from .live_view_script_d import LIVE_SCRIPT_D
from .live_view_style import LIVE_STYLE


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
