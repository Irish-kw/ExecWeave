"""Arrange must preserve the same semantic lane and evidence-band contracts as first load."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from test_graph_node_sizing_e2e import LONG_LABEL, _browser, _launch, _nodes, _render

pytestmark = pytest.mark.viewer_e2e

_ORPHAN_FILES = "viewer-cluster:orphan-files"


def _arrange_graph() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "nodes": [
            {
                "id": "process:p",
                "type": "process",
                "name": LONG_LABEL,
                "attributes": {},
            },
            {
                "id": "agent:/root",
                "type": "agent",
                "name": "/root",
                "attributes": {"agent_role": "root", "agent_path": "/root"},
            },
            {
                "id": "agent:/root/a",
                "type": "agent",
                "name": "a",
                "attributes": {"agent_role": "child", "agent_path": "/root/a"},
            },
            {
                "id": "file:connected",
                "type": "file",
                "name": "connected.md",
                "attributes": {},
            },
            {
                "id": "file:orphan",
                "type": "file",
                "name": "orphan.tmp",
                "attributes": {},
            },
        ],
        "edges": [
            {
                "id": "e0",
                "source": "process:p",
                "target": "agent:/root",
                "relation": "STARTED_AGENT",
                "attributes": {},
            },
            {
                "id": "e1",
                "source": "agent:/root",
                "target": "agent:/root/a",
                "relation": "SPAWNED_AGENT",
                "attributes": {},
            },
            {
                "id": "e2",
                "source": "agent:/root/a",
                "target": "file:connected",
                "relation": "WROTE_FILE",
                "attributes": {},
            },
        ],
    }


def _assert_constraints(nodes: list[dict[str, Any]]) -> None:
    drawn = {node["id"]: node for node in nodes}
    process = drawn["process:p"]
    root = drawn["agent:/root"]
    connected = drawn["file:connected"]
    orphan = drawn[_ORPHAN_FILES]

    assert process["width"] > 160, "fixture must exercise adaptive lane width"
    assert process["x"] + process["width"] <= root["x"], (
        f"wide runtime reaches into root lane after Arrange: process={process}, root={root}"
    )
    assert connected["y"] < orphan["y"], (
        f"connected evidence was demoted into the detached band after Arrange: "
        f"connected={connected}, orphan={orphan}"
    )


def test_arrange_keeps_semantic_lane_widths_and_evidence_bands(tmp_path: Path) -> None:
    viewer = _render(tmp_path, _arrange_graph())
    manager, executable = _browser()
    with manager as playwright:
        browser = _launch(playwright, executable)
        try:
            page = browser.new_page(viewport={"width": 1600, "height": 900})
            page.goto(viewer.as_uri())
            _assert_constraints(_nodes(page))

            arrange = page.locator("#arrange")
            assert arrange.count() == 1, "dashboard lost the Arrange control"
            arrange.click()
            page.wait_for_timeout(150)
            _assert_constraints(_nodes(page))
        finally:
            browser.close()
