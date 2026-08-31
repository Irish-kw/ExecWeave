"""One agent execution must be published as exactly one conversation.

A Codex child is observed through two kinds of evidence that name its thread
differently: the parent's routing records and the child's own archived rollout carry
the provider-native thread id, while the subagent's final-response content carries a
synthesized ``<provider>:<node-id>``. Grouping by raw thread alone published those as
two conversations for the same agent, and the CI checker's agent-path dict quietly
overwrote one with the other.

Merging is driven by positive identity evidence only — a shared graph agent node (whose
id encodes the provider-native subagent id) or a shared raw thread. Matching labels,
nicknames, or agent paths never merge anything on their own.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from execweave import agent_topology
from execweave.agent_trace import cursor_subagent, opencode_session_agent
from execweave.claude_delegation import _subagent as claude_subagent
from execweave.content_evidence import content_observation_event
from execweave.content_store import FullFidelityContentStore
from execweave.conversation_archive import codex_conversation_archive_events
from execweave.conversation_records import conversation_record_entries
from execweave.codex_full_fidelity import codex_hook_to_content_events

SESSION_ID = "01a04cea-0a14-71e0-8c32-4aeafda0f039"
CHILD_ID = "01a04cea-67b2-7683-9f6b-cd644497b862"
CHILD_PATH = "/root/explorer"

CHILD_TASK = "CHILD TASK ASSIGNMENT"
CHILD_PRIVATE = "CHILD PRIVATE TRANSCRIPT CONTENT"
CHILD_FINAL = "CHILD FINAL RESPONSE"
ROOT_PROMPT = "ROOT PROMPT"
ROOT_FINAL = "ROOT FINAL ANSWER"


def _record(ordinal: int, record_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "timestamp": f"2026-08-29T09:00:{ordinal:02d}.000Z",
        "ordinal": ordinal,
        "type": record_type,
        "payload": payload,
    }


def _message(
    ordinal: int, role: str, text: str, *, phase: str | None = None, user: bool = False
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "type": "message",
        "role": role,
        "content": [
            {"type": "input_text" if role == "user" else "output_text", "text": text}
        ],
    }
    if phase is not None:
        payload["phase"] = phase
    if user:
        payload["internal_chat_message_metadata_passthrough"] = {
            "content_item_kinds": ["user.text"]
        }
    return _record(ordinal, "response_item", payload)


def _parent_rollout() -> list[dict[str, Any]]:
    """Root's own turns plus the routing records naming the child."""
    return [
        _record(0, "session_meta", {"id": SESSION_ID, "session_id": SESSION_ID}),
        _message(1, "user", ROOT_PROMPT, user=True),
        _record(2, "response_item", {
            "type": "function_call", "name": "spawn_agent", "namespace": "collaboration",
            "call_id": "call_spawn_1",
            "arguments": json.dumps({"task_name": "explorer", "message": CHILD_TASK}),
        }),
        _record(3, "event_msg", {
            "type": "item_completed", "thread_id": SESSION_ID,
            "item": {"type": "SubAgentActivity", "id": "call_spawn_1", "kind": "started",
                     "agent_thread_id": CHILD_ID, "agent_path": CHILD_PATH},
        }),
        _record(4, "response_item", {
            "type": "function_call_output", "call_id": "call_spawn_1",
            "output": json.dumps({"task_name": CHILD_PATH}),
        }),
        _record(5, "response_item", {
            "type": "agent_message", "id": "amsg_1", "author": CHILD_PATH, "recipient": "/root",
            "content": [{"type": "input_text",
                         "text": f"Message Type: FINAL_ANSWER\nTask name: /root\n"
                                 f"Sender: {CHILD_PATH}\nPayload:\n{CHILD_FINAL}"}],
        }),
        _message(6, "assistant", ROOT_FINAL, phase="final_answer"),
    ]


def _child_rollout() -> list[dict[str, Any]]:
    """Inherited parent context, then the child's own private turns."""
    return [
        _record(0, "session_meta", {
            "id": CHILD_ID, "session_id": CHILD_ID,
            "source": {"subagent": {"thread_spawn": {
                "agent_path": CHILD_PATH, "agent_nickname": "explorer",
                "parent_thread_id": SESSION_ID}}},
            "subagent_history_start_ordinal": 2,
        }),
        _message(1, "user", ROOT_PROMPT, user=True),
        _message(2, "user", CHILD_TASK),
        _message(3, "assistant", CHILD_PRIVATE, phase="commentary"),
        _message(4, "assistant", CHILD_FINAL, phase="final_answer"),
    ]


@pytest.fixture()
def codex_two_evidence_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> dict[str, Any]:
    """Record one Codex child through both evidence surfaces at the raw hook layer.

    Transcript archival gives the provider-native thread id; subagent final-response
    content gives a synthesized one. Both describe the same execution.
    """
    codex_home = tmp_path / "codex-home"
    sessions = codex_home / "sessions" / "2026" / "08" / "29"
    sessions.mkdir(parents=True)
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    parent_path = sessions / f"rollout-2026-08-29T09-00-00-{SESSION_ID}.jsonl"
    child_path = sessions / f"rollout-2026-08-29T09-01-00-{CHILD_ID}.jsonl"
    for path, records in ((parent_path, _parent_rollout()), (child_path, _child_rollout())):
        path.write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records),
            encoding="utf-8",
        )

    run_root = tmp_path / "run"
    store = FullFidelityContentStore(run_root)
    base = {"session_id": SESSION_ID, "cwd": str(tmp_path), "model": "gpt-5.6-terra"}
    subagent_stop = {
        **base,
        "hook_event_name": "SubagentStop",
        "agent_id": CHILD_ID,
        "agent_type": "default",
        "last_assistant_message": CHILD_FINAL,
        "transcript_path": str(parent_path),
        "agent_transcript_path": str(child_path),
    }
    session_end = {
        **base, "hook_event_name": "SessionEnd", "transcript_path": str(parent_path)
    }

    events: list[dict[str, Any]] = []
    # Evidence surface 1: the subagent's final response, carrying a synthesized thread.
    events.extend(
        codex_hook_to_content_events(
            subagent_stop, store=store, timestamp="2026-08-29T09:02:00Z"
        )
    )
    # Evidence surface 2: the archived transcripts, carrying provider-native threads.
    events.extend(
        codex_conversation_archive_events(
            subagent_stop, store=store, timestamp="2026-08-29T09:02:01Z"
        )
    )
    events.extend(
        codex_conversation_archive_events(
            session_end, store=store, timestamp="2026-08-29T09:02:02Z"
        )
    )
    return {"events": events, "run_root": run_root}


def _graph(events: list[dict[str, Any]]) -> dict[str, Any]:
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    for index, event in enumerate(events):
        for entity in (event.get("source"), event.get("target")):
            if isinstance(entity, dict) and isinstance(entity.get("id"), str):
                node = nodes.setdefault(entity["id"], {**entity, "attributes": {}})
                incoming = entity.get("attributes") or {}
                for key, value in incoming.items():
                    if value is None:
                        node["attributes"].setdefault(key, None)
                    elif node["attributes"].get(key) is None:
                        node["attributes"][key] = value
        source, target = event.get("source"), event.get("target")
        if not isinstance(source, dict) or not isinstance(target, dict):
            continue
        edges.append(
            {
                "source": source["id"],
                "target": target["id"],
                "relation": event.get("relation"),
                "first_sequence": index,
                "last_sequence": index,
                "first_seen": event["timestamp"],
                "last_seen": event["timestamp"],
            }
        )
    return {"nodes": list(nodes.values()), "edges": edges}


def _previews(run: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        entry["conversation_preview"]
        for entry in conversation_record_entries(_graph(run["events"]), run["run_root"])
        if isinstance(entry.get("conversation_preview"), dict)
    ]


def _for_agent(previews: list[dict[str, Any]], agent_path: str) -> list[dict[str, Any]]:
    return [p for p in previews if p.get("agent_path") == agent_path]


def _texts(preview: dict[str, Any]) -> str:
    return "\n".join(str(m.get("text") or "") for m in preview.get("messages") or [])


# ── The regression itself ────────────────────────────────────────────────────


def test_two_evidence_surfaces_produce_one_child_conversation(
    codex_two_evidence_run: dict[str, Any],
) -> None:
    previews = _previews(codex_two_evidence_run)
    assert len(_for_agent(previews, CHILD_PATH)) == 1, (
        "the same child execution was published as several conversations: "
        f"{[p['thread_id'] for p in _for_agent(previews, CHILD_PATH)]}"
    )
    assert len(_for_agent(previews, "/root")) == 1


def test_the_single_child_entry_carries_every_evidence_kind(
    codex_two_evidence_run: dict[str, Any],
) -> None:
    child = _for_agent(_previews(codex_two_evidence_run), CHILD_PATH)[0]
    text = _texts(child)
    assert CHILD_TASK in text, "child assignment/routing evidence was lost in the merge"
    assert CHILD_PRIVATE in text, "child private transcript content was lost in the merge"
    assert CHILD_FINAL in text, "child final response was lost in the merge"


def test_both_contributing_thread_identities_are_preserved(
    codex_two_evidence_run: dict[str, Any],
) -> None:
    child = _for_agent(_previews(codex_two_evidence_run), CHILD_PATH)[0]
    evidence = child["evidence_thread_ids"]
    assert len(evidence) > 1, f"only one thread identity survived: {evidence}"
    assert CHILD_ID in evidence, "the provider-native rollout thread id was discarded"
    assert any(thread != CHILD_ID for thread in evidence), (
        "the synthesized routing thread id was discarded"
    )
    # The published id is the provider's own, never downgraded to the synthesized one.
    assert child["thread_id"] == CHILD_ID
    assert child["thread_id_source"] == agent_topology.THREAD_ID_PROVIDER_NATIVE
    assert child["thread_id"] in evidence


def test_merging_preserves_topology_completeness_and_parent_linkage(
    codex_two_evidence_run: dict[str, Any],
) -> None:
    previews = _previews(codex_two_evidence_run)
    child = _for_agent(previews, CHILD_PATH)[0]
    root = _for_agent(previews, "/root")[0]

    assert child["is_root"] is False
    assert child["agent_path_source"] == agent_topology.PATH_PROVIDER_DECLARED
    assert child["topology_state"] == agent_topology.TOPOLOGY_OBSERVED
    assert child["parent_agent_path"] == "/root"
    assert child["parent_relation_source"]
    assert child["parent_thread_id"] == root["thread_id"]
    assert child["provider_native_id"] == CHILD_ID
    assert (
        child["conversation_completeness"]
        == agent_topology.COMPLETENESS_PROVIDER_TRANSCRIPT
    )


def test_child_private_content_still_never_reaches_root(
    codex_two_evidence_run: dict[str, Any],
) -> None:
    """Merging must not become a licence to pool content across agents."""
    previews = _previews(codex_two_evidence_run)
    assert CHILD_PRIVATE not in _texts(_for_agent(previews, "/root")[0])


# ── Negative evidence: what must never cause a merge ─────────────────────────


def _content_graph(
    run_root: Path, records: list[tuple[dict[str, Any], str, str]]
) -> dict[str, Any]:
    store = FullFidelityContentStore(run_root)
    events = []
    for index, (source, content_kind, value) in enumerate(records):
        reference = store.put_text(value, content_kind=content_kind)
        events.append(
            content_observation_event(
                timestamp=f"2026-08-29T00:0{index}:00Z",
                provider=str((source.get("attributes") or {}).get("provider") or "x"),
                source=source,
                reference=reference,
                relation="PRODUCED_ASSISTANT_RESPONSE",
                observed_field="text",
                evidence_source="provider_plugin",
                attribution="provider_hook",
            )
        )
    return _graph(events)


def test_matching_labels_and_paths_alone_never_merge_two_agents(tmp_path: Path) -> None:
    """Two distinct subagents that share a label, a nickname and a parent stay apart."""
    first = cursor_subagent(
        {"session_id": "s1", "subagent_id": "child-1", "subagent_type": "Explore"}
    )
    second = cursor_subagent(
        {"session_id": "s1", "subagent_id": "child-2", "subagent_type": "Explore"}
    )
    assert first is not None and second is not None
    graph = _content_graph(
        tmp_path,
        [
            (first, "cursor.subagent_summary", "FIRST CHILD SUMMARY"),
            (second, "cursor.subagent_summary", "SECOND CHILD SUMMARY"),
        ],
    )
    previews = [
        entry["conversation_preview"]
        for entry in conversation_record_entries(graph, tmp_path)
        if isinstance(entry.get("conversation_preview"), dict)
    ]
    children = [p for p in previews if not p["is_root"]]
    assert len(children) == 2, "two distinct subagents collapsed into one conversation"
    assert {p["agent_path"] for p in children} == {"/root/child-1", "/root/child-2"}
    for preview in children:
        text = _texts(preview)
        other = "SECOND" if "FIRST" in text else "FIRST"
        assert f"{other} CHILD SUMMARY" not in text


def _assert_independent_root_previews(
    previews: list[dict[str, Any]],
    *,
    alias: str,
    first_text: str,
    second_text: str,
) -> None:
    assert len(previews) == 2, "independent root executions collapsed into one conversation"
    assert all(preview["is_root"] is True for preview in previews)
    assert len({preview["thread_id"] for preview in previews}) == 2
    assert all(preview["thread_id"].startswith(f"{alias}::agent=") for preview in previews)
    assert all(preview["evidence_thread_ids"] == [alias] for preview in previews)
    texts = [_texts(preview) for preview in previews]
    assert sum(first_text in text for text in texts) == 1
    assert sum(second_text in text for text in texts) == 1
    assert all(not (first_text in text and second_text in text) for text in texts)


def test_two_same_provider_root_sessions_share_the_synthesized_root_thread(
    tmp_path: Path,
) -> None:
    """Historical test ID retained; the contract now requires execution isolation.

    Stage integrity treats test node IDs as release API. The old name described the
    defect, so keeping it preserves regression history while these assertions pin the
    corrected behavior: a shared synthesized display alias cannot merge executions.
    """
    graph = _content_graph(
        tmp_path,
        [
            (opencode_session_agent("ses_one"), "opencode.assistant_response", "ANSWER ONE"),
            (opencode_session_agent("ses_two"), "opencode.assistant_response", "ANSWER TWO"),
        ],
    )
    previews = [
        entry["conversation_preview"]
        for entry in conversation_record_entries(graph, tmp_path)
        if isinstance(entry.get("conversation_preview"), dict)
    ]
    _assert_independent_root_previews(
        previews,
        alias="opencode:root",
        first_text="ANSWER ONE",
        second_text="ANSWER TWO",
    )


def test_two_antigravity_root_conversations_are_isolated(tmp_path: Path) -> None:
    first = {
        "id": "agent:antigravity:conversation:ag-root-one",
        "type": "agent",
        "name": "Antigravity conversation",
        "attributes": {
            "provider": "antigravity",
            "conversation_id": "ag-root-one",
            "identity_semantics": "provider_conversation_id",
        },
    }
    second = {
        "id": "agent:antigravity:conversation:ag-root-two",
        "type": "agent",
        "name": "Antigravity conversation",
        "attributes": {
            "provider": "antigravity",
            "conversation_id": "ag-root-two",
            "identity_semantics": "provider_conversation_id",
        },
    }
    graph = _content_graph(
        tmp_path,
        [
            (first, "antigravity.assistant_response", "AG ANSWER ONE"),
            (second, "antigravity.assistant_response", "AG ANSWER TWO"),
        ],
    )
    previews = [
        entry["conversation_preview"]
        for entry in conversation_record_entries(graph, tmp_path)
        if isinstance(entry.get("conversation_preview"), dict)
    ]
    _assert_independent_root_previews(
        previews,
        alias="antigravity:root",
        first_text="AG ANSWER ONE",
        second_text="AG ANSWER TWO",
    )


# ── Cross-provider: existing thread identity contracts are unchanged ─────────


@pytest.mark.parametrize(
    "provider,source,content_kind",
    [
        ("claude", {"id": "agent:Claude Code", "type": "agent", "name": "Claude Code",
                    "attributes": {"provider": "claude", "session_id": "s"}},
         "claude.assistant_final_response"),
        ("cursor", {"id": "agent:Cursor", "type": "agent", "name": "Cursor",
                    "attributes": {"provider": "cursor", "conversation_id": "c"}},
         "cursor.assistant_final_response"),
        ("opencode", opencode_session_agent("ses_solo"), "opencode.assistant_response"),
        ("gemini", {"id": "agent:Gemini CLI", "type": "agent", "name": "Gemini CLI",
                    "attributes": {"provider": "gemini", "session_id": "g"}},
         "gemini.assistant_final_response"),
        ("antigravity", {"id": "agent:antigravity:conversation:c7", "type": "agent",
                         "name": "Antigravity conversation",
                         "attributes": {"provider": "antigravity", "conversation_id": "c7"}},
         "antigravity.assistant_response"),
        ("openrouter", {"id": "agent:openrouter", "type": "agent", "name": "OpenRouter",
                        "attributes": {"provider": "openrouter", "session_id": "o"}},
         "inference_gateway.openrouter.response"),
    ],
    ids=["claude", "cursor", "opencode", "gemini", "antigravity", "gateway"],
)
def test_root_thread_identity_contract_is_unchanged(
    tmp_path: Path, provider: str, source: dict[str, Any], content_kind: str
) -> None:
    """Providers exposing no thread of their own keep the synthesized id they had."""
    run_root = tmp_path / provider
    graph = _content_graph(run_root, [(source, content_kind, "answer")])
    previews = [
        entry["conversation_preview"]
        for entry in conversation_record_entries(graph, run_root)
        if isinstance(entry.get("conversation_preview"), dict)
    ]
    assert len(previews) == 1
    assert previews[0]["thread_id"] == f"{provider}:root"
    assert previews[0]["is_root"] is True
    assert previews[0]["evidence_thread_ids"] == [f"{provider}:root"]


def test_claude_subagent_parent_link_contract_is_unchanged(tmp_path: Path) -> None:
    child = claude_subagent({"session_id": "s", "agent_id": "7", "agent_type": "Explore"})
    assert child is not None
    graph = _content_graph(
        tmp_path,
        [
            ({"id": "agent:Claude Code", "type": "agent", "name": "Claude Code",
              "attributes": {"provider": "claude", "session_id": "s"}},
             "claude.assistant_final_response", "root answer"),
            (child, "claude.subagent_final_response", "child answer"),
        ],
    )
    previews = [
        entry["conversation_preview"]
        for entry in conversation_record_entries(graph, tmp_path)
        if isinstance(entry.get("conversation_preview"), dict)
    ]
    child_preview = next(p for p in previews if not p["is_root"])
    assert child_preview["parent_thread_id"] == "claude:root"
