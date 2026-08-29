from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .conversation_preview import conversation_preview

_CONVERSATION_PATH_RE = re.compile(
    r"^content/sha256/(?P<sha256>[0-9a-f]{64})\.(?P<suffix>json|txt|bin)$"
)
_CONVERSATION_TOKENS = (
    "conversation_transcript",
    "conversation_item",
    "agent_message",
    "user_message",
    "user_prompt",
    "assistant_display",
    "assistant_response",
    "assistant_final_response",
    "assistant_messages",
    "assistant_content_blocks",
    "response_object",
    "standard_logging_response",
    "completed_text",
    "agent_response_candidate",
    "subtask_prompt",
    "subtask_description",
    "subagent_task",
    "subagent_description",
    "subagent_summary",
    "subagent_final_response",
    "prompt_submission_candidate",
    "inference_message",
    "request_messages",
    "request_prompt",
    "request_input",
    "model_context_messages",
)


def is_conversation_content_kind(content_kind: str) -> bool:
    """Return whether one stored value belongs in the user-facing conversation index."""
    if not isinstance(content_kind, str) or not content_kind:
        return False
    value = content_kind.lower()
    if value == "inference_gateway.openrouter.response":
        return True
    return any(token in value for token in _CONVERSATION_TOKENS)


def _safe_content_reference(node: dict[str, Any]) -> dict[str, Any] | None:
    if node.get("type") != "observed_content":
        return None
    attributes = node.get("attributes")
    if not isinstance(attributes, dict):
        return None
    path = attributes.get("path")
    sha256 = attributes.get("sha256")
    content_kind = attributes.get("content_kind")
    if not all(isinstance(value, str) and value for value in (path, sha256, content_kind)):
        return None
    if not is_conversation_content_kind(content_kind):
        return None
    match = _CONVERSATION_PATH_RE.fullmatch(path)
    if match is None or match.group("sha256") != sha256:
        return None
    size_bytes = attributes.get("size_bytes")
    if not isinstance(size_bytes, int) or isinstance(size_bytes, bool) or size_bytes < 0:
        return None
    return {
        "path": path,
        "sha256": sha256,
        "size_bytes": size_bytes,
        "content_kind": content_kind,
        "media_type": attributes.get("media_type"),
        "representation": attributes.get("representation"),
        "complete_from_source": attributes.get("complete_from_source"),
    }


def _provider(source: dict[str, Any] | None, content_kind: str) -> str:
    if isinstance(source, dict):
        attributes = source.get("attributes")
        if isinstance(attributes, dict):
            for key in ("provider", "provider_name"):
                value = attributes.get(key)
                if isinstance(value, str) and value:
                    return value
    parts = content_kind.split(".")
    if len(parts) > 1 and parts[0] == "inference_gateway":
        return parts[1]
    if parts and parts[0] == "openai_compatible":
        return "openai-compatible"
    prefix = parts[0] if parts else ""
    return prefix if prefix else "unknown"


def _run_local_path(root: Path, relative: str) -> Path | None:
    try:
        candidate = (root / relative).resolve(strict=False)
        candidate.relative_to(root)
    except (OSError, RuntimeError, ValueError):
        return None
    return candidate if candidate.is_file() else None


def _conversation_preview(
    root: Path | None,
    reference: dict[str, Any],
    *,
    provider: str,
    source: dict[str, Any] | None,
    timestamp: object,
    ordinal: object,
) -> dict[str, Any] | None:
    if root is None:
        return None
    relative = reference.get("path")
    content_kind = reference.get("content_kind")
    if not isinstance(relative, str) or not isinstance(content_kind, str):
        return None
    path = _run_local_path(root, relative)
    if path is None:
        return None
    return conversation_preview(
        path,
        content_kind=content_kind,
        provider=provider,
        source=source,
        timestamp=timestamp,
        ordinal=ordinal,
    )


def _entry_rank(entry: dict[str, Any]) -> tuple[int, int, str]:
    last_sequence = entry.get("last_sequence")
    sequence = last_sequence if isinstance(last_sequence, int) else -1
    size = entry.get("size_bytes")
    size_bytes = size if isinstance(size, int) else -1
    return sequence, size_bytes, str(entry.get("path") or "")


def _message_key(message: dict[str, Any]) -> tuple[object, ...]:
    return (
        message.get("ordinal"),
        message.get("kind"),
        message.get("sender"),
        message.get("recipient"),
        message.get("text"),
        message.get("content_state"),
        message.get("phase"),
        message.get("task_name"),
    )


def _message_sort_key(message: dict[str, Any], index: int) -> tuple[object, ...]:
    ordinal = message.get("ordinal")
    return (
        0 if isinstance(ordinal, int) else 1,
        ordinal if isinstance(ordinal, int) else 2**63 - 1,
        str(message.get("timestamp") or ""),
        index,
    )


def _cross_source_message_sort_key(message: dict[str, Any], index: int) -> tuple[object, ...]:
    """Order a thread assembled from several transcripts by observation time.

    Ordinals are positions within one transcript, so they do not compare across
    transcripts. A thread whose evidence spans more than one stored blob orders by
    timestamp instead, and keeps the ordinal only as a tiebreak within one source.
    """
    timestamp = message.get("timestamp")
    ordinal = message.get("ordinal")
    return (
        0 if isinstance(timestamp, str) and timestamp else 1,
        str(timestamp or ""),
        ordinal if isinstance(ordinal, int) else 2**63 - 1,
        index,
    )


def _conversation_scope(
    entry: dict[str, Any],
    preview: dict[str, Any],
) -> tuple[str, str, str]:
    provider = str(entry.get("provider") or "unknown").lower()
    thread_id = str(
        preview.get("thread_id") or f"{provider}:{entry.get('source_id') or 'unknown'}"
    )
    agent_path = preview.get("agent_path")
    agent_scope = (
        str(agent_path)
        if isinstance(agent_path, str) and agent_path
        else str(entry.get("source_id") or "unknown")
    )
    return provider, thread_id, agent_scope


def _parent_agent_path(agent_path: object) -> str | None:
    if not isinstance(agent_path, str) or not agent_path.startswith("/root/"):
        return None
    parent = agent_path.rsplit("/", 1)[0]
    return parent or "/root"


def _merge_conversation_previews(entries: list[dict[str, Any]]) -> None:
    """Merge incremental provider content without crossing agent identity boundaries."""
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    thread_agents: dict[tuple[str, str], set[str]] = {}
    for entry in entries:
        preview = entry.get("conversation_preview")
        if not isinstance(preview, dict):
            continue
        scope = _conversation_scope(entry, preview)
        grouped.setdefault(scope, []).append(entry)
        thread_agents.setdefault(scope[:2], set()).add(scope[2])

    scoped_thread_ids: dict[tuple[str, str, str], str] = {}
    for scope in grouped:
        provider, raw_thread_id, agent_scope = scope
        if len(thread_agents.get((provider, raw_thread_id), set())) > 1:
            scoped_thread_ids[scope] = f"{raw_thread_id}::agent={agent_scope}"
        else:
            scoped_thread_ids[scope] = raw_thread_id

    merged_by_scope: dict[tuple[str, str, str], dict[str, Any]] = {}
    for scope, group in grouped.items():
        representative = max(group, key=_entry_rank)
        previews = [
            entry["conversation_preview"]
            for entry in group
            if isinstance(entry.get("conversation_preview"), dict)
        ]
        merged_messages: list[dict[str, Any]] = []
        for preview in previews:
            for message in preview.get("messages") or []:
                if isinstance(message, dict):
                    merged_messages.append(dict(message))
        sources = {str(entry.get("sha256") or "") for entry in group}
        sort_key = _cross_source_message_sort_key if len(sources) > 1 else _message_sort_key
        indexed = list(enumerate(merged_messages))
        indexed.sort(key=lambda pair: sort_key(pair[1], pair[0]))
        seen: set[tuple[object, ...]] = set()
        deduped: list[dict[str, Any]] = []
        for _, message in indexed:
            key = _message_key(message)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(message)

        truncated = len(deduped) > 80
        if truncated:
            deduped = deduped[:10] + deduped[-70:]

        latest_preview = representative["conversation_preview"]
        merged_preview: dict[str, Any] = {}
        for field in (
            "parent_thread_id",
            "agent_path",
            "agent_label",
            "provider_label",
            "agent_nickname",
            "is_root",
        ):
            for preview in reversed(previews):
                value = preview.get(field)
                if value is not None and value != "":
                    merged_preview[field] = value
                    break
        for field in (
            "parent_thread_id",
            "agent_path",
            "agent_label",
            "provider_label",
            "agent_nickname",
            "is_root",
        ):
            merged_preview.setdefault(field, latest_preview.get(field))
        merged_preview["thread_id"] = scoped_thread_ids[scope]
        merged_preview["message_count"] = len(deduped)
        merged_preview["messages_truncated"] = truncated or any(
            bool(preview.get("messages_truncated")) for preview in previews
        )
        merged_preview["messages"] = deduped

        for entry in group:
            entry.pop("conversation_preview", None)
        representative["conversation_preview"] = merged_preview
        merged_by_scope[scope] = merged_preview

    for scope, preview in merged_by_scope.items():
        parent_thread_id = preview.get("parent_thread_id")
        parent_path = _parent_agent_path(preview.get("agent_path"))
        if not isinstance(parent_thread_id, str) or not parent_thread_id or parent_path is None:
            continue
        parent_scope = (scope[0], parent_thread_id, parent_path)
        scoped_parent = scoped_thread_ids.get(parent_scope)
        if scoped_parent is not None:
            preview["parent_thread_id"] = scoped_parent


def _derived_agent_entry_source_id(entry: dict[str, Any], preview: dict[str, Any]) -> str:
    """Address a derived thread by the provider agent identity the graph also uses."""
    provider = str(entry.get("provider") or "provider").lower()
    agent_id = preview.get("agent_id")
    parent_thread_id = preview.get("parent_thread_id")
    if isinstance(agent_id, str) and agent_id and isinstance(parent_thread_id, str):
        return f"agent:{provider}:{parent_thread_id}:subagent:{agent_id}"
    return f"agent:{provider}:{preview.get('agent_path') or 'agent'}"


def _derived_agent_entries(
    entry: dict[str, Any],
    previews: list[Any],
) -> list[dict[str, Any]]:
    """Materialize agent-local threads a transcript carries routing evidence about.

    One provider transcript can be the only observable evidence for another agent's
    conversation. Those records are published under that agent's own identity so a
    parent thread never stands in for its children, while still referencing the same
    stored evidence blob.
    """
    results: list[dict[str, Any]] = []
    for preview in previews:
        if not isinstance(preview, dict) or not preview.get("messages"):
            continue
        agent_path = preview.get("agent_path")
        if not isinstance(agent_path, str) or not agent_path:
            continue
        derived_entry = dict(entry)
        derived_entry.pop("conversation_preview", None)
        derived_entry["source_id"] = _derived_agent_entry_source_id(entry, preview)
        derived_entry["source_name"] = preview.get("agent_label") or agent_path
        derived_entry["source_type"] = "agent"
        derived_entry["conversation_preview"] = preview
        results.append(derived_entry)
    return results


def conversation_record_entries(
    graph: dict[str, Any],
    run_root: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Build stable run-relative conversation references and provider-neutral visible previews."""
    root = Path(run_root).expanduser().resolve() if run_root is not None else None
    nodes = [node for node in graph.get("nodes", []) if isinstance(node, dict)]
    edges = [edge for edge in graph.get("edges", []) if isinstance(edge, dict)]
    node_by_id = {
        str(node["id"]): node
        for node in nodes
        if isinstance(node.get("id"), str) and node.get("id")
    }
    entries: list[dict[str, Any]] = []
    for edge in edges:
        target_id = edge.get("target")
        if not isinstance(target_id, str):
            continue
        target = node_by_id.get(target_id)
        if target is None:
            continue
        reference = _safe_content_reference(target)
        if reference is None:
            continue
        source_id = edge.get("source")
        source = node_by_id.get(source_id) if isinstance(source_id, str) else None
        provider = _provider(source, str(reference["content_kind"]))
        preview = _conversation_preview(
            root,
            reference,
            provider=provider,
            source=source,
            timestamp=edge.get("first_seen"),
            ordinal=edge.get("first_sequence"),
        )
        source_name = source.get("name") if isinstance(source, dict) else None
        if isinstance(preview, dict):
            agent_label = preview.get("agent_label")
            agent_path = preview.get("agent_path")
            if isinstance(agent_label, str) and agent_label:
                source_name = agent_label
            elif isinstance(agent_path, str) and agent_path:
                source_name = agent_path
        entry = {
            "provider": provider,
            "relation": edge.get("relation"),
            "source_id": source_id,
            "source_name": source_name,
            "source_type": source.get("type") if isinstance(source, dict) else None,
            "content_kind": reference["content_kind"],
            "path": reference["path"],
            "sha256": reference["sha256"],
            "size_bytes": reference["size_bytes"],
            "media_type": reference["media_type"],
            "representation": reference["representation"],
            "complete_from_source": reference["complete_from_source"],
            "first_sequence": edge.get("first_sequence"),
            "last_sequence": edge.get("last_sequence"),
            "first_seen": edge.get("first_seen"),
            "last_seen": edge.get("last_seen"),
        }
        derived = preview.pop("derived_agent_previews", None) if isinstance(preview, dict) else None
        if preview is not None:
            entry["conversation_preview"] = preview
        entries.append(entry)
        if isinstance(derived, list):
            entries.extend(_derived_agent_entries(entry, derived))

    entries.sort(
        key=lambda entry: (
            entry["first_sequence"]
            if isinstance(entry.get("first_sequence"), int)
            else 2**63 - 1,
            str(entry.get("first_seen") or ""),
            str(entry.get("provider") or ""),
            str(entry.get("source_id") or ""),
            str(entry.get("path") or ""),
        )
    )
    _merge_conversation_previews(entries)
    return entries


def _markdown_text(value: object) -> str:
    text = str(value) if value not in (None, "") else "unknown"
    return text.replace("|", "\\|").replace("\n", " ")


def _markdown_message_text(value: object) -> str:
    if not isinstance(value, str) or not value:
        return ""
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\r", "")
        .replace("\n", "  \n")
    )


def _preview_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rich = [entry for entry in entries if isinstance(entry.get("conversation_preview"), dict)]
    return sorted(
        rich,
        key=lambda entry: (
            0 if (entry.get("conversation_preview") or {}).get("is_root") else 1,
            str((entry.get("conversation_preview") or {}).get("agent_path") or ""),
            str(entry.get("provider") or ""),
            str(entry.get("source_id") or ""),
        ),
    )


def _render_markdown(entries: list[dict[str, Any]]) -> str:
    lines = [
        "# ExecWeave Conversation Records",
        "",
        "This index uses run-local, content-addressed evidence and a provider-neutral visible conversation projection. Provider-specific cache folders are not required for inspection.",
        "",
        f"Records: **{len(entries)}**",
        "",
    ]
    if not entries:
        lines.extend(
            [
                "No run-local conversation record was captured for this run.",
                "",
            ]
        )
        return "\n".join(lines)

    lines.extend(
        [
            "| # | Provider | Source | Relation | Content | Bytes | Stored copy |",
            "| ---: | --- | --- | --- | --- | ---: | --- |",
        ]
    )
    for index, entry in enumerate(entries, start=1):
        path = str(entry["path"])
        lines.append(
            "| "
            + " | ".join(
                [
                    str(index),
                    _markdown_text(entry.get("provider")),
                    _markdown_text(entry.get("source_name") or entry.get("source_id")),
                    _markdown_text(entry.get("relation")),
                    _markdown_text(entry.get("content_kind")),
                    str(entry.get("size_bytes") or 0),
                    f"[Open]({path})",
                ]
            )
            + " |"
        )

    rich_entries = _preview_entries(entries)
    if rich_entries:
        lines.extend(["", "## Visible conversation timeline", ""])
    for entry in rich_entries:
        preview = entry.get("conversation_preview") or {}
        agent_label = (
            preview.get("agent_label")
            or preview.get("agent_path")
            or entry.get("source_name")
            or entry.get("source_id")
        )
        provider_label = preview.get("provider_label") or entry.get("provider")
        heading = f"### {_markdown_text(provider_label)} · {_markdown_text(agent_label)}"
        nickname = preview.get("agent_nickname")
        if isinstance(nickname, str) and nickname and nickname != agent_label:
            heading += f" ({_markdown_text(nickname)})"
        lines.extend([heading, ""])

        messages = preview.get("messages")
        if not isinstance(messages, list) or not messages:
            lines.extend(["No user-visible messages were projected from this evidence.", ""])
            continue
        for message in messages:
            if not isinstance(message, dict):
                continue
            sender = message.get("sender") or agent_label
            recipient = message.get("recipient")
            direction = str(sender)
            if isinstance(recipient, str) and recipient:
                direction += f" → {recipient}"
            kind = str(message.get("kind") or "message")
            phase = message.get("phase")
            label = f"**{_markdown_text(kind)}**"
            if isinstance(phase, str) and phase:
                label += f" / {_markdown_text(phase)}"
            timestamp = message.get("timestamp")
            prefix = f"- `{_markdown_text(timestamp)}` {direction} · {label}: "
            if message.get("content_state") == "provider_encrypted":
                lines.append(
                    prefix
                    + "*provider-encrypted payload; plaintext is not exposed by the observed provider surface*"
                )
            else:
                text = _markdown_message_text(message.get("text"))
                lines.append(prefix + (text or "*(no plaintext body exposed)*"))
        lines.append("")

    lines.extend(
        [
            "Paths above are SHA-256-addressed copies inside this ExecWeave run. External provider cache paths are intentionally not required for inspection.",
            "",
        ]
    )
    return "\n".join(lines)


def write_conversation_records(
    graph: dict[str, Any],
    run_root: str | Path,
) -> tuple[Path, Path]:
    """Write deterministic JSON + Markdown indexes beside the viewer artifacts."""
    root = Path(run_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    entries = conversation_record_entries(graph, root)
    visible_message_count = sum(
        len(preview.get("messages") or [])
        for entry in entries
        if isinstance((preview := entry.get("conversation_preview")), dict)
    )
    payload = {
        "schema_version": "0.3",
        "scope": "run_local_provider_neutral_conversation_projection",
        "entry_count": len(entries),
        "visible_message_count": visible_message_count,
        "external_provider_folder_lookup_required": False,
        "entries": entries,
    }
    json_path = root / "conversations.json"
    markdown_path = root / "conversations.md"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(_render_markdown(entries), encoding="utf-8")
    return json_path, markdown_path
