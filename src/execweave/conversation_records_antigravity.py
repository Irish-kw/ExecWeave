from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import conversation_preview as _preview_module
from .conversation_records_common import history_message_key as _history_message_key


def apply_stable_ordinals(
    path: str | Path,
    *,
    content_kind: str,
    provider: str,
    preview: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Keep user-visible Antigravity turns on the transcript's own step indexes."""
    if (
        not isinstance(preview, dict)
        or provider.strip().lower() != "antigravity"
        or not content_kind.startswith("antigravity.conversation_transcript")
    ):
        return preview
    messages = preview.get("messages")
    if not isinstance(messages, list):
        return preview
    stable_ordinals = _antigravity_step_ordinals(path)
    if len(stable_ordinals) != len(messages):
        return preview
    for message, stable_ordinal in zip(messages, stable_ordinals, strict=True):
        if isinstance(message, dict) and stable_ordinal is not None:
            message["ordinal"] = stable_ordinal
    return preview


def _antigravity_step_ordinals(path: str | Path) -> list[int | None]:
    """Recover stable step indexes for user-visible Antigravity transcript records."""
    source_path = Path(path).expanduser().resolve(strict=False)
    try:
        lines = source_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return []

    ordinals: list[int | None] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue
        role = str(record.get("source") or "").strip().lower()
        record_type = str(record.get("type") or "").strip().lower()
        text = _preview_module._text_parts(record.get("content") or record.get("text"))
        visible_user = role in {"user_explicit", "user", "human"} and record_type in {
            "user_input",
            "user_message",
            "",
        }
        visible_assistant = role in {"model", "assistant"} and record_type == "planner_response"
        if not text or not (visible_user or visible_assistant):
            continue
        record_ordinal = record.get("ordinal")
        if isinstance(record_ordinal, int) and not isinstance(record_ordinal, bool):
            ordinals.append(record_ordinal)
            continue
        step_index = record.get("step_index")
        ordinals.append(
            step_index
            if isinstance(step_index, int) and not isinstance(step_index, bool)
            else None
        )
    return ordinals


def _project_antigravity_addressed_tasks(
    entries: list[dict[str, Any]],
    graph: dict[str, Any],
) -> None:
    """Project exact parent-addressed send_message text into the child timeline.

    Raw Antigravity topology already carries positive ``parent_scope_id`` evidence on
    each validated child node. Raw send_message conversation evidence carries exact
    provider sender and recipient conversation IDs. Join those two facts only for
    presentation: an addressed parent message becomes a child task opener, while raw
    evidence remains unchanged and delivery/consumption remain explicitly unobserved.
    """
    prefix = "agent:antigravity:conversation:"
    topology: dict[str, tuple[str, str]] = {}
    for node in graph.get("nodes", []):
        if not isinstance(node, dict) or node.get("type") != "agent":
            continue
        node_id = node.get("id")
        attrs = node.get("attributes")
        attrs = attrs if isinstance(attrs, dict) else {}
        if not isinstance(node_id, str) or not node_id.startswith(prefix):
            continue
        if str(attrs.get("provider") or "").lower() != "antigravity":
            continue
        parent_path = attrs.get("parent_agent_path")
        parent_scope = attrs.get("parent_scope_id")
        if not isinstance(parent_path, str) or not parent_path:
            continue
        if not isinstance(parent_scope, str) or not parent_scope:
            continue
        topology[node_id.removeprefix(prefix)] = (parent_scope, parent_path)

    children: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if str(entry.get("provider") or "").lower() != "antigravity":
            continue
        source_id = entry.get("source_id")
        preview = entry.get("conversation_preview")
        if not isinstance(source_id, str) or not source_id.startswith(prefix):
            continue
        child_id = source_id.removeprefix(prefix)
        if child_id not in topology or not isinstance(preview, dict):
            continue
        children[child_id] = entry

    additions: dict[str, list[dict[str, Any]]] = {child_id: [] for child_id in children}
    for entry in entries:
        if str(entry.get("provider") or "").lower() != "antigravity":
            continue
        preview = entry.get("conversation_preview")
        if not isinstance(preview, dict):
            continue
        for message in preview.get("messages") or []:
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
            parent_scope, parent_path = topology[child_id]
            if sender_id != parent_scope:
                continue
            child_preview = child_entry["conversation_preview"]
            task = dict(message)
            task.update(
                {
                    "kind": "task",
                    "phase": "assignment",
                    "sender": parent_path,
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
