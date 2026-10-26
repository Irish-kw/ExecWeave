from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CURSOR_HOOKS_REFERENCE = "https://cursor.com/docs/hooks"

OFFICIAL_CURSOR_HOOK_EVENTS = frozenset(
    {
        "sessionStart",
        "sessionEnd",
        "preToolUse",
        "postToolUse",
        "postToolUseFailure",
        "subagentStart",
        "subagentStop",
        "beforeShellExecution",
        "afterShellExecution",
        "beforeMCPExecution",
        "afterMCPExecution",
        "beforeReadFile",
        "afterFileEdit",
        "beforeSubmitPrompt",
        "preCompact",
        "stop",
        "afterAgentResponse",
        "afterAgentThought",
        "beforeTabFileRead",
        "afterTabFileEdit",
        "workspaceOpen",
    }
)

_ALREADY_PROJECTED_ELSEWHERE = frozenset(
    {
        "preToolUse",
        "postToolUse",
        "postToolUseFailure",
        "subagentStart",
        "subagentStop",
        "beforeShellExecution",
        "afterShellExecution",
        "beforeMCPExecution",
        "afterMCPExecution",
        "beforeReadFile",
        "afterFileEdit",
        "beforeSubmitPrompt",
        "afterAgentResponse",
        "afterAgentThought",
        "beforeTabFileRead",
        "afterTabFileEdit",
    }
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


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


def _root_agent() -> dict[str, Any]:
    return _entity(
        "agent",
        "agent:Cursor",
        name="Cursor",
        attributes={"provider": "cursor"},
    )


def _application() -> dict[str, Any]:
    return _entity(
        "provider_application",
        "provider-application:cursor",
        name="Cursor",
        attributes={"provider": "cursor"},
    )


def _event(
    *,
    timestamp: str,
    event_type: str,
    relation: str,
    source: dict[str, Any],
    target: dict[str, Any],
    attributes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    merged: dict[str, Any] = {
        "backend": "semantic",
        "provider": "cursor",
        "evidence_source": "provider_hook",
        "attribution": "cursor_official_hook_contract",
        "causal": False,
        "inferred": False,
        "official_hook_contract": True,
        "official_hook_reference": CURSOR_HOOKS_REFERENCE,
    }
    if attributes:
        merged.update(attributes)
    return {
        "timestamp": timestamp,
        "event_type": event_type,
        "relation": relation,
        "source": source,
        "target": target,
        "attributes": merged,
    }


def _common(payload: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "cursor_hook_event_name": payload.get("hook_event_name"),
    }
    for key in (
        "conversation_id",
        "generation_id",
        "session_id",
        "cursor_version",
        "model",
        "model_id",
    ):
        value = payload.get(key)
        if isinstance(value, (str, int, float, bool)) and value != "":
            result[f"cursor_{key}"] = value
    roots = payload.get("workspace_roots")
    if isinstance(roots, list):
        result["cursor_workspace_root_count"] = len(roots)
    return result


def _session(payload: dict[str, Any]) -> dict[str, Any]:
    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        raise ValueError(f"{payload.get('hook_event_name')} requires session_id")
    return _entity(
        "provider_session",
        f"provider-session:cursor:{session_id}",
        name=session_id,
        attributes={
            "provider": "cursor",
            "session_id": session_id,
            "identity_semantics": "provider_session_id",
        },
    )


def _observation_id(payload: dict[str, Any], *, timestamp: str, phase: str) -> str:
    stable = {
        "conversation_id": payload.get("conversation_id"),
        "generation_id": payload.get("generation_id"),
        "session_id": payload.get("session_id"),
        "hook_event_name": payload.get("hook_event_name"),
        "phase": phase,
        "timestamp": timestamp,
    }
    raw = json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _observation(
    payload: dict[str, Any],
    *,
    timestamp: str,
    phase: str,
    entity_type: str,
    name: str,
    attributes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ident = _observation_id(payload, timestamp=timestamp, phase=phase)
    merged = {
        "provider": "cursor",
        "observation_phase": phase,
        "identity_semantics": "provider_hook_observation_without_stable_stage_id",
    }
    if attributes:
        merged.update(attributes)
    return _entity(
        entity_type,
        f"{entity_type}:cursor:{ident}",
        name=name,
        attributes=merged,
    )


def _workspace_roots(payload: dict[str, Any]) -> list[str]:
    roots = payload.get("workspace_roots")
    if not isinstance(roots, list):
        raise ValueError("workspaceOpen requires workspace_roots")
    normalized = [root for root in roots if isinstance(root, str) and root]
    if not normalized:
        raise ValueError("workspaceOpen requires at least one workspace root")
    if len(normalized) != len(roots):
        raise ValueError("workspaceOpen workspace_roots must contain only non-empty strings")
    return normalized


def cursor_workspace_scope(payload: dict[str, Any]) -> tuple[str, Path]:
    """Return a stable, non-session workspace scope from provider-exposed roots."""

    roots = _workspace_roots(payload)
    canonical = json.dumps(
        sorted(roots),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]
    return digest, Path(roots[0]).expanduser()


def _workspace(payload: dict[str, Any]) -> dict[str, Any]:
    digest, _root = cursor_workspace_scope(payload)
    roots = _workspace_roots(payload)
    return _entity(
        "workspace",
        f"workspace:cursor:{digest}",
        name="Cursor workspace",
        attributes={
            "provider": "cursor",
            "workspace_root_count": len(roots),
            "identity_semantics": "sha256_of_sorted_provider_workspace_roots",
            "outside_agent_session": True,
        },
    )


def cursor_official_hook_semantic_events(
    payload: dict[str, Any],
    *,
    timestamp: str | None = None,
) -> list[dict[str, Any]]:
    """Project lifecycle semantics explicitly guaranteed by Cursor's hook contract."""

    hook = payload.get("hook_event_name")
    if not isinstance(hook, str) or not hook:
        raise ValueError("Cursor hook payload requires hook_event_name")
    if hook not in OFFICIAL_CURSOR_HOOK_EVENTS or hook in _ALREADY_PROJECTED_ELSEWHERE:
        return []

    observed_at = timestamp or _now()
    common = _common(payload)

    if hook == "sessionStart":
        background = payload.get("is_background_agent")
        if not isinstance(background, bool):
            raise ValueError("sessionStart requires is_background_agent")
        common.update(
            {
                "is_background_agent": background,
                "fire_and_forget_hook": True,
                "session_creation_blocked_by_hook_asserted": False,
            }
        )
        mode = payload.get("composer_mode")
        if isinstance(mode, str) and mode:
            common["composer_mode"] = mode
        return [
            _event(
                timestamp=observed_at,
                event_type="semantic.cursor.session.started",
                relation="STARTED_PROVIDER_SESSION",
                source=_root_agent(),
                target=_session(payload),
                attributes=common,
            )
        ]

    if hook == "sessionEnd":
        reason = payload.get("reason")
        if reason not in {"completed", "aborted", "error", "window_close", "user_close"}:
            raise ValueError("sessionEnd requires a documented reason")
        common["cursor_session_end_reason"] = reason
        for key in ("duration_ms", "is_background_agent", "final_status"):
            value = payload.get(key)
            if isinstance(value, (str, int, float, bool)) and value != "":
                common[key] = value
        common.update(
            {
                "fire_and_forget_hook": True,
                "flow_control_ignored_by_provider": True,
                "error_message_stored_separately": isinstance(
                    payload.get("error_message"), str
                ),
            }
        )
        return [
            _event(
                timestamp=observed_at,
                event_type="semantic.cursor.session.ended",
                relation="OBSERVED_PROVIDER_SESSION_END",
                source=_root_agent(),
                target=_session(payload),
                attributes=common,
            )
        ]

    if hook == "preCompact":
        trigger = payload.get("trigger")
        if trigger not in {"auto", "manual"}:
            raise ValueError("preCompact requires trigger auto or manual")
        for key in (
            "context_usage_percent",
            "context_tokens",
            "context_window_size",
            "message_count",
            "messages_to_compact",
            "is_first_compaction",
        ):
            value = payload.get(key)
            if isinstance(value, (int, float, bool)) and not (
                isinstance(value, bool) and key != "is_first_compaction"
            ):
                common[key] = value
        common.update(
            {
                "compaction_trigger": trigger,
                "observational_hook": True,
                "compaction_block_or_modify_supported": False,
                "compaction_completion_asserted": False,
            }
        )
        target = _observation(
            payload,
            timestamp=observed_at,
            phase="pre_compact",
            entity_type="context_compaction",
            name="Cursor pre-compaction observation",
            attributes={"trigger": trigger},
        )
        return [
            _event(
                timestamp=observed_at,
                event_type="semantic.cursor.compaction.pre",
                relation="OBSERVED_PRE_COMPACTION",
                source=_root_agent(),
                target=target,
                attributes=common,
            )
        ]

    if hook == "stop":
        status = payload.get("status")
        if status not in {"completed", "aborted", "error"}:
            raise ValueError("stop requires status completed, aborted, or error")
        loop_count = payload.get("loop_count")
        if not isinstance(loop_count, int) or isinstance(loop_count, bool) or loop_count < 0:
            raise ValueError("stop requires non-negative integer loop_count")
        common.update(
            {
                "status": status,
                "loop_count": loop_count,
                "followup_message_supported": True,
                "agent_loop_can_resume_via_followup": True,
                "provider_session_end_asserted": False,
            }
        )
        target = _observation(
            payload,
            timestamp=observed_at,
            phase="stop",
            entity_type="agent_turn_stop",
            name="Cursor agent loop stop",
            attributes={
                "completion_semantics": "agent_loop_ended_before_optional_hook_followup"
            },
        )
        return [
            _event(
                timestamp=observed_at,
                event_type="semantic.cursor.turn.stop_observed",
                relation="OBSERVED_TURN_STOP",
                source=_root_agent(),
                target=target,
                attributes=common,
            )
        ]

    if hook == "workspaceOpen":
        roots = _workspace_roots(payload)
        workspace = _workspace(payload)
        common.update(
            {
                "outside_agent_session": True,
                "conversation_identity_available": False,
                "session_identity_available": False,
                "fires_on_workspace_open_and_folder_change": True,
            }
        )
        events = [
            _event(
                timestamp=observed_at,
                event_type="semantic.cursor.workspace.open_observed",
                relation="OBSERVED_WORKSPACE_OPEN",
                source=_application(),
                target=workspace,
                attributes=common,
            )
        ]
        for root in roots:
            events.append(
                _event(
                    timestamp=observed_at,
                    event_type="semantic.cursor.workspace.root_observed",
                    relation="WORKSPACE_HAS_ROOT",
                    source=workspace,
                    target=_entity(
                        "directory",
                        f"directory:cursor:{root}",
                        name=root,
                        attributes={
                            "provider": "cursor",
                            "absolute_path_from_provider": True,
                        },
                    ),
                    attributes={
                        **common,
                        "workspace_root_exact_from_provider": True,
                    },
                )
            )
        return events

    return []
