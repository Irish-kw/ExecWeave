"""Camera scheduling must not starve while native live deltas arrive rapidly."""

from __future__ import annotations

from pathlib import Path

import pytest

from test_viewer_agent_isolation_e2e import _browser, _launch

pytestmark = pytest.mark.viewer_e2e

_CORE_SEAM = (
    "window.__execweaveCore={getActivities:()=>activities.slice(),getGraph:()=>graph,"
    "getDisplayGraph:()=>({...graph,nodes:[...nodeById.values()],edges:[...edgeById.values()],"
    "node_count:nodeById.size,edge_count:edgeById.size}),getPositions:()=>new Map(positions),"
    "selectEdge,selectNode,focusNode,markLatest,setCameraMode};"
)
_CORE_TEST_SEAM = (
    "window.__execweaveCore={getActivities:()=>activities.slice(),getGraph:()=>graph,"
    "getDisplayGraph:()=>({...graph,nodes:[...nodeById.values()],edges:[...edgeById.values()],"
    "node_count:nodeById.size,edge_count:edgeById.size}),getPositions:()=>new Map(positions),"
    "selectEdge,selectNode,focusNode,markLatest,setCameraMode,applyDelta,setSnapshot,scheduleCamera,"
    "getCameraMode:()=>cameraMode};"
)
_FIT_SEAM = "function fit(animate=true,minScale=.07){"
_FIT_TEST_SEAM = (
    "function fit(animate=true,minScale=.07){"
    "window.__execweaveFitCalls=(window.__execweaveFitCalls||0)+1;"
)


def _initial_graph() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "node_count": 3,
        "edge_count": 2,
        "event_count": 2,
        "nodes": [
            {"id": "process:python", "type": "process", "name": "python", "attributes": {}},
            {
                "id": "agent:/root",
                "type": "agent",
                "name": "/root",
                "attributes": {"agent_role": "root", "agent_path": "/root"},
            },
            {
                "id": "file:acceptance",
                "type": "file",
                "name": "acceptance.txt",
                "attributes": {},
            },
        ],
        "edges": [
            {
                "id": "e-process-root",
                "source": "process:python",
                "target": "agent:/root",
                "relation": "STARTED_AGENT",
                "attributes": {},
            },
            {
                "id": "e-root-file",
                "source": "agent:/root",
                "target": "file:acceptance",
                "relation": "WROTE_FILE",
                "attributes": {},
            },
        ],
    }


def _instrumented_viewer(tmp_path: Path) -> Path:
    from execweave.dashboard_shell import render_static_dashboard_html

    html = render_static_dashboard_html(_initial_graph())
    assert _CORE_SEAM in html, "dashboard core seam changed; update this test deliberately"
    assert html.count(_FIT_SEAM) == 1, "dashboard fit seam changed; update this test deliberately"
    html = html.replace(_CORE_SEAM, _CORE_TEST_SEAM, 1)
    html = html.replace(_FIT_SEAM, _FIT_TEST_SEAM, 1)
    viewer = tmp_path / "camera-scheduler.html"
    viewer.write_text(html, encoding="utf-8")
    return viewer


def test_fit_camera_executes_during_rapid_delta_burst(tmp_path: Path) -> None:
    viewer = _instrumented_viewer(tmp_path)
    manager, executable = _browser()
    with manager as playwright:
        browser = _launch(playwright, executable)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.goto(viewer.as_uri())
            page.locator('.node[data-id="file:acceptance"]').wait_for(
                state="visible", timeout=15000
            )
            assert page.evaluate("() => window.__execweaveCore.getCameraMode()") == "fit"
            initial_fit_calls = page.evaluate("() => window.__execweaveFitCalls||0")

            update = {
                "event_count": 3,
                "node_count": 4,
                "edge_count": 3,
                "nodes_added": [
                    {
                        "id": "endpoint:loopback",
                        "type": "network_endpoint",
                        "name": "127.0.0.1:64024",
                        "event_count": 1,
                        "attributes": {},
                    }
                ],
                "nodes_updated": [],
                "edges_added": [
                    {
                        "id": "e-process-endpoint",
                        "source": "process:python",
                        "target": "endpoint:loopback",
                        "relation": "CONNECTED_TO",
                        "attributes": {},
                    }
                ],
                "edges_updated": [],
            }
            page.evaluate(
                """update => {
                window.__execweaveCore.applyDelta(update);
                window.__execweaveRapidScheduleTicks=0;
                window.__execweaveRapidSchedule=setInterval(()=>{
                  window.__execweaveRapidScheduleTicks+=1;
                  window.__execweaveCore.scheduleCamera(false);
                  if(window.__execweaveRapidScheduleTicks>=20){
                    clearInterval(window.__execweaveRapidSchedule);
                    window.__execweaveRapidSchedule=null;
                  }
                },50);
                }""",
                update,
            )
            endpoint_node = page.locator('.node[data-id="endpoint:loopback"]')
            endpoint_node.wait_for(state="visible", timeout=15000)
            page.wait_for_timeout(450)

            ticks = page.evaluate("() => window.__execweaveRapidScheduleTicks")
            fit_calls = page.evaluate("() => window.__execweaveFitCalls||0")
            assert ticks < 20, "the assertion must run while the rapid schedule burst is active"
            assert page.evaluate("() => window.__execweaveCore.getCameraMode()") == "fit"
            assert fit_calls > initial_fit_calls, (
                "Fit camera was starved by repeated live scheduling; no fit executed "
                "during the active burst"
            )

            page.evaluate(
                """() => {
                if(window.__execweaveRapidSchedule){
                  clearInterval(window.__execweaveRapidSchedule);
                  window.__execweaveRapidSchedule=null;
                }
                }"""
            )
            page.wait_for_timeout(300)
            endpoint_node.click(timeout=5000)
            details = page.locator("#details").inner_text()
            assert "ADDRESS" in details
            assert "127.0.0.1:64024" in details
            assert "REACHED BY" in details
        finally:
            browser.close()


def test_selection_owns_camera_and_focus_survives_full_live_snapshot(tmp_path: Path) -> None:
    viewer = _instrumented_viewer(tmp_path)
    manager, executable = _browser()
    with manager as playwright:
        browser = _launch(playwright, executable)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.goto(viewer.as_uri())
            process = page.locator('.node[data-id="process:python"]')
            process.wait_for(state="visible", timeout=15000)

            page.locator("#zoom-in").click()
            page.wait_for_timeout(250)
            process.click()
            page.wait_for_timeout(250)
            before = page.evaluate(
                """() => ({
                  transform:document.getElementById('viewport').getAttribute('transform'),
                  selected:[...document.querySelectorAll('.node.selected')].map(n=>n.dataset.id),
                  dimmed:[...document.querySelectorAll('.node.context-dim')].map(n=>n.dataset.id),
                  camera:window.__execweaveCore.getCameraMode()
                })"""
            )
            assert before["camera"] == "manual"
            assert before["selected"] == ["process:python"]
            assert "file:acceptance" in before["dimmed"]

            updated = _initial_graph()
            updated["event_count"] = 3
            updated["node_count"] = 4
            updated["edge_count"] = 3
            updated["nodes"].append(
                {
                    "id": "endpoint:loopback",
                    "type": "network_endpoint",
                    "name": "127.0.0.1:11434",
                    "attributes": {},
                }
            )
            updated["edges"].append(
                {
                    "id": "e-process-endpoint",
                    "source": "process:python",
                    "target": "endpoint:loopback",
                    "relation": "CONNECTED_TO",
                    "attributes": {},
                }
            )
            page.evaluate("graph => window.__execweaveCore.setSnapshot(graph)", updated)
            page.wait_for_timeout(450)
            after = page.evaluate(
                """() => ({
                  transform:document.getElementById('viewport').getAttribute('transform'),
                  selected:[...document.querySelectorAll('.node.selected')].map(n=>n.dataset.id),
                  dimmed:[...document.querySelectorAll('.node.context-dim')].map(n=>n.dataset.id),
                  opacities:[...document.querySelectorAll('.node')].map(n=>({id:n.dataset.id,opacity:Number(getComputedStyle(n).opacity)})),
                  camera:window.__execweaveCore.getCameraMode()
                })"""
            )

            assert after["transform"] == before["transform"]
            assert after["camera"] == "manual"
            assert after["selected"] == ["process:python"]
            assert "file:acceptance" in after["dimmed"]
            assert any(
                node["id"] == "file:acceptance" and node["opacity"] < 1
                for node in after["opacities"]
            )
        finally:
            browser.close()


def test_delta_vertical_retention_never_reintroduces_node_overlap(tmp_path: Path) -> None:
    viewer = _instrumented_viewer(tmp_path)
    manager, executable = _browser()
    with manager as playwright:
        browser = _launch(playwright, executable)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.goto(viewer.as_uri())
            page.locator('.node[data-id="file:acceptance"]').wait_for(
                state="visible", timeout=15000
            )

            for index in range(2):
                node_id = f"file:orphan-{index}"
                page.evaluate(
                    """update => window.__execweaveCore.applyDelta(update)""",
                    {
                        "event_count": 3 + index,
                        "node_count": 4 + index,
                        "edge_count": 2,
                        "nodes_added": [
                            {
                                "id": node_id,
                                "type": "file",
                                "name": f"orphan-{index}.txt",
                                "attributes": {},
                            }
                        ],
                        "nodes_updated": [],
                        "edges_added": [],
                        "edges_updated": [],
                    },
                )
                page.locator(f'.node[data-id="{node_id}"]').wait_for(
                    state="visible", timeout=15000
                )

            boxes = page.locator(".node").evaluate_all(
                """nodes => nodes.map(node => {
                  const box = node.getBoundingClientRect();
                  return {id: node.dataset.id, left: box.left, right: box.right,
                    top: box.top, bottom: box.bottom};
                })"""
            )
            overlaps = []
            for index, first in enumerate(boxes):
                for second in boxes[index + 1 :]:
                    if (
                        min(first["right"], second["right"])
                        > max(first["left"], second["left"])
                        and min(first["bottom"], second["bottom"])
                        > max(first["top"], second["top"])
                    ):
                        overlaps.append((first["id"], second["id"]))
            assert overlaps == []
        finally:
            browser.close()
