"""Semantic acceptance predicates, deliberately separate from argv/body search."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConversationSnapshot:
    owner: str
    prompt: str
    final: str
    tools: tuple[str, ...] = ()
    children: tuple[str, ...] = ()


def verify_conversation(
    snapshot: ConversationSnapshot, *, marker: str, done: str, foreign_markers: tuple[str, ...] = ()
) -> dict[str, bool]:
    """Markers in a prompt cannot establish assistant completion or ownership."""
    return {
        "/root": snapshot.owner == "/root",
        "Prompt": marker in snapshot.prompt
        and snapshot.prompt.strip() not in {"", "Not observed", "Not observed."},
        "Final": snapshot.final.strip() == done,
        "Isolation": not any(
            marker in snapshot.prompt or marker in snapshot.final for marker in foreign_markers
        ),
    }


def same_conversation(live: ConversationSnapshot, finished: ConversationSnapshot) -> bool:
    return live == finished
