from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

_LOGICAL_MESSAGE_WINDOW_SECONDS = 5.0
_SURFACE_PRIORITY = {
    "owner_provider_transcript": 0,
    "parent_routing_transcript": 1,
    "hook_supplied_content": 2,
    "other_provider_evidence": 9,
}


def _surface(entry: dict[str, Any], preview: dict[str, Any]) -> str:
    content_kind = str(entry.get("content_kind") or "").lower()
    if content_kind.startswith("codex.conversation_transcript"):
        if (
            preview.get("conversation_completeness") == "routing_only"
            or preview.get("evidence_scope") == "cross_agent_routing"
        ):
            return "parent_routing_transcript"
        return "owner_provider_transcript"
    if content_kind.startswith("codex."):
        return "hook_supplied_content"
    return "other_provider_evidence"


def _exact_key(message: dict[str, Any]) -> tuple[object, ...]:
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


def _sort_key(message: dict[str, Any], index: int, *, cross_source: bool) -> tuple[object, ...]:
    ordinal = message.get("ordinal")
    timestamp = message.get("timestamp")
    if cross_source:
        return (
            0 if isinstance(timestamp, str) and timestamp else 1,
            str(timestamp or ""),
            ordinal if isinstance(ordinal, int) else 2**63 - 1,
            index,
        )
    return (
        0 if isinstance(ordinal, int) else 1,
        ordinal if isinstance(ordinal, int) else 2**63 - 1,
        str(timestamp or ""),
        index,
    )


def _logical_key(message: dict[str, Any]) -> tuple[object, ...] | None:
    text = message.get("text")
    if (
        message.get("content_state") != "plaintext"
        or not isinstance(text, str)
        or not text
    ):
        return None
    kind = str(message.get("kind") or "").lower()
    phase = str(message.get("phase") or "").lower()
    if kind == "user_message" and message.get("sender") == "user":
        semantic_kind = "user_message"
    elif phase == "final_answer" or kind in {"subagent_final_response", "final_answer"}:
        semantic_kind = "final_answer"
    else:
        return None
    return (
        semantic_kind,
        message.get("sender"),
        message.get("recipient"),
        text,
        message.get("content_state"),
    )


def _timestamp_seconds(value: object) -> float | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def _observation(
    entry: dict[str, Any],
    preview: dict[str, Any],
    message: dict[str, Any],
) -> dict[str, Any]:
    return {
        "surface": _surface(entry, preview),
        "content_kind": entry.get("content_kind"),
        "relation": entry.get("relation"),
        "source_id": entry.get("source_id"),
        "sha256": entry.get("sha256"),
        "timestamp": message.get("timestamp"),
        "ordinal": message.get("ordinal"),
        "kind": message.get("kind"),
        "phase": message.get("phase"),
    }


def _observation_key(observation: dict[str, Any]) -> tuple[object, ...]:
    return tuple(
        observation.get(field)
        for field in (
            "surface",
            "content_kind",
            "relation",
            "source_id",
            "sha256",
            "timestamp",
            "ordinal",
            "kind",
            "phase",
        )
    )


def _dedupe_observations(observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[object, ...]] = set()
    result: list[dict[str, Any]] = []
    for observation in observations:
        key = _observation_key(observation)
        if key in seen:
            continue
        seen.add(key)
        result.append(observation)
    return result


def dedupe_codex_message_observations(
    observed: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]],
    *,
    cross_source: bool,
) -> list[dict[str, Any]]:
    """Collapse duplicate *observations* of one Codex logical message.

    Raw content/evidence entries stay untouched. This only affects the visible timeline.
    A collapse requires exact plaintext semantics plus complementary evidence surfaces
    close in time. Two observations from the same surface never collapse merely because
    their text matches, so a user or agent can legitimately repeat an identical message.
    """
    if not observed:
        return []

    ordered = list(enumerate(observed))
    ordered.sort(key=lambda pair: _sort_key(pair[1][0], pair[0], cross_source=cross_source))

    # Preserve the old exact-observation dedupe first, but retain provenance when the
    # exact same observation is carried by more than one stored evidence record.
    items: list[dict[str, Any]] = []
    exact_seen: dict[tuple[object, ...], int] = {}
    for _original_index, (message, entry, preview) in ordered:
        copied = dict(message)
        observation = _observation(entry, preview, copied)
        exact = _exact_key(copied)
        existing = exact_seen.get(exact)
        if existing is not None:
            items[existing]["observations"].append(observation)
            continue
        exact_seen[exact] = len(items)
        items.append(
            {
                "message": copied,
                "surface": observation["surface"],
                "priority": _SURFACE_PRIORITY.get(str(observation["surface"]), 9),
                "time": _timestamp_seconds(copied.get("timestamp")),
                "logical_key": _logical_key(copied),
                "observations": [observation],
            }
        )

    buckets: dict[tuple[object, ...], list[int]] = {}
    passthrough: list[int] = []
    for index, item in enumerate(items):
        key = item["logical_key"]
        if key is None:
            passthrough.append(index)
        else:
            buckets.setdefault(key, []).append(index)

    grouped: list[list[int]] = [[index] for index in passthrough]
    for indices in buckets.values():
        remaining = set(indices)
        while remaining:
            minimum_priority = min(int(items[index]["priority"]) for index in remaining)
            anchors = sorted(
                index for index in remaining if int(items[index]["priority"]) == minimum_priority
            )
            anchor_groups: dict[int, list[int]] = {index: [index] for index in anchors}
            anchor_surface = str(items[anchors[0]]["surface"])

            for surface in sorted(
                {
                    str(items[index]["surface"])
                    for index in remaining
                    if str(items[index]["surface"]) != anchor_surface
                },
                key=lambda value: (_SURFACE_PRIORITY.get(value, 9), value),
            ):
                candidates = [index for index in remaining if str(items[index]["surface"]) == surface]
                pairs: list[tuple[float, int, int]] = []
                for anchor in anchors:
                    anchor_time = items[anchor]["time"]
                    if not isinstance(anchor_time, float):
                        continue
                    for candidate in candidates:
                        candidate_time = items[candidate]["time"]
                        if not isinstance(candidate_time, float):
                            continue
                        distance = abs(anchor_time - candidate_time)
                        if distance <= _LOGICAL_MESSAGE_WINDOW_SECONDS:
                            pairs.append((distance, anchor, candidate))
                pairs.sort()
                used_anchors: set[int] = set()
                used_candidates: set[int] = set()
                for _distance, anchor, candidate in pairs:
                    if anchor in used_anchors or candidate in used_candidates:
                        continue
                    anchor_groups[anchor].append(candidate)
                    used_anchors.add(anchor)
                    used_candidates.add(candidate)

            consumed = {index for group in anchor_groups.values() for index in group}
            grouped.extend(anchor_groups.values())
            remaining.difference_update(consumed)

    logical_messages: list[tuple[dict[str, Any], int]] = []
    for group in grouped:
        anchor = min(
            group,
            key=lambda index: (
                int(items[index]["priority"]),
                str(items[index]["message"].get("timestamp") or ""),
                index,
            ),
        )
        message = dict(items[anchor]["message"])
        evidence: list[dict[str, Any]] = []
        for index in group:
            evidence.extend(items[index]["observations"])
        evidence = _dedupe_observations(evidence)
        if len(evidence) > 1:
            message["evidence_observation_count"] = len(evidence)
            message["evidence_observations"] = evidence
        logical_messages.append((message, min(group)))

    logical_messages.sort(
        key=lambda pair: _sort_key(pair[0], pair[1], cross_source=cross_source)
    )
    return [message for message, _index in logical_messages]
