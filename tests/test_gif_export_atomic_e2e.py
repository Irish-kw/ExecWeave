"""Real Chromium + decoded pixels; isolated renderer scope, not HTTP/auth acceptance."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from PIL import Image, ImageChops, ImageStat

from execweave.dashboard_shell import render_static_dashboard_html
from test_viewer_agent_isolation_e2e import _browser, _launch

pytestmark = pytest.mark.viewer_e2e


def _graph() -> dict:
    nodes = [{"id": "agent:root", "type": "agent", "name": "/root", "attributes": {"agent_path": "/root"}}]
    edges = []
    for index in range(6):
        nodes.append({"id": f"file:{index}", "type": "file", "name": f"report-{index}.txt", "attributes": {"path": f"/work/report-{index}.txt"}})
        edges.append({"id": f"write:{index}", "source": "agent:root", "target": f"file:{index}", "relation": "WROTE", "first_sequence": index + 1})
    return {"session_id": "atomic-gif", "nodes": nodes, "edges": edges, "node_count": len(nodes), "edge_count": len(edges)}


def _out(tmp_path: Path, name: str) -> Path:
    root = Path(os.environ.get("EXECWEAVE_VISUAL_ARTIFACT_DIR", str(tmp_path)))
    out = root / name
    out.mkdir(parents=True, exist_ok=True)
    return out


@pytest.mark.parametrize("theme", ["dark", "light"])
@pytest.mark.parametrize("mutation", ["filter", "theme", "viewport"])
def test_export_keeps_one_view_and_decoded_frames_grow_one_node_at_a_time(
    tmp_path: Path, theme: str, mutation: str
) -> None:
    out = _out(tmp_path, f"gif-atomic-{theme}-{mutation}")
    manager, executable = _browser()
    with manager as playwright:
        browser = _launch(playwright, executable)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000}, accept_downloads=True, reduced_motion="reduce")
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.set_content(render_static_dashboard_html(_graph()))
            page.wait_for_selector(".node")
            if page.locator("html").get_attribute("data-theme") != theme:
                page.locator("#theme-toggle").click()
            page.wait_for_timeout(300)
            assert page.locator(".node").count() == 7
            page.locator("#svg").screenshot(path=str(out / "expected.png"))
            expected = Image.open(out / "expected.png").convert("RGB")
            regions = page.evaluate("""() => {
              const svg=document.getElementById('svg').getBoundingClientRect();
              return [...document.querySelectorAll('.node')].map(node=>{
                const r=node.querySelector('rect').getBoundingClientRect();
                return {id:node.dataset.id,box:[Math.ceil(r.left-svg.left+5),Math.ceil(r.top-svg.top+5),Math.floor(r.right-svg.left-5),Math.floor(r.bottom-svg.top-5)]};
              });
            }""")
            for region in regions:
                x1, y1, x2, y2 = region["box"]
                assert 0 <= x1 < x2 <= expected.width and 0 <= y1 < y2 <= expected.height
            # Hold the first decoder only to create a deterministic scheduling
            # window. It still decodes the real SVG and the downloaded GIF below.
            page.evaluate("""() => {
              const decode=HTMLImageElement.prototype.decode;
              window.__held=false;window.__released=false;
              HTMLImageElement.prototype.decode=async function(){
                if(!window.__held){window.__held=true;while(!window.__released)await new Promise(r=>setTimeout(r,10));}
                return decode.call(this);
              };
            }""")
            with page.expect_download(timeout=60000) as download:
                page.locator("#download-gif").click()
                page.wait_for_function("window.__held")
                if mutation == "filter":
                    page.locator("#file-graph-filter").select_option("hide")
                    page.wait_for_function("window.__execweaveCore.getDisplayGraph().nodes.length===1")
                elif mutation == "theme":
                    page.locator("#theme-toggle").click()
                else:
                    page.set_viewport_size({"width": 1100, "height": 780})
                page.evaluate("window.__released=true")
            download.value.save_as(str(out / "replay.gif"))
            decoded = []
            delays = []
            with Image.open(out / "replay.gif") as gif:
                for index in range(gif.n_frames):
                    gif.seek(index)
                    decoded.append(gif.convert("RGB"))
                    delays.append(gif.info["duration"])
            assert len(decoded) == 7
            seen = set()
            evidence = []
            for index, frame in enumerate(decoded):
                assert frame.size == expected.size
                frame.save(out / f"frame-{index:02}.png")
                scores = {r["id"]: sum(ImageStat.Stat(ImageChops.difference(expected.crop(r["box"]), frame.crop(r["box"]))).mean) / 3 for r in regions}
                visible = {node_id for node_id, score in scores.items() if score < 8}
                evidence.append({"frame": index, "visible": sorted(visible), "scores": scores})
                assert seen <= visible, evidence  # No previously seen node disappears.
                assert len(visible - seen) == 1, evidence
                seen = visible
            assert seen == {r["id"] for r in regions}
            score = sum(ImageStat.Stat(ImageChops.difference(expected, decoded[-1])).mean) / 3
            assert score < 2.5, score
            assert delays[-1] >= 800
            assert "Saved node-by-node replay" in page.locator("#gif-notice").inner_text()
            assert page.locator("#download-gif").is_enabled()
            assert not errors
            (out / "decoded-evidence.json").write_text(json.dumps({"renderer_scope": "in-memory shipped Dashboard, not origin/auth acceptance", "theme": theme, "mutation": mutation, "frames": evidence, "final_pixel_mae": score, "delays": delays, "errors": errors}, indent=2), encoding="utf-8")
        finally:
            browser.close()


def test_snapshot_error_is_reported_and_a_second_download_recovers(tmp_path: Path) -> None:
    out = _out(tmp_path, "gif-snapshot-error-retry")
    manager, executable = _browser()
    with manager as playwright:
        browser = _launch(playwright, executable)
        try:
            page = browser.new_page(accept_downloads=True, reduced_motion="reduce")
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.set_content(render_static_dashboard_html(_graph()))
            page.wait_for_selector(".node")
            page.evaluate("""() => {
              const original=window.getComputedStyle;
              window.__restoreStyle=()=>{window.getComputedStyle=original};
              window.getComputedStyle=()=>{throw new Error('snapshot-style-failure')};
            }""")
            # Invoke the real button handler without forcing Playwright's own
            # actionability machinery to call the temporarily failing style API.
            page.evaluate("document.getElementById('download-gif').click()")
            page.wait_for_function("document.getElementById('gif-notice').textContent.includes('snapshot-style-failure')", timeout=5000)
            page.evaluate("window.__restoreStyle()")
            assert page.locator("#download-gif").is_enabled()
            with page.expect_download(timeout=60000) as download:
                page.locator("#download-gif").click()
            download.value.save_as(str(out / "recovered.gif"))
            with Image.open(out / "recovered.gif") as gif:
                assert gif.n_frames == 7
                for index in range(gif.n_frames):
                    gif.seek(index)
                    gif.load()
            assert not errors
        finally:
            browser.close()
