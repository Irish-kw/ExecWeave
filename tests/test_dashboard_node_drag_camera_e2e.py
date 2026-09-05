"""Node inspection must not accidentally take over the live camera."""

from __future__ import annotations

from pathlib import Path

import pytest

from test_dashboard_camera_scheduler_e2e import _instrumented_viewer
from test_viewer_agent_isolation_e2e import _browser, _launch

pytestmark = pytest.mark.viewer_e2e


def _camera_mode(page) -> str:
    return str(page.evaluate("() => window.__execweaveCore.getCameraMode()"))


def _position(page, node_id: str) -> dict[str, float]:
    value = page.evaluate("id => window.__execweaveCore.getPositions().get(id)", node_id)
    assert isinstance(value, dict)
    return value


def test_node_click_preserves_fit_but_real_drag_takes_camera(tmp_path: Path) -> None:
    viewer = _instrumented_viewer(tmp_path)
    manager, executable = _browser()
    with manager as playwright:
        browser = _launch(playwright, executable)
        try:
            page = browser.new_page(viewport={"width": 1366, "height": 768})
            page.goto(viewer.as_uri())
            node_id = "file:acceptance"
            node = page.locator(f'.node[data-id="{node_id}"]')
            node.wait_for(state="visible", timeout=15000)

            assert _camera_mode(page) == "fit"
            node.click(timeout=5000)
            assert _camera_mode(page) == "fit", (
                "A plain node inspection click must not switch Fit to Manual"
            )

            before = _position(page, node_id)
            box = node.bounding_box()
            assert box is not None
            center_x = box["x"] + box["width"] / 2
            center_y = box["y"] + box["height"] / 2

            page.mouse.move(center_x, center_y)
            page.mouse.down()
            page.mouse.move(center_x + 2, center_y + 1)
            assert _camera_mode(page) == "fit", (
                "Sub-threshold pointer jitter must not take over the camera"
            )
            assert _position(page, node_id) == before

            page.mouse.move(center_x + 14, center_y + 1)
            assert _camera_mode(page) == "manual", (
                "Crossing the node-drag threshold must explicitly take over the camera"
            )
            page.mouse.move(center_x + 32, center_y + 1)
            page.mouse.up()

            after = _position(page, node_id)
            assert abs(float(after["x"]) - float(before["x"])) > 3
        finally:
            browser.close()
