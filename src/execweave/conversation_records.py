from __future__ import annotations

from pathlib import Path
from typing import Any

from . import _conversation_records_core as _core
from ._conversation_records_core import *  # noqa: F403
from .agent_topology import THREAD_ID_EXECWEAVE_DERIVED, THREAD_ID_PROVIDER_NATIVE
from .conversation_message_identity import dedupe_codex_message_observations
from .conversation_records_antigravity import (
    _project_antigravity_addressed_tasks,
    apply_stable_ordinals,
)
from .conversation_records_codex import (
    _same_merged_execution,
    drop_root_user_prompts_from_codex_children,
)
from .conversation_records_common import history_message_key as _history_message_key
from .conversation_records_ollama import _ollama_current_turn, _ollama_root_agent_id

_core_conversation_preview = _core.conversation_preview
_core_merge_conversation_previews = _core._merge_conversation_previews


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
    return apply_stable_ordinals(
        path,
        content_kind=content_kind,
        provider=provider,
        preview=preview,
    )


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

    drop_root_user_prompts_from_codex_children(entries)


_core_conversation_record_entries = _core.conversation_record_entries


def conversation_record_entries(
    graph: dict[str, Any],
    run_root: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Publish root-only Ollama turns under the one run root without changing raw evidence."""
    entries = _core_conversation_record_entries(graph, run_root)
    _project_antigravity_addressed_tasks(entries, graph)
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
