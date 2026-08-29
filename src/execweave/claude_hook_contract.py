from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from .claude_full_fidelity import claude_hook_to_content_events as _legacy_content_events
from .content_evidence import content_observation_event
from .content_store import ContentReference, FullFidelityContentStore
from .agent_topology import EVIDENCE_SUBAGENT_LIFECYCLE_HOOK, subagent_topology

CLAUDE_HOOKS_REFERENCE = "https://code.claude.com/docs/en/hooks"

OFFICIAL_CLAUDE_HOOK_EVENTS = frozenset(
    {
        "SessionStart",
        "Setup",
        "InstructionsLoaded",
        "UserPromptSubmit",
        "UserPromptExpansion",
        "MessageDisplay",
        "PreToolUse",
        "PermissionRequest",
        "PostToolUse",
        "PostToolUseFailure",
        "PostToolBatch",
        "PermissionDenied",
        "Notification",
        "SubagentStart",
        "SubagentStop",
        "TaskCreated",
        "TaskCompleted",
        "Stop",
        "StopFailure",
        "TeammateIdle",
        "ConfigChange",
        "CwdChanged",
        "DirectoryAdded",
        "FileChanged",
        "WorktreeCreate",
        "WorktreeRemove",
        "PreCompact",
        "PostCompact",
        "Elicitation",
        "ElicitationResult",
        "SessionEnd",
    }
)

# Configuring WorktreeCreate replaces Claude Code's default worktree creation.
# FileChanged's matcher also defines the literal watch list. Neither is safe to
# enable as an unconditional passive observer.
UNSAFE_DEFAULT_CLAUDE_HOOK_EVENTS = frozenset({"WorktreeCreate", "FileChanged"})
PASSIVE_CLAUDE_HOOK_EVENTS = OFFICIAL_CLAUDE_HOOK_EVENTS - UNSAFE_DEFAULT_CLAUDE_HOOK_EVENTS

_ALREADY_PROJECTED_ELSEWHERE = frozenset(
    {
        "UserPromptSubmit",
        "MessageDisplay",
        "PreToolUse",
        "PostToolUse",
        "PostToolUseFailure",
        "PostToolBatch",
        "SubagentStart",
        "SubagentStop",
    }
)

_EXTRA_CONTENT_FIELDS: dict[str, frozenset[str]] = {
    "UserPromptExpansion": frozenset({"prompt", "command_args"}),
    "PermissionRequest": frozenset({"tool_input"}),
    "PermissionDenied": frozenset({"tool_input", "reason"}),
    "Notification": frozenset({"message", "title"}),
    "TaskCreated": frozenset({"task_subject", "task_description"}),
    "TaskCompleted": frozenset({"task_subject", "task_description"}),
    "Stop": frozenset({"background_tasks", "session_crons"}),
    "PreCompact": frozenset({"custom_instructions"}),
    "PostCompact": frozenset({"compact_summary"}),
    "Elicitation": frozenset({"message", "requested_schema", "url"}),
    "ElicitationResult": frozenset({"content"}),
}


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


def _main_agent() -> dict[str, Any]:
    return _entity("agent", "agent:Claude Code", name="Claude Code")


def _actor(payload: dict[str, Any]) -> dict[str, Any]:
    agent_id = payload.get("agent_id")
    if not isinstance(agent_id, str) or not agent_id:
        return _main_agent()
    session_id = payload.get("session_id")
    session = session_id if isinstance(session_id, str) and session_id else "unknown"
    agent_type = payload.get("agent_type")
    name = agent_type if isinstance(agent_type, str) and agent_type else "Claude subagent"
    return _entity(
        "agent",
        f"agent:claude:{session}:subagent:{agent_id}",
        name=name,
        attributes={
            "provider": "claude",
            "session_id": session,
            "agent_id": agent_id,
            "agent_type": name,
            "identity_source": "provider_exposed_agent_id",
            **subagent_topology(
                evidence=EVIDENCE_SUBAGENT_LIFECYCLE_HOOK,
                parent_scope_id=session,
            ),
        },
    )


def _session(payload: dict[str, Any]) -> dict[str, Any]:
    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        raise ValueError("Claude official hook payload requires session_id")
    return _entity(
        "provider_session",
        f"provider-session:claude:{session_id}",
        name=session_id,
        attributes={"provider": "claude", "session_id": session_id},
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
        "provider": "claude",
        "evidence_source": "provider_hook",
        "attribution": "claude_official_hook_contract",
        "causal": False,
        "inferred": False,
        "official_hook_contract": True,
        "official_hook_reference": CLAUDE_HOOKS_REFERENCE,
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
    attrs: dict[str, Any] = {"claude_hook_event_name": payload.get("hook_event_name")}
    for key in ("session_id", "cwd", "permission_mode", "agent_id", "agent_type"):
        value = payload.get(key)
        if isinstance(value, (str, int, float, bool)) and value != "":
            attrs[f"claude_{key}"] = value
    return attrs


def _observation_id(payload: dict[str, Any], *, timestamp: str, phase: str) -> str:
    stable = {
        "session_id": payload.get("session_id"),
        "hook_event_name": payload.get("hook_event_name"),
        "agent_id": payload.get("agent_id"),
        "task_id": payload.get("task_id"),
        "elicitation_id": payload.get("elicitation_id"),
        "tool_use_id": payload.get("tool_use_id"),
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
    merged = {"provider": "claude", "observation_phase": phase}
    if attributes:
        merged.update(attributes)
    return _entity(
        entity_type,
        f"{entity_type}:claude:{ident}",
        name=name,
        attributes=merged,
    )


def _file(path: str, *, instruction: bool = False) -> dict[str, Any]:
    return _entity(
        "file",
        f"file:{path}",
        name=path.rsplit("/", 1)[-1] or path,
        attributes={
            "provider": "claude",
            "absolute_path_from_provider": True,
            "instruction_file": instruction,
        },
    )


def _directory(path: str, *, kind: str = "directory") -> dict[str, Any]:
    return _entity(
        kind,
        f"{kind}:claude:{path}",
        name=path,
        attributes={"provider": "claude", "absolute_path_from_provider": True},
    )


def _tool_call(payload: dict[str, Any]) -> dict[str, Any]:
    session_id = payload.get("session_id")
    session = session_id if isinstance(session_id, str) and session_id else "unknown"
    tool_use_id = payload.get("tool_use_id")
    use_id = tool_use_id if isinstance(tool_use_id, str) and tool_use_id else "unknown"
    tool_name = payload.get("tool_name")
    name = tool_name if isinstance(tool_name, str) and tool_name else "unknown"
    return _entity(
        "tool_call",
        f"tool-call:claude:{session}:{use_id}",
        name=name,
        attributes={"provider": "claude", "tool_use_id": use_id, "tool_name": name},
    )


def _task(payload: dict[str, Any]) -> dict[str, Any]:
    session_id = payload.get("session_id")
    session = session_id if isinstance(session_id, str) and session_id else "unknown"
    task_id = payload.get("task_id")
    if not isinstance(task_id, str) or not task_id:
        raise ValueError(f"{payload.get('hook_event_name')} requires task_id")
    subject = payload.get("task_subject")
    name = subject if isinstance(subject, str) and subject else task_id
    attrs: dict[str, Any] = {"provider": "claude", "session_id": session, "task_id": task_id}
    teammate = payload.get("teammate_name")
    if isinstance(teammate, str) and teammate:
        attrs["teammate_name"] = teammate
        attrs["teammate_name_is_stable_agent_identity"] = False
    team_name = payload.get("team_name")
    if isinstance(team_name, str) and team_name:
        attrs["team_name"] = team_name
        attrs["team_name_deprecated_by_provider"] = True
    return _entity("agent_task", f"agent-task:claude:{session}:{task_id}", name=name, attributes=attrs)


def _mcp_server(payload: dict[str, Any]) -> dict[str, Any]:
    name = payload.get("mcp_server_name")
    if not isinstance(name, str) or not name:
        raise ValueError(f"{payload.get('hook_event_name')} requires mcp_server_name")
    return _entity(
        "mcp_server",
        f"mcp-server:claude:{name}",
        name=name,
        attributes={"provider": "claude", "server_name": name},
    )


def _elicitation(payload: dict[str, Any], *, timestamp: str) -> dict[str, Any]:
    server = payload.get("mcp_server_name")
    if not isinstance(server, str) or not server:
        raise ValueError(f"{payload.get('hook_event_name')} requires mcp_server_name")
    elicitation_id = payload.get("elicitation_id")
    if isinstance(elicitation_id, str) and elicitation_id:
        ident = elicitation_id
        identity = "provider_exposed_elicitation_id"
    else:
        ident = _observation_id(payload, timestamp=timestamp, phase="elicitation")
        identity = "hook_observation_without_elicitation_id"
    attrs: dict[str, Any] = {
        "provider": "claude",
        "mcp_server_name": server,
        "identity_semantics": identity,
    }
    mode = payload.get("mode")
    if isinstance(mode, str) and mode:
        attrs["mode"] = mode
    return _entity(
        "mcp_elicitation",
        f"mcp-elicitation:claude:{server}:{ident}",
        name=f"{server} elicitation",
        attributes=attrs,
    )


def claude_official_hook_semantic_events(
    payload: dict[str, Any],
    *,
    timestamp: str | None = None,
) -> list[dict[str, Any]]:
    """Project only semantics explicitly exposed by the current Claude Code hook contract."""

    hook_event = payload.get("hook_event_name")
    if not isinstance(hook_event, str) or not hook_event:
        raise ValueError("Claude hook payload requires hook_event_name")
    if hook_event not in OFFICIAL_CLAUDE_HOOK_EVENTS or hook_event in _ALREADY_PROJECTED_ELSEWHERE:
        return []

    observed_at = timestamp or _now()
    actor = _actor(payload)
    common = _common(payload)

    if hook_event == "SessionStart":
        source = payload.get("source")
        if isinstance(source, str) and source:
            common["claude_session_source"] = source
        return [
            _event(
                timestamp=observed_at,
                event_type="semantic.claude.session.started",
                relation="STARTED_PROVIDER_SESSION",
                source=actor,
                target=_session(payload),
                attributes=common,
            )
        ]

    if hook_event == "SessionEnd":
        reason = payload.get("reason")
        if isinstance(reason, str) and reason:
            common["claude_session_end_reason"] = reason
        return [
            _event(
                timestamp=observed_at,
                event_type="semantic.claude.session.ended",
                relation="OBSERVED_PROVIDER_SESSION_END",
                source=actor,
                target=_session(payload),
                attributes=common,
            )
        ]

    if hook_event == "Setup":
        trigger = payload.get("trigger")
        if isinstance(trigger, str) and trigger:
            common["setup_trigger"] = trigger
        target = _observation(
            payload,
            timestamp=observed_at,
            phase="setup",
            entity_type="provider_setup",
            name=f"Claude setup {trigger or 'unknown'}",
        )
        return [
            _event(
                timestamp=observed_at,
                event_type="semantic.claude.setup.observed",
                relation="OBSERVED_PROVIDER_SETUP",
                source=actor,
                target=target,
                attributes=common,
            )
        ]

    if hook_event == "InstructionsLoaded":
        path = payload.get("file_path")
        if not isinstance(path, str) or not path:
            raise ValueError("InstructionsLoaded requires file_path")
        for key in ("memory_type", "load_reason", "trigger_file_path", "parent_file_path"):
            value = payload.get(key)
            if value is not None:
                common[key] = value
        globs = payload.get("globs")
        if isinstance(globs, list):
            common["globs"] = globs
        return [
            _event(
                timestamp=observed_at,
                event_type="semantic.claude.instructions.loaded",
                relation="LOADED_INSTRUCTION_FILE",
                source=actor,
                target=_file(path, instruction=True),
                attributes=common,
            )
        ]

    if hook_event == "UserPromptExpansion":
        for key in ("expansion_type", "command_name", "command_source"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                common[key] = value
        common["prompt_stored_separately"] = isinstance(payload.get("prompt"), str)
        common["command_args_stored_separately"] = isinstance(payload.get("command_args"), str)
        target = _observation(
            payload,
            timestamp=observed_at,
            phase="prompt_expansion",
            entity_type="prompt_expansion",
            name=str(payload.get("command_name") or "Claude prompt expansion"),
        )
        return [
            _event(
                timestamp=observed_at,
                event_type="semantic.claude.prompt.expansion",
                relation="OBSERVED_PROMPT_EXPANSION",
                source=actor,
                target=target,
                attributes=common,
            )
        ]

    if hook_event == "PermissionRequest":
        tool_name = payload.get("tool_name")
        if not isinstance(tool_name, str) or not tool_name:
            raise ValueError("PermissionRequest requires tool_name")
        tool_input = payload.get("tool_input")
        common["tool_name"] = tool_name
        if isinstance(tool_input, dict):
            common["tool_input_keys"] = sorted(str(key) for key in tool_input)
        target = _observation(
            payload,
            timestamp=observed_at,
            phase="permission_request",
            entity_type="permission_request",
            name=f"{tool_name} permission request",
            attributes={"identity_semantics": "provider_hook_observation_without_tool_use_id"},
        )
        return [
            _event(
                timestamp=observed_at,
                event_type="semantic.claude.permission.requested",
                relation="OBSERVED_PERMISSION_REQUEST",
                source=actor,
                target=target,
                attributes=common,
            )
        ]

    if hook_event == "PermissionDenied":
        tool_use_id = payload.get("tool_use_id")
        if not isinstance(tool_use_id, str) or not tool_use_id:
            raise ValueError("PermissionDenied requires tool_use_id")
        common["permission_denial_reason_stored_separately"] = isinstance(payload.get("reason"), str)
        return [
            _event(
                timestamp=observed_at,
                event_type="semantic.claude.permission.denied",
                relation="PERMISSION_DENIED_TOOL_CALL",
                source=actor,
                target=_tool_call(payload),
                attributes=common,
            )
        ]

    if hook_event == "Notification":
        notification_type = payload.get("notification_type")
        if isinstance(notification_type, str) and notification_type:
            common["notification_type"] = notification_type
        common["message_stored_separately"] = isinstance(payload.get("message"), str)
        common["title_stored_separately"] = isinstance(payload.get("title"), str)
        target = _observation(
            payload,
            timestamp=observed_at,
            phase="notification",
            entity_type="provider_notification",
            name=str(notification_type or "Claude notification"),
        )
        return [
            _event(
                timestamp=observed_at,
                event_type="semantic.claude.notification.observed",
                relation="OBSERVED_NOTIFICATION",
                source=actor,
                target=target,
                attributes=common,
            )
        ]

    if hook_event in {"TaskCreated", "TaskCompleted"}:
        relation = "CREATED_AGENT_TASK" if hook_event == "TaskCreated" else "COMPLETED_AGENT_TASK"
        stage = "created" if hook_event == "TaskCreated" else "completed"
        common["task_subject_stored_separately"] = isinstance(payload.get("task_subject"), str)
        common["task_description_stored_separately"] = isinstance(payload.get("task_description"), str)
        return [
            _event(
                timestamp=observed_at,
                event_type=f"semantic.claude.task.{stage}",
                relation=relation,
                source=actor,
                target=_task(payload),
                attributes=common,
            )
        ]

    if hook_event == "Stop":
        common["stop_hook_active"] = bool(payload.get("stop_hook_active", False))
        background_tasks = payload.get("background_tasks")
        session_crons = payload.get("session_crons")
        if isinstance(background_tasks, list):
            common["background_task_count"] = len(background_tasks)
        if isinstance(session_crons, list):
            common["session_cron_count"] = len(session_crons)
        common["last_assistant_message_stored_separately"] = isinstance(
            payload.get("last_assistant_message"), str
        )
        target = _observation(
            payload,
            timestamp=observed_at,
            phase="stop",
            entity_type="agent_turn_stop",
            name="Claude turn stop",
            attributes={
                "completion_semantics": (
                    "provider_stop_hook_fired_after_response; hook_can_request_continuation"
                )
            },
        )
        return [
            _event(
                timestamp=observed_at,
                event_type="semantic.claude.turn.stop_observed",
                relation="OBSERVED_TURN_STOP",
                source=actor,
                target=target,
                attributes=common,
            )
        ]

    if hook_event == "StopFailure":
        error = payload.get("error")
        if isinstance(error, str) and error:
            common["error_type"] = error
        common["error_details_stored_separately"] = isinstance(payload.get("error_details"), str)
        common["rendered_error_stored_separately"] = isinstance(
            payload.get("last_assistant_message"), str
        )
        target = _observation(
            payload,
            timestamp=observed_at,
            phase="stop_failure",
            entity_type="agent_turn_failure",
            name=f"Claude stop failure {error or 'unknown'}",
            attributes={"last_assistant_message_semantics": "rendered_api_error_not_conversational_output"},
        )
        return [
            _event(
                timestamp=observed_at,
                event_type="semantic.claude.turn.failed",
                relation="OBSERVED_TURN_FAILURE",
                source=actor,
                target=target,
                attributes=common,
            )
        ]

    if hook_event == "TeammateIdle":
        teammate = payload.get("teammate_name")
        if not isinstance(teammate, str) or not teammate:
            raise ValueError("TeammateIdle requires teammate_name")
        target = _observation(
            payload,
            timestamp=observed_at,
            phase="teammate_idle",
            entity_type="teammate_state",
            name=teammate,
            attributes={
                "teammate_name": teammate,
                "teammate_name_is_stable_agent_identity": False,
                "team_name": payload.get("team_name"),
                "team_name_deprecated_by_provider": True,
            },
        )
        return [
            _event(
                timestamp=observed_at,
                event_type="semantic.claude.teammate.idle",
                relation="OBSERVED_TEAMMATE_IDLE",
                source=actor,
                target=target,
                attributes=common,
            )
        ]

    if hook_event == "ConfigChange":
        source_name = payload.get("source")
        if not isinstance(source_name, str) or not source_name:
            raise ValueError("ConfigChange requires source")
        file_path = payload.get("file_path")
        target = _entity(
            "configuration",
            f"configuration:claude:{source_name}:{file_path or 'unspecified'}",
            name=source_name,
            attributes={
                "provider": "claude",
                "source": source_name,
                "file_path": file_path,
            },
        )
        return [
            _event(
                timestamp=observed_at,
                event_type="semantic.claude.config.changed",
                relation="OBSERVED_CONFIG_CHANGE",
                source=actor,
                target=target,
                attributes=common,
            )
        ]

    if hook_event == "CwdChanged":
        old_cwd = payload.get("old_cwd")
        new_cwd = payload.get("new_cwd")
        if not isinstance(new_cwd, str) or not new_cwd:
            raise ValueError("CwdChanged requires new_cwd")
        if isinstance(old_cwd, str) and old_cwd:
            common["old_cwd"] = old_cwd
        return [
            _event(
                timestamp=observed_at,
                event_type="semantic.claude.cwd.changed",
                relation="CHANGED_WORKING_DIRECTORY",
                source=actor,
                target=_directory(new_cwd),
                attributes=common,
            )
        ]

    if hook_event == "DirectoryAdded":
        directory = payload.get("directory")
        if not isinstance(directory, str) or not directory:
            raise ValueError("DirectoryAdded requires directory")
        source_name = payload.get("source")
        if isinstance(source_name, str) and source_name:
            common["directory_add_source"] = source_name
        return [
            _event(
                timestamp=observed_at,
                event_type="semantic.claude.directory.added",
                relation="ADDED_WORKING_DIRECTORY",
                source=actor,
                target=_directory(directory),
                attributes=common,
            )
        ]

    if hook_event == "FileChanged":
        path = payload.get("file_path")
        if not isinstance(path, str) or not path:
            raise ValueError("FileChanged requires file_path")
        change = payload.get("event")
        if isinstance(change, str) and change:
            common["file_change_event"] = change
        common["default_execweave_hook_enabled"] = False
        return [
            _event(
                timestamp=observed_at,
                event_type="semantic.claude.file.changed",
                relation="OBSERVED_FILE_CHANGE",
                source=actor,
                target=_file(path),
                attributes=common,
            )
        ]

    if hook_event == "WorktreeCreate":
        # ExecWeave intentionally does not default-enable this event because a
        # configured hook replaces Claude Code's built-in worktree creation.
        return []

    if hook_event == "WorktreeRemove":
        path = payload.get("worktree_path")
        if not isinstance(path, str) or not path:
            raise ValueError("WorktreeRemove requires worktree_path")
        return [
            _event(
                timestamp=observed_at,
                event_type="semantic.claude.worktree.removed",
                relation="REMOVED_WORKTREE",
                source=actor,
                target=_directory(path, kind="worktree"),
                attributes=common,
            )
        ]

    if hook_event in {"PreCompact", "PostCompact"}:
        phase = "pre" if hook_event == "PreCompact" else "post"
        trigger = payload.get("trigger")
        if trigger not in {"manual", "auto"}:
            raise ValueError(f"{hook_event} requires trigger manual or auto")
        target = _observation(
            payload,
            timestamp=observed_at,
            phase=f"compaction_{phase}",
            entity_type="context_compaction",
            name=f"Claude compaction {phase}",
            attributes={
                "trigger": trigger,
                "pairing_semantics": "no_pre_post_pairing_asserted_without_provider_compaction_id",
            },
        )
        common.update(
            {
                "compaction_trigger": trigger,
                "compaction_phase": phase,
                "pre_post_pairing_asserted": False,
            }
        )
        if hook_event == "PostCompact":
            common["compact_summary_stored_separately"] = isinstance(
                payload.get("compact_summary"), str
            )
        else:
            common["custom_instructions_stored_separately"] = isinstance(
                payload.get("custom_instructions"), str
            )
        return [
            _event(
                timestamp=observed_at,
                event_type=f"semantic.claude.compaction.{phase}",
                relation="OBSERVED_PRE_COMPACTION" if phase == "pre" else "COMPACTED_CONTEXT",
                source=actor,
                target=target,
                attributes=common,
            )
        ]

    if hook_event == "Elicitation":
        server = _mcp_server(payload)
        elicitation = _elicitation(payload, timestamp=observed_at)
        common["message_stored_separately"] = isinstance(payload.get("message"), str)
        common["requested_schema_stored_separately"] = isinstance(
            payload.get("requested_schema"), dict
        )
        common["url_stored_separately"] = isinstance(payload.get("url"), str)
        return [
            _event(
                timestamp=observed_at,
                event_type="semantic.claude.mcp.elicitation",
                relation="OBSERVED_MCP_ELICITATION",
                source=server,
                target=elicitation,
                attributes=common,
            )
        ]

    if hook_event == "ElicitationResult":
        server = _mcp_server(payload)
        elicitation = _elicitation(payload, timestamp=observed_at)
        action = payload.get("action")
        if isinstance(action, str) and action:
            common["elicitation_action"] = action
        common["content_stored_separately"] = "content" in payload
        return [
            _event(
                timestamp=observed_at,
                event_type="semantic.claude.mcp.elicitation_result",
                relation="OBSERVED_MCP_ELICITATION_RESULT",
                source=elicitation,
                target=server,
                attributes=common,
            )
        ]

    return []


def _store_value(
    store: FullFidelityContentStore,
    value: Any,
    *,
    content_kind: str,
) -> ContentReference:
    if isinstance(value, str):
        return store.put_text(value, content_kind=content_kind)
    return store.put_json(value, content_kind=content_kind)


def _content_event(
    *,
    store: FullFidelityContentStore,
    value: Any,
    content_kind: str,
    timestamp: str,
    source: dict[str, Any],
    relation: str,
    observed_field: str,
) -> dict[str, Any]:
    reference = _store_value(store, value, content_kind=content_kind)
    return content_observation_event(
        timestamp=timestamp,
        provider="claude",
        source=source,
        reference=reference,
        relation=relation,
        observed_field=observed_field,
        evidence_source="provider_hook",
        attribution="claude_official_hook_contract",
        attributes={
            "claude_hook_event_name": source.get("attributes", {}).get("hook_event_name"),
            "official_hook_contract": True,
            "official_hook_reference": CLAUDE_HOOKS_REFERENCE,
        },
    )


def _content_source(payload: dict[str, Any], *, timestamp: str) -> dict[str, Any]:
    hook_event = payload.get("hook_event_name")
    if hook_event in {"TaskCreated", "TaskCompleted"}:
        return _task(payload)
    if hook_event in {"Elicitation", "ElicitationResult"}:
        return _elicitation(payload, timestamp=timestamp)
    return _actor(payload)


def _extra_content_events(
    payload: dict[str, Any],
    *,
    store: FullFidelityContentStore,
    timestamp: str,
) -> list[dict[str, Any]]:
    hook_event = payload.get("hook_event_name")
    if not isinstance(hook_event, str):
        return []
    source = _content_source(payload, timestamp=timestamp)
    specs: dict[str, tuple[str, str]] = {}

    if hook_event == "UserPromptExpansion":
        specs = {
            "prompt": ("claude.prompt_expansion.original_prompt", "OBSERVED_EXPANSION_PROMPT"),
            "command_args": ("claude.prompt_expansion.command_args", "OBSERVED_EXPANSION_ARGUMENTS"),
        }
    elif hook_event == "PermissionRequest":
        specs = {"tool_input": ("claude.permission.tool_input", "OBSERVED_PERMISSION_TOOL_INPUT")}
    elif hook_event == "PermissionDenied":
        specs = {
            "tool_input": ("claude.permission_denied.tool_input", "OBSERVED_DENIED_TOOL_INPUT"),
            "reason": ("claude.permission_denied.reason", "OBSERVED_PERMISSION_DENIAL_REASON"),
        }
    elif hook_event == "Notification":
        specs = {
            "message": ("claude.notification.message", "OBSERVED_NOTIFICATION_MESSAGE"),
            "title": ("claude.notification.title", "OBSERVED_NOTIFICATION_TITLE"),
        }
    elif hook_event in {"TaskCreated", "TaskCompleted"}:
        specs = {
            "task_subject": ("claude.task.subject", "HAS_TASK_SUBJECT"),
            "task_description": ("claude.task.description", "HAS_TASK_DESCRIPTION"),
        }
    elif hook_event == "Stop":
        specs = {
            "background_tasks": ("claude.stop.background_tasks", "OBSERVED_BACKGROUND_TASKS"),
            "session_crons": ("claude.stop.session_crons", "OBSERVED_SESSION_CRONS"),
        }
    elif hook_event == "PreCompact":
        specs = {
            "custom_instructions": (
                "claude.compaction.custom_instructions",
                "OBSERVED_COMPACTION_INSTRUCTIONS",
            )
        }
    elif hook_event == "PostCompact":
        specs = {
            "compact_summary": ("claude.compaction.summary", "OBSERVED_COMPACTION_SUMMARY")
        }
    elif hook_event == "Elicitation":
        specs = {
            "message": ("claude.elicitation.message", "OBSERVED_ELICITATION_MESSAGE"),
            "requested_schema": ("claude.elicitation.requested_schema", "OBSERVED_ELICITATION_SCHEMA"),
            "url": ("claude.elicitation.url", "OBSERVED_ELICITATION_URL"),
        }
    elif hook_event == "ElicitationResult":
        specs = {"content": ("claude.elicitation.result_content", "OBSERVED_ELICITATION_CONTENT")}

    events: list[dict[str, Any]] = []
    for field, (content_kind, relation) in specs.items():
        if field not in payload or payload[field] is None:
            continue
        events.append(
            _content_event(
                store=store,
                value=payload[field],
                content_kind=content_kind,
                timestamp=timestamp,
                source=source,
                relation=relation,
                observed_field=field,
            )
        )
    return events


def claude_official_full_fidelity_events(
    payload: dict[str, Any],
    *,
    store: FullFidelityContentStore,
    timestamp: str | None = None,
) -> list[dict[str, Any]]:
    """Preserve official Claude hook payloads without duplicating large content in metadata."""

    hook_event = payload.get("hook_event_name")
    if not isinstance(hook_event, str) or not hook_event:
        raise ValueError("Claude hook payload requires hook_event_name")
    observed_at = timestamp or _now()

    legacy_payload = dict(payload)
    for field in _EXTRA_CONTENT_FIELDS.get(hook_event, frozenset()):
        legacy_payload.pop(field, None)

    events = _legacy_content_events(
        legacy_payload,
        store=store,
        timestamp=observed_at,
    )
    events.extend(
        _extra_content_events(
            payload,
            store=store,
            timestamp=observed_at,
        )
    )
    return events
