from __future__ import annotations

from typing import Any

from execweave.conversation_records import _merge_conversation_previews

CHILD_PATH = "/root/explorer"
CHILD_ID = "child-thread"
SOURCE_ID = "agent:codex:root-thread:subagent:child-thread"
FINAL = "SAME FINAL ANSWER"


def _message(
    timestamp: str,
    ordinal: int,
    *,
    kind: str = "subagent_final_response",
    phase: str | None = "final_answer",
    text: str | None = FINAL,
    sender: str = CHILD_PATH,
    recipient: str | None = "/root",
    content_state: str = "plaintext",
) -> dict[str, Any]:
    return {
        "timestamp": timestamp,
        "ordinal": ordinal,
        "kind": kind,
        "sender": sender,
        "recipient": recipient,
        "text": text,
        "content_state": content_state,
        "phase": phase,
        "task_name": None,
    }


def _preview(
    messages: list[dict[str, Any]],
    *,
    thread_id: str = CHILD_ID,
    routing_only: bool = False,
    root: bool = False,
) -> dict[str, Any]:
    return {
        "thread_id": thread_id,
        "thread_id_source": "provider_native",
        "parent_thread_id": None if root else "root-thread",
        "agent_path": "/root" if root else CHILD_PATH,
        "agent_label": "Codex" if root else "explorer",
        "provider_label": "OpenAI Codex",
        "is_root": root,
        "conversation_completeness": "routing_only" if routing_only else "provider_transcript",
        "message_count": len(messages),
        "messages_truncated": False,
        "messages": messages,
    }


def _entry(
    content_kind: str,
    preview: dict[str, Any],
    *,
    sha: str,
    source_id: str = SOURCE_ID,
    relation: str = "HAS_CONVERSATION_TRANSCRIPT",
    sequence: int = 1,
) -> dict[str, Any]:
    return {
        "provider": "codex",
        "relation": relation,
        "source_id": source_id,
        "source_name": "explorer",
        "source_type": "agent",
        "content_kind": content_kind,
        "path": f"content/sha256/{sha}.json",
        "sha256": sha,
        "size_bytes": 1,
        "first_sequence": sequence,
        "last_sequence": sequence,
        "conversation_preview": preview,
    }


def _visible(entries: list[dict[str, Any]]) -> dict[str, Any]:
    previews = [
        entry["conversation_preview"]
        for entry in entries
        if isinstance(entry.get("conversation_preview"), dict)
    ]
    assert len(previews) == 1
    return previews[0]


def test_child_final_observed_on_three_surfaces_is_one_logical_message() -> None:
    entries = [
        _entry(
            "codex.conversation_transcript.subagent",
            _preview([_message("2026-08-29T00:00:00.000Z", 10)]),
            sha="a" * 64,
            sequence=10,
        ),
        _entry(
            "codex.subagent_final_response",
            _preview(
                [_message("2026-08-29T00:00:00.300Z", 20)],
                thread_id="codex:derived-child",
            ),
            sha="b" * 64,
            relation="PRODUCED_ASSISTANT_RESPONSE",
            sequence=20,
        ),
        _entry(
            "codex.conversation_transcript.main",
            _preview(
                [
                    _message(
                        "2026-08-29T00:00:02.700Z",
                        30,
                        kind="final_answer",
                        phase=None,
                    )
                ],
                routing_only=True,
            ),
            sha="c" * 64,
            sequence=30,
        ),
    ]

    _merge_conversation_previews(entries)
    visible = _visible(entries)
    final = [message for message in visible["messages"] if message.get("text") == FINAL]
    assert len(final) == 1
    assert final[0]["kind"] == "subagent_final_response"
    assert final[0]["evidence_observation_count"] == 3
    assert {item["surface"] for item in final[0]["evidence_observations"]} == {
        "owner_provider_transcript",
        "parent_routing_transcript",
        "hook_supplied_content",
    }
    assert len(entries) == 3, "raw evidence records must not be discarded"
    assert {entry["content_kind"] for entry in entries} == {
        "codex.conversation_transcript.subagent",
        "codex.subagent_final_response",
        "codex.conversation_transcript.main",
    }


def test_root_prompt_hook_and_rollout_observations_collapse() -> None:
    prompt = "ROOT PROMPT"
    root_source = "agent:OpenAI Codex"
    entries = [
        _entry(
            "codex.user_prompt",
            _preview(
                [
                    _message(
                        "2026-08-29T00:00:00.000Z",
                        10,
                        kind="user_message",
                        phase=None,
                        text=prompt,
                        sender="user",
                        recipient="/root",
                    )
                ],
                thread_id="codex:root",
                root=True,
            ),
            sha="d" * 64,
            source_id=root_source,
            relation="RECEIVED_USER_PROMPT",
            sequence=10,
        ),
        _entry(
            "codex.conversation_transcript.main",
            _preview(
                [
                    _message(
                        "2026-08-29T00:00:00.100Z",
                        2,
                        kind="user_message",
                        phase=None,
                        text=prompt,
                        sender="user",
                        recipient="/root",
                    )
                ],
                thread_id="root-thread",
                root=True,
            ),
            sha="e" * 64,
            source_id=root_source,
            sequence=11,
        ),
    ]

    _merge_conversation_previews(entries)
    prompt_messages = [
        message
        for message in _visible(entries)["messages"]
        if message.get("text") == prompt
    ]
    assert len(prompt_messages) == 1
    assert prompt_messages[0]["evidence_observation_count"] == 2


def test_two_genuine_identical_finals_remain_two_messages() -> None:
    owner_messages = [
        _message("2026-08-29T00:00:00.000Z", 10),
        _message("2026-08-29T00:00:04.000Z", 11),
    ]
    entries = [
        _entry(
            "codex.conversation_transcript.subagent",
            _preview(owner_messages),
            sha="f" * 64,
            sequence=10,
        ),
        _entry(
            "codex.subagent_final_response",
            _preview(
                [_message("2026-08-29T00:00:00.200Z", 20)],
                thread_id="codex:derived-child",
            ),
            sha="1" * 64,
            sequence=20,
        ),
        _entry(
            "codex.subagent_final_response",
            _preview(
                [_message("2026-08-29T00:00:04.200Z", 21)],
                thread_id="codex:derived-child",
            ),
            sha="2" * 64,
            sequence=21,
        ),
    ]

    _merge_conversation_previews(entries)
    finals = [
        message
        for message in _visible(entries)["messages"]
        if message.get("text") == FINAL
    ]
    assert len(finals) == 2, "text equality must not erase a genuine repeated message"
    assert [message["evidence_observation_count"] for message in finals] == [2, 2]


def test_encrypted_messages_are_never_guessed_equal() -> None:
    entries = [
        _entry(
            "codex.conversation_transcript.subagent",
            _preview(
                [
                    _message(
                        "2026-08-29T00:00:00.000Z",
                        10,
                        kind="task",
                        phase="assignment",
                        text=None,
                        sender="/root",
                        recipient=CHILD_PATH,
                        content_state="provider_encrypted",
                    )
                ]
            ),
            sha="3" * 64,
            sequence=10,
        ),
        _entry(
            "codex.conversation_transcript.main",
            _preview(
                [
                    _message(
                        "2026-08-29T00:00:00.100Z",
                        20,
                        kind="new_task",
                        phase=None,
                        text=None,
                        sender="/root",
                        recipient=CHILD_PATH,
                        content_state="provider_encrypted",
                    )
                ],
                routing_only=True,
            ),
            sha="4" * 64,
            sequence=20,
        ),
    ]

    _merge_conversation_previews(entries)
    assert len(_visible(entries)["messages"]) == 2


def test_non_codex_keeps_existing_exact_observation_behavior() -> None:
    text = "same text may be repeated"
    source_id = "agent:other"
    first = _entry(
        "claude.assistant_response",
        _preview(
            [
                _message(
                    "2026-08-29T00:00:00.000Z",
                    1,
                    kind="assistant_message",
                    phase="response",
                    text=text,
                    sender="/root",
                    recipient=None,
                )
            ],
            thread_id="claude:root",
            root=True,
        ),
        sha="5" * 64,
        source_id=source_id,
        sequence=1,
    )
    second = _entry(
        "claude.assistant_response",
        _preview(
            [
                _message(
                    "2026-08-29T00:00:00.100Z",
                    2,
                    kind="assistant_message",
                    phase="response",
                    text=text,
                    sender="/root",
                    recipient=None,
                )
            ],
            thread_id="claude:root",
            root=True,
        ),
        sha="6" * 64,
        source_id=source_id,
        sequence=2,
    )
    first["provider"] = second["provider"] = "claude"

    entries = [first, second]
    _merge_conversation_previews(entries)
    assert len(_visible(entries)["messages"]) == 2
