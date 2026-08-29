from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .agent_topology import (
    COMPLETENESS_ROUTING_ONLY,
    EVIDENCE_CROSS_AGENT_ROUTING,
    PATH_PROVIDER_DECLARED,
    ROOT_PATH,
    THREAD_ID_PROVIDER_NATIVE,
    TOPOLOGY_OBSERVED,
    strongest_completeness,
)
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


def _conversation_identity_keys(
    entry: dict[str, Any],
    preview: dict[str, Any],
) -> tuple[str, str, set[tuple[str, str]]]:
    """Return the positive evidence that identifies this record's agent execution.

    Two records may be merged only when evidence establishes they describe the *same*
    execution. Two kinds of positive evidence qualify:

    ``graph_agent``
        The same graph agent node. That id already encodes the provider-native
        identity it was built from (``agent:codex:<session>:subagent:<agent_id>``), so
        sharing it is a provider-grounded statement that this is one execution.

    ``provider_thread``
        The same raw thread identity, which is how incremental provider content for one
        conversation has always been recognized.

    Matching labels, nicknames, similar-looking thread ids, or both being children of
    ``/root`` are deliberately absent: none of them establishes shared identity. The
    agent path is carried in every key rather than being a key itself, so records for
    two different agents can never merge no matter what else they share.
    """
    provider = str(entry.get("provider") or "unknown").lower()
    agent_path = preview.get("agent_path")
    agent_scope = (
        str(agent_path)
        if isinstance(agent_path, str) and agent_path
        else str(entry.get("source_id") or "unknown")
    )
    keys: set[tuple[str, str]] = set()
    source_id = entry.get("source_id")
    if isinstance(source_id, str) and source_id:
        keys.add(("graph_agent", source_id))
    thread_id = preview.get("thread_id")
    if isinstance(thread_id, str) and thread_id:
        keys.add(("provider_thread", thread_id))
    if not keys:
        keys.add(("unidentified", str(id(entry))))
    return provider, agent_scope, keys


def _canonical_thread_id(previews: list[dict[str, Any]]) -> tuple[str | None, list[str]]:
    """Pick the preferred thread id for one execution and keep every contributing id.

    A provider-native id wins over an ExecWeave-synthesized one, so merging never
    downgrades an identity the provider actually published, and a provider that exposes
    no thread of its own keeps the synthesized id it has always had. Selection is
    deterministic: sorted within each class.
    """
    native: set[str] = set()
    derived: set[str] = set()
    for preview in previews:
        thread_id = preview.get("thread_id")
        if not isinstance(thread_id, str) or not thread_id:
            continue
        if preview.get("thread_id_source") == THREAD_ID_PROVIDER_NATIVE:
            native.add(thread_id)
        else:
            derived.add(thread_id)
    evidence = sorted(native | derived)
    if native:
        return sorted(native)[0], evidence
    if derived:
        return sorted(derived)[0], evidence
    return None, evidence


def _parent_agent_path(agent_path: object) -> str | None:
    if not isinstance(agent_path, str) or not agent_path.startswith("/root/"):
        return None
    parent = agent_path.rsplit("/", 1)[0]
    return parent or "/root"


def _merge_conversation_previews(entries: list[dict[str, Any]]) -> None:
    """Merge evidence describing one agent execution, without crossing identities.

    One execution can be observed through several kinds of evidence that name its
    thread differently — a provider-native Codex rollout id on one record and a
    synthesized ``<provider>:root`` on another. Grouping by raw thread alone published
    those as two conversations for the same agent. Records are therefore grouped by the
    transitive closure of positive identity evidence (see
    :func:`_conversation_identity_keys`), which merges those records while still
    keeping genuinely distinct agents and distinct conversations apart.
    """
    indexed_entries: list[dict[str, Any]] = [
        entry for entry in entries if isinstance(entry.get("conversation_preview"), dict)
    ]
    if not indexed_entries:
        return

    parents = list(range(len(indexed_entries)))

    def find(node: int) -> int:
        while parents[node] != node:
            parents[node] = parents[parents[node]]
            node = parents[node]
        return node

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parents[max(left_root, right_root)] = min(left_root, right_root)

    scopes: list[tuple[str, str]] = []
    first_seen: dict[tuple[str, str, str, str], int] = {}
    for index, entry in enumerate(indexed_entries):
        provider, agent_scope, keys = _conversation_identity_keys(
            entry, entry["conversation_preview"]
        )
        scopes.append((provider, agent_scope))
        for kind, value in keys:
            # The agent scope is part of every key, so evidence can never join records
            # that belong to two different agents.
            slot = (provider, agent_scope, kind, value)
            union(index, first_seen.setdefault(slot, index))

    components: dict[int, list[int]] = {}
    for index in range(len(indexed_entries)):
        components.setdefault(find(index), []).append(index)

    # A provider can reuse one thread id across agents. Detect that before publishing,
    # so a reused id still cannot fold Agent 1 into Agent 2.
    canonical_owners: dict[tuple[str, str], set[str]] = {}
    resolved: dict[int, tuple[str | None, list[str]]] = {}
    for root, members in components.items():
        previews = [indexed_entries[i]["conversation_preview"] for i in members]
        canonical, evidence = _canonical_thread_id(previews)
        resolved[root] = (canonical, evidence)
        if canonical is not None:
            provider, agent_scope = scopes[members[0]]
            canonical_owners.setdefault((provider, canonical), set()).add(agent_scope)

    thread_alias: dict[tuple[str, str, str], str] = {}
    merged_by_root: dict[int, dict[str, Any]] = {}
    for root, members in components.items():
        group = [indexed_entries[i] for i in members]
        provider, agent_scope = scopes[members[0]]
        previews = [entry["conversation_preview"] for entry in group]
        canonical, evidence_thread_ids = resolved[root]

        published = canonical if canonical is not None else agent_scope
        if canonical is not None and len(canonical_owners[(provider, canonical)]) > 1:
            published = f"{canonical}::agent={agent_scope}"

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

        representative = max(group, key=_entry_rank)
        canonical_preview = next(
            (preview for preview in previews if preview.get("thread_id") == canonical),
            None,
        )
        # The record that owns the canonical thread describes this agent directly, so
        # its identity fields are preferred over one that inherited them from a parent.
        search_order = [canonical_preview] if canonical_preview is not None else []
        search_order += list(reversed(previews))

        merged_preview: dict[str, Any] = {}
        carried = (
            "parent_thread_id",
            "agent_path",
            "agent_label",
            "provider_label",
            "agent_nickname",
            "is_root",
            "agent_path_source",
            "topology_state",
            "topology_evidence",
            "parent_agent_path",
            "parent_relation_source",
            "provider_native_id",
            "thread_id_source",
        )
        for field in carried:
            for preview in search_order:
                value = preview.get(field)
                if value is not None and value != "":
                    merged_preview[field] = value
                    break
        for field in carried:
            merged_preview.setdefault(field, representative["conversation_preview"].get(field))
        merged_preview["conversation_completeness"] = strongest_completeness(
            [str(preview.get("conversation_completeness") or "") for preview in previews]
        )
        merged_preview["thread_id"] = published
        merged_preview["evidence_thread_ids"] = evidence_thread_ids
        merged_preview["message_count"] = len(deduped)
        merged_preview["messages_truncated"] = truncated or any(
            bool(preview.get("messages_truncated")) for preview in previews
        )
        merged_preview["messages"] = deduped

        for raw_thread_id in evidence_thread_ids:
            thread_alias[(provider, raw_thread_id, agent_scope)] = published

        for entry in group:
            entry.pop("conversation_preview", None)
        representative["conversation_preview"] = merged_preview
        merged_by_root[root] = merged_preview

    # Parent links were recorded against a contributing thread id, which may not be the
    # one published. Re-point them at the parent's canonical thread.
    for root, preview in merged_by_root.items():
        parent_thread_id = preview.get("parent_thread_id")
        parent_path = preview.get("parent_agent_path") or _parent_agent_path(
            preview.get("agent_path")
        )
        if not isinstance(parent_thread_id, str) or not parent_thread_id:
            continue
        if not isinstance(parent_path, str) or not parent_path:
            continue
        provider = scopes[components[root][0]][0]
        alias = thread_alias.get((provider, parent_thread_id, parent_path))
        if alias is not None:
            preview["parent_thread_id"] = alias


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
        preview.setdefault("agent_path_source", PATH_PROVIDER_DECLARED)
        preview.setdefault("topology_state", TOPOLOGY_OBSERVED)
        preview.setdefault("topology_evidence", EVIDENCE_CROSS_AGENT_ROUTING)
        preview.setdefault("parent_agent_path", ROOT_PATH)
        preview.setdefault("parent_relation_source", EVIDENCE_CROSS_AGENT_ROUTING)
        preview.setdefault("conversation_completeness", COMPLETENESS_ROUTING_ONLY)
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
        # Lead with the agent path. A provider nickname is often unrelated to the task
        # the agent was given ("OpenAI Codex · Avicenna" for /root/ci_agent), so heading
        # every section with provider plus nickname made six agents indistinguishable.
        agent_path = preview.get("agent_path")
        identity = (
            agent_path if isinstance(agent_path, str) and agent_path else agent_label
        )
        heading = f"### {_markdown_text(identity)} · {_markdown_text(provider_label)}"
        for annotation in (agent_label, preview.get("agent_nickname")):
            if (
                isinstance(annotation, str)
                and annotation
                and annotation != identity
                and annotation != provider_label
                and f"({_markdown_text(annotation)})" not in heading
            ):
                heading += f" ({_markdown_text(annotation)})"
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
