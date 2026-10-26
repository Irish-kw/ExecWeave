"""Arrange cancels prior camera work without changing the selected camera mode.

Real Chromium runs the shipped HTML and its native timers/animation frames.
Fixtures are synthetic; these tests do not claim native HTTP/provider coverage.
"""
from __future__ import annotations

import pytest

from execweave.dashboard_shell import render_static_dashboard_html
from execweave.viewer_projection import project_viewer_graph
from layout_acceptance_fixtures import fixture
from test_investigation_workspace import browser_page
from test_dashboard_camera_scheduler_e2e import _CORE_SEAM, _CORE_TEST_SEAM

__all__ = ["browser_page"]
pytestmark = pytest.mark.viewer_e2e


# Observe the real DOM transition instead of assuming the first animation frame
# runs within 60 ms. The timeout rejects absent motion; it never permits a pass.
_WAIT_FOR_CAMERA_MOTION = r"""
function waitForCameraMotion(viewport, initial, timeoutMs=3000){
  return new Promise((resolve,reject)=>{
    let timer;
    const changed=()=>viewport.getAttribute('transform')!==initial;
    const finish=()=>{observer.disconnect();clearTimeout(timer);resolve()};
    const observer=new MutationObserver(()=>{if(changed())finish()});
    observer.observe(viewport,{attributes:true,attributeFilter:['transform']});
    timer=setTimeout(()=>{
      observer.disconnect();reject(new Error('Camera did not produce an observable animation frame'));
    },timeoutMs);
    if(changed())finish();
  });
}
"""


@pytest.mark.parametrize("mode", ["fit", "follow"])
@pytest.mark.parametrize("pending", [True, False], ids=["queued", "animating"])
def test_arrange_preserves_camera_and_next_update_can_resume(browser_page, mode, pending):
    page = browser_page
    data = project_viewer_graph(fixture("many-files"))
    html = render_static_dashboard_html(data)
    assert html.count(_CORE_SEAM) == 1
    # Export the real scheduler through the same observation seam as the
    # historical camera tests; no handler, timer or renderer is replaced.
    page.set_content(html.replace(_CORE_SEAM, _CORE_TEST_SEAM, 1))
    # Run the existing resize/mode handlers rather than replacing any scheduler.
    result = page.evaluate("""async ({mode,pending})=>{
    """ + _WAIT_FOR_CAMERA_MOTION + """
      const core=window.__execweaveCore,viewport=document.getElementById('viewport');
      core.selectNode(core.getDisplayGraph().nodes.find(n=>n.type==='agent').id);
      const selected=document.querySelector('.node.selected').dataset.id;
      const initial=viewport.getAttribute('transform');
      document.getElementById('svg').style.width='700px';
      const motion=pending?null:waitForCameraMotion(viewport,initial);
      core.setCameraMode(mode,{apply:!pending});
      if(pending)core.scheduleCamera(true);
      else await motion;
      const before=viewport.getAttribute('transform');
      document.getElementById('arrange').click();
      const immediate=viewport.getAttribute('transform');
      await new Promise(resolve=>setTimeout(resolve,550));
      const after=viewport.getAttribute('transform');
      const retainedSelection=document.querySelector('.node.selected')?.dataset.id;
      const retainedMode=document.querySelector('[data-camera].active')?.dataset.camera;
      // A later scheduled update can resume Fit/Follow. Arrange must not permanently
      // disable scheduling, change modes, or prevent subsequent live growth.
      core.scheduleCamera(true);
      await new Promise(resolve=>setTimeout(resolve,550));
      return {initial,before,immediate,after,selected,retainedSelection,retainedMode,
        resumed:viewport.getAttribute('transform')};
    }""", {"mode": mode, "pending": pending})
    if not pending:
        assert result["initial"] != result["before"], "the animation must actually begin"
    assert result["before"] == result["immediate"] == result["after"], result
    assert result["retainedMode"] == mode
    assert result["retainedSelection"] == result["selected"]
    assert result["resumed"] != result["after"], "future automatic camera work must remain enabled"
    assert page.evaluate("window.__execweaveCore.getGraph()") == data


def test_arrange_stops_zoom_animation_but_keeps_manual_camera(browser_page):
    page = browser_page
    page.set_content(render_static_dashboard_html(project_viewer_graph(fixture("3-agent"))))
    result = page.evaluate("""async ()=>{
      const viewport=document.getElementById('viewport');
      document.getElementById('zoom-in').click();
      await new Promise(resolve=>setTimeout(resolve,35));
      const before=viewport.getAttribute('transform');
      document.getElementById('arrange').click();
      await new Promise(resolve=>setTimeout(resolve,350));
      return {before,after:viewport.getAttribute('transform'),
        mode:document.querySelector('[data-camera].active')?.dataset.camera};
    }""")
    assert result["before"] == result["after"], result
    assert result["mode"] == "manual"


def test_duplicate_resize_does_not_change_camera_without_viewport_change(browser_page):
    page = browser_page
    page.set_content(render_static_dashboard_html(project_viewer_graph(fixture("many-files"))))
    result = page.evaluate("""async ()=>{
      const viewport=document.getElementById('viewport');
      const before=viewport.getAttribute('transform');
      window.dispatchEvent(new Event('resize'));
      await new Promise(resolve=>setTimeout(resolve,550));
      return {before,after:viewport.getAttribute('transform')};
    }""")
    assert result["before"] == result["after"], result


def test_actual_viewport_resize_still_refits(browser_page):
    page = browser_page
    page.set_content(render_static_dashboard_html(project_viewer_graph(fixture("many-files"))))
    before = page.locator("#viewport").get_attribute("transform")
    page.set_viewport_size({"width": 1100, "height": 850})
    page.wait_for_function("value=>document.getElementById('viewport').getAttribute('transform')!==value", arg=before)
    assert page.locator('[data-camera].active').get_attribute("data-camera") == "fit"


def test_motion_precondition_rejects_no_motion_and_unrelated_mutation(browser_page):
    page = browser_page
    page.set_content('<svg><g id="viewport" transform="translate(0 0)"></g></svg>')
    result = page.evaluate("""async ()=>{
    """ + _WAIT_FOR_CAMERA_MOTION + """
      const viewport=document.getElementById('viewport');
      const motion=waitForCameraMotion(viewport,viewport.getAttribute('transform'),75);
      viewport.setAttribute('data-unrelated','changed');
      try{await motion;return 'unexpected success'}catch(error){return error.message}
    }""")
    assert result == "Camera did not produce an observable animation frame"


def test_motion_precondition_waits_for_delayed_real_camera_frame(browser_page):
    page = browser_page
    data = project_viewer_graph(fixture("many-files"))
    html = render_static_dashboard_html(data)
    assert html.count(_CORE_SEAM) == 1
    page.set_content(html.replace(_CORE_SEAM, _CORE_TEST_SEAM, 1))
    result = page.evaluate("""async ()=>{
    """ + _WAIT_FOR_CAMERA_MOTION + """
      const core=window.__execweaveCore,viewport=document.getElementById('viewport');
      core.setCameraMode('manual',{apply:false});
      const initial=viewport.getAttribute('transform');
      document.getElementById('svg').style.width='700px';
      const motion=waitForCameraMotion(viewport,initial);
      // Exercise a later real frame without replacing timers, RAF or camera code.
      let requested=false;
      const timer=setTimeout(()=>{requested=true;core.setCameraMode('follow')},150);
      try{await motion;return {requested,initial,after:viewport.getAttribute('transform')}}
      finally{clearTimeout(timer)}
    }""")
    assert result['requested'] is True
    assert result['initial'] != result['after']
    assert page.evaluate("window.__execweaveCore.getGraph()") == data
