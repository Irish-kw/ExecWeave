from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import antigravity_full_fidelity_collaboration_base as _base
from . import antigravity_adapter_base as _semantic
from .agent_topology import EVIDENCE_VALIDATED_CHILD_TRANSCRIPT, subagent_topology
from .antigravity_subagent_linkage import (
    derived_child_agent_path,
    read_transcript_records,
    transcript_subagent_links,
    validated_subagent_links,
    validated_transcript_path,
)
from .content_evidence import content_observation_event
from .content_store import FullFidelityContentStore
from .conversation_archive import antigravity_conversation_archive_events


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


def _assignment_event(
    *,
    timestamp: str,
    conversation_id: str,
    step: int,
    subagent_index: int,
    child_id: str,
    spec: dict[str, Any],
) -> dict[str, Any]:
    role = spec.get("Role") if isinstance(spec.get("Role"), str) else None
    type_name = spec.get("TypeName") if isinstance(spec.get("TypeName"), str) else None
    workspace = spec.get("Workspace") if isinstance(spec.get("Workspace"), str) else None
    subtask = _entity(
        "subtask",
        f"subtask:antigravity:{conversation_id}:{step}:{subagent_index}",
        name=role or type_name or "Antigravity subtask",
        attributes={
            "provider": "antigravity",
            "conversation_id": conversation_id,
            "step_index": step,
            "subagent_index": subagent_index,
            "role": role,
            "type_name": type_name,
            "workspace": workspace,
            "identity_semantics": "provider_invoke_subagent_spec_index",
        },
    )
    child_label = role or type_name or "Antigravity subagent"
    child = _entity(
        "agent",
        f"agent:antigravity:conversation:{child_id}",
        name=child_label,
        attributes={
            "provider": "antigravity",
            "conversation_id": child_id,
            "agent_type": child_label,
            "agent_nickname": role or type_name,
            "provider_role_slot": subagent_index,
            "provider_role_type": type_name,
            "provider_role_workspace": workspace,
            "provider_role_path": derived_child_agent_path(spec, child_id),
            "identity_semantics": "provider_transcript_result_conversation_id",
            "execution_observed": False,
            "lifecycle_authority": "child_provider_hooks",
            **subagent_topology(
                evidence=EVIDENCE_VALIDATED_CHILD_TRANSCRIPT,
                parent_scope_id=conversation_id,
            ),
        },
    )
    return {
        "timestamp": timestamp,
        "event_type": "semantic.antigravity.subtask.assigned",
        "relation": "ASSIGNED_AGENT_TASK",
        "source": subtask,
        "target": child,
        "attributes": {
            "backend": "semantic",
            "provider": "antigravity",
            "attribution": "antigravity_hook",
            "evidence_source": "provider_hook_plus_validated_transcript",
            "causal": False,
            "inferred": False,
            "identity_exact": True,
            "identity_method": "validated_transcript_record_order_and_provider_ids",
            "provider_collaboration_tool_exact": True,
            "provider_post_tool_success": True,
            "provider_child_identity_exact": True,
            "correlation_method": "validated_transcript_record_order_and_provider_ids",
            "transcript_wire_semantics": "live_verified_implementation_wire",
            "transcript_record_order_validated": True,
            "timing_inference_used": False,
            "child_lifecycle_inferred": False,
            "child_lifecycle_authority": "child_provider_hooks",
        },
    }


def _child_session_event(*, assignment: dict[str, Any], parent_id: str) -> dict[str, Any]:
    """Connect the parent conversation agent to the child on the viewer graph."""
    child = assignment.get("target")
    child = child if isinstance(child, dict) else {}
    parent = _entity(
        "agent",
        f"agent:antigravity:conversation:{parent_id}",
        name="Antigravity conversation",
        attributes={
            "provider": "antigravity",
            "conversation_id": parent_id,
            "identity_semantics": "provider_conversation_id",
        },
    )
    attributes = assignment.get("attributes")
    return {
        "timestamp": assignment.get("timestamp"),
        "event_type": "semantic.antigravity.agent_session.child",
        "relation": "HAS_CHILD_AGENT_SESSION",
        "source": parent,
        "target": child,
        "attributes": dict(attributes) if isinstance(attributes, dict) else {},
    }


def _subtask_request_event(*, assignment: dict[str, Any], parent_id: str) -> dict[str, Any]:
    """Connect the requesting agent to the subtask before its child is known."""
    subtask = assignment.get("source")
    subtask = subtask if isinstance(subtask, dict) else {}
    attributes = assignment.get("attributes")
    request_attributes = dict(attributes) if isinstance(attributes, dict) else {}
    request_attributes.update(
        {
            "provider": "antigravity",
            "attribution": "antigravity_hook",
            "evidence_source": "provider_hook_plus_validated_transcript",
            "causal": False,
            "inferred": False,
            "identity_exact": True,
            "provider_collaboration_tool_exact": True,
            "provider_post_tool_success": True,
        }
    )
    return {
        "timestamp": assignment.get("timestamp"),
        "event_type": "semantic.antigravity.subtask.requested",
        "relation": "REQUESTED_SUBTASK",
        "source": _entity(
            "agent",
            f"agent:antigravity:conversation:{parent_id}",
            name="Antigravity conversation",
            attributes={
                "provider": "antigravity",
                "conversation_id": parent_id,
                "identity_semantics": "provider_conversation_id",
            },
        ),
        "target": subtask,
        "attributes": request_attributes,
    }


def _append_missing_subtask_requests(
    events: list[dict[str, Any]],
    assignments: list[dict[str, Any]],
    *,
    parent_id: str,
) -> None:
    """Add root-to-subtask edges without duplicating request-only evidence."""
    requested_ids = {
        target.get("id")
        for event in events
        if event.get("relation") == "REQUESTED_SUBTASK"
        and isinstance((target := event.get("target")), dict)
        and isinstance(target.get("id"), str)
    }
    for assignment in assignments:
        source = assignment.get("source")
        if not isinstance(source, dict) or not isinstance(source.get("id"), str):
            continue
        if source["id"] in requested_ids:
            continue
        events.append(_subtask_request_event(assignment=assignment, parent_id=parent_id))
        requested_ids.add(source["id"])


def _child_task_content_event(
    *,
    assignment: dict[str, Any],
    spec: dict[str, Any],
    store: FullFidelityContentStore,
    timestamp: str,
) -> dict[str, Any] | None:
    prompt = spec.get("Prompt")
    child = assignment.get("target")
    if not isinstance(prompt, str) or not prompt or not isinstance(child, dict):
        return None
    reference = store.put_text(prompt, content_kind="antigravity.subtask_prompt")
    attributes = assignment.get("attributes")
    return content_observation_event(
        timestamp=timestamp,
        provider="antigravity",
        source=child,
        reference=reference,
        relation="OBSERVED_SUBAGENT_TASK",
        observed_field="toolCall.args.Subagents[].Prompt",
        evidence_source="provider_hook_plus_validated_transcript",
        attribution="antigravity_hook",
        event_type="semantic.antigravity.subtask.child_content",
        attributes={
            **(attributes if isinstance(attributes, dict) else {}),
            "conversation_projection_basis": "validated_child_conversation_id",
        },
    )


def _child_transcript_tool_events(
    *,
    link: dict[str, Any],
    assignment: dict[str, Any],
    parent_payload: dict[str, Any],
    timestamp: str,
) -> list[dict[str, Any]]:
    """Project explicit tool calls recorded in a validated child transcript.

    AGY does not emit a separate PostToolUse hook for every child conversation.
    The child transcript is nevertheless a provider-owned, request/result-linked
    record, so its explicit MODEL tool calls can be represented without guessing
    ownership from timing or filesystem activity.
    """
    child_id = link.get("conversation_id")
    transcript = link.get("transcript_path")
    child = assignment.get("target")
    if (
        not isinstance(child_id, str)
        or not child_id
        or not isinstance(transcript, Path)
        or not isinstance(child, dict)
        or child.get("type") != "agent"
    ):
        return []
    # ``Path`` is deliberately checked without accepting path-like strings here:
    # only the linkage validator may authorize which child transcript is read.
    records = read_transcript_records(transcript)
    events: list[dict[str, Any]] = []
    evidence = {
        "backend": "semantic",
        "attribution": "antigravity_child_transcript",
        "evidence_source": "provider_validated_child_transcript",
        "provider": "antigravity",
        "causal": False,
        "inferred": False,
        "identity_exact": True,
        "identity_method": "validated_parent_result_child_transcript_path",
        "transcript_path": str(transcript),
        "transcript_record_order_validated": True,
        "child_tool_call_observed": True,
    }
    for ordinal, record in enumerate(records):
        if (
            record.get("source") != "MODEL"
            or record.get("type") != "PLANNER_RESPONSE"
            or record.get("status") != "DONE"
        ):
            continue
        calls = record.get("tool_calls")
        if not isinstance(calls, list):
            continue
        raw_step = record.get("step_index")
        step = raw_step if isinstance(raw_step, int) and not isinstance(raw_step, bool) and raw_step >= 0 else ordinal
        for call_index, raw_call in enumerate(calls):
            if not isinstance(raw_call, dict):
                continue
            name = raw_call.get("name")
            raw_args = raw_call.get("args")
            if not isinstance(name, str) or not name or not isinstance(raw_args, dict):
                continue
            args: dict[str, Any] = {}
            for key, value in raw_args.items():
                if isinstance(value, str):
                    try:
                        decoded = json.loads(value)
                    except json.JSONDecodeError:
                        decoded = value
                    args[key] = decoded if decoded is not None else value
                else:
                    args[key] = value
            child_payload = dict(parent_payload)
            child_payload.update(
                {
                    "conversationId": child_id,
                    "transcriptPath": str(transcript),
                    "stepIdx": step,
                    "toolCall": {"name": name, "args": args},
                }
            )
            call_entity, tool_entity, canonical_args = _semantic._tool_call(child_payload)
            call_attributes = dict(call_entity.get("attributes") or {})
            call_attributes.update(
                {
                    "attribution": "antigravity_child_transcript",
                    "evidence_source": "provider_validated_child_transcript",
                    "transcript_record_ordinal": ordinal,
                    "transcript_tool_call_index": call_index,
                    "transcript_path": str(transcript),
                }
            )
            call_entity["attributes"] = call_attributes
            events.append(
                _semantic._event(
                    timestamp=timestamp,
                    event_type="semantic.antigravity.child.tool.observed",
                    relation="REQUESTED_TOOL_CALL",
                    source=child,
                    target=call_entity,
                    payload=child_payload,
                    attributes=evidence,
                )
            )
            events.append(
                _semantic._event(
                    timestamp=timestamp,
                    event_type="semantic.antigravity.child.tool.selected",
                    relation="USES_TOOL",
                    source=call_entity,
                    target=tool_entity,
                    payload=child_payload,
                    attributes=evidence,
                )
            )
            command = _semantic._command_entity(canonical_args) if name != "apply_patch" else None
            if command is not None:
                events.append(
                    _semantic._event(
                        timestamp=timestamp,
                        event_type="semantic.antigravity.child.command.declared",
                        relation="DECLARED_COMMAND",
                        source=call_entity,
                        target=command,
                        payload=child_payload,
                        attributes=evidence,
                    )
                )
            file_entity = _semantic._file_entity(child_payload, canonical_args)
            patch_targets = (
                _semantic._apply_patch_targets(
                    canonical_args.get("patch") or canonical_args.get("command")
                )
                if name == "apply_patch"
                else []
            )
            file_targets: list[tuple[dict[str, Any], str | None]]
            if patch_targets:
                file_targets = [
                    (
                        _semantic._file_entity(
                            child_payload,
                            {"TargetFile": raw_path},
                        ),
                        operation,
                    )
                    for operation, raw_path in patch_targets
                ]
            elif file_entity is not None:
                file_targets = [(file_entity, None)]
            else:
                file_targets = []
            for file_entity, patch_operation in file_targets:
                if file_entity is None:
                    continue
                file_attributes = dict(file_entity.get("attributes") or {})
                file_attributes.update(
                    {
                        "declared_by_provider_transcript": True,
                        "transcript_path": str(transcript),
                    }
                )
                if patch_operation is not None:
                    file_attributes["patch_operation"] = patch_operation
                file_entity["attributes"] = file_attributes
                events.append(
                    _semantic._event(
                        timestamp=timestamp,
                        event_type="semantic.antigravity.child.file.declared",
                        relation="DECLARED_TARGET",
                        source=call_entity,
                        target=file_entity,
                        payload=child_payload,
                        attributes=evidence,
                    )
                )
    return events


def _child_transcript_archive_events(
    *,
    link: dict[str, Any],
    parent_payload: dict[str, Any],
    store: FullFidelityContentStore,
    timestamp: str,
) -> list[dict[str, Any]]:
    """Archive a validated child transcript discovered in the parent result.

    Antigravity does not reliably emit lifecycle hooks for every subagent.  The
    parent result nevertheless contains an exact child conversation id and
    ``logAbsoluteUri``.  Once the linkage validator has accepted that pair, it
    is sufficient evidence to materialize the child's conversation record; the
    child tool projection and the conversation archive should not depend on a
    separate child Stop hook arriving later.
    """
    child_id = link.get("conversation_id")
    transcript = link.get("transcript_path")
    if (
        not isinstance(child_id, str)
        or not child_id
        or not isinstance(transcript, Path)
    ):
        return []
    child_payload = dict(parent_payload)
    child_payload.update(
        {
            "conversationId": child_id,
            "transcriptPath": str(transcript),
        }
    )
    return antigravity_conversation_archive_events(
        child_payload,
        store=store,
        timestamp=timestamp,
    )


def _subagent_assignment_events(
    payload: dict[str, Any],
    *,
    timestamp: str,
    store: FullFidelityContentStore,
) -> list[dict[str, Any]]:
    tool_call = payload.get("toolCall")
    if not isinstance(tool_call, dict) or tool_call.get("name") != "invoke_subagent":
        return []
    args = tool_call.get("args")
    if not isinstance(args, dict):
        return []
    error = payload.get("error")
    if isinstance(error, str) and error.strip():
        return []
    conversation_id = payload.get("conversationId")
    step = payload.get("stepIdx")
    if not isinstance(conversation_id, str) or not conversation_id:
        return []
    if not isinstance(step, int) or isinstance(step, bool) or step < 0:
        return []
    specs = args.get("Subagents")
    if not isinstance(specs, list):
        return []

    links = validated_subagent_links(payload, args=args)
    events: list[dict[str, Any]] = []
    for link in links:
        subagent_index = link["subagent_index"]
        if not isinstance(subagent_index, int) or not 0 <= subagent_index < len(specs):
            return []
        spec = specs[subagent_index]
        child_id = link["conversation_id"]
        if not isinstance(spec, dict) or not isinstance(child_id, str):
            return []
        assignment = _assignment_event(
            timestamp=timestamp,
            conversation_id=conversation_id,
            step=step,
            subagent_index=subagent_index,
            child_id=child_id,
            spec=spec,
        )
        events.append(assignment)
        events.append(_child_session_event(assignment=assignment, parent_id=conversation_id))
        events.extend(
            _child_transcript_archive_events(
                link=link,
                parent_payload=payload,
                store=store,
                timestamp=timestamp,
            )
        )
        events.extend(
            _child_transcript_tool_events(
                link=link,
                assignment=assignment,
                parent_payload=payload,
                timestamp=timestamp,
            )
        )
        task_content = _child_task_content_event(
            assignment=assignment,
            spec=spec,
            store=store,
            timestamp=timestamp,
        )
        if task_content is not None:
            events.append(task_content)
    return events


def _transcript_assignment_events(
    payload: dict[str, Any],
    *,
    timestamp: str,
    store: FullFidelityContentStore,
) -> list[dict[str, Any]]:
    """Assign children from a parent transcript even when PostToolUse was not invoke_subagent.

    Field Agy runs have been observed to archive four conversation transcripts while
    the only PostToolUse name on the wire is ``schedule``. The spawn request/result
    still sits in the parent transcript. Scanning that validated file is the same
    provider join as the hook-time path; it does not invent children.
    """
    conversation_id = payload.get("conversationId")
    if not isinstance(conversation_id, str) or not conversation_id:
        return []
    transcript = validated_transcript_path(payload)
    if transcript is None:
        return []
    links = transcript_subagent_links(
        read_transcript_records(transcript),
        parent_id=conversation_id,
    )
    events: list[dict[str, Any]] = []
    assignments: list[dict[str, Any]] = []
    for link in links:
        spec = link["spec"]
        child_id = link["conversation_id"]
        if not isinstance(spec, dict) or not isinstance(child_id, str):
            return []
        assignment = _assignment_event(
            timestamp=timestamp,
            conversation_id=conversation_id,
            step=link["step_index"],
            subagent_index=link["subagent_index"],
            child_id=child_id,
            spec=spec,
        )
        assignments.append(assignment)
        events.append(assignment)
        events.append(_child_session_event(assignment=assignment, parent_id=conversation_id))
        events.extend(
            _child_transcript_archive_events(
                link=link,
                parent_payload=payload,
                store=store,
                timestamp=timestamp,
            )
        )
        events.extend(
            _child_transcript_tool_events(
                link=link,
                assignment=assignment,
                parent_payload=payload,
                timestamp=timestamp,
            )
        )
        task_content = _child_task_content_event(
            assignment=assignment,
            spec=spec,
            store=store,
            timestamp=timestamp,
        )
        if task_content is not None:
            events.append(task_content)
    _append_missing_subtask_requests(events, assignments, parent_id=conversation_id)
    return events


def antigravity_hook_to_content_events(
    payload: dict[str, Any],
    *,
    hook_event: str,
    store: FullFidelityContentStore,
    timestamp: str | None = None,
) -> list[dict[str, Any]]:
    events = _base.antigravity_hook_to_content_events(
        payload,
        hook_event=hook_event,
        store=store,
        timestamp=timestamp,
    )
    if timestamp is None:
        from datetime import datetime, timezone

        timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    if hook_event == "PostToolUse":
        assigned = _subagent_assignment_events(
            payload,
            timestamp=timestamp,
            store=store,
        )
        assignments = [
            event
            for event in assigned
            if event.get("relation") == "ASSIGNED_AGENT_TASK"
        ]
        _append_missing_subtask_requests(
            events,
            assignments,
            parent_id=str(payload.get("conversationId") or ""),
        )
        events.extend(assigned)
        tool_call = payload.get("toolCall")
        tool_name = tool_call.get("name") if isinstance(tool_call, dict) else None
        if not assigned and tool_name != "invoke_subagent":
            # ``schedule`` still leaves the spawn pair in the parent transcript.
            # Do not use this relaxed join to override an invoke_subagent hook
            # that already abstained (mismatched URI, torn write, workspace).
            events.extend(
                _transcript_assignment_events(
                    payload,
                    timestamp=timestamp,
                    store=store,
                )
            )
    # Codex snapshots provider transcripts on lifecycle events that already
    # name the rollout path, not only on a terminal Stop. Antigravity exposes
    # the same validated brain path on PreInvocation / PostInvocation; waiting
    # for Stop leaves live and finished dashboards with conversation identity
    # and no prompt/response text when Stop never arrives.
    if hook_event in {"PostToolUse", "PreInvocation", "PostInvocation", "Stop"}:
        events.extend(
            antigravity_conversation_archive_events(
                payload,
                store=store,
                timestamp=timestamp,
            )
        )
        if hook_event != "PostToolUse":
            events.extend(
                _transcript_assignment_events(
                    payload,
                    timestamp=timestamp,
                    store=store,
                )
            )
    return events
