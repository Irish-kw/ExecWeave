from __future__ import annotations

from pathlib import Path

import pytest

from execweave.dashboard_shell import render_static_dashboard_html
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


def test_download_gif_is_nonzero_valid_and_repeatable(tmp_path: Path) -> None:
    viewer = tmp_path / "viewer.html"
    viewer.write_text(render_static_dashboard_html(_gif_graph()), encoding="utf-8")
    manager, executable = _browser()
    with manager as playwright:
        browser = _launch(playwright, executable)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000}, accept_downloads=True)
            page_errors: list[str] = []
            page.on("pageerror", lambda error: page_errors.append(str(error)))
            page.goto(viewer.as_uri())
            page.wait_for_selector(".node", timeout=15000)
            page.eval_on_selector("#finished-actions", "element => element.hidden=false")
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
                sizes.append(len(payload))
                page.wait_for_function(
                    "() => !document.getElementById('download-gif').disabled", timeout=5000
                )

            assert all(size > 0 for size in sizes)
            assert not page_errors
            assert page.locator(".node").count() > 0
        finally:
            browser.close()
