"""Lock the Windows Agy live wire that banner-only fixtures missed.

Observed on run a9bfdccc2a0e4a09844ebcd5ef47ee4f (agy_windows.rar):
parent 17789bfa, children bbfc040b / 34c18337, invoke_subagent result wrapped in
Created At headers plus a prose trailer, PostToolUse name=schedule only.
"""

from __future__ import annotations

import json
from pathlib import Path

from execweave.antigravity_full_fidelity import antigravity_hook_to_content_events
from execweave.antigravity_subagent_linkage import transcript_subagent_links
from execweave.content_store import FullFidelityContentStore
from execweave.conversation_preview_common import _line_transcript_messages
from execweave.conversation_records import conversation_record_entries
from execweave.graph import GraphAccumulator
from execweave.viewer_dashboard_clean import _DASHBOARD_JS
from execweave.viewer_projection import project_viewer_graph


PARENT = "17789bfa-e341-4e37-9bc6-f6acbad589e1"
CHILD_A = "bbfc040b-4f3b-40c0-a58b-f8e4f9f5fe97"
CHILD_B = "34c18337-3dec-4e89-b22f-d5e7e685be08"


def _brain(root: Path, conversation_id: str) -> Path:
    path = (
        root
        / "antigravity-cli"
        / "brain"
        / conversation_id
        / ".system_generated"
        / "logs"
        / "transcript_full.jsonl"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _write(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def _windows_result(child_a: str, child_b: str, child_a_uri: str, child_b_uri: str, workspace_uri: str) -> str:
    first = json.dumps(
        {"conversationId": child_a, "logAbsoluteUri": child_a_uri, "workspaceUris": [workspace_uri]},
        indent=2,
    )
    second = json.dumps(
        {"conversationId": child_b, "logAbsoluteUri": child_b_uri, "workspaceUris": [workspace_uri]},
        indent=2,
    )
    return (
        "Created At: 2026-09-02T10:46:09+08:00\n"
        "Completed At: 2026-09-02T10:46:09+08:00\n"
        "Created the following subagents:\n"
        f"{first}\n{second}\n"
        "The subagents will send you a message when they have completed their task "
        "or require guidance. There is no need to poll for their responses."
    )


def _specs() -> list[dict[str, str]]:
    return [
        {
            "Model": "inherit",
            "Prompt": "請發表你對於「誰才是最猛 Agent」的參戰宣誓！展現你的極限算力霸氣！",
            "Role": "極限算力狂人",
            "TypeName": "DebaterA",
        },
        {
            "Model": "inherit",
            "Prompt": "請發表你對於「誰才是最猛 Agent」的參戰宣誓！用你的高維演算法與邏輯狠狠壓制對手！",
            "Role": "深層演算法大師",
            "TypeName": "DebaterB",
        },
    ]


def _parent_rows(tmp_path: Path) -> list[dict[str, object]]:
    child_a = _brain(tmp_path, CHILD_A)
    child_b = _brain(tmp_path, CHILD_B)
    return [
        {
            "step_index": 0,
            "source": "USER_EXPLICIT",
            "type": "USER_INPUT",
            "status": "DONE",
            "created_at": "2026-09-02T02:45:46Z",
            "content": "<USER_REQUEST>\n你是誰\n</USER_REQUEST>",
        },
        {
            "step_index": 1,
            "source": "MODEL",
            "type": "PLANNER_RESPONSE",
            "status": "DONE",
            "created_at": "2026-09-02T02:45:46Z",
            "content": "我是 Antigravity",
        },
        {
            "step_index": 2,
            "source": "USER_EXPLICIT",
            "type": "USER_INPUT",
            "status": "DONE",
            "created_at": "2026-09-02T02:46:04Z",
            "content": "<USER_REQUEST>\n開兩個agent討論誰最猛\n</USER_REQUEST>",
        },
        {
            "step_index": 6,
            "source": "MODEL",
            "type": "PLANNER_RESPONSE",
            "status": "DONE",
            "created_at": "2026-09-02T02:46:07Z",
            "tool_calls": [{"name": "invoke_subagent", "args": {"Subagents": _specs()}}],
        },
        {
            "step_index": 7,
            "source": "MODEL",
            "type": "GENERIC",
            "status": "DONE",
            "created_at": "2026-09-02T02:46:09Z",
            "content": _windows_result(
                CHILD_A,
                CHILD_B,
                child_a.resolve().as_uri(),
                child_b.resolve().as_uri(),
                tmp_path.resolve().as_uri(),
            ),
        },
        {
            "step_index": 8,
            "source": "MODEL",
            "type": "PLANNER_RESPONSE",
            "status": "DONE",
            "created_at": "2026-09-02T02:46:10Z",
            "content": "已經召喚兩位辯手",
        },
        {
            "step_index": 20,
            "source": "USER_EXPLICIT",
            "type": "USER_INPUT",
            "status": "DONE",
            "created_at": "2026-09-02T02:47:00Z",
            "content": "<USER_REQUEST>\n讓這兩個agent繼續問 我帥不帥\n</USER_REQUEST>",
        },
    ]


def _child_rows(first_message: str, inbound: str, second_message: str) -> list[dict[str, object]]:
    return [
        {
            "step_index": 0,
            "source": "USER_EXPLICIT",
            "type": "USER_INPUT",
            "status": "DONE",
            "created_at": "2026-09-02T02:46:09Z",
            "content": "<USER_REQUEST>請發表你對於「誰才是最猛 Agent」的參戰宣誓！</USER_REQUEST>",
        },
        {
            "step_index": 1,
            "source": "MODEL",
            "type": "PLANNER_RESPONSE",
            "status": "DONE",
            "created_at": "2026-09-02T02:46:10Z",
            "tool_calls": [{"name": "send_message", "args": {"Recipient": PARENT, "Message": first_message}}],
        },
        {
            "step_index": 2,
            "source": "MODEL",
            "type": "PLANNER_RESPONSE",
            "status": "DONE",
            "created_at": "2026-09-02T02:46:11Z",
            "content": "宣誓已成功發送給主裁判",
        },
        {
            "step_index": 4,
            "source": "SYSTEM",
            "type": "SYSTEM_MESSAGE",
            "status": "DONE",
            "created_at": "2026-09-02T02:46:16Z",
            "content": (
                "The following is a <SYSTEM_MESSAGE> not actually sent by the user.\n"
                "<SYSTEM_MESSAGE>\n"
                f"[Message] timestamp=2026-09-02T02:46:16Z sender={PARENT} "
                f"priority=MESSAGE_PRIORITY_HIGH content={inbound}\n"
                "</SYSTEM_MESSAGE>"
            ),
        },
        {
            "step_index": 5,
            "source": "MODEL",
            "type": "PLANNER_RESPONSE",
            "status": "DONE",
            "created_at": "2026-09-02T02:46:20Z",
            "content": "反擊已成功送出",
            "tool_calls": [{"name": "send_message", "args": {"Recipient": PARENT, "Message": second_message}}],
        },
    ]


def test_windows_invoke_result_envelope_links_both_children(tmp_path: Path) -> None:
    parent = _brain(tmp_path, PARENT)
    _write(parent, _parent_rows(tmp_path))
    _write(_brain(tmp_path, CHILD_A), [{"step_index": 0, "source": "MODEL", "type": "PLANNER_RESPONSE", "status": "DONE", "content": "a"}])
    _write(_brain(tmp_path, CHILD_B), [{"step_index": 0, "source": "MODEL", "type": "PLANNER_RESPONSE", "status": "DONE", "content": "b"}])
    from execweave.antigravity_subagent_linkage import read_transcript_records

    links = transcript_subagent_links(read_transcript_records(parent), parent_id=PARENT)
    assert [link["conversation_id"] for link in links] == [CHILD_A, CHILD_B]
    assert links[0]["agent_path"] == "/root/極限算力狂人"
    assert links[1]["agent_path"] == "/root/深層演算法大師"


def test_child_preview_folds_inbound_rounds_not_only_first_ack(tmp_path: Path) -> None:
    path = tmp_path / "child.jsonl"
    _write(
        path,
        _child_rows("FIRST DEBATE DECLARATION", "SECOND ROUND FROM PARENT", "SECOND DEBATE REPLY"),
    )
    messages = _line_transcript_messages(
        path,
        timestamp="2026-09-02T02:46:10Z",
        ordinal=0,
        agent_path="/root/極限算力狂人",
        antigravity=True,
    )
    texts = [message.get("text") for message in messages]
    assert "FIRST DEBATE DECLARATION" in texts
    assert "SECOND ROUND FROM PARENT" in texts
    assert "SECOND DEBATE REPLY" in texts
    openers = [message for message in messages if message.get("kind") in {"user_message", "subagent_task"}]
    assert len(openers) >= 2


def test_windows_schedule_run_connects_children_and_hides_execution_zero(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    store = FullFidelityContentStore(run_root)
    parent = _brain(tmp_path, PARENT)
    child_a = _brain(tmp_path, CHILD_A)
    child_b = _brain(tmp_path, CHILD_B)
    _write(parent, _parent_rows(tmp_path))
    _write(child_a, _child_rows("A FIRST", "A SECOND TASK", "A SECOND REPLY"))
    _write(child_b, _child_rows("B FIRST", "B SECOND TASK", "B SECOND REPLY"))
    graph = GraphAccumulator(session_id="agy-windows-wire", source_path=run_root / "events.jsonl")
    for conversation_id, path in ((PARENT, parent), (CHILD_A, child_a), (CHILD_B, child_b)):
        payload = {
            "conversationId": conversation_id,
            "workspacePaths": [str(tmp_path.resolve())],
            "transcriptPath": str(path),
            "executionNum": 0,
            "terminationReason": "NO_TOOL_CALL",
            "fullyIdle": True,
            "stepIdx": 16,
            "toolCall": {"name": "schedule", "args": {"Action": "run"}},
            "error": "",
        }
        for hook in ("PostToolUse", "Stop"):
            for event in antigravity_hook_to_content_events(
                payload,
                hook_event=hook,
                store=store,
                timestamp="2026-09-02T02:48:00Z",
            ):
                graph.apply(event)
    materialized = graph.to_dict()
    entries = conversation_record_entries(materialized, run_root)
    by_id = {
        entry["source_id"]: entry["conversation_preview"]
        for entry in entries
        if isinstance(entry.get("conversation_preview"), dict)
        and entry.get("source_id")
    }
    parent_preview = by_id[f"agent:antigravity:conversation:{PARENT}"]
    child_a_preview = by_id[f"agent:antigravity:conversation:{CHILD_A}"]
    child_b_preview = by_id[f"agent:antigravity:conversation:{CHILD_B}"]
    assert parent_preview["is_root"] is True
    assert parent_preview["agent_path"] == "/root"
    assert child_a_preview["is_root"] is False
    assert child_a_preview["agent_path"] == f"/root/{CHILD_A}"
    assert child_b_preview["is_root"] is False
    assert child_b_preview["agent_path"] == f"/root/{CHILD_B}"
    assert child_a_preview["parent_agent_path"] == "/root"
    assert child_a_preview["agent_nickname"] == "極限算力狂人"
    assert child_b_preview["agent_nickname"] == "深層演算法大師"
    assert "A SECOND TASK" in [message.get("text") for message in child_a_preview["messages"]]
    assert "B SECOND REPLY" in [message.get("text") for message in child_b_preview["messages"]]

    projected = project_viewer_graph(materialized)
    child_edges = [
        edge
        for edge in projected["edges"]
        if edge.get("relation") == "HAS_CHILD_AGENT_SESSION"
    ]
    targets = {edge["target"] for edge in child_edges}
    assert f"agent:antigravity:conversation:{CHILD_A}" in targets
    assert f"agent:antigravity:conversation:{CHILD_B}" in targets

    assert "agent_execution" in _DASHBOARD_JS
    assert "hiddenTypes=new Set([" in _DASHBOARD_JS
    assert "'agent_execution'" in _DASHBOARD_JS
