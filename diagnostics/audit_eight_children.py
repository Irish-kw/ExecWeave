"""Headed hit-target audit of the existing synthetic Antigravity UI contract.

Ready-made graph/conversation entries bypass native capture: explicitly UI-only.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from uuid import uuid4

from playwright.sync_api import sync_playwright
from execweave.dashboard_shell import render_static_dashboard_html

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tests"))
from test_antigravity_multi_conversation_isolation import CHILDREN, ROOT_ID, _fixture  # noqa: E402


def main() -> int:
    out = REPO / ".execweave-acceptance" / "eight-child-audit" / uuid4().hex[:8]
    out.mkdir(parents=True)
    graph, entries, updated = _fixture()
    long_text = "--long-text" in sys.argv
    if long_text:
        for collection in (entries, updated):
            for entry in collection:
                for message in entry.get("conversation_preview", {}).get("messages", []):
                    if message.get("text") == "ROOT PROMPT TWO":
                        message["text"] += "\n" + ("非英文長提示與空白 Unicode 零信任驗證\n" * 1000)
    viewer = out / "viewer.html"
    viewer.write_text(
        render_static_dashboard_html(graph, conversation_entries=entries), encoding="utf-8"
    )
    results = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        try:
            for width, height in ((1440, 1000), (1920, 1080), (1366, 768), (1280, 720)):
                row = {
                    "viewport": [width, height],
                    "status": "FAIL",
                    "long_text": long_text,
                    "console": [],
                    "children_checked": [],
                }
                results.append(row)
                page = browser.new_page(viewport={"width": width, "height": height})
                page.on("pageerror", lambda error, row=row: row["console"].append(str(error)))
                page.on(
                    "console",
                    lambda message, row=row: (
                        row["console"].append(message.text) if message.type == "error" else None
                    ),
                )

                def click(node_id):
                    page.locator(".node[data-id=" + json.dumps(node_id) + "]").click(timeout=6000)

                try:
                    page.goto(viewer.as_uri())
                    page.wait_for_selector(".node")
                    click(ROOT_ID)
                    page.wait_for_function(
                        "() => document.querySelector('#details').innerText.includes('ROOT FINAL TWO')"
                    )
                    details = page.locator("#details")
                    assert "ROOT PROMPT TWO" in details.inner_text()
                    assert "RESPONSE UNIQUE" not in details.inner_text()
                    row["root_geometry"] = details.evaluate(
                        "e=>{const r=e.getBoundingClientRect();return {bottom:r.bottom, right:r.right, viewportHeight:innerHeight, viewportWidth:innerWidth, pageOverflow:document.documentElement.scrollWidth>innerWidth+1}}"
                    )
                    final = details.get_by_text("ROOT FINAL TWO", exact=True)
                    final.scroll_into_view_if_needed()
                    final_box = final.bounding_box()
                    assert final_box and 0 <= final_box["y"] < height
                    row["root_final_scroll_reachable"] = True
                    fold = page.locator("#details .execweave-agent-older").filter(
                        has_text="ROOT PROMPT ONE"
                    )
                    assert fold.count() == 1 and not fold.evaluate("e=>e.open")
                    fold.locator("summary").click()
                    assert fold.evaluate("e=>e.open")
                    assert "ROOT FINAL ONE" in fold.inner_text()
                    page.evaluate(
                        "entries=>window.__execweaveAgentPanel.setEntries(entries)", updated
                    )
                    assert fold.evaluate("e=>e.open")
                    fold.locator("summary").click()
                    assert not fold.evaluate("e=>e.open")
                    page.screenshot(path=str(out / f"{width}-root.png"))
                    for index, (child, _role, _round) in enumerate(CHILDREN, 1):
                        click(f"agent:antigravity:conversation:{child}")
                        page.wait_for_function(
                            "s=>document.querySelector('#details').innerText.includes(s)",
                            arg=f"RESPONSE UNIQUE {index}",
                        )
                        text = details.inner_text()
                        assert f"TASK UNIQUE {index}" in text and f"THINKING UNIQUE {index}" in text
                        assert "ROOT FINAL" not in text
                        for other in range(1, 9):
                            if other != index:
                                assert f"RESPONSE UNIQUE {other}" not in text
                        row["children_checked"].append(child)
                    page.screenshot(path=str(out / f"{width}-child.png"))
                    row["detail_geometry"] = details.evaluate(
                        "e=>{const r=e.getBoundingClientRect();return {left:r.left,right:r.right,top:r.top,bottom:r.bottom,width:innerWidth,height:innerHeight,scrollWidth:e.scrollWidth,clientWidth:e.clientWidth}}"
                    )
                    assert not page.evaluate("document.documentElement.scrollWidth>innerWidth+1")
                    click(ROOT_ID)
                    assert not fold.evaluate("e=>e.open")
                    page.reload()
                    page.wait_for_selector(".node")
                    click(ROOT_ID)
                    assert "ROOT FINAL TWO" in details.inner_text()
                    assert not row["console"]
                    row["status"] = "PASS"
                except Exception as error:
                    row["failure"] = f"{type(error).__name__}: {error}"
                    page.screenshot(path=str(out / f"{width}-FAILURE.png"))
                finally:
                    page.close()
                    (out / "result.json").write_text(
                        json.dumps(results, indent=2), encoding="utf-8"
                    )
        finally:
            browser.close()
    print(json.dumps({"path": str(out), "results": results}))
    return 0 if all(row["status"] == "PASS" for row in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
