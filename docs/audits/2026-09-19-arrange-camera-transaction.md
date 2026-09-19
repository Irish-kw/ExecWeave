# Arrange camera transaction

Baseline: `75afa9ffefdfe70a00adbcdbe6eb68c8804dabd8`, PR #110.

I isolated two camera-timing paths. A queued resize/automatic Fit or an active
Fit, Follow or zoom animation could continue after Arrange, even though the
arrangement handler itself did not request a camera move. Separately, a delayed
initial browser resize notification could trigger a second Fit without any
window-size change, between the first geometry measurement and the click.

The repair is confined to `live_view_script_c.py`. A capture-phase click handler
cancels the prior camera timer and animation before the existing Arrange handler
runs. It preserves the transform and selected camera mode. Future automatic
updates and explicit camera actions still work. The window resize handler now
ignores duplicate notifications with unchanged viewport dimensions, but genuine
viewport changes still schedule Fit/Follow normally. The geometry solver, node
selection, raw graph, view defaults and evidence readers are unchanged.

Seven new Chromium regression cases run the shipped Dashboard with synthetic
fixtures. Four use the same observation/export seam as historical camera tests
to call the real scheduler, without replacing any timer or renderer. The tests
cover queued/active Fit and Follow, zoom in Manual mode, duplicate resize, and a
real browser viewport resize. They preserve the selected agent and raw graph and
require subsequent camera work to resume. These are component/browser checks,
not fresh provider recordings or native HTTP/offline acceptance.

The identical seven tests on the unmodified baseline produced **6 failed,
1 passed**. The repair produced **7 passed**. An initial cancellation-only
candidate still failed two historical geometry cases (**32 passed, 2 failed**
including the then-five new cases); browser traces located the resize work that
started before the click. That candidate was not published and its temporary
change to `viewer_flow_canvas.py` was removed. The final geometry result is
recorded in the PR and accompanying validation report.

No historical test, workflow, dependency, version, main-branch file or release
setting is changed. In particular the restored historical geometry test remains
byte-identical to main. This batch consists of one production file, one added
test file and this record. Reverting the production change restores the old
camera behavior without altering stored run data. Complete release acceptance
and the other open work packages remain outside this isolated repair.
