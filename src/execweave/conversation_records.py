from __future__ import annotations

from typing import Any

from . import _conversation_records_core as _core
from ._conversation_records_core import *  # noqa: F403
from .agent_topology import THREAD_ID_EXECWEAVE_DERIVED, THREAD_ID_PROVIDER_NATIVE
from .conversation_message_identity import dedupe_codex_message_observations

_core_merge_conversation_previews = _core._merge_conversation_previews


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


def _merge_conversation_previews(entries: list[dict[str, Any]]) -> None:
    """Merge execution identity first, then reconcile duplicate Codex observations.

    The core merge remains the authority for union/publication. This facade tightens
    only its identity-key policy, snapshots per-evidence previews, repairs any parent
    aliases that changed during publication, then lets complementary Codex observations
    render once while retaining provenance. Raw evidence entries are never removed.
    """
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


# Functions defined in the core module resolve these globals at call time. Rebinding
# keeps the public API stable while tightening identity before the observation stage.
_core._conversation_identity_keys = _conversation_identity_keys
_core._merge_conversation_previews = _merge_conversation_previews
