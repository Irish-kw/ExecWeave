from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

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


def conversation_record_entries(graph: dict[str, Any]) -> list[dict[str, Any]]:
    """Build stable run-relative conversation references from graph evidence only."""
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
        entry = {
            "provider": _provider(source, str(reference["content_kind"])),
            "relation": edge.get("relation"),
            "source_id": source_id,
            "source_name": source.get("name") if isinstance(source, dict) else None,
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


def _render_markdown(entries: list[dict[str, Any]]) -> str:
    lines = [
        "# ExecWeave Conversation Records",
        "",
        "This index points only to run-local, content-addressed evidence. You do not need to browse provider-specific Agent folders.",
        "",
        f"Records: **{len(entries)}**",
        "",
    ]
    if not entries:
        lines.extend(["No conversation content was exposed by the selected integrations for this run.", ""])
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
    lines.extend(
        [
            "",
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
    entries = conversation_record_entries(graph)
    payload = {
        "schema_version": "0.1",
        "scope": "run_local_content_references",
        "entry_count": len(entries),
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
