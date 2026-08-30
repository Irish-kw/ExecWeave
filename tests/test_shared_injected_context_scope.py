"""A shared preamble is something an agent was handed, not something it wrote.

Codex prepends the same multi-kilobyte block to every subagent and records it where
that agent's own assignment belongs, so four siblings render as four copies of one
plugin catalogue. The index marks such a block by the only fact that needs no knowledge
of the provider: it was handed to more than one agent.

Judged on repetition alone the rule also caught a child's answer. A child reports back
to its parent, so its answer appears in its own record and in the parent's — two agent
paths, one text — and the child lost the answer it had just given. Two of five agents in
a real run were affected; the other three only escaped because their answers were
shorter than the length threshold.
"""

from __future__ import annotations

from typing import Any

from execweave._conversation_records_core import (
    SHARED_INJECTED_CONTEXT,
    _mark_shared_injected_context,
)

PREAMBLE = "<recommended_plugins>\n" + "\n".join(f"- Plugin {i:03d}" for i in range(200))
ANSWER = "The governance view, at length. " * 20


def _entry(path: str, messages: list[dict[str, Any]]) -> dict[str, Any]:
    return {"conversation_preview": {"agent_path": path, "messages": messages}}


def _handed_to(path: str, text: str) -> dict[str, Any]:
    return {"sender": "/root", "recipient": path, "kind": "task", "text": text}


def _written_by(path: str, text: str) -> dict[str, Any]:
    return {
        "sender": path,
        "recipient": "/root",
        "kind": "subagent_final_response",
        "phase": "final_answer",
        "text": text,
    }


def _roles(entries: list[dict[str, Any]]) -> list[list[object]]:
    return [
        [message.get("content_role") for message in entry["conversation_preview"]["messages"]]
        for entry in entries
    ]


def test_a_block_handed_to_several_agents_is_marked() -> None:
    entries = [
        _entry("/root/alpha", [_handed_to("/root/alpha", PREAMBLE)]),
        _entry("/root/bravo", [_handed_to("/root/bravo", PREAMBLE)]),
    ]
    _mark_shared_injected_context(entries)
    assert _roles(entries) == [[SHARED_INJECTED_CONTEXT], [SHARED_INJECTED_CONTEXT]]


def test_a_block_handed_to_one_agent_is_that_agents_own_assignment() -> None:
    entries = [
        _entry("/root/alpha", [_handed_to("/root/alpha", PREAMBLE)]),
        _entry("/root/bravo", [_handed_to("/root/bravo", "answer question 2")]),
    ]
    _mark_shared_injected_context(entries)
    assert _roles(entries) == [[None], [None]]


def test_an_answer_repeated_in_the_parents_record_stays_the_childs_own() -> None:
    """The regression: the child's answer is in two records, and it is still its own."""
    child = _written_by("/root/governance", ANSWER)
    relayed = dict(child)
    entries = [
        _entry("/root/governance", [_handed_to("/root/governance", PREAMBLE), child]),
        _entry("/root/alpha", [_handed_to("/root/alpha", PREAMBLE)]),
        _entry("/root", [relayed]),
    ]
    _mark_shared_injected_context(entries)

    assert child.get("content_role") is None, "the child lost the answer it wrote"
    assert relayed.get("content_role") is None, "the parent lost the answer it received"
    marked = [
        message
        for entry in entries
        for message in entry["conversation_preview"]["messages"]
        if message.get("content_role") == SHARED_INJECTED_CONTEXT
    ]
    assert [message["recipient"] for message in marked] == ["/root/governance", "/root/alpha"]
