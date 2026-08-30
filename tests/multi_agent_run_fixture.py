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


# Codex encrypts some delegations, and a plain answer may legitimately quote the
# words a routing envelope uses. Both are carried here so a browser check can tell
# "observed but not exposed" apart from "never recorded", and so a parser that scans
# for Sender:/Task name: outside a real Payload envelope loses a whole answer.
ENCRYPTED_SPAWN_INDEX = 1
QUOTED_ROUTING_ANSWER = (
    "The log line I was asked about reads:\n"
    "Sender: upstream-service\n"
    "Task name: nightly-rebuild\n"
    "Message type: heartbeat\n"
    "That is quoted prose, not an envelope."
)


def _root_rollout(*, truncated: bool = False) -> str:
    lines = [json.dumps({"type": "session_meta", "payload": {
        "id": ROOT_THREAD, "agent_path": "/root"}}, ensure_ascii=False)]
    ordinal = 1
    lines.append(_line(ordinal, {"type": "message", "role": "user",
        "content": [{"type": "input_text", "text": "spawn four agents"}],
        "internal_chat_message_metadata_passthrough": {"content_item_kinds": ["user.text"]}}))
    for index, (thread, path, nickname, marker) in enumerate(CHILDREN):
        ordinal += 1
        call_id = f"call_{index}"
        message = (
            "gAAAAA" + "encrypted-delegation"
            if index == ENCRYPTED_SPAWN_INDEX
            else f"answer question {index + 1}"
        )
        lines.append(_line(ordinal, {"type": "function_call", "name": "spawn_agent",
            "call_id": call_id, "arguments": json.dumps({"message": message})}))
        ordinal += 1
        lines.append(_line(ordinal, {"type": "function_call_output", "call_id": call_id,
            "output": json.dumps({"task_name": path, "thread_id": thread})}))
    if truncated:
        # Codex archives the rollout on every Stop hook, so the first snapshot of a run
        # holds the prompt and the delegations but none of the answers. A viewer that
        # reads one entry per agent instead of aggregating them shows this one forever.
        return "\n".join(lines) + "\n"
    for index, (thread, path, nickname, marker) in enumerate(CHILDREN):
        ordinal += 1
        answer = (
            f"{marker} done\n{QUOTED_ROUTING_ANSWER}"
            if index == 0
            else f"{marker} done"
        )
        lines.append(_line(ordinal, {"type": "agent_message", "author": path,
            "recipient": "/root",
            "content": [{"type": "output_text", "text": answer}]}))
    ordinal += 1
    summary = " · ".join(f"{marker}" for _, _, _, marker in CHILDREN)
    lines.append(_line(ordinal, {"type": "message", "role": "assistant",
        "phase": "final_answer",
        "content": [{"type": "output_text", "text": f"all four answered: {summary}"}]}))
    return "\n".join(lines) + "\n"


# Codex prepends the same multi-kilobyte plugin catalogue and environment block to
# every subagent, and the rollout records it where that agent's own assignment
# belongs. Read literally, four siblings were each handed the same enormous task and
# the four panels are indistinguishable. The fixture carries it verbatim-identical
# across the children so a viewer that presents it as the agent's assignment fails.
INJECTED_CONTEXT = "<recommended_plugins>\n" + "\n".join(
    f"- Plugin {index:03d} (plugin-{index:03d}@curated-remote)" for index in range(120)
) + "\n</recommended_plugins>\n<environment_context><cwd>/workspace</cwd></environment_context>"


def _child_rollout(thread: str, path: str, nickname: str, marker: str, index: int) -> str:
    lines = [json.dumps({"type": "session_meta", "payload": {
        "id": thread, "agent_path": path, "agent_nickname": nickname,
        "parent_thread_id": ROOT_THREAD}}, ensure_ascii=False)]
    lines.append(_line(0, {"type": "message", "role": "user",
        "content": [{"type": "input_text", "text": INJECTED_CONTEXT}]}))
    lines.append(_line(1, {"type": "message", "role": "user",
        "content": [{"type": "input_text", "text": f"answer question {index + 1}"}]}))
    lines.append(_line(2, {"type": "message", "role": "assistant", "phase": "final_answer",
        "content": [{"type": "output_text", "text": f"{marker} is the answer"}]}))
    return "\n".join(lines) + "\n"


def build_run(
    root: Path,
    *,
    per_agent_rollouts: bool = True,
    snapshots: int = 1,
) -> dict[str, Any]:
    """Build the run. With ``per_agent_rollouts`` off, only the root rollout exists.

    That is what a real Codex run looks like: the parent's file records the delegations
    it issued and the returns it received, so every child's turns are read from it.
    Each agent then cited the parent's whole transcript as its own raw evidence, and
    the link inside a child's section opened the entire run.
    """
    store = root / "content" / "sha256"
    store.mkdir(parents=True, exist_ok=True)
    nodes: list[dict[str, Any]] = [{"id": "agent:OpenAI Codex", "type": "agent",
        "name": "OpenAI Codex", "attributes": {"provider": "codex", "agent_role": "root",
        "root_agent_path": "/root"}}]
    edges: list[dict[str, Any]] = []
    documents: list[tuple[str, str]] = []
    if snapshots > 1:
        # Codex archives the rollout on every Stop hook, so one agent owns several
        # content records and the earliest ones carry nothing a reader can use: a real
        # four-agent run produced fourteen entries of which nine had no conversation at
        # all. A viewer that reads the first record matching an agent finds one of
        # these and shows an empty inspector for the rest of the run. The earliest
        # archive is written first so index order alone would select it.
        documents.append(("agent:OpenAI Codex", "partial archive, no session metadata\n"))
    documents.append(("agent:OpenAI Codex", _root_rollout()))
    for index, (thread, path, nickname, marker) in enumerate(CHILDREN):
        node_id = f"agent:codex:{ROOT_THREAD}:subagent:{thread}"
        nodes.append({"id": node_id, "type": "agent", "name": "default",
            "attributes": {"provider": "codex", "agent_role": "subagent",
                "subagent_id": thread, "agent_nickname": nickname,
                "child_agent_path": path, "parent_agent_path": "/root"}})
        if per_agent_rollouts:
            documents.append((node_id, _child_rollout(thread, path, nickname, marker, index)))
    # A run graph is mostly not agents. Selecting one of these used to resolve to the
    # same empty selection an unselected graph does, so a process or a network endpoint
    # drew every agent's conversation.
    nodes.append({"id": "process:codex", "type": "process", "name": "codex",
        "attributes": {"pid": 4242}})
    nodes.append({"id": "endpoint:203.0.113.7:443", "type": "network_endpoint",
        "name": "203.0.113.7:443", "attributes": {"port": 443}})
    edges.append({"source": "agent:OpenAI Codex", "target": "process:codex",
        "relation": "OBSERVED_PROCESS"})
    edges.append({"source": "process:codex", "target": "endpoint:203.0.113.7:443",
        "relation": "OBSERVED_CONNECTION"})

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
