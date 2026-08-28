from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .codex_conversation import codex_rollout_preview

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
    "completed_text",
    "subtask_prompt",
    "subtask_description",
    "subagent_task",
    "subagent_description",
    "subagent_summary",
    "subagent_final_response",
    "prompt_submission_candidate",
    "inference_message",
    "model_context_messages",
)


def is_conversation_content_kind(content_kind: str) -> bool:
    """Return whether one stored value belongs in the user-facing conversation index."""
    if not isinstance(content_kind, str) or not content_kind:
        return False
    value = content_kind.lower()
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
            value = attributes.get("provider")
            if isinstance(value, str) and value:
                return value
    prefix = content_kind.split(".", 1)[0]
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
) -> dict[str, Any] | None:
    if root is None:
        return None
    content_kind = reference.get("content_kind")
    if not isinstance(content_kind, str) or not content_kind.startswith(
        "codex.conversation_transcript"
    ):
        return None
    relative = reference.get("path")
    if not isinstance(relative, str):
        return None
    path = _run_local_path(root, relative)
    return codex_rollout_preview(path) if path is not None else None


def conversation_record_entries(
    graph: dict[str, Any],
    run_root: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Build stable run-relative conversation references and safe visible previews."""
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
        preview = _conversation_preview(root, reference)
        source_name = source.get("name") if isinstance(source, dict) else None
        if isinstance(preview, dict):
            agent_path = preview.get("agent_path")
            if isinstance(agent_path, str) and agent_path:
                source_name = agent_path
        entry = {
            "provider": _provider(source, str(reference["content_kind"])),
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
        if preview is not None:
            entry["conversation_preview"] = preview
        entries.append(entry)
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
    latest: dict[str, dict[str, Any]] = {}
    for entry in entries:
        preview = entry.get("conversation_preview")
        if not isinstance(preview, dict):
            continue
        thread_id = preview.get("thread_id")
        key = str(thread_id or entry.get("source_id") or entry.get("path"))
        current = latest.get(key)
        if current is None:
            latest[key] = entry
            continue
        current_sequence = current.get("last_sequence")
        next_sequence = entry.get("last_sequence")
        current_rank = current_sequence if isinstance(current_sequence, int) else -1
        next_rank = next_sequence if isinstance(next_sequence, int) else -1
        if next_rank > current_rank or (
            next_rank == current_rank
            and int(entry.get("size_bytes") or 0) > int(current.get("size_bytes") or 0)
        ):
            latest[key] = entry
    return sorted(
        latest.values(),
        key=lambda entry: (
            str((entry.get("conversation_preview") or {}).get("agent_path") or ""),
            str(entry.get("source_id") or ""),
        ),
    )


def _render_markdown(entries: list[dict[str, Any]]) -> str:
    lines = [
        "# ExecWeave Conversation Records",
        "",
        "This index uses run-local, content-addressed evidence. Provider-specific Agent folders are not required for inspection.",
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
        agent_path = preview.get("agent_path") or entry.get("source_name") or entry.get("source_id")
        nickname = preview.get("agent_nickname")
        heading = f"### {_markdown_text(agent_path)}"
        if isinstance(nickname, str) and nickname:
            heading += f" ({_markdown_text(nickname)})"
        lines.extend([heading, ""])
        messages = preview.get("messages")
        if not isinstance(messages, list) or not messages:
            lines.extend(["No user-visible messages were projected from this rollout.", ""])
            continue
        for message in messages:
            if not isinstance(message, dict):
                continue
            sender = message.get("sender") or agent_path
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
                    + "*provider-encrypted payload; plaintext is not exposed by the Codex rollout*"
                )
            else:
                text = _markdown_message_text(message.get("text"))
                lines.append(prefix + (text or "*(no plaintext body exposed)*"))
        lines.append("")

    lines.extend(
        [
            "Paths above are SHA-256-addressed copies inside this ExecWeave run. External Claude, Codex, Cursor, OpenCode, or Antigravity cache paths are intentionally not required for inspection.",
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
        "schema_version": "0.2",
        "scope": "run_local_content_references",
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
