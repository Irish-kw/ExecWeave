from pathlib import Path


def replace_once(path_s: str, old: str, new: str) -> None:
    path = Path(path_s)
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"guard failed for {path_s}: expected 1 occurrence, got {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    "src/execweave/antigravity_subagent_linkage.py",
    '    allowed = {"Prompt", "Role", "TypeName", "Workspace"}\n',
    '    # Current Antigravity includes Model in each invoke_subagent spec.\n'
    '    # Keep the allow-list strict while accepting that live-verified field.\n'
    '    allowed = {"Model", "Prompt", "Role", "TypeName", "Workspace"}\n',
)
replace_once(
    "src/execweave/antigravity_subagent_linkage.py",
    '''        workspace = raw.get("Workspace")
        if workspace is not None and (not isinstance(workspace, str) or not workspace):
            return None
        specs.append(dict(raw))
''',
    '''        model = raw.get("Model")
        if model is not None and (not isinstance(model, str) or not model):
            return None
        workspace = raw.get("Workspace")
        if workspace is not None and (not isinstance(workspace, str) or not workspace):
            return None
        specs.append(dict(raw))
''',
)
replace_once(
    "src/execweave/antigravity_subagent_linkage.py",
    '''def _matching_result(record: dict[str, Any]) -> list[dict[str, Any]] | None:
    if record.get("source") != "MODEL":
        return None
    if record.get("type") != "INVOKE_SUBAGENT" or record.get("status") != "DONE":
        return None
    return _parse_result_content(record.get("content"))
''',
    '''def _matching_result(record: dict[str, Any]) -> list[dict[str, Any]] | None:
    if record.get("source") != "MODEL" or record.get("status") != "DONE":
        return None
    # Older builds labelled the immediate result INVOKE_SUBAGENT; the current
    # live wire labels that same record GENERIC. GENERIC is accepted only if its
    # payload passes _parse_result_content's exact provider prefix/schema checks.
    if record.get("type") not in {"INVOKE_SUBAGENT", "GENERIC"}:
        return None
    return _parse_result_content(record.get("content"))
''',
)

replace_once(
    "src/execweave/conversation_preview.py",
    '''        "agent_nickname": (
            attrs.get("agent_nickname")
            if isinstance(attrs.get("agent_nickname"), str)
            else None
        ),
        **topology.to_dict(),
''',
    '''        "agent_nickname": (
            attrs.get("agent_nickname")
            if isinstance(attrs.get("agent_nickname"), str)
            else None
        ),
        "parent_scope_id": (
            attrs.get("parent_scope_id")
            if isinstance(attrs.get("parent_scope_id"), str)
            else None
        ),
        **topology.to_dict(),
''',
)

path = Path("src/execweave/conversation_records.py")
text = path.read_text(encoding="utf-8")
marker = '''def _restore_complete_histories(
    entries: list[dict[str, Any]],
    snapshots: list[tuple[dict[str, Any], dict[str, Any]]],
) -> None:
'''
if text.count(marker) != 1:
    raise SystemExit("conversation_records helper marker changed")
helper = '''def _project_antigravity_addressed_tasks(
    entries: list[dict[str, Any]],
    snapshots: list[tuple[dict[str, Any], dict[str, Any]]],
) -> None:
    """Project exact parent-addressed send_message text into the child timeline.

    This is presentation-only. Antigravity exposes an exact recipient conversation ID
    for send_message, but does not expose delivery/consumption. We therefore use the
    message as a task opener only when the recipient already has positive child topology
    and the exact sender matches that child's provider parent_scope_id. Raw evidence is
    unchanged and the projected message explicitly remains delivery_observed=False.
    """
    prefix = "agent:antigravity:conversation:"
    children: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if str(entry.get("provider") or "").lower() != "antigravity":
            continue
        source_id = entry.get("source_id")
        preview = entry.get("conversation_preview")
        if not isinstance(source_id, str) or not source_id.startswith(prefix):
            continue
        if not isinstance(preview, dict) or not preview.get("parent_agent_path"):
            continue
        parent_scope = preview.get("parent_scope_id")
        if not isinstance(parent_scope, str) or not parent_scope:
            continue
        children[source_id.removeprefix(prefix)] = entry

    additions: dict[str, list[dict[str, Any]]] = {child_id: [] for child_id in children}
    for observed_entry, observed_preview in snapshots:
        if str(observed_entry.get("provider") or "").lower() != "antigravity":
            continue
        for message in observed_preview.get("messages") or []:
            if not isinstance(message, dict) or message.get("kind") != "send_message":
                continue
            sender = message.get("sender")
            recipient = message.get("recipient")
            if not isinstance(sender, str) or not sender.startswith("antigravity:"):
                continue
            if not isinstance(recipient, str) or not recipient.startswith("antigravity:"):
                continue
            sender_id = sender.removeprefix("antigravity:")
            child_id = recipient.removeprefix("antigravity:")
            child_entry = children.get(child_id)
            if child_entry is None:
                continue
            child_preview = child_entry["conversation_preview"]
            if child_preview.get("parent_scope_id") != sender_id:
                continue
            task = dict(message)
            task.update(
                {
                    "kind": "task",
                    "phase": "assignment",
                    "sender": str(child_preview.get("parent_agent_path") or "/root"),
                    "recipient": str(child_preview.get("agent_path") or ""),
                    "content_role": "antigravity_addressed_task",
                    "provider_sender_id": sender_id,
                    "provider_recipient_id": child_id,
                    "delivery_observed": False,
                    "consumption_observed": False,
                }
            )
            additions[child_id].append(task)

    for child_id, tasks in additions.items():
        if not tasks:
            continue
        preview = children[child_id]["conversation_preview"]
        combined = [
            dict(message)
            for message in preview.get("messages") or []
            if isinstance(message, dict)
        ] + tasks
        combined.sort(
            key=lambda message: (
                str(message.get("timestamp") or ""),
                message.get("ordinal")
                if isinstance(message.get("ordinal"), int)
                else 2**63 - 1,
            )
        )
        seen: set[tuple[object, ...]] = set()
        messages: list[dict[str, Any]] = []
        for message in combined:
            key = _history_message_key(message)
            if key in seen:
                continue
            seen.add(key)
            messages.append(message)
        preview["message_count"] = len(messages)
        preview["messages_truncated"] = False
        preview["messages"] = messages


'''
text = text.replace(marker, helper + marker, 1)
old = '''    _core_merge_conversation_previews(entries)
    _repair_parent_thread_aliases(entries)
    _restore_complete_histories(entries, snapshots)
'''
new = '''    _core_merge_conversation_previews(entries)
    _repair_parent_thread_aliases(entries)
    _restore_complete_histories(entries, snapshots)
    _project_antigravity_addressed_tasks(entries, snapshots)
'''
if text.count(old) != 1:
    raise SystemExit("conversation_records post-merge marker changed")
path.write_text(text.replace(old, new, 1), encoding="utf-8")

replace_once(
    "src/execweave/viewer_agent_panel.py",
    '''function canonicalRootRecord(){
  const roots=entries.filter(entryHasRootAuthority);
  const sourceIds=[...new Set(roots.map(entry=>String(entry?.source_id||'')).filter(Boolean))];
  if(sourceIds.length!==1)return null;
  return aggregate(roots.filter(entry=>String(entry?.source_id||'')===sourceIds[0]));
}
''',
    '''function canonicalRootRecord(){
  const roots=entries.filter(entryHasRootAuthority);
  const sourceIds=[...new Set(roots.map(entry=>String(entry?.source_id||'')).filter(Boolean))];
  if(sourceIds.length===1)return aggregate(roots.filter(entry=>String(entry?.source_id||'')===sourceIds[0]));
  if(sourceIds.length)return null;
  const agy=entries.filter(entry=>{
    const preview=entry?.conversation_preview;
    return String(entry?.provider||'').toLowerCase()==='antigravity'&&!!preview&&
      String(entry?.source_id||'').startsWith('agent:antigravity:conversation:')&&
      !String(preview.parent_agent_path||'').trim();
  });
  const agyIds=[...new Set(agy.map(entry=>String(entry?.source_id||'')).filter(Boolean))];
  if(agyIds.length!==1)return null;
  return aggregate(agy.filter(entry=>String(entry?.source_id||'')===agyIds[0]));
}
''',
)

replace_once(
    "src/execweave/viewer_dashboard_focus.py",
    '''  const presentationAlias=new Map();
  const antigravityRoot=prepared.find(node=>String(node?.id||'')==='agent:Antigravity');
  const antigravityMains=prepared.filter(node=>{
    const attrs=node?.attributes||{};
    return node?.type==='agent'&&String(attrs.provider||'').toLowerCase()==='antigravity'&&
      String(node.id||'').startsWith('agent:antigravity:conversation:')&&!String(attrs.parent_agent_path||'').trim();
  });
  if(antigravityRoot&&antigravityMains.length===1){
    const main=antigravityMains[0];presentationAlias.set(antigravityRoot.id,main.id);
    prepared=prepared.filter(node=>node.id!==antigravityRoot.id).map(node=>node.id===main.id?{...node,name:'/root'}:node);
  }
''',
    '''  const presentationAlias=new Map();
  const antigravityRoot=prepared.find(node=>String(node?.id||'')==='agent:Antigravity');
  const antigravityScoped=prepared.filter(node=>{
    const attrs=node?.attributes||{};
    return node?.type==='agent'&&String(attrs.provider||'').toLowerCase()==='antigravity'&&
      String(node.id||'').startsWith('agent:antigravity:conversation:');
  });
  const parentScopes=new Set(antigravityScoped.filter(node=>String(node?.attributes?.parent_agent_path||'').trim()).map(node=>String(node?.attributes?.parent_scope_id||'')).filter(Boolean));
  const evidenceMains=antigravityScoped.filter(node=>{const attrs=node?.attributes||{};return !String(attrs.parent_agent_path||'').trim()&&parentScopes.has(String(attrs.conversation_id||''));});
  const fallbackMains=antigravityScoped.filter(node=>{const attrs=node?.attributes||{};return !String(attrs.parent_agent_path||'').trim()&&!attrs.routing_identity_only;});
  const antigravityMains=evidenceMains.length?evidenceMains:fallbackMains;
  if(antigravityRoot&&antigravityMains.length===1){
    const main=antigravityMains[0];presentationAlias.set(antigravityRoot.id,main.id);
    prepared=prepared.filter(node=>node.id!==antigravityRoot.id).map(node=>node.id===main.id?{...node,name:'/root'}:node);
  }else if(antigravityRoot&&antigravityScoped.length){
    prepared=prepared.filter(node=>node.id!==antigravityRoot.id);
  }
''',
)

Path("tests/test_antigravity_root_child_history_v2.py").write_text(r'''from __future__ import annotations

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
            text = details.inner_text()
            assert "child A first task" in text
            assert "child A first response" in text
            assert "child A second task" in text
            assert "child A second response" in text
            assert "sibling note, not a task" not in text
            assert details.locator(".execweave-agent-older").count() == 1
            older = details.locator(".execweave-agent-older").first
            assert not older.evaluate("node=>node.open")
            older.locator("summary").click()
            assert older.evaluate("node=>node.open")
            page.evaluate("items=>window.__execweaveAgentPanel.setEntries(items)", entries)
            assert details.locator(".execweave-agent-older").first.evaluate("node=>node.open")
        finally:
            browser.close()
''', encoding="utf-8")
