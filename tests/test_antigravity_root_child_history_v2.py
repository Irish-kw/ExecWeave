from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from execweave.antigravity_full_fidelity import antigravity_hook_to_content_events
from execweave.content_store import FullFidelityContentStore
from execweave.conversation_records import conversation_record_entries
from execweave.graph import GraphAccumulator
from execweave.viewer_projection import write_graph_html

ROOT = "root-current-wire"
CHILD_A = "child-current-a"
CHILD_B = "child-current-b"
ROOT_ID = f"agent:antigravity:conversation:{ROOT}"
CHILD_A_ID = f"agent:antigravity:conversation:{CHILD_A}"
CHILD_B_ID = f"agent:antigravity:conversation:{CHILD_B}"


def _brain_transcript(tmp_path: Path, conversation_id: str) -> Path:
    path = tmp_path / "brain" / conversation_id / ".system_generated" / "logs" / "transcript.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _write(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def _root_rows(tmp_path: Path) -> tuple[list[dict[str, object]], list[dict[str, str]]]:
    specs = [
        {"Model": "inherit", "Prompt": "child A first task", "Role": "Role A", "TypeName": "worker", "Workspace": "inherit"},
        {"Model": "inherit", "Prompt": "child B first task", "Role": "Role B", "TypeName": "worker", "Workspace": "inherit"},
    ]
    result = (
        "Created the following subagents:\n"
        + json.dumps({"conversationId": CHILD_A, "logAbsoluteUri": _brain_transcript(tmp_path, CHILD_A).as_uri(), "workspaceUris": [tmp_path.as_uri()]})
        + "\n"
        + json.dumps({"conversationId": CHILD_B, "logAbsoluteUri": _brain_transcript(tmp_path, CHILD_B).as_uri(), "workspaceUris": [tmp_path.as_uri()]})
    )
    rows: list[dict[str, object]] = [
        {"step_index": 0, "source": "USER_EXPLICIT", "type": "USER_INPUT", "status": "DONE", "created_at": "2026-09-01T01:00:00Z", "content": "<USER_REQUEST>root first request</USER_REQUEST>"},
        {"step_index": 1, "source": "MODEL", "type": "PLANNER_RESPONSE", "status": "DONE", "created_at": "2026-09-01T01:00:01Z", "tool_calls": [{"name": "invoke_subagent", "args": {"Subagents": specs}}]},
        {"step_index": 2, "source": "MODEL", "type": "GENERIC", "status": "DONE", "created_at": "2026-09-01T01:00:02Z", "content": result},
        {"step_index": 3, "source": "MODEL", "type": "PLANNER_RESPONSE", "status": "DONE", "created_at": "2026-09-01T01:00:03Z", "content": "root first response"},
        {"step_index": 4, "source": "USER_EXPLICIT", "type": "USER_INPUT", "status": "DONE", "created_at": "2026-09-01T01:00:50Z", "content": "<USER_REQUEST>root second request</USER_REQUEST>"},
        {"step_index": 5, "source": "MODEL", "type": "PLANNER_RESPONSE", "status": "DONE", "created_at": "2026-09-01T01:00:51Z", "content": "root dispatches a new child task"},
    ]
    return rows, specs


def _build(tmp_path: Path) -> tuple[dict[str, object], Path]:
    run_root = tmp_path / "run"
    store = FullFidelityContentStore(run_root)
    root_path = _brain_transcript(tmp_path, ROOT)
    root_rows, specs = _root_rows(tmp_path)
    _write(root_path, root_rows)
    _write(_brain_transcript(tmp_path, CHILD_A), [
        {"step_index": 0, "source": "MODEL", "type": "PLANNER_RESPONSE", "status": "DONE", "created_at": "2026-09-01T01:00:05Z", "content": "child A first response"},
        {"step_index": 4, "source": "MODEL", "type": "PLANNER_RESPONSE", "status": "DONE", "created_at": "2026-09-01T01:01:05Z", "content": "child A second response"},
    ])
    _write(_brain_transcript(tmp_path, CHILD_B), [
        {"step_index": 0, "source": "MODEL", "type": "PLANNER_RESPONSE", "status": "DONE", "created_at": "2026-09-01T01:00:06Z", "content": "child B first response"},
    ])
    graph = GraphAccumulator(session_id="agy-root-child-v2", source_path=run_root / "events.jsonl")
    invoke_payload = {"conversationId": ROOT, "workspacePaths": [str(tmp_path)], "transcriptPath": str(root_path), "stepIdx": 1, "toolCall": {"name": "invoke_subagent", "args": {"Subagents": specs}}}
    for event in antigravity_hook_to_content_events(invoke_payload, hook_event="PostToolUse", store=store, timestamp="2026-09-01T01:00:04Z"):
        graph.apply(event)
    root_stop = {"conversationId": ROOT, "workspacePaths": [str(tmp_path)], "transcriptPath": str(root_path), "executionNum": 1, "terminationReason": "done", "fullyIdle": True}
    for event in antigravity_hook_to_content_events(root_stop, hook_event="Stop", store=store, timestamp="2026-09-01T01:03:00Z"):
        graph.apply(event)
    for child_id in (CHILD_A, CHILD_B):
        stop_payload = {"conversationId": child_id, "workspacePaths": [str(tmp_path)], "transcriptPath": str(_brain_transcript(tmp_path, child_id)), "executionNum": 1, "terminationReason": "done", "fullyIdle": True}
        for event in antigravity_hook_to_content_events(stop_payload, hook_event="Stop", store=store, timestamp="2026-09-01T01:02:00Z"):
            graph.apply(event)
    followup = {"conversationId": ROOT, "stepIdx": 10, "workspacePaths": [str(tmp_path)], "toolCall": {"name": "send_message", "args": {"Recipient": CHILD_A, "Message": "child A second task"}}}
    for event in antigravity_hook_to_content_events(followup, hook_event="PostToolUse", store=store, timestamp="2026-09-01T01:01:00Z"):
        graph.apply(event)
    sibling = {"conversationId": CHILD_B, "stepIdx": 11, "workspacePaths": [str(tmp_path)], "toolCall": {"name": "send_message", "args": {"Recipient": CHILD_A, "Message": "sibling note, not a task"}}}
    for event in antigravity_hook_to_content_events(sibling, hook_event="PostToolUse", store=store, timestamp="2026-09-01T01:01:01Z"):
        graph.apply(event)
    materialized = graph.to_dict()
    materialized["nodes"].append({"id": "agent:Antigravity", "type": "agent", "name": "Antigravity", "attributes": {"provider": "antigravity"}})
    return materialized, run_root


def _entry(entries: list[dict[str, object]], source_id: str) -> dict[str, object]:
    matches = [entry for entry in entries if entry.get("source_id") == source_id and isinstance(entry.get("conversation_preview"), dict)]
    assert len(matches) == 1, (source_id, len(matches))
    return matches[0]


def test_current_generic_result_and_model_field_produce_positive_child_topology(tmp_path: Path) -> None:
    graph, run_root = _build(tmp_path)
    for child_id in (CHILD_A_ID, CHILD_B_ID):
        child = next(node for node in graph["nodes"] if node["id"] == child_id)
        attrs = child["attributes"]
        assert attrs["parent_agent_path"] == "/root"
        assert attrs["parent_scope_id"] == ROOT
        assert attrs["parent_relation_source"] == "provider_validated_child_transcript"
    entries = conversation_record_entries(graph, run_root)
    preview_a = _entry(entries, CHILD_A_ID)["conversation_preview"]
    texts_a = [message["text"] for message in preview_a["messages"]]
    assert texts_a == ["child A first task", "child A first response", "child A second task", "child A second response"]
    second = next(message for message in preview_a["messages"] if message["text"] == "child A second task")
    assert second["phase"] == "assignment"
    assert second["content_role"] == "antigravity_addressed_task"
    assert second["provider_sender_id"] == ROOT
    assert second["provider_recipient_id"] == CHILD_A
    assert second["delivery_observed"] is False
    assert second["consumption_observed"] is False
    assert "sibling note, not a task" not in texts_a
    preview_b = _entry(entries, CHILD_B_ID)["conversation_preview"]
    assert "child A second task" not in [message["text"] for message in preview_b["messages"]]


def _required_browser(playwright: object):
    try:
        return playwright.chromium.launch()
    except Exception as error:  # noqa: BLE001
        if os.environ.get("EXECWEAVE_E2E_REQUIRED", "").lower() not in {"", "0", "false"}:
            pytest.fail(f"Chromium required for Antigravity root/child history gate: {error}")
        pytest.skip(f"Chromium unavailable: {error}")


@pytest.mark.viewer_e2e
def test_dashboard_has_one_root_and_reused_child_has_folded_history(tmp_path: Path) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    graph, run_root = _build(tmp_path)
    entries = conversation_record_entries(graph, run_root)
    viewer = run_root / "viewer.html"
    write_graph_html(graph, viewer)
    with sync_api.sync_playwright() as playwright:
        browser = _required_browser(playwright)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.goto(viewer.as_uri())
            page.wait_for_selector(".node")
            visible = page.eval_on_selector_all(".node", "nodes=>nodes.map(node=>({id:node.dataset.id,text:node.textContent}))")
            ids = [item["id"] for item in visible]
            assert "agent:Antigravity" not in ids
            assert ROOT_ID in ids
            assert "/root" in next(item for item in visible if item["id"] == ROOT_ID)["text"]
            assert "Role A" in next(item for item in visible if item["id"] == CHILD_A_ID)["text"]
            assert "Role B" in next(item for item in visible if item["id"] == CHILD_B_ID)["text"]
            page.eval_on_selector(f'.node[data-id="{CHILD_A_ID}"]', "node=>node.dispatchEvent(new MouseEvent('click',{bubbles:true}))")
            page.wait_for_function("()=>(document.getElementById('details')?.innerText||'').includes('child A second task')")
            details = page.locator("#details")
            current = details.inner_text()
            assert "child A second task" in current
            assert "child A second response" in current
            assert "sibling note, not a task" not in current
            assert details.locator(".execweave-agent-older").count() == 1
            older = details.locator(".execweave-agent-older").first
            assert not older.evaluate("node=>node.open")
            older.locator("summary").click()
            assert older.evaluate("node=>node.open")
            expanded = older.inner_text()
            assert "child A first task" in expanded
            assert "child A first response" in expanded
            assert "child A second task" not in expanded
            assert "child A second response" not in expanded
            page.evaluate("items=>window.__execweaveAgentPanel.setEntries(items)", entries)
            persisted = details.locator(".execweave-agent-older").first
            assert persisted.evaluate("node=>node.open")
            persisted_text = persisted.inner_text()
            assert "child A first task" in persisted_text
            assert "child A first response" in persisted_text
        finally:
            browser.close()
