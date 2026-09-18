"""Framework task navigation must not invent provider delegation semantics."""
from __future__ import annotations

import json
import os
import shutil
from copy import deepcopy

import pytest

from execweave.framework_adapters import AdapterContext, CAMELAdapter, ContentCapturePolicy
from execweave.graph import GraphAccumulator
from execweave.viewer_content_browser import inject_content_browser


@pytest.fixture
def page():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as runtime:
        executable = os.environ.get("EXECWEAVE_E2E_CHROMIUM") or shutil.which("chromium")
        browser = runtime.chromium.launch(
            **({"executable_path": executable} if executable else {})
        )
        current = browser.new_page()
        errors = []
        current.on("pageerror", lambda error: errors.append(str(error)))
        current.set_content(inject_content_browser(
            '<html><body><div id="nodes"></div><div id="details"></div></body></html>'
        ))
        try:
            yield current
            assert errors == []
        finally:
            browser.close()


def task_graph(relation="ASSIGNED_TO", *, task_type="task", owner_type="agent"):
    return {
        "session_id": "task-contract",
        "nodes": [
            {"id": "worker", "type": owner_type, "name": "same label"},
            {"id": "other", "type": "agent", "name": "same label"},
            {"id": "task", "type": task_type},
            {"id": "body", "type": "observed_content", "attributes": {
                "content_kind": "test.task_prompt", "sha256": "c" * 64,
                "path": f"content/sha256/{'c' * 64}.txt", "size_bytes": 64,
            }},
        ],
        "edges": [
            {"id": "assignment", "source": "task", "target": "worker", "relation": relation},
            {"id": "content", "source": "task", "target": "body", "relation": "HAS_TASK_CONTENT"},
        ],
    }


def rows(page, graph, selected="worker"):
    before = deepcopy(graph)
    result = page.evaluate(
        "([graph,id])=>{const before=JSON.stringify(graph);"
        "const rows=window.__execweaveRecordedSources.rowsFor(graph,graph,id);"
        "return {rows,unchanged:before===JSON.stringify(graph)}}",
        [graph, selected],
    )
    assert graph == before and result["unchanged"]
    return result["rows"]


@pytest.mark.viewer_e2e
def test_real_adapter_assignment_reaches_only_its_assigned_agent(page, tmp_path):
    context = AdapterContext(
        framework="camel", run_id="task-contract", session_id="task-contract",
        sidecar=tmp_path / "semantic.jsonl", content_root=tmp_path,
        capture_policy=ContentCapturePolicy("prompt_and_response"),
    )
    adapter = CAMELAdapter(context)
    worker = adapter.agent_created("worker", name="same label")
    other = adapter.agent_created("other", name="same label")
    task = adapter.task_created("task", content="Inspect this assigned task.")
    adapter.task_assigned(task, worker)
    events = [json.loads(line) for line in (tmp_path / "semantic.jsonl").read_text(encoding="utf-8").splitlines()]
    assignment = next(event for event in events if event["relation"] == "ASSIGNED_TO")
    assert assignment["source"]["type"] == "task"
    assert assignment["target"]["type"] == "agent"
    accumulator = GraphAccumulator(session_id="task-contract", source_path=tmp_path / "events.jsonl")
    for event in events:
        accumulator.apply(event)
    graph = accumulator.to_dict()
    found = rows(page, graph, worker.id)
    assert found and all(row["source_id"] == task.id for row in found)
    assert all(row["source_relation"] == "ASSIGNED_TO" for row in found)
    assert rows(page, graph, other.id) == []


@pytest.mark.viewer_e2e
@pytest.mark.parametrize("relation", [
    "ASSIGNED_AGENT_TASK", "REQUESTED_SUBTASK", "TARGETS_AGENT_PROFILE",
    "HAS_CHILD_AGENT_SESSION", "TASK_COMPLETED", "UNKNOWN_RELATION",
])
def test_other_relations_are_not_framework_task_assignments(page, relation):
    assert rows(page, task_graph(relation)) == []


@pytest.mark.viewer_e2e
@pytest.mark.parametrize("owner_type", ["process", "model", "tool", "agent_profile"])
def test_task_assignment_target_must_be_an_agent(page, owner_type):
    assert rows(page, task_graph(owner_type=owner_type)) == []


@pytest.mark.viewer_e2e
@pytest.mark.parametrize("task_type", ["subtask", "tool_call", "model_call"])
def test_task_assignment_source_must_be_a_framework_task(page, task_type):
    assert rows(page, task_graph(task_type=task_type)) == []


@pytest.mark.viewer_e2e
@pytest.mark.parametrize("marker", ["inferred", "viewer_only"])
def test_synthetic_assignment_is_not_raw_ownership_evidence(page, marker):
    graph = task_graph()
    graph["edges"][0][marker] = True
    assert rows(page, graph) == []


@pytest.mark.viewer_e2e
def test_assignment_direction_is_not_reversed(page):
    graph = task_graph()
    graph["edges"][0].update(source="worker", target="task")
    assert rows(page, graph) == []


@pytest.mark.viewer_e2e
def test_noncausal_observed_assignment_remains_valid(page):
    graph = task_graph()
    graph["edges"][0].update(causal=False, inferred=False, viewer_only=False)
    assert len(rows(page, graph)) == 1
    assert rows(page, graph, "other") == []


@pytest.mark.viewer_e2e
def test_rejected_assignment_does_not_hide_direct_task_content(page):
    graph = task_graph("ASSIGNED_AGENT_TASK")
    assert rows(page, graph) == []
    found = rows(page, graph, "task")
    assert len(found) == 1 and found[0]["edge_id"] == "content"


@pytest.mark.viewer_e2e
def test_assigned_task_panel_opens_shared_reader(page):
    graph = task_graph()
    page.evaluate("graph=>{window.__execweaveStaticMode=true;window.__execweaveStaticGraph=graph;}", graph)
    page.evaluate("document.getElementById('nodes').innerHTML='<button class=\"node selected\" data-id=\"worker\">Worker</button>'")
    panel = page.locator("#execweave-recorded-sources")
    panel.wait_for(state="visible")
    assert panel.locator(".execweave-source-card").count() == 1
    panel.get_by_role("button", name="Read HAS_TASK_CONTENT", exact=True).click()
    assert page.locator("#execweave-content-dialog").get_attribute("data-state") == "folder_required"
    assert "worker" in page.locator("#execweave-content-meta").inner_text()
    page.get_by_role("button", name="Close", exact=True).click()
    page.evaluate("document.querySelector('.node').dataset.id='other'")
    page.wait_for_function("!document.getElementById('execweave-recorded-sources')")
