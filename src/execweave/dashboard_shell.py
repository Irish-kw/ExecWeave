from __future__ import annotations

from . import _dashboard_shell_base as _base


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


# Patch the shared shell after all existing semantic-layout injections have run. The
# base renderer function reads its module-global DASHBOARD_HTML at call time, so static
# viewer.html and live mode both consume the same patched document.
_base.DASHBOARD_HTML = _preserve_readable_initial_camera(
    _start_in_fit_camera_mode(
        _route_bundle_edges_on_ordered_rails(_base.DASHBOARD_HTML)
    )
)
DASHBOARD_HTML = _base.DASHBOARD_HTML
render_static_dashboard_html = _base.render_static_dashboard_html


def __getattr__(name: str):
    """Preserve access to internal helpers while this acceptance shim is isolated."""
    return getattr(_base, name)
