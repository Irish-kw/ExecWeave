from __future__ import annotations

from pathlib import Path
import io
import json

import pytest

from execweave.dashboard_shell import DASHBOARD_HTML, render_static_dashboard_html
from test_viewer_agent_isolation_e2e import _browser, _launch


pytestmark = pytest.mark.viewer_e2e


def _gif_graph() -> dict[str, object]:
    nodes = [
        {"id": "process:root", "type": "process", "name": "python", "attributes": {}}
    ]
    edges = []
    for index in range(30):
        node_id = f"endpoint:127.0.0.1:{12000 + index}"
        nodes.append(
            {
                "id": node_id,
                "type": "network_endpoint",
                "name": f"127.0.0.1:{12000 + index}",
                "attributes": {"host": "127.0.0.1", "port": 12000 + index},
            }
        )
        edges.append(
            {
                "id": f"edge:{index}",
                "source": "process:root",
                "target": node_id,
                "relation": "CONNECTED_TO",
                "first_sequence": index + 1,
                "attributes": {},
            }
        )
    return {
        "schema_version": "1.0",
        "session_id": "gif-repeat",
        "node_count": len(nodes),
        "edge_count": len(edges),
        "event_count": len(edges),
        "nodes": nodes,
        "edges": edges,
    }


def _replay_contract(page) -> dict:
    return page.evaluate(
        """() => {
          const graph=window.__execweaveCore.getDisplayGraph?.()
            ||window.__execweaveCore.getGraph?.()||{};
          const steps=window.__execweaveGifTopologySteps(graph);
          return {
            nodeCount:(graph.nodes||[]).length,
            edgeCount:(graph.edges||[]).length,
            steps,
            stepCount:steps.length,
            nodeStepCount:steps.filter(step=>step.nodeId).length,
            edgeStepCount:steps.filter(step=>step.edgeId).length,
          };
        }"""
    )


def _assert_download_gif_is_nonzero_valid_and_repeatable(
    tmp_path: Path, *, finished_live: bool
) -> None:
    viewer = tmp_path / "viewer.html"
    viewer.write_text(render_static_dashboard_html(_gif_graph()), encoding="utf-8")
    manager, executable = _browser()
    with manager as playwright:
        browser = _launch(playwright, executable)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000}, accept_downloads=True)
            page_errors: list[str] = []
            page.on("pageerror", lambda error: page_errors.append(str(error)))
            if finished_live:
                page.route(
                    "**/live.json?*",
                    lambda route: route.fulfill(
                        json={
                            "kind": "snapshot",
                            "graph": _gif_graph(),
                            "sequence": 1,
                            "live_finished": True,
                        }
                    ),
                )
                page.route(
                    "http://gif.test/",
                    lambda route: route.fulfill(body=DASHBOARD_HTML, content_type="text/html"),
                )
                page.goto("http://gif.test/")
            else:
                page.goto(viewer.as_uri())
            page.wait_for_selector(".node", timeout=15000)
            contract = _replay_contract(page)
            assert contract["stepCount"] >= contract["nodeCount"] >= 2
            assert contract["nodeStepCount"] == contract["nodeCount"]
            assert contract["edgeStepCount"] == contract["edgeCount"]
            assert all(set(step) == {"nodeId", "edgeId"} for step in contract["steps"])
            assert all(step["nodeId"] is None or isinstance(step["nodeId"], str) for step in contract["steps"])

            page.evaluate(
                """() => {
                  window.__gifDiagnostic={objectUrls:[],anchorClicks:0};
                  const create=URL.createObjectURL.bind(URL);
                  URL.createObjectURL=blob=>{window.__gifDiagnostic.objectUrls.push({size:blob.size,type:blob.type});return create(blob)};
                  const click=HTMLAnchorElement.prototype.click;
                  HTMLAnchorElement.prototype.click=function(){window.__gifDiagnostic.anchorClicks+=1;return click.call(this)};
                }"""
            )

            sizes = []
            for attempt in range(2):
                with page.expect_download(timeout=60000) as download_info:
                    page.locator("#download-gif").click()
                download = download_info.value
                assert download.suggested_filename.endswith(".gif")
                output = tmp_path / f"export-{attempt + 1}.gif"
                download.save_as(str(output))
                payload = output.read_bytes()
                assert payload[:6] in (b"GIF87a", b"GIF89a")
                assert payload[-1:] == b"\x3b"
                assert len(payload) > 1024
                from PIL import Image, ImageChops, ImageStat

                with Image.open(io.BytesIO(payload)) as image:
                    assert image.n_frames == contract["stepCount"]
                    first = image.convert("RGB")
                    image.seek(image.n_frames - 1)
                    final = image.convert("RGB")
                    assert image.width > 480
                    assert sum(ImageStat.Stat(ImageChops.difference(first, final)).mean) > 0.5
                sizes.append(len(payload))
                page.wait_for_function(
                    "() => !document.getElementById('download-gif').disabled", timeout=5000
                )

            assert all(size > 0 for size in sizes)
            assert not page_errors
            assert page.locator(".node").count() > 0
        finally:
            browser.close()


def test_download_gif_is_nonzero_valid_and_repeatable(tmp_path: Path) -> None:
    """Keep the historical test node ID stable for stage-integrity gating."""
    _assert_download_gif_is_nonzero_valid_and_repeatable(tmp_path, finished_live=False)


def test_finished_live_download_gif_is_nonzero_valid_and_repeatable(tmp_path: Path) -> None:
    _assert_download_gif_is_nonzero_valid_and_repeatable(tmp_path, finished_live=True)


def _evolving_graph(count: int) -> dict:
    nodes = [{"id": "agent:root", "type": "agent", "name": "Coordinator", "attributes": {}}]
    edges = []
    for index in range(count):
        node = {
            "id": f"file:{index}",
            "type": "file",
            "name": f"report-{index:02}.txt",
            "first_seen": f"2026-09-08T00:00:{index:02}Z",
            "attributes": {"path": f"/work/report-{index:02}.txt"},
        }
        nodes.append(node)
        edges.append(
            {
                "id": f"write:{index}",
                "source": "agent:root",
                "target": node["id"],
                "relation": "WROTE",
                "first_sequence": index + 1,
                "first_seen": f"2026-09-08T00:00:{index:02}Z",
                "attributes": {},
            }
        )
    nodes.append(
        {
            "id": "file:isolated",
            "type": "file",
            "name": "early-isolated.txt",
            "first_seen": "2026-09-08T00:00:59Z",
            "attributes": {"path": "/work/early-isolated.txt"},
        }
    )
    if count >= 8:
        nodes.append(
            {
                "id": "model:shared",
                "type": "model",
                "name": "Shared model",
                "first_seen": "2026-09-08T00:01:00Z",
                "attributes": {},
            }
        )
        for index in range(3):
            agent_id = f"agent:worker:{index}"
            nodes.append(
                {
                    "id": agent_id,
                    "type": "agent",
                    "name": f"Worker {index}",
                    "first_seen": f"2026-09-08T00:01:0{index}Z",
                    "attributes": {"agent_path": f"/root/worker_{index}"},
                }
            )
            edges.append(
                {
                    "id": f"model:{index}",
                    "source": agent_id,
                    "target": "model:shared",
                    "relation": "USES",
                    "first_sequence": count + index + 1,
                    "first_seen": f"2026-09-08T00:01:1{index}Z",
                    "attributes": {},
                }
            )
    return {
        "session_id": "visual-parity",
        "nodes": nodes,
        "edges": edges,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "event_count": count,
    }


@pytest.mark.parametrize("count", [3, 18], ids=["simple", "folded"])
@pytest.mark.parametrize("theme", ["dark", "light"])
def test_downloaded_frames_match_live_view_and_elapsed_time(
    tmp_path: Path, count: int, theme: str
) -> None:
    """Historical name retained: export now checks final visual parity and node-by-node replay."""
    from PIL import Image, ImageChops, ImageFilter, ImageStat

    manager, executable = _browser()
    with manager as playwright:
        browser = _launch(playwright, executable)
        try:
            page = browser.new_page(
                viewport={"width": 1440, "height": 1000},
                accept_downloads=True,
                reduced_motion="reduce",
            )
            page.add_init_script(f"localStorage.setItem('execweave-theme', {json.dumps(theme)})")
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            graph = _evolving_graph(count)
            page.route(
                "**/live.json?*",
                lambda route: route.fulfill(
                    json={
                        "kind": "snapshot",
                        "graph": graph,
                        "sequence": 1,
                        "live_finished": True,
                    }
                ),
            )
            page.route(
                "http://gif.test/",
                lambda route: route.fulfill(body=DASHBOARD_HTML, content_type="text/html"),
            )
            page.goto("http://gif.test/")
            page.wait_for_selector(".node")
            page.wait_for_selector("#download-gif:visible")
            page.wait_for_timeout(300)

            contract = _replay_contract(page)
            assert contract["nodeStepCount"] == contract["nodeCount"]
            assert all(step["nodeId"] is None or isinstance(step["nodeId"], str) for step in contract["steps"])

            screenshot_path = tmp_path / "dashboard-final.png"
            page.locator("#svg").screenshot(path=str(screenshot_path))
            expected = Image.open(screenshot_path).convert("RGB")
            text_regions = page.evaluate(
                """() => {
                  const svg=document.getElementById('svg').getBoundingClientRect();
                  return [...document.querySelectorAll('.node .name-label')].map(e=>{
                    const r=e.getBoundingClientRect();
                    return [Math.max(0,Math.floor(r.left-svg.left)),Math.max(0,Math.floor(r.top-svg.top)),
                            Math.min(svg.width,Math.ceil(r.right-svg.left)),Math.min(svg.height,Math.ceil(r.bottom-svg.top))];
                  }).filter(r=>r[2]>r[0]&&r[3]>r[1]);
                }"""
            )

            with page.expect_download(timeout=60000) as download_info:
                page.locator("#download-gif").click()
            output = tmp_path / "replay.gif"
            download_info.value.save_as(str(output))

            frames, delays = [], []
            with Image.open(output) as gif:
                assert gif.n_frames == contract["stepCount"]
                for index in range(gif.n_frames):
                    gif.seek(index)
                    frames.append(gif.convert("RGB"))
                    delays.append(gif.info["duration"])

            assert len(frames) >= contract["nodeCount"]
            assert all(frame.size == expected.size for frame in frames)
            assert 80 <= min(delays[:-1] or delays) <= 200
            assert delays[-1] >= 800

            final = frames[-1]
            score = sum(ImageStat.Stat(ImageChops.difference(expected, final)).mean) / 3
            assert score < 2.5, score
            assert sum(ImageStat.Stat(ImageChops.difference(frames[0], final)).mean) > 0.5

            text_expected = expected.convert("L").filter(ImageFilter.GaussianBlur(0.5))
            text_actual = final.convert("L").filter(ImageFilter.GaussianBlur(0.5))
            for region in text_regions:
                diff = ImageChops.difference(
                    text_expected.crop(region), text_actual.crop(region)
                )
                assert ImageStat.Stat(diff).mean[0] < 10, region

            assert not errors
        finally:
            browser.close()


def test_failed_gif_rasterization_is_reported_and_can_be_retried(tmp_path: Path) -> None:
    viewer = tmp_path / "viewer.html"
    viewer.write_text(render_static_dashboard_html(_gif_graph()), encoding="utf-8")
    manager, executable = _browser()
    with manager as playwright:
        browser = _launch(playwright, executable)
        try:
            page = browser.new_page(accept_downloads=True)
            page.goto(viewer.as_uri())
            page.wait_for_selector(".node")
            page.evaluate(
                """() => {
                  window.originalDecode=HTMLImageElement.prototype.decode;
                  HTMLImageElement.prototype.decode=()=>Promise.reject(new Error('decode unavailable'));
                }"""
            )
            page.locator("#download-gif").click()
            page.wait_for_function(
                "document.getElementById('gif-notice').textContent.includes('decode unavailable')"
            )
            assert page.locator("#download-gif").is_enabled()
            page.evaluate("() => { HTMLImageElement.prototype.decode=window.originalDecode; }")
            with page.expect_download(timeout=60000) as download:
                page.locator("#download-gif").click()
            assert download.value.failure() is None
        finally:
            browser.close()
