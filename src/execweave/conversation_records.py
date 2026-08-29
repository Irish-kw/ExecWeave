from __future__ import annotations

from typing import Any

from . import _conversation_records_core as _core
from ._conversation_records_core import *  # noqa: F403
from .conversation_message_identity import dedupe_codex_message_observations

_core_merge_conversation_previews = _core._merge_conversation_previews


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

    The core merge remains the authority for conversation/execution identity. Before it
    consumes the per-evidence previews, this facade snapshots them so a provider message
    observed through several complementary Codex surfaces can later render once while
    retaining provenance for every observation. Raw evidence entries are never removed.
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


# Functions defined in the core module resolve this global at call time. Rebinding it
# here keeps the public API stable while adding the observation-reconciliation stage.
_core._merge_conversation_previews = _merge_conversation_previews
