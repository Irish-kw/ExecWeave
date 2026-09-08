from __future__ import annotations

from pathlib import Path
import io
import json
import time

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
                page.route("**/live.json?*", lambda route: route.fulfill(json={
                    "kind": "snapshot", "graph": _gif_graph(), "sequence": 1, "live_finished": True}))
                page.route("http://gif.test/", lambda route: route.fulfill(
                    body=DASHBOARD_HTML, content_type="text/html"))
                page.goto("http://gif.test/")
            else:
                page.goto(viewer.as_uri())
            page.wait_for_selector(".node", timeout=15000)
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
                downloads = []
                page.once("download", lambda download: downloads.append(download))
                page.locator("#download-gif").click()
                page.wait_for_timeout(3000)
                assert downloads, {
                    "state": page.evaluate(
                    """() => ({
                      diagnostic:window.__gifDiagnostic,
                      button:document.getElementById('download-gif').textContent,
                      disabled:document.getElementById('download-gif').disabled,
                      onclick:String(document.getElementById('download-gif').onclick),
                      graph:window.__execweaveCore.getGraph()
                    })"""
                    ),
                    "page_errors": page_errors,
                }
                download = downloads[0]
                assert download.suggested_filename.endswith(".gif")
                output = tmp_path / f"export-{attempt + 1}.gif"
                download.save_as(str(output))
                payload = output.read_bytes()
                assert payload[:6] in (b"GIF87a", b"GIF89a")
                assert payload[-1:] == b"\x3b"
                assert len(payload) > 1024
                from PIL import Image

                with Image.open(io.BytesIO(payload)) as image:
                    image.load()  # A GIF header alone does not validate LZW decoding.
                    assert image.n_frames == 1  # A reopened graph has no recorded history.
                    assert image.width > 480
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
        node = {"id": f"file:{index}", "type": "file", "name": f"report-{index:02}.txt",
                "first_sequence": index + 1, "attributes": {"path": f"/work/report-{index:02}.txt"}}
        nodes.append(node)
        edges.append({"id": f"write:{index}", "source": "agent:root", "target": node["id"],
                      "relation": "WROTE", "first_sequence": index + 1, "attributes": {}})
    # The old edge-only replay delayed unconnected nodes until its very last frame.
    nodes.append({"id": "file:isolated", "type": "file", "name": "early-isolated.txt",
                  "attributes": {"path": "/work/early-isolated.txt"}})
    if count >= 8:
        nodes.append({"id": "model:shared", "type": "model", "name": "Shared model",
                      "attributes": {}})
        for index in range(3):
            agent_id = f"agent:worker:{index}"
            nodes.append({"id": agent_id, "type": "agent", "name": f"Worker {index}",
                          "attributes": {"agent_path": f"/root/worker_{index}"}})
            # Bundled edge metadata contains an XML-invalid NUL separator.
            edges.append({"id": f"model:{index}", "source": agent_id, "target": "model:shared",
                          "relation": "USES", "first_sequence": count + index + 1,
                          "attributes": {}})
    return {"session_id": "visual-parity", "nodes": nodes, "edges": edges,
            "node_count": len(nodes), "edge_count": len(edges), "event_count": count}


@pytest.mark.parametrize("counts", [(1, 2, 3), (2, 8, 18)], ids=["simple", "folded"])
@pytest.mark.parametrize("theme", ["dark", "light"])
def test_downloaded_frames_match_live_view_and_elapsed_time(tmp_path: Path, counts: tuple, theme: str) -> None:
    """Compare decoded product downloads with independent browser screenshots."""
    from PIL import Image, ImageChops, ImageFilter, ImageStat

    manager, executable = _browser()
    with manager as playwright:
        browser = _launch(playwright, executable)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000},
                                    accept_downloads=True, reduced_motion="reduce")
            page.add_init_script(f"localStorage.setItem('execweave-theme', {json.dumps(theme)})")
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            state = {"graph": _evolving_graph(counts[0]), "sequence": 1, "finished": False}
            sent = [0]

            def live(route):
                if sent[0] != state["sequence"]:
                    data = {"kind": "snapshot", "graph": state["graph"]}
                    sent[0] = state["sequence"]
                else:
                    data = {"kind": "noop"}
                data.update(sequence=sent[0], live_finished=state["finished"])
                route.fulfill(json=data)

            page.route("**/live.json?*", live)
            page.route("http://gif.test/", lambda route: route.fulfill(body=DASHBOARD_HTML,
                                                                       content_type="text/html"))
            page.goto("http://gif.test/")
            page.wait_for_selector(".node")
            started = time.monotonic()
            checkpoints = []
            text_regions = []
            for stage, count in enumerate(counts):
                state.update(graph=_evolving_graph(count), sequence=stage + 1)
                page.wait_for_function("count => window.__execweaveCore.getGraph().event_count === count", arg=count)
                page.wait_for_timeout(1100)
                path = tmp_path / f"dashboard-{stage}.png"
                page.locator("#svg").screenshot(path=str(path))
                checkpoints.append(Image.open(path).convert("RGB"))
                text_regions.append(page.evaluate("""() => {
                  const svg=document.getElementById('svg').getBoundingClientRect();
                  return [...document.querySelectorAll('.node .name-label')].map(e=>{
                    const r=e.getBoundingClientRect();
                    return [Math.max(0,Math.floor(r.left-svg.left)),Math.max(0,Math.floor(r.top-svg.top)),
                            Math.min(svg.width,Math.ceil(r.right-svg.left)),Math.min(svg.height,Math.ceil(r.bottom-svg.top))];
                  }).filter(r=>r[2]>r[0]&&r[3]>r[1]);
                }"""))
            state["finished"] = True
            page.wait_for_selector("#download-gif:visible")
            with page.expect_download(timeout=60000) as download_info:
                page.locator("#download-gif").click()
            elapsed = time.monotonic() - started
            output = tmp_path / "recorded.gif"
            download_info.value.save_as(str(output))
            frames, delays = [], []
            with Image.open(output) as gif:
                for index in range(gif.n_frames):
                    gif.seek(index)
                    frame = gif.convert("RGB")
                    frame.save(tmp_path / f"frame-{index:03}.png")
                    frames.append(frame)
                    delays.append(gif.info["duration"])
            assert len(frames) >= 3
            assert all(frame.size == checkpoints[0].size for frame in frames)
            # Encoding time is not part of the recorded timeline.
            assert 3000 <= sum(delays) <= elapsed * 1000 + 300
            matches = []
            for stage, expected in enumerate(checkpoints):
                scores = [sum(ImageStat.Stat(ImageChops.difference(expected, f)).mean) / 3
                          for f in frames]
                best = min(range(len(scores)), key=scores.__getitem__)
                ImageChops.difference(expected, frames[best]).save(tmp_path / f"diff-{stage}.png")
                matches.append(best)
                assert scores[best] < 2.5, {"stage": stage, "scores": scores}
                # Check each node's text/geometry, not just the mostly empty background.
                # Browser LCD subpixel AA and canvas grayscale AA differ at tiny
                # font sizes. Compare lightly smoothed luminance, retaining glyphs.
                text_expected = expected.convert("L").filter(ImageFilter.GaussianBlur(0.5))
                text_actual = frames[best].convert("L").filter(ImageFilter.GaussianBlur(0.5))
                for region in text_regions[stage]:
                    diff = ImageChops.difference(text_expected.crop(region), text_actual.crop(region))
                    assert ImageStat.Stat(diff).mean[0] < 10, (stage, region)
                if stage == len(checkpoints) - 1:
                    assert scores[-1] < 2.5
            assert matches == sorted(set(matches)), matches
            (tmp_path / "comparison.json").write_text(json.dumps({"matches": matches, "delays": delays}))
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
            page.evaluate("""() => {
              window.originalDecode=HTMLImageElement.prototype.decode;
              HTMLImageElement.prototype.decode=()=>Promise.reject(new Error('decode unavailable'));
            }""")
            page.locator("#download-gif").click()
            page.wait_for_function("document.getElementById('gif-notice').textContent.includes('decode unavailable')")
            assert page.locator("#download-gif").is_enabled()
            page.evaluate("() => { HTMLImageElement.prototype.decode=window.originalDecode; }")
            with page.expect_download() as download:
                page.locator("#download-gif").click()
            assert download.value.failure() is None
        finally:
            browser.close()
