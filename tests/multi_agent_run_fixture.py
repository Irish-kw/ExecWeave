"""A synthetic Codex run with four sibling subagents, built for viewer tests.

Every agent answers a different question and stamps a unique marker, so a viewer
that shows one agent another agent's conversation is caught by reading the page:
each subagent section must carry exactly its own marker. The root legitimately
carries all four, which keeps the check honest — a viewer that rendered nothing
would otherwise pass.

The two sibling ids in the middle share their first eight characters, the way
Codex's time-ordered ids do for agents spawned in the same millisecond.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT_THREAD = "01a05200-0000-7000-8000-00000000cafe"
CHILDREN = (
    ("01a05201-0000-7000-8000-000000000001", "/root/question_1", "Avicenna", "MARKER-ALPHA"),
    ("01a05201-0000-7000-8000-000000000002", "/root/question_2", "Banach", "MARKER-BRAVO"),
    ("01a05201-0000-7000-8000-000000000003", "/root/question_3", "Volta", "MARKER-CHARLIE"),
    ("01a05202-0000-7000-8000-000000000004", "/root/question_4", "Kepler", "MARKER-DELTA"),
)


def _line(ordinal: int, payload: dict[str, Any]) -> str:
    return json.dumps(
        {"type": "response_item", "timestamp": f"2026-01-01T00:00:{ordinal:02d}Z",
         "ordinal": ordinal, "payload": payload},
        ensure_ascii=False,
    )


def _root_rollout() -> str:
    lines = [json.dumps({"type": "session_meta", "payload": {
        "id": ROOT_THREAD, "agent_path": "/root"}}, ensure_ascii=False)]
    ordinal = 1
    lines.append(_line(ordinal, {"type": "message", "role": "user",
        "content": [{"type": "input_text", "text": "spawn four agents"}],
        "internal_chat_message_metadata_passthrough": {"content_item_kinds": ["user.text"]}}))
    for index, (thread, path, nickname, marker) in enumerate(CHILDREN):
        ordinal += 1
        call_id = f"call_{index}"
        lines.append(_line(ordinal, {"type": "function_call", "name": "spawn_agent",
            "call_id": call_id,
            "arguments": json.dumps({"message": f"answer question {index + 1}"})}))
        ordinal += 1
        lines.append(_line(ordinal, {"type": "function_call_output", "call_id": call_id,
            "output": json.dumps({"agent_path": path, "thread_id": thread})}))
    for thread, path, nickname, marker in CHILDREN:
        ordinal += 1
        lines.append(_line(ordinal, {"type": "agent_message", "author": path,
            "recipient": "/root",
            "content": [{"type": "output_text", "text": f"{marker} done"}]}))
    ordinal += 1
    summary = " · ".join(f"{marker}" for _, _, _, marker in CHILDREN)
    lines.append(_line(ordinal, {"type": "message", "role": "assistant",
        "phase": "final_answer",
        "content": [{"type": "output_text", "text": f"all four answered: {summary}"}]}))
    return "\n".join(lines) + "\n"


def _child_rollout(thread: str, path: str, nickname: str, marker: str, index: int) -> str:
    lines = [json.dumps({"type": "session_meta", "payload": {
        "id": thread, "agent_path": path, "agent_nickname": nickname,
        "parent_thread_id": ROOT_THREAD}}, ensure_ascii=False)]
    lines.append(_line(1, {"type": "message", "role": "user",
        "content": [{"type": "input_text", "text": f"answer question {index + 1}"}]}))
    lines.append(_line(2, {"type": "message", "role": "assistant", "phase": "final_answer",
        "content": [{"type": "output_text", "text": f"{marker} is the answer"}]}))
    return "\n".join(lines) + "\n"


def build_run(root: Path) -> dict[str, Any]:
    store = root / "content" / "sha256"
    store.mkdir(parents=True, exist_ok=True)
    nodes: list[dict[str, Any]] = [{"id": "agent:OpenAI Codex", "type": "agent",
        "name": "OpenAI Codex", "attributes": {"provider": "codex", "agent_role": "root",
        "root_agent_path": "/root"}}]
    edges: list[dict[str, Any]] = []
    documents = [("agent:OpenAI Codex", _root_rollout())]
    for index, (thread, path, nickname, marker) in enumerate(CHILDREN):
        node_id = f"agent:codex:{ROOT_THREAD}:subagent:{thread}"
        nodes.append({"id": node_id, "type": "agent", "name": "default",
            "attributes": {"provider": "codex", "agent_role": "subagent",
                "subagent_id": thread, "agent_nickname": nickname,
                "child_agent_path": path, "parent_agent_path": "/root"}})
        documents.append((node_id, _child_rollout(thread, path, nickname, marker, index)))
    for sequence, (source_id, text) in enumerate(documents):
        raw = text.encode("utf-8")
        digest = hashlib.sha256(raw).hexdigest()
        relative = f"content/sha256/{digest}.txt"
        (root / relative).write_bytes(raw)
        content_id = f"content:{digest}"
        nodes.append({"id": content_id, "type": "observed_content",
            "name": "conversation", "attributes": {"path": relative, "sha256": digest,
                "content_kind": "codex.conversation_transcript", "size_bytes": len(raw),
                "media_type": "text/plain", "representation": "complete",
                "complete_from_source": True}})
        edges.append({"source": source_id, "target": content_id,
            "relation": "HAS_CONVERSATION_TRANSCRIPT", "first_sequence": sequence,
            "first_seen": f"2026-01-01T00:00:{sequence:02d}Z"})
    return {"nodes": nodes, "edges": edges, "node_count": len(nodes), "edge_count": len(edges)}
