from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import conversation_preview as _preview_module
from .agent_topology import (
    EVIDENCE_VALIDATED_CHILD_TRANSCRIPT,
    PATH_EXECWEAVE_DERIVED,
    ROOT_PATH,
    THREAD_ID_EXECWEAVE_DERIVED,
    TOPOLOGY_PROVIDER_REPORTED,
)
from .antigravity_subagent_linkage import read_transcript_records, transcript_subagent_links
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


def _conversation_id_from_source(source_id: object) -> str | None:
    prefix = "agent:antigravity:conversation:"
    if not isinstance(source_id, str) or not source_id.startswith(prefix):
        return None
    conversation_id = source_id.removeprefix(prefix)
    return conversation_id or None


def _restamp_agent_path(preview: dict[str, Any], previous: str, current: str) -> None:
    if not previous or previous == current:
        return
    for message in preview.get("messages") or []:
        if not isinstance(message, dict):
            continue
        if message.get("sender") == previous:
            message["sender"] = current
        if message.get("recipient") == previous:
            message["recipient"] = current


def _apply_child_identity(
    preview: dict[str, Any],
    *,
    agent_path: str,
    parent_scope_id: str,
    nickname: str | None,
) -> None:
    previous = str(preview.get("agent_path") or ROOT_PATH)
    preview["agent_path"] = agent_path
    preview["agent_path_source"] = PATH_EXECWEAVE_DERIVED
    preview["is_root"] = False
    preview["topology_state"] = TOPOLOGY_PROVIDER_REPORTED
    preview["parent_agent_path"] = ROOT_PATH
    preview["topology_evidence"] = EVIDENCE_VALIDATED_CHILD_TRANSCRIPT
    preview["parent_relation_source"] = EVIDENCE_VALIDATED_CHILD_TRANSCRIPT
    preview["parent_thread_id"] = f"antigravity:{parent_scope_id}"
    preview["thread_id"] = f"antigravity:{preview.get('provider_native_id') or agent_path}"
    preview["thread_id_source"] = THREAD_ID_EXECWEAVE_DERIVED
    if isinstance(nickname, str) and nickname:
        preview["agent_nickname"] = nickname
        preview["agent_label"] = nickname
    else:
        preview["agent_label"] = agent_path.rsplit("/", 1)[-1] or agent_path
    _restamp_agent_path(preview, previous, agent_path)


def apply_antigravity_role_path_fallback(
    entries: list[dict[str, Any]],
    graph: dict[str, Any],
    run_root: str | Path | None,
) -> None:
    """When graph topology is missing, derive /root/<Role> from archived transcripts.

    Same failure mode as Codex omitting agent_path: every conversation collapses to
    /root, recipients never match, and child history has no opener. The parent
    transcript already names child conversation ids in the invoke_subagent result.
    """
    if run_root is None:
        return
    root = Path(run_root).expanduser().resolve(strict=False)
    by_id: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if str(entry.get("provider") or "").lower() != "antigravity":
            continue
        conversation_id = _conversation_id_from_source(entry.get("source_id"))
        preview = entry.get("conversation_preview")
        relative = entry.get("path")
        if conversation_id is None or not isinstance(preview, dict):
            continue
        if not isinstance(relative, str) or not relative:
            continue
        by_id[conversation_id] = entry

    declared_children: set[str] = set()
    for node in graph.get("nodes", []):
        if not isinstance(node, dict) or node.get("type") != "agent":
            continue
        attrs = node.get("attributes")
        attrs = attrs if isinstance(attrs, dict) else {}
        if str(attrs.get("provider") or "").lower() != "antigravity":
            continue
        if isinstance(attrs.get("parent_agent_path"), str) and attrs.get("parent_agent_path"):
            child_id = attrs.get("conversation_id")
            if isinstance(child_id, str) and child_id:
                declared_children.add(child_id)

    for conversation_id, entry in list(by_id.items()):
        relative = entry.get("path")
        if not isinstance(relative, str):
            continue
        try:
            transcript = (root / relative).resolve(strict=False)
            transcript.relative_to(root)
        except (OSError, RuntimeError, ValueError):
            continue
        if not transcript.is_file():
            continue
        links = transcript_subagent_links(
            read_transcript_records(transcript),
            parent_id=conversation_id,
        )
        for link in links:
            child_id = link["conversation_id"]
            child_entry = by_id.get(child_id)
            if child_entry is None:
                continue
            if child_id in declared_children:
                continue
            child_preview = child_entry.get("conversation_preview")
            if not isinstance(child_preview, dict):
                continue
            if child_preview.get("is_root") is False and str(
                child_preview.get("agent_path") or ""
            ).startswith("/root/"):
                continue
            spec = link["spec"]
            nickname = spec.get("Role") if isinstance(spec.get("Role"), str) else spec.get("TypeName")
            nickname = nickname if isinstance(nickname, str) else None
            _apply_child_identity(
                child_preview,
                agent_path=str(link["agent_path"]),
                parent_scope_id=conversation_id,
                nickname=nickname,
            )
            prompt = spec.get("Prompt")
            if isinstance(prompt, str) and prompt.strip():
                task = {
                    "timestamp": None,
                    "ordinal": 0,
                    "kind": "task",
                    "phase": "assignment",
                    "sender": ROOT_PATH,
                    "recipient": child_preview["agent_path"],
                    "text": prompt,
                    "content_state": "plaintext",
                    "content_role": "antigravity_addressed_task",
                    "provider_sender_id": conversation_id,
                    "provider_recipient_id": child_id,
                    "delivery_observed": False,
                    "consumption_observed": False,
                    "task_name": nickname,
                }
                messages = [
                    dict(message)
                    for message in child_preview.get("messages") or []
                    if isinstance(message, dict)
                ]
                messages.append(task)
                messages.sort(
                    key=lambda message: (
                        str(message.get("timestamp") or ""),
                        message.get("ordinal")
                        if isinstance(message.get("ordinal"), int)
                        else 2**63 - 1,
                    )
                )
                seen: set[tuple[object, ...]] = set()
                unique: list[dict[str, Any]] = []
                for message in messages:
                    key = _history_message_key(message)
                    if key in seen:
                        continue
                    seen.add(key)
                    unique.append(message)
                child_preview["messages"] = unique
                child_preview["message_count"] = len(unique)
                child_preview["messages_truncated"] = False


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
