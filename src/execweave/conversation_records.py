from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import _conversation_records_core as _core
from . import conversation_preview as _preview_module
from ._conversation_records_core import *  # noqa: F403
from .agent_topology import THREAD_ID_EXECWEAVE_DERIVED, THREAD_ID_PROVIDER_NATIVE
from .conversation_message_identity import dedupe_codex_message_observations

_core_conversation_preview = _core.conversation_preview
_core_merge_conversation_previews = _core._merge_conversation_previews


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


def _conversation_preview(
    path: str | Path,
    *,
    content_kind: str,
    provider: str,
    source: dict[str, Any] | None,
    timestamp: object = None,
    ordinal: object = None,
) -> dict[str, Any] | None:
    preview = _core_conversation_preview(
        path,
        content_kind=content_kind,
        provider=provider,
        source=source,
        timestamp=timestamp,
        ordinal=ordinal,
    )
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


def _conversation_identity_keys(
    entry: dict[str, Any],
    preview: dict[str, Any],
) -> tuple[str, str, set[tuple[str, str]]]:
    """Return positive identity evidence without promoting presentation aliases.

    New conversation previews carry explicit thread provenance. For those records, use
    the provider-native execution identity (or the graph source id) as the namespace so
    two independent roots can both render as ``/root`` without becoming one execution.
    Legacy/hand-built records without provenance retain the historical path namespace.

    An ExecWeave-derived thread id such as ``opencode:root`` is only a presentation
    alias and is therefore never a positive union key. Provider-native threads remain
    positive identity evidence. Matching labels, nicknames and paths never union by
    themselves.
    """
    provider = str(entry.get("provider") or "unknown").lower()
    source_id = entry.get("source_id")
    source_id = source_id if isinstance(source_id, str) and source_id else None
    agent_path = preview.get("agent_path")
    agent_path = agent_path if isinstance(agent_path, str) and agent_path else None

    thread_source = preview.get("thread_id_source")
    if thread_source in {THREAD_ID_PROVIDER_NATIVE, THREAD_ID_EXECWEAVE_DERIVED}:
        native_id = preview.get("provider_native_id")
        if isinstance(native_id, str) and native_id:
            agent_scope = native_id
        elif source_id is not None:
            agent_scope = source_id
        else:
            agent_scope = agent_path or "unknown"
    else:
        # Backward compatibility for artifacts/tests written before thread provenance
        # existed. The path remains a namespace only; it is not itself a union key.
        agent_scope = agent_path or source_id or "unknown"

    keys: set[tuple[str, str]] = set()
    if source_id is not None:
        keys.add(("graph_agent", source_id))

    thread_id = preview.get("thread_id")
    if (
        isinstance(thread_id, str)
        and thread_id
        and thread_source != THREAD_ID_EXECWEAVE_DERIVED
    ):
        # ``None`` is accepted for legacy artifacts whose thread provenance predates
        # the explicit source field. Explicitly-derived ids are the dangerous case.
        keys.add(("provider_thread", thread_id))

    if not keys:
        keys.add(("unidentified", str(id(entry))))
    return provider, agent_scope, keys


def _repair_parent_thread_aliases(entries: list[dict[str, Any]]) -> None:
    """Repair parent publication aliases only when topology makes the owner unique."""
    aliases: dict[tuple[str, str, str], set[str]] = {}
    for entry in entries:
        preview = entry.get("conversation_preview")
        if not isinstance(preview, dict):
            continue
        provider = str(entry.get("provider") or "unknown").lower()
        agent_path = preview.get("agent_path")
        published = preview.get("thread_id")
        if not isinstance(agent_path, str) or not agent_path:
            continue
        if not isinstance(published, str) or not published:
            continue
        raw_ids = {
            value
            for value in preview.get("evidence_thread_ids") or []
            if isinstance(value, str) and value
        }
        if not raw_ids:
            raw_ids.add(published)
        for raw_id in raw_ids:
            aliases.setdefault((provider, raw_id, agent_path), set()).add(published)

    for entry in entries:
        preview = entry.get("conversation_preview")
        if not isinstance(preview, dict):
            continue
        parent_thread_id = preview.get("parent_thread_id")
        if not isinstance(parent_thread_id, str) or not parent_thread_id:
            continue
        parent_path = preview.get("parent_agent_path")
        if not isinstance(parent_path, str) or not parent_path:
            parent_path = _core._parent_agent_path(preview.get("agent_path"))
        if not isinstance(parent_path, str) or not parent_path:
            continue
        provider = str(entry.get("provider") or "unknown").lower()
        candidates = aliases.get((provider, parent_thread_id, parent_path), set())
        if len(candidates) == 1:
            preview["parent_thread_id"] = next(iter(candidates))


def _same_merged_execution(
    representative_entry: dict[str, Any],
    merged_preview: dict[str, Any],
    observed_entry: dict[str, Any],
    observed_preview: dict[str, Any],
) -> bool:
    if str(observed_entry.get("provider") or "").lower() != "codex":
        return False
    if observed_preview.get("agent_path") != merged_preview.get("agent_path"):
        return False

    representative_source = representative_entry.get("source_id")
    observed_source = observed_entry.get("source_id")
    if (
        isinstance(representative_source, str)
        and representative_source
        and observed_source == representative_source
    ):
        return True

    evidence_thread_ids = {
        value
        for value in merged_preview.get("evidence_thread_ids") or []
        if isinstance(value, str) and value
    }
    published_thread = merged_preview.get("thread_id")
    if isinstance(published_thread, str) and published_thread:
        evidence_thread_ids.add(published_thread)
    observed_thread = observed_preview.get("thread_id")
    return isinstance(observed_thread, str) and observed_thread in evidence_thread_ids



def _history_message_key(message: dict[str, Any]) -> tuple[object, ...]:
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


def _restore_complete_histories(
    entries: list[dict[str, Any]],
    snapshots: list[tuple[dict[str, Any], dict[str, Any]]],
) -> None:
    """Never silently drop middle rounds for providers whose history is user-facing."""
    for entry in entries:
        provider = str(entry.get("provider") or "").lower()
        if provider not in {"antigravity", "ollama"}:
            continue
        merged = entry.get("conversation_preview")
        source_id = entry.get("source_id")
        if not isinstance(merged, dict) or not isinstance(source_id, str) or not source_id:
            continue
        observed: list[dict[str, Any]] = []
        for observed_entry, observed_preview in snapshots:
            if str(observed_entry.get("provider") or "").lower() != provider:
                continue
            if observed_entry.get("source_id") != source_id:
                continue
            for message in observed_preview.get("messages") or []:
                if isinstance(message, dict):
                    observed.append(dict(message))
        if not observed:
            continue
        if provider == "ollama" and not any(
            message.get("content_role")
            in {"ollama_request_surface", "ollama_response_surface"}
            for message in observed
        ):
            # Legacy/provider-neutral root records have no wire-surface provenance.
            # Leave the core incremental merge untouched instead of applying the
            # Ollama cumulative-history repair to unrelated synthetic/root records.
            continue
        indexed = list(enumerate(observed))
        indexed.sort(
            key=lambda pair: (
                str(pair[1].get("timestamp") or ""),
                pair[1].get("ordinal")
                if isinstance(pair[1].get("ordinal"), int)
                else 2**63 - 1,
                pair[0],
            )
        )
        seen: set[tuple[object, ...]] = set()
        messages: list[dict[str, Any]] = []
        for _, message in indexed:
            key = _history_message_key(message)
            if key in seen:
                continue
            seen.add(key)
            messages.append(message)
        merged["message_count"] = len(messages)
        merged["messages_truncated"] = False
        merged["messages"] = messages


def _ollama_current_turn(preview: dict[str, Any]) -> None:
    """Reduce a cumulative Ollama chat request to the exact turn this exchange created."""
    messages = [message for message in preview.get("messages") or [] if isinstance(message, dict)]
    users = [
        message
        for message in messages
        if message.get("sender") == "user"
        and message.get("content_role") == "ollama_request_surface"
    ]
    response_assistants = [
        message
        for message in messages
        if message.get("content_role") == "ollama_response_surface"
        and str(message.get("kind") or "").startswith("assistant")
    ]
    if not users:
        return
    current = [users[-1]]
    if response_assistants:
        current.append(response_assistants[-1])
    preview["message_count"] = len(current)
    preview["messages_truncated"] = False
    preview["messages"] = current


def _ollama_root_agent_id(graph: dict[str, Any]) -> str | None:
    candidates = []
    for node in graph.get("nodes", []):
        if not isinstance(node, dict) or node.get("type") != "agent":
            continue
        node_id = node.get("id")
        if isinstance(node_id, str) and node_id.lower() == "agent:ollama":
            candidates.append(node_id)
    return candidates[0] if len(candidates) == 1 else None


def _merge_conversation_previews(entries: list[dict[str, Any]]) -> None:
    """Merge execution identity first, then reconcile duplicate Codex observations.

    The core merge remains the authority for union/publication. This facade tightens
    only its identity-key policy, snapshots per-evidence previews, repairs any parent
    aliases that changed during publication, then lets complementary Codex observations
    render once while retaining provenance. Raw evidence entries are never removed.
    """
    # Preserve which side of an Ollama exchange produced each visible message.
    # Cumulative request.messages can contain historical assistant text, so publication
    # must select the assistant observed on the response surface rather than guessing
    # from list position.
    for entry in entries:
        if str(entry.get("provider") or "").lower() != "ollama":
            continue
        preview = entry.get("conversation_preview")
        if not isinstance(preview, dict):
            continue
        kind = str(entry.get("content_kind") or "").lower()
        relation = str(entry.get("relation") or "").upper()
        if "assistant_messages" in kind or relation == "OBSERVED_ASSISTANT_MESSAGES":
            role = "ollama_response_surface"
        elif "request_messages" in kind or "request_prompt" in kind or "request_input" in kind:
            role = "ollama_request_surface"
        else:
            continue
        for message in preview.get("messages") or []:
            if isinstance(message, dict):
                message["content_role"] = role

    snapshots: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for entry in entries:
        preview = entry.get("conversation_preview")
        if not isinstance(preview, dict):
            continue
        snapshots.append(
            (
                dict(entry),
                {
                    **preview,
                    "messages": [
                        dict(message)
                        for message in preview.get("messages") or []
                        if isinstance(message, dict)
                    ],
                },
            )
        )

    _core_merge_conversation_previews(entries)
    _repair_parent_thread_aliases(entries)
    _restore_complete_histories(entries, snapshots)

    for entry in entries:
        if str(entry.get("provider") or "").lower() != "codex":
            continue
        merged_preview = entry.get("conversation_preview")
        if not isinstance(merged_preview, dict):
            continue

        observed: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]] = []
        source_hashes: set[str] = set()
        input_truncated = False
        for observed_entry, observed_preview in snapshots:
            if not _same_merged_execution(
                entry,
                merged_preview,
                observed_entry,
                observed_preview,
            ):
                continue
            input_truncated = input_truncated or bool(observed_preview.get("messages_truncated"))
            sha256 = observed_entry.get("sha256")
            if isinstance(sha256, str) and sha256:
                source_hashes.add(sha256)
            for message in observed_preview.get("messages") or []:
                if isinstance(message, dict):
                    observed.append((dict(message), observed_entry, observed_preview))

        if not observed:
            continue
        messages = dedupe_codex_message_observations(
            observed,
            cross_source=len(source_hashes) > 1,
        )
        truncated = len(messages) > 80
        if truncated:
            messages = messages[:10] + messages[-70:]
        merged_preview["message_count"] = len(messages)
        merged_preview["messages_truncated"] = truncated or input_truncated
        merged_preview["messages"] = messages



_core_conversation_record_entries = _core.conversation_record_entries


def conversation_record_entries(
    graph: dict[str, Any],
    run_root: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Publish root-only Ollama turns under the one run root without changing raw evidence."""
    entries = _core_conversation_record_entries(graph, run_root)
    root_id = _ollama_root_agent_id(graph)
    if root_id is None:
        return entries

    normalized = False
    for entry in entries:
        if str(entry.get("provider") or "").lower() != "ollama":
            continue
        preview = entry.get("conversation_preview")
        if not isinstance(preview, dict) or preview.get("is_root") is not True:
            continue
        if entry.get("source_type") != "inference_request":
            continue
        _ollama_current_turn(preview)
        preview["provider_native_id"] = root_id
        original_source_id = entry.get("source_id")
        if isinstance(original_source_id, str) and original_source_id != root_id:
            entry["evidence_source_id"] = original_source_id
            entry["evidence_source_type"] = entry.get("source_type")
        entry["source_id"] = root_id
        entry["source_name"] = "Ollama"
        entry["source_type"] = "agent"
        normalized = True

    if normalized:
        _merge_conversation_previews(entries)
    return entries


# Functions defined in the core module resolve these globals at call time. Rebinding
# keeps the public API stable while tightening identity before the observation stage.
_core.conversation_preview = _conversation_preview
_core._conversation_identity_keys = _conversation_identity_keys
_core._merge_conversation_previews = _merge_conversation_previews
_core.conversation_record_entries = conversation_record_entries
