from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from execweave import agent_topology
from execweave.antigravity_full_fidelity import _assignment_event
from execweave.dashboard_shell import render_static_dashboard_html

ROOT_CONVERSATION = "root-conversation"
ROOT_ID = f"agent:antigravity:conversation:{ROOT_CONVERSATION}"
UNRESOLVED_ID = "agent:antigravity:conversation:unresolved-conversation"
CHILDREN = [
    (f"child-{index}", f"Role {index}", 1 if index <= 5 else 2)
    for index in range(1, 9)
]


def _message(
    *,
    timestamp: str,
    ordinal: int,
    kind: str,
    sender: str | None,
    recipient: str | None,
    text: str,
    phase: str | None = None,
) -> dict[str, Any]:
    return {
        "timestamp": timestamp,
        "ordinal": ordinal,
        "kind": kind,
        "sender": sender,
        "recipient": recipient,
        "text": text,
        "content_state": "plaintext",
        "phase": phase,
        "task_name": None,
    }


def _entry(
    *,
    source_id: str,
    path: str,
    label: str,
    messages: list[dict[str, Any]],
    is_root: bool,
    topology_state: str,
    topology_evidence: str,
    parent_path: str | None = None,
    sequence: int = 1,
) -> dict[str, Any]:
    return {
        "provider": "antigravity",
        "source_id": source_id,
        "path": f"content/{source_id.rsplit(':', 1)[-1]}-{sequence}.jsonl",
        "size_bytes": 1,
        "last_sequence": sequence,
        "conversation_preview": {
            "thread_id": f"antigravity:{source_id}",
            "thread_id_source": agent_topology.THREAD_ID_EXECWEAVE_DERIVED,
            "parent_thread_id": None if is_root else "antigravity:root",
            "agent_path": path,
            "agent_path_source": agent_topology.PATH_EXECWEAVE_DERIVED,
            "topology_state": topology_state,
            "topology_evidence": topology_evidence,
            "parent_agent_path": parent_path,
            "parent_relation_source": topology_evidence if parent_path else None,
            "provider_native_id": source_id.rsplit(":", 1)[-1],
            "agent_label": label,
            "provider_label": "Antigravity",
            "agent_nickname": None if is_root else label,
            "is_root": is_root,
            "message_count": len(messages),
            "messages_truncated": False,
            "messages": messages,
        },
    }


def _root_messages() -> list[dict[str, Any]]:
    return [
        _message(
            timestamp="2026-09-01T10:00:00Z",
            ordinal=10,
            kind="user_message",
            sender="user",
            recipient="/root",
            text="ROOT PROMPT ONE",
        ),
        _message(
            timestamp="2026-09-01T10:50:00Z",
            ordinal=20,
            kind="assistant_final_response",
            sender="/root",
            recipient=None,
            text="ROOT FINAL ONE",
            phase="final_answer",
        ),
        _message(
            timestamp="2026-09-01T11:00:00Z",
            ordinal=30,
            kind="user_message",
            sender="user",
            recipient="/root",
            text="ROOT PROMPT TWO",
        ),
        _message(
            timestamp="2026-09-01T11:50:00Z",
            ordinal=40,
            kind="assistant_final_response",
            sender="/root",
            recipient=None,
            text="ROOT FINAL TWO",
            phase="final_answer",
        ),
    ]


def _child_messages(child_id: str, round_no: int, index: int) -> list[dict[str, Any]]:
    path = f"/root/{child_id}"
    hour = 10 if round_no == 1 else 11
    return [
        _message(
            timestamp=f"2026-09-01T{hour:02d}:10:{index:02d}Z",
            ordinal=100 + index,
            kind="subagent_task",
            sender="/root",
            recipient=path,
            text=f"TASK UNIQUE {index}",
            phase="assignment",
        ),
        _message(
            timestamp=f"2026-09-01T{hour:02d}:20:{index:02d}Z",
            ordinal=200 + index,
            kind="assistant_message",
            sender=path,
            recipient=None,
            text=f"THINKING UNIQUE {index}",
            phase="commentary",
        ),
        _message(
            timestamp=f"2026-09-01T{hour:02d}:30:{index:02d}Z",
            ordinal=300 + index,
            kind="subagent_final_response",
            sender=path,
            recipient="/root",
            text=f"RESPONSE UNIQUE {index}",
            phase="final_answer",
        ),
    ]


def _fixture() -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    root_node = {
        "id": ROOT_ID,
        "type": "agent",
        "name": "Antigravity root conversation",
        "attributes": {
            "provider": "antigravity",
            "conversation_id": ROOT_CONVERSATION,
            **agent_topology.root_topology(),
        },
    }
    nodes = [root_node]
    edges: list[dict[str, Any]] = []
    root_messages = _root_messages()
    entries = [
        _entry(
            source_id=ROOT_ID,
            path="/root",
            label="Antigravity",
            messages=root_messages[:2],
            is_root=True,
            topology_state=agent_topology.TOPOLOGY_PROVIDER_REPORTED,
            topology_evidence=agent_topology.EVIDENCE_PROVIDER_SESSION_ROOT,
            sequence=1,
        ),
        _entry(
            source_id=ROOT_ID,
            path="/root",
            label="Antigravity",
            messages=root_messages,
            is_root=True,
            topology_state=agent_topology.TOPOLOGY_PROVIDER_REPORTED,
            topology_evidence=agent_topology.EVIDENCE_PROVIDER_SESSION_ROOT,
            sequence=2,
        ),
    ]

    for index, (child_id, role, round_no) in enumerate(CHILDREN, start=1):
        node_id = f"agent:antigravity:conversation:{child_id}"
        child_attrs = agent_topology.subagent_topology(
            evidence=agent_topology.EVIDENCE_VALIDATED_CHILD_TRANSCRIPT,
            parent_scope_id=ROOT_CONVERSATION,
        )
        nodes.append(
            {
                "id": node_id,
                "type": "agent",
                "name": "Antigravity conversation",
                "attributes": {
                    "provider": "antigravity",
                    "conversation_id": child_id,
                    "agent_type": role,
                    "agent_nickname": role,
                    **child_attrs,
                },
            }
        )
        edges.append(
            {
                "id": f"root-child-{index}",
                "source": ROOT_ID,
                "target": node_id,
                "relation": "HAS_CHILD_AGENT_SESSION",
                "count": 1,
                "first_sequence": index,
                "last_sequence": index,
                "first_seen": f"2026-09-01T10:0{min(index, 9)}:00Z",
                "last_seen": f"2026-09-01T10:0{min(index, 9)}:00Z",
            }
        )
        entries.append(
            _entry(
                source_id=node_id,
                path=f"/root/{child_id}",
                label=role,
                messages=_child_messages(child_id, round_no, index),
                is_root=False,
                topology_state=agent_topology.TOPOLOGY_PROVIDER_REPORTED,
                topology_evidence=agent_topology.EVIDENCE_VALIDATED_CHILD_TRANSCRIPT,
                parent_path="/root",
                sequence=10 + index,
            )
        )

    nodes.append(
        {
            "id": UNRESOLVED_ID,
            "type": "agent",
            "name": "Antigravity conversation",
            "attributes": {
                "provider": "antigravity",
                "conversation_id": "unresolved-conversation",
            },
        }
    )
    entries.append(
        _entry(
            source_id=UNRESOLVED_ID,
            path="/root",
            label="unresolved-conversation",
            messages=[
                _message(
                    timestamp="2026-09-01T10:25:00Z",
                    ordinal=999,
                    kind="assistant_message",
                    sender="/root",
                    recipient=None,
                    text="UNRESOLVED PRIVATE RESPONSE",
                    phase="response",
                )
            ],
            is_root=True,
            topology_state=agent_topology.TOPOLOGY_DERIVED,
            topology_evidence=agent_topology.EVIDENCE_NO_PARENT_EVIDENCE,
            sequence=99,
        )
    )
    graph = {
        "graph_schema_version": "0.2",
        "session_id": "antigravity-two-round-eight-child",
        "event_count": 0,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "nodes": nodes,
        "edges": edges,
    }
    updated = list(entries)
    updated.append(
        _entry(
            source_id=ROOT_ID,
            path="/root",
            label="Antigravity",
            messages=root_messages,
            is_root=True,
            topology_state=agent_topology.TOPOLOGY_PROVIDER_REPORTED,
            topology_evidence=agent_topology.EVIDENCE_PROVIDER_SESSION_ROOT,
            sequence=100,
        )
    )
    return graph, entries, updated


def test_validated_antigravity_assignment_uses_common_child_topology() -> None:
    event = _assignment_event(
        timestamp="2026-09-01T10:00:00Z",
        conversation_id=ROOT_CONVERSATION,
        step=7,
        subagent_index=0,
        child_id="child-1",
        spec={
            "Prompt": "inspect one thing",
            "Role": "security reviewer",
            "TypeName": "research",
            "Workspace": "inherit",
        },
    )
    child = event["target"]
    attrs = child["attributes"]
    assert attrs[agent_topology.ATTR_ROLE] == agent_topology.AGENT_ROLE_SUBAGENT
    assert attrs[agent_topology.ATTR_PARENT_SCOPE] == ROOT_CONVERSATION
    assert (
        attrs[agent_topology.ATTR_PARENT_EVIDENCE]
        == agent_topology.EVIDENCE_VALIDATED_CHILD_TRANSCRIPT
    )
    assert "agent_path" not in attrs, "a validated child must not be downgraded to a legacy bare path"
    assert attrs["agent_nickname"] == "security reviewer"

    resolved = agent_topology.resolve_agent_topology(child)
    assert resolved.is_root is False
    assert resolved.agent_path == "/root/child-1"
    assert resolved.agent_path_source == agent_topology.PATH_EXECWEAVE_DERIVED
    assert resolved.topology_state == agent_topology.TOPOLOGY_PROVIDER_REPORTED


def test_provider_shaped_fixture_contains_two_root_rounds_and_eight_unique_children() -> None:
    graph, entries, updated = _fixture()
    del updated
    children = [
        node
        for node in graph["nodes"]
        if node["id"].startswith("agent:antigravity:conversation:child-")
    ]
    assert len(children) == 8
    root_entries = [entry for entry in entries if entry["source_id"] == ROOT_ID]
    assert len(root_entries) == 2, "the fixture must exercise cumulative root Stop snapshots"
    assert [message["text"] for message in root_entries[-1]["conversation_preview"]["messages"]] == [
        "ROOT PROMPT ONE",
        "ROOT FINAL ONE",
        "ROOT PROMPT TWO",
        "ROOT FINAL TWO",
    ]
    child_responses = {
        entry["conversation_preview"]["messages"][-1]["text"]
        for entry in entries
        if entry["source_id"].startswith("agent:antigravity:conversation:child-")
    }
    assert len(child_responses) == 8


@pytest.mark.viewer_e2e
def test_antigravity_two_round_eight_child_dashboard_isolation_and_fold_state(
    tmp_path: Path,
) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    graph, entries, updated_entries = _fixture()
    viewer = tmp_path / "viewer.html"
    viewer.write_text(
        render_static_dashboard_html(graph, conversation_entries=entries),
        encoding="utf-8",
    )

    required = os.environ.get("EXECWEAVE_E2E_REQUIRED", "").strip().lower() not in {
        "",
        "0",
        "false",
    }
    with sync_api.sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch()
        except Exception as error:  # noqa: BLE001 - browser availability is environmental
            if required:
                pytest.fail(f"Chromium is required for this release gate: {error}")
            pytest.skip(f"Chromium is not available: {error}")

        try:
            page = browser.new_page(viewport={"width": 1600, "height": 1100})
            page.goto(viewer.as_uri())
            page.wait_for_selector(".node", timeout=15000)

            def click(node_id: str) -> None:
                clicked = page.eval_on_selector_all(
                    ".node",
                    """(nodes,id)=>{const node=nodes.find(item=>item.dataset.id===id);
                    if(!node)return false;node.dispatchEvent(new MouseEvent('click',{bubbles:true}));return true}""",
                    node_id,
                )
                assert clicked, node_id

            click(ROOT_ID)
            page.wait_for_function(
                "()=>(document.getElementById('details')?.innerText||'').includes('ROOT PROMPT TWO')"
            )
            root_text = page.locator("#details").inner_text()
            assert "ROOT PROMPT TWO" in root_text and "ROOT FINAL TWO" in root_text
            assert "Prompt" in root_text and "Final response" in root_text
            for index in range(1, 9):
                assert f"RESPONSE UNIQUE {index}" not in root_text
            assert "UNRESOLVED PRIVATE RESPONSE" not in root_text
            assert page.locator("#details .execweave-agent-older").count() == 1
            old_round = page.locator("#details .execweave-agent-older").filter(has_text="ROOT PROMPT ONE")
            assert old_round.count() == 1
            assert not old_round.first.evaluate("node=>node.open")
            old_round.first.locator("summary").click()
            assert old_round.first.evaluate("node=>node.open")
            old_text = old_round.first.inner_text()
            assert "ROOT PROMPT ONE" in old_text and "ROOT FINAL ONE" in old_text

            page.evaluate(
                "payload=>window.__execweaveAgentPanel.setEntries(payload)",
                updated_entries,
            )
            assert old_round.first.evaluate("node=>node.open"), (
                "a cumulative Stop snapshot changed reader-controlled fold state"
            )
            assert page.locator("#details .execweave-agent-older").count() == 1

            for index, (child_id, role, _round_no) in enumerate(CHILDREN, start=1):
                node_id = f"agent:antigravity:conversation:{child_id}"
                label = page.eval_on_selector_all(
                    ".node",
                    "(nodes,id)=>nodes.find(item=>item.dataset.id===id)?.textContent||''",
                    node_id,
                )
                assert role in label, f"provider role was not used as the child label: {label!r}"
                click(node_id)
                page.wait_for_function(
                    "needle=>(document.getElementById('details')?.innerText||'').includes(needle)",
                    f"RESPONSE UNIQUE {index}",
                )
                text = page.locator("#details").inner_text()
                assert "Task" in text and "Thinking" in text and "Response" in text
                assert "Prompt" not in text and "Final response" not in text
                assert f"TASK UNIQUE {index}" in text
                assert f"THINKING UNIQUE {index}" in text
                assert f"RESPONSE UNIQUE {index}" in text
                for other in range(1, 9):
                    if other != index:
                        assert f"RESPONSE UNIQUE {other}" not in text
                assert "ROOT FINAL ONE" not in text and "ROOT FINAL TWO" not in text

            click(UNRESOLVED_ID)
            page.wait_for_function(
                "()=>(document.getElementById('details')?.innerText||'').includes('UNRESOLVED PRIVATE RESPONSE')"
            )
            unresolved_text = page.locator("#details").inner_text()
            assert "Task" in unresolved_text and "Response" in unresolved_text
            assert "Prompt" not in unresolved_text and "Final response" not in unresolved_text
            assert "ROOT FINAL ONE" not in unresolved_text
        finally:
            browser.close()
