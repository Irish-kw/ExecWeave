from __future__ import annotations

from . import _dashboard_shell_base as _base


def _inject_parallel_bundle_rails(html: str) -> str:
    seam = "const ordered=members.slice().sort((a,b)=>endpointCoord(a.target)[1]-endpointCoord(b.target)[1]||a.target.localeCompare(b.target));"
    old = seam + "const trunkX=sourcePort[0]+Math.max(80,(targetLeadX-sourcePort[0])*.48);"
    new = seam + "const bundleCenter=sourcePort[0]+Math.max(80,(targetLeadX-sourcePort[0])*.48);"
    if old not in html:
        raise RuntimeError("dashboard bundle injection seam missing")
    html = html.replace(old, new, 1)
    old_path = "const end=endpointPort(e.target,'left'),memberY=end[1],path=`M ${sourcePort[0]} ${sourcePort[1]} H ${trunkX} V ${memberY} H ${end[0]}`;"
    new_path = (
        "const end=endpointPort(e.target,'left'),memberY=end[1],memberIndex=ordered.findIndex(item=>item.id===e.id),"
        "railGap=8,railX=bundleCenter+(memberIndex-(ordered.length-1)/2)*railGap,"
        "path=`M ${sourcePort[0]} ${sourcePort[1]} H ${railX} V ${memberY} H ${end[0]}`;"
    )
    if old_path not in html:
        raise RuntimeError("dashboard bundle path injection seam missing")
    return html.replace(old_path, new_path, 1)


def _start_in_fit_camera_mode(html: str) -> str:
    """Keep live growth inside the graph viewport until the user takes the camera.

    The first live snapshot is often only a small process tree. It is automatically
    fitted before later file/network nodes arrive. Starting in manual mode froze that
    tiny-snapshot transform, so later nodes could render underneath the inspector and
    become impossible to click. Fit mode follows growth; existing pan/zoom handlers
    still call ``userTookCamera`` and switch to Manual on the first user camera action.
    """
    seams = (
        (
            "let cameraMode='manual',cameraTimer=null,hasFitted=false;",
            "let cameraMode='fit',cameraTimer=null,hasFitted=false;",
            "dashboard camera state seam missing",
        ),
        (
            '<button type="button" data-camera="manual" class="active">Manual</button><button type="button" data-camera="fit">Fit graph</button>',
            '<button type="button" data-camera="manual">Manual</button><button type="button" data-camera="fit" class="active">Fit graph</button>',
            "dashboard camera controls seam missing",
        ),
        (
            '<strong id="camera-label">Manual</strong>',
            '<strong id="camera-label">Fit graph</strong>',
            "dashboard camera label seam missing",
        ),
    )
    for old, new, error in seams:
        if html.count(old) != 1:
            raise RuntimeError(error)
        html = html.replace(old, new, 1)
    return html


def _preserve_readable_initial_camera(html: str) -> str:
    old_fit = "function fit(animate=true){const bounds=graphBounds();if(!bounds)return;const box=svg.getBoundingClientRect(),w=Math.max(1,bounds.maxX-bounds.minX),h=Math.max(1,bounds.maxY-bounds.minY),scale=Math.min(1.2,Math.max(.07,Math.min((box.width-72)/w,(box.height-72)/h))),next={x:36-bounds.minX*scale,y:36-bounds.minY*scale,scale};animate?animateTo(next):setTransform(next)}"
    new_fit = "function fit(animate=true,minScale=null){const bounds=graphBounds();if(!bounds)return;const box=svg.getBoundingClientRect(),w=Math.max(1,bounds.maxX-bounds.minX),h=Math.max(1,bounds.maxY-bounds.minY),naturalScale=Math.min(1.2,Math.max(.07,Math.min((box.width-72)/w,(box.height-72)/h))),scale=minScale===null?naturalScale:Math.min(1.2,Math.max(naturalScale,minScale)),cameraWidth=(typeof execweaveCameraWidth==='function'?execweaveCameraWidth(bounds):w),next={x:36-bounds.minX*scale,y:36-bounds.minY*scale,scale},right=next.x+(bounds.minX+cameraWidth)*scale,maxRight=Math.max(36,box.width-36);if(right>maxRight)next.x-=right-maxRight;animate?animateTo(next):setTransform(next)}"
    if old_fit not in html:
        raise RuntimeError("dashboard fit injection seam missing")
    html = html.replace(old_fit, new_fit, 1)
    for old, new in (
        ("if(!hasFitted&&nodes.size>0){fit(false);hasFitted=true}", "if(!hasFitted&&nodes.size>0){fit(false,.5);hasFitted=true}"),
        ("if(!hasFitted&&nodes.size>0){fit(false);hasFitted=true}else scheduleCamera(false)", "if(!hasFitted&&nodes.size>0){fit(false,.5);hasFitted=true}else scheduleCamera(false)"),
    ):
        if old not in html:
            raise RuntimeError("dashboard initial camera seam missing")
        html = html.replace(old, new, 1)
    return html


DASHBOARD_HTML = _preserve_readable_initial_camera(
    _start_in_fit_camera_mode(_inject_parallel_bundle_rails(_base.DASHBOARD_HTML))
)


def __getattr__(name: str):
    return getattr(_base, name)
