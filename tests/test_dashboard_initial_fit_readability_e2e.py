from __future__ import annotations

import os
from pathlib import Path

import pytest

from dashboard_readability_fixture import build_dashboard_readability_graph
from execweave.dashboard_shell import render_static_dashboard_html

pytestmark = pytest.mark.viewer_e2e


def _artifact_dir() -> Path | None:
    value = os.environ.get("EXECWEAVE_VISUAL_ARTIFACT_DIR")
    if not value:
        return None
    path = Path(value).expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def test_dense_initial_view_keeps_agents_readable_and_fit_remains_available(tmp_path: Path) -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        if os.environ.get("EXECWEAVE_E2E_REQUIRED"):
            pytest.fail("playwright is required for the initial readability gate")
        pytest.skip("playwright is not installed")

    graph = build_dashboard_readability_graph()
    viewer = tmp_path / "viewer.html"
    viewer.write_text(render_static_dashboard_html(graph), encoding="utf-8")

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch()
        except Exception as error:  # noqa: BLE001 - keep browser diagnostics in CI
            if os.environ.get("EXECWEAVE_E2E_REQUIRED"):
                pytest.fail(f"chromium would not launch: {error}")
            pytest.skip(f"chromium would not launch: {error}")
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 720})
            page.goto(viewer.as_uri())
            page.wait_for_function(
                """()=>document.querySelectorAll(
                  '.node[data-layout-lane="agent"],.node[data-layout-lane="root"]'
                ).length===7""",
                timeout=15000,
            )
            page.wait_for_timeout(250)

            metrics = page.evaluate(
                """()=>{
                  const agents=[...document.querySelectorAll(
                    '.node[data-layout-lane="agent"],.node[data-layout-lane="root"]')];
                  const nodeHeights=agents.map(node=>node.getBoundingClientRect().height);
                  const labelHeights=agents.map(node=>
                    node.querySelector('.name-label')?.getBoundingClientRect().height||0);
                  return {
                    minNodeHeight:Math.min(...nodeHeights),
                    minLabelHeight:Math.min(...labelHeights),
                    viewportTransform:document.getElementById('viewport')?.getAttribute('transform')||''
                  };
                }"""
            )

            artifacts = _artifact_dir()
            if artifacts is not None:
                page.screenshot(
                    path=str(artifacts / "dashboard-initial-fit-1280x720.png"),
                    full_page=True,
                )

            assert metrics["minLabelHeight"] >= 7, (
                "first-paint agent labels are too small to read at 1280x720: "
                f"{metrics}"
            )
            assert metrics["minNodeHeight"] >= 24, (
                "first-paint agent hit targets are too small at 1280x720: "
                f"{metrics}"
            )

            page.locator('[data-camera="fit"]').click()
            page.wait_for_timeout(350)
            coverage = page.evaluate(
                """()=>{
                  const svg=document.getElementById('svg').getBoundingClientRect();
                  const nodes=[...document.querySelectorAll('.node')]
                    .filter(node=>getComputedStyle(node).display!=='none');
                  const tolerance=4;
                  return {
                    count:nodes.length,
                    allInside:nodes.every(node=>{
                      const box=node.getBoundingClientRect();
                      return box.left>=svg.left-tolerance&&box.right<=svg.right+tolerance&&
                        box.top>=svg.top-tolerance&&box.bottom<=svg.bottom+tolerance;
                    })
                  };
                }"""
            )
            assert coverage["count"] > 0 and coverage["allInside"], (
                "Fit graph must remain an explicit whole-graph navigation affordance: "
                f"{coverage}"
            )
        finally:
            browser.close()
