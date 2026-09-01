from __future__ import annotations

import os
from pathlib import Path

import pytest

from execweave.viewer_projection import write_graph_html

MAIN = "main-real-wire"
CHILD = "child-real-wire"
MAIN_ID = f"agent:antigravity:conversation:{MAIN}"
CHILD_ID = f"agent:antigravity:conversation:{CHILD}"


def _edge(
    edge_id: str, source: str, target: str, relation: str, sequence: int, second: int
) -> dict[str, object]:
    stamp = f"2026-09-01T08:00:{second:02d}Z"
    return {
        "id": edge_id,
        "source": source,
        "target": target,
        "relation": relation,
        "count": 1,
        "first_sequence": sequence,
        "last_sequence": sequence,
        "first_seen": stamp,
        "last_seen": stamp,
    }


def _graph() -> dict[str, object]:
    generic = {
        "id": "agent:antigravity",
        "type": "agent",
        "name": "Antigravity",
        "attributes": {"provider": "antigravity", "agent_role": "root"},
    }
    main = {
        "id": MAIN_ID,
        "type": "agent",
        "name": "Antigravity conversation",
        "attributes": {
            "provider": "antigravity",
            "conversation_id": MAIN,
            "agent_role": "root",
            "agent_path": "/root",
        },
    }
    # Deliberately carries stale root-looking archive metadata. Positive parent scope must win.
    child = {
        "id": CHILD_ID,
        "type": "agent",
        "name": "worker",
        "attributes": {
            "provider": "antigravity",
            "conversation_id": CHILD,
            "agent_role": "root",
            "root_agent_path": "/root",
            "parent_agent_path": "/root",
            "parent_scope_id": MAIN_ID,
            "agent_path": f"/root/{CHILD}",
        },
    }
    tool_a = {
        "id": "tool:antigravity:run_command:a",
        "type": "tool",
        "name": "run_command",
        "attributes": {"provider": "antigravity", "native_name": "run_command"},
    }
    tool_b = {
        "id": "tool:antigravity:run_command:b",
        "type": "tool",
        "name": "run_command",
        "attributes": {"provider": "antigravity", "native_name": "run_command"},
    }
    call_1 = {
        "id": f"tool-call:antigravity:{MAIN}:one",
        "type": "tool_call",
        "name": "run_command",
        "attributes": {
            "provider": "antigravity",
            "tool_name": "run_command",
            "conversation_id": MAIN,
            "step_index": 7,
            "arguments": {"command": "echo one"},
            "output": "one",
        },
    }
    obs_1 = {
        "id": f"tool-call-observation:antigravity:{MAIN}:7",
        "type": "tool_call_observation",
        "name": "run_command",
        "attributes": {
            "provider": "antigravity",
            "tool_name": "run_command",
            "conversation_id": MAIN,
            "step_index": 7,
        },
    }
    call_2 = {
        "id": f"tool-call:antigravity:{MAIN}:two",
        "type": "tool_call",
        "name": "run_command",
        "attributes": {
            "provider": "antigravity",
            "tool_name": "run_command",
            "conversation_id": MAIN,
            "step_index": 8,
            "arguments": {"command": "echo two"},
            "output": "two",
        },
    }
    obs_2 = {
        "id": f"tool-call-observation:antigravity:{MAIN}:8",
        "type": "tool_call_observation",
        "name": "run_command",
        "attributes": {
            "provider": "antigravity",
            "tool_name": "run_command",
            "conversation_id": MAIN,
            "step_index": 8,
        },
    }
    input_1 = {
        "id": "observed-content:input:one",
        "type": "observed_content",
        "name": "antigravity.tool_input",
        "attributes": {
            "content_kind": "antigravity.tool_input",
            "sha256": "111",
            "path": "content/111.json",
            "size_bytes": 22,
        },
    }
    input_2 = {
        "id": "observed-content:input:two",
        "type": "observed_content",
        "name": "antigravity.tool_input",
        "attributes": {
            "content_kind": "antigravity.tool_input",
            "sha256": "222",
            "path": "content/222.json",
            "size_bytes": 22,
        },
    }
    nodes = [generic, main, child, tool_a, tool_b, call_1, obs_1, call_2, obs_2, input_1, input_2]
    edges = [
        _edge("spawn", MAIN_ID, CHILD_ID, "SPAWNED_AGENT", 1, 1),
        _edge("request-1", MAIN_ID, call_1["id"], "REQUESTED_TOOL_CALL", 2, 2),
        _edge("uses-1", call_1["id"], tool_a["id"], "USES_TOOL", 3, 3),
        _edge("input-1", obs_1["id"], input_1["id"], "OBSERVED_TOOL_INPUT_AFTER_EXECUTION", 4, 4),
        _edge("request-2", MAIN_ID, call_2["id"], "REQUESTED_TOOL_CALL", 5, 5),
        _edge("uses-2", call_2["id"], tool_b["id"], "USES_TOOL", 6, 6),
        _edge("input-2", obs_2["id"], input_2["id"], "OBSERVED_TOOL_INPUT_AFTER_EXECUTION", 7, 7),
    ]
    return {
        "graph_schema_version": "0.2",
        "session_id": "root-layout-tool-aggregation",
        "event_count": 7,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "nodes": nodes,
        "edges": edges,
    }


def _required_browser(playwright: object):
    try:
        return playwright.chromium.launch()
    except Exception as error:  # noqa: BLE001
        if os.environ.get("EXECWEAVE_E2E_REQUIRED", "").lower() not in {"", "0", "false"}:
            pytest.fail(f"Chromium required for root/layout/tool-call gate: {error}")
        pytest.skip(f"Chromium unavailable: {error}")


def test_dashboard_source_contains_drag_arrange_and_occurrence_contract() -> None:
    from execweave import live as live_module

    html = live_module._LIVE_HTML
    assert 'id="arrange"' in html
    assert "window.__execweaveArrangeGraph=execweaveArrangeGraph" in html
    assert "execweaveDragBound" in html
    assert "tool_call_observation" in html
    assert "viewer_tool_call_occurrences" in html
    assert "viewer_root_selection" in html


@pytest.mark.viewer_e2e
def test_real_shape_dashboard_root_drag_arrange_and_tool_occurrences(tmp_path: Path) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    viewer = tmp_path / "viewer.html"
    write_graph_html(_graph(), viewer)
    with sync_api.sync_playwright() as playwright:
        browser = _required_browser(playwright)
        try:
            page = browser.new_page(viewport={"width": 1600, "height": 1050})
            page.goto(viewer.as_uri())
            page.wait_for_selector(".node")
            display = page.evaluate("()=>window.__execweaveCore.getDisplayGraph()")
            agents = [node for node in display["nodes"] if node.get("type") == "agent"]
            assert [node["id"] for node in agents if node.get("name") == "/root"] == [MAIN_ID]
            assert "agent:antigravity" not in {node["id"] for node in agents}
            main = next(node for node in agents if node["id"] == MAIN_ID)
            child = next(node for node in agents if node["id"] == CHILD_ID)
            assert main["attributes"]["viewer_root"] is True
            assert child["attributes"]["viewer_root"] is False
            assert (
                page.locator(f'.node[data-id="{MAIN_ID}"]').get_attribute("data-layout-lane")
                == "root"
            )
            assert (
                page.locator(f'.node[data-id="{CHILD_ID}"]').get_attribute("data-layout-lane")
                == "agent"
            )

            assert not [
                node
                for node in display["nodes"]
                if node.get("type") in {"tool_call", "tool_call_observation"}
            ]
            tools = [node for node in display["nodes"] if node.get("type") == "tool"]
            assert len(tools) == 1
            tool = tools[0]
            assert tool["attributes"]["viewer_occurrence_count"] == 2
            occurrences = tool["attributes"]["viewer_tool_call_occurrences"]
            assert [item["input"]["command"] for item in occurrences] == ["echo one", "echo two"]
            assert [item["output"] for item in occurrences] == ["one", "two"]
            assert all(len(item["call_ids"]) == 2 for item in occurrences)
            tool_edges = [
                edge for edge in display["edges"] if edge.get("relation") == "CALLED_TOOL"
            ]
            assert len(tool_edges) == 1 and tool_edges[0]["count"] == 2

            tool_id = tool["id"]
            page.locator(f'.node[data-id="{tool_id}"]').click()
            details = page.locator("#details")
            page.wait_for_function(
                "()=>(document.getElementById('details')?.innerText||'').includes('Invocations · 2 calls')"
            )
            assert "Invocations · 2 calls" in details.inner_text()
            folds = details.locator(".execweave-tool-occurrence")
            assert folds.count() == 2
            for index, command in enumerate(("echo one", "echo two")):
                folds.nth(index).locator("summary").click()
                assert command in folds.nth(index).inner_text()

            root = page.locator(f'.node[data-id="{MAIN_ID}"]')
            before = page.evaluate(
                "id=>{const p=window.__execweaveCore.getPositions().get(id);return{x:p.x,y:p.y}}",
                MAIN_ID,
            )
            box = root.bounding_box()
            assert box is not None
            page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            page.mouse.down()
            page.mouse.move(
                box["x"] + box["width"] / 2 + 180, box["y"] + box["height"] / 2 + 120, steps=8
            )
            page.mouse.up()
            after_drag = page.evaluate(
                "id=>{const p=window.__execweaveCore.getPositions().get(id);return{x:p.x,y:p.y}}",
                MAIN_ID,
            )
            assert (
                abs(after_drag["x"] - before["x"]) > 50 or abs(after_drag["y"] - before["y"]) > 50
            )

            page.locator("#arrange").click()
            page.wait_for_timeout(350)
            after_arrange = page.evaluate(
                "id=>{const p=window.__execweaveCore.getPositions().get(id);return{x:p.x,y:p.y}}",
                MAIN_ID,
            )
            assert (
                abs(after_arrange["x"] - after_drag["x"]) > 30
                or abs(after_arrange["y"] - after_drag["y"]) > 30
            )
            assert (
                page.locator(f'.node[data-id="{MAIN_ID}"]').get_attribute("data-layout-lane")
                == "root"
            )
            assert (
                page.locator(f'.node[data-id="{CHILD_ID}"]').get_attribute("data-layout-lane")
                == "agent"
            )

            page.locator(f'.node[data-id="{tool_id}"]').click()
            screenshot = os.environ.get("EXECWEAVE_REAL_DASHBOARD_SCREENSHOT")
            if screenshot:
                Path(screenshot).parent.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=screenshot, full_page=True)
        finally:
            browser.close()
