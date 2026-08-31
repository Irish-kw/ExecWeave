from __future__ import annotations

from typing import Any

from . import _conversation_records_core as _core
from ._conversation_records_core import *  # noqa: F403
from .agent_topology import THREAD_ID_PROVIDER_NATIVE
from .conversation_message_identity import dedupe_codex_message_observations

_core_merge_conversation_previews = _core._merge_conversation_previews


def _execution_scope(entry: dict[str, Any], preview: dict[str, Any]) -> str:
    """Return the strongest execution identity available for conversation grouping.

    A rendered path such as ``/root`` is presentation/topology, not execution identity.
    Prefer provider-native thread identity when the provider published one, then the
    provider-native agent/session identity carried by topology projection, then the
    graph source id. Only evidence with none of those falls back to the rendered path.
    """
    thread_id = preview.get("thread_id")
    if (
        preview.get("thread_id_source") == THREAD_ID_PROVIDER_NATIVE
        and isinstance(thread_id, str)
        and thread_id
    ):
        return thread_id

    provider_native_id = preview.get("provider_native_id")
    if isinstance(provider_native_id, str) and provider_native_id:
        return provider_native_id

    source_id = entry.get("source_id")
    if isinstance(source_id, str) and source_id:
        return source_id

    agent_path = preview.get("agent_path")
    if isinstance(agent_path, str) and agent_path:
        return agent_path
    return "unknown"


def _conversation_identity_keys(
    entry: dict[str, Any],
    preview: dict[str, Any],
) -> tuple[str, str, set[tuple[str, str]]]:
    """Return only positive identity evidence for one agent execution.

    ExecWeave-derived thread ids such as ``opencode:root`` are display aliases. They
    must never become cross-execution union keys. Provider-native threads remain
    positive identity, and graph-agent identity remains valid inside the stronger
    execution scope returned by :func:`_execution_scope`.
    """
    provider = str(entry.get("provider") or "unknown").lower()
    agent_scope = _execution_scope(entry, preview)
    keys: set[tuple[str, str]] = set()

    source_id = entry.get("source_id")
    if isinstance(source_id, str) and source_id:
        keys.add(("graph_agent", source_id))

    thread_id = preview.get("thread_id")
    if (
        preview.get("thread_id_source") == THREAD_ID_PROVIDER_NATIVE
        and isinstance(thread_id, str)
        and thread_id
    ):
        keys.add(("provider_thread", thread_id))

    if not keys:
        keys.add(("unidentified", str(id(entry))))
    return provider, agent_scope, keys


def _repair_parent_thread_aliases(entries: list[dict[str, Any]]) -> None:
    """Re-point parent links after execution-scoped publication, without guessing.

    The core historically used ``agent_path`` as its merge scope and also as the parent
    alias lookup scope. R1 deliberately separates those concepts. Rebuild the alias
    table by topology path after merging, and update a child only when one unambiguous
    published parent owns that raw thread id at that path.
    """
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
        parent_path = preview.get("parent_agent_path")
        if not isinstance(parent_thread_id, str) or not parent_thread_id:
            continue
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

    The core merge remains the authority for union and publication. This facade supplies
    the execution-scoped positive-key policy, snapshots per-evidence previews, repairs
    topology-path aliases after publication, then lets complementary Codex observations
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
# them here keeps the public API stable while tightening execution identity and adding
# the observation-reconciliation stage.
_core._conversation_identity_keys = _conversation_identity_keys
_core._merge_conversation_previews = _merge_conversation_previews
