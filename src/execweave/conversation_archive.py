from __future__ import annotations

from pathlib import Path
from typing import Any

from .antigravity_subagent_linkage import validated_transcript_path as _antigravity_transcript_path
from .content_evidence import content_observation_event
from .content_store import FullFidelityContentStore


def _entity(
    entity_type: str,
    entity_id: str,
    *,
    name: str | None = None,
    attributes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "type": entity_type,
        "id": entity_id,
        "name": name,
        "attributes": attributes or {},
    }


def _canonical_absolute_path(value: object) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        path = Path(value).expanduser()
        if not path.is_absolute():
            return None
        return path.resolve(strict=False)
    except (OSError, RuntimeError, ValueError):
        return None


def _claude_main_transcript(payload: dict[str, Any]) -> Path | None:
    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        return None
    path = _canonical_absolute_path(payload.get("transcript_path"))
    if path is None or path.suffix.lower() != ".jsonl":
        return None
    if path.name != f"{session_id}.jsonl":
        return None
    return path


def _claude_subagent_transcript(payload: dict[str, Any]) -> Path | None:
    parent = _claude_main_transcript(payload)
    agent_id = payload.get("agent_id")
    if parent is None or not isinstance(agent_id, str) or not agent_id:
        return None
    candidate = _canonical_absolute_path(payload.get("agent_transcript_path"))
    if candidate is None:
        return None
    expected = (parent.with_suffix("") / "subagents" / f"agent-{agent_id}.jsonl").resolve(
        strict=False
    )
    return candidate if candidate == expected else None


def _archive(
    *,
    path: Path,
    store: FullFidelityContentStore,
    timestamp: str,
    provider: str,
    source: dict[str, Any],
    content_kind: str,
    observed_field: str,
    attribution: str,
    evidence_source: str,
    attributes: dict[str, Any],
) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    try:
        reference = store.put_file(
            path,
            content_kind=content_kind,
            media_type="text/plain; charset=utf-8",
            representation="provider_transcript_jsonl_snapshot",
        )
    except (OSError, RuntimeError, ValueError):
        return []
    return [
        content_observation_event(
            timestamp=timestamp,
            provider=provider,
            source=source,
            reference=reference,
            relation="HAS_CONVERSATION_TRANSCRIPT",
            observed_field=observed_field,
            evidence_source=evidence_source,
            attribution=attribution,
            event_type=f"semantic.{provider}.conversation.transcript.archived",
            attributes={
                "provider_transcript_snapshot": True,
                "external_provider_path_copied_into_run": True,
                "external_provider_path_required_for_later_inspection": False,
                "original_external_path_exposed_on_archive_edge": False,
                **attributes,
            },
        )
    ]


def claude_conversation_archive_events(
    payload: dict[str, Any],
    *,
    store: FullFidelityContentStore,
    timestamp: str,
) -> list[dict[str, Any]]:
    """Snapshot provider-declared Claude transcripts into the run after strict path checks."""
    hook = payload.get("hook_event_name")
    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        return []
    if hook == "SessionEnd":
        path = _claude_main_transcript(payload)
        if path is None:
            return []
        source = _entity(
            "agent",
            "agent:Claude Code",
            name="Claude Code",
            attributes={"provider": "claude", "session_id": session_id},
        )
        return _archive(
            path=path,
            store=store,
            timestamp=timestamp,
            provider="claude",
            source=source,
            content_kind="claude.conversation_transcript.main",
            observed_field="transcript_path",
            attribution="claude_hook",
            evidence_source="provider_transcript",
            attributes={
                "claude_hook_event_name": hook,
                "provider_session_id_exact": True,
                "transcript_scope": "main_session",
            },
        )
    if hook == "SubagentStop":
        path = _claude_subagent_transcript(payload)
        agent_id = payload.get("agent_id")
        if path is None or not isinstance(agent_id, str) or not agent_id:
            return []
        agent_type = payload.get("agent_type")
        name = agent_type if isinstance(agent_type, str) and agent_type else "Claude subagent"
        source = _entity(
            "agent",
            f"agent:claude:{session_id}:subagent:{agent_id}",
            name=name,
            attributes={
                "provider": "claude",
                "session_id": session_id,
                "agent_id": agent_id,
                "agent_type": name,
                "identity_semantics": "provider_exposed_agent_id",
            },
        )
        return _archive(
            path=path,
            store=store,
            timestamp=timestamp,
            provider="claude",
            source=source,
            content_kind="claude.conversation_transcript.subagent",
            observed_field="agent_transcript_path",
            attribution="claude_hook",
            evidence_source="provider_transcript",
            attributes={
                "claude_hook_event_name": hook,
                "provider_subagent_id_exact": True,
                "transcript_scope": "subagent",
            },
        )
    return []


def antigravity_conversation_archive_events(
    payload: dict[str, Any],
    *,
    store: FullFidelityContentStore,
    timestamp: str,
) -> list[dict[str, Any]]:
    """Snapshot only a validated Antigravity brain transcript supplied by the Stop hook."""
    conversation_id = payload.get("conversationId")
    if not isinstance(conversation_id, str) or not conversation_id:
        return []
    path = _antigravity_transcript_path(payload)
    if path is None:
        return []
    source = _entity(
        "agent",
        f"agent:antigravity:conversation:{conversation_id}",
        name="Antigravity conversation",
        attributes={
            "provider": "antigravity",
            "conversation_id": conversation_id,
            "identity_semantics": "provider_conversation_id",
        },
    )
    return _archive(
        path=path,
        store=store,
        timestamp=timestamp,
        provider="antigravity",
        source=source,
        content_kind="antigravity.conversation_transcript",
        observed_field="transcriptPath",
        attribution="antigravity_hook",
        evidence_source="provider_hook_plus_validated_transcript",
        attributes={
            "provider_conversation_id_exact": True,
            "transcript_scope": "conversation",
            "transcript_wire_semantics": "live_verified_implementation_wire",
        },
    )
