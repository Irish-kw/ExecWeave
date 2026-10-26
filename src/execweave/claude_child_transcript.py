"""Project explicitly recorded Claude child-transcript tool calls into the graph."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .claude_adapter import (
    _actor,
    _command_entity,
    _declared_file_entity,
    _tool_call_entity,
    _tool_entity,
)
from .conversation_archive import _claude_subagent_transcript

_MAX_TRANSCRIPT_BYTES = 64 * 1024 * 1024
_FILE_TOOL_NAMES = frozenset({"read", "edit", "write", "notebookedit"})


def _event(
    *,
    timestamp: str,
    event_type: str,
    relation: str,
    source: dict[str, Any],
    target: dict[str, Any],
    attributes: dict[str, Any],
) -> dict[str, Any]:
    return {
        "timestamp": timestamp,
        "event_type": event_type,
        "relation": relation,
        "source": source,
        "target": target,
        "attributes": {
            "backend": "semantic",
            "provider": "claude",
            "attribution": "claude_child_transcript",
            "evidence_source": "provider_validated_child_transcript",
            "causal": False,
            "inferred": False,
            "provider_agent_id_exact": True,
            "transcript_record_order_validated": True,
            **attributes,
        },
    }


def _read_records(path: Path) -> list[dict[str, Any]]:
    try:
        if path.stat().st_size > _MAX_TRANSCRIPT_BYTES:
            return []
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return []
    records: list[dict[str, Any]] = []
    for line in raw.splitlines():
        try:
            record = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(record, dict):
            records.append(record)
    return records


def _record_belongs_to_agent(record: dict[str, Any], agent_id: str) -> bool:
    for key in ("agentId", "agent_id"):
        value = record.get(key)
        if isinstance(value, str) and value:
            return value == agent_id
    return True


def _tool_uses(record: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    message = record.get("message")
    if not isinstance(message, dict):
        return []
    content = message.get("content")
    if not isinstance(content, list):
        return []
    result: list[tuple[str, str, dict[str, Any]]] = []
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "tool_use":
            continue
        tool_use_id = block.get("id") or block.get("tool_use_id")
        tool_name = block.get("name")
        tool_input = block.get("input")
        if not isinstance(tool_use_id, str) or not tool_use_id:
            continue
        if not isinstance(tool_name, str) or not tool_name:
            continue
        if not isinstance(tool_input, dict):
            continue
        result.append((tool_use_id, tool_name, tool_input))
    return result


def _tool_results(record: dict[str, Any]) -> list[tuple[str, bool]]:
    message = record.get("message")
    if not isinstance(message, dict):
        return []
    content = message.get("content")
    if not isinstance(content, list):
        return []
    result: list[tuple[str, bool]] = []
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "tool_result":
            continue
        tool_use_id = block.get("tool_use_id") or block.get("id")
        if not isinstance(tool_use_id, str) or not tool_use_id:
            continue
        result.append((tool_use_id, block.get("is_error") is True))
    return result


def _edge_key(event: dict[str, Any]) -> tuple[str, str, str] | None:
    source = event.get("source")
    target = event.get("target")
    relation = event.get("relation")
    source_id = source.get("id") if isinstance(source, dict) else None
    target_id = target.get("id") if isinstance(target, dict) else None
    if not all(isinstance(value, str) and value for value in (source_id, target_id, relation)):
        return None
    return source_id, relation, target_id


def _existing_edge_keys(sidecar: str | Path | None) -> set[tuple[str, str, str]]:
    if sidecar is None:
        return set()
    path = Path(sidecar).expanduser()
    try:
        raw_lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return set()
    keys: set[tuple[str, str, str]] = set()
    for line in raw_lines:
        try:
            event = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(event, dict):
            key = _edge_key(event)
            if key is not None:
                keys.add(key)
    return keys


def claude_child_transcript_semantic_events(
    payload: dict[str, Any],
    *,
    timestamp: str,
    sidecar: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Project tool calls only from a path validated as this Claude child transcript.

    Claude's hooks can expose the child identity and transcript path at
    ``SubagentStop``. The path validator is deliberately strict so an arbitrary
    transcript path cannot be promoted into child ownership. Tool/file semantics
    are emitted only from explicit assistant ``tool_use`` blocks.
    """

    if payload.get("hook_event_name") != "SubagentStop":
        return []
    agent_id = payload.get("agent_id")
    session_id = payload.get("session_id")
    if not isinstance(agent_id, str) or not agent_id:
        return []
    if not isinstance(session_id, str) or not session_id:
        return []
    transcript = _claude_subagent_transcript(payload)
    if transcript is None or not transcript.is_file():
        return []

    child = _actor(payload)
    evidence = {
        "claude_session_id": session_id,
        "claude_agent_id": agent_id,
        "transcript_path": str(transcript),
    }
    calls: list[tuple[int, int, str, str, dict[str, Any]]] = []
    calls_by_id: dict[str, tuple[str, str, dict[str, Any], int, int]] = {}
    results: list[tuple[int, int, str, bool]] = []
    for ordinal, record in enumerate(_read_records(transcript)):
        if not _record_belongs_to_agent(record, agent_id):
            continue
        for call_index, (tool_use_id, tool_name, tool_input) in enumerate(_tool_uses(record)):
            if tool_use_id in calls_by_id:
                continue
            calls.append((ordinal, call_index, tool_use_id, tool_name, tool_input))
            calls_by_id[tool_use_id] = (tool_name, tool_use_id, tool_input, ordinal, call_index)
        for result_index, (tool_use_id, is_error) in enumerate(_tool_results(record)):
            results.append((ordinal, result_index, tool_use_id, is_error))

    events: list[dict[str, Any]] = []
    for ordinal, call_index, tool_use_id, tool_name, tool_input in calls:
            child_payload = {
                **payload,
                "tool_name": tool_name,
                "tool_use_id": tool_use_id,
                "tool_input": tool_input,
            }
            call = _tool_call_entity(child_payload, tool_name)
            tool = _tool_entity(tool_name)
            call_attributes = {
                **evidence,
                "transcript_record_ordinal": ordinal,
                "transcript_tool_call_index": call_index,
            }
            call["attributes"] = {
                **(call.get("attributes") or {}),
                "attribution": "claude_child_transcript",
                "evidence_source": "provider_validated_child_transcript",
                **call_attributes,
            }
            events.append(
                _event(
                    timestamp=timestamp,
                    event_type="semantic.claude.child.tool.requested",
                    relation="REQUESTED_TOOL_CALL",
                    source=child,
                    target=call,
                    attributes=call_attributes,
                )
            )
            events.append(
                _event(
                    timestamp=timestamp,
                    event_type="semantic.claude.child.tool.selected",
                    relation="USES_TOOL",
                    source=call,
                    target=tool,
                    attributes=call_attributes,
                )
            )

            normalized_name = tool_name.strip().lower()
            if normalized_name in {"bash", "powershell"}:
                command = _command_entity(tool_input)
                if command is not None:
                    events.append(
                        _event(
                            timestamp=timestamp,
                            event_type="semantic.claude.child.command.declared",
                            relation="DECLARED_COMMAND",
                            source=call,
                            target=command,
                            attributes=call_attributes,
                        )
                    )
            if normalized_name in _FILE_TOOL_NAMES:
                target_file = _declared_file_entity(child_payload, tool_input)
                if target_file is not None:
                    target_file["attributes"] = {
                        **(target_file.get("attributes") or {}),
                        "declared_by_provider_transcript": True,
                        "transcript_path": str(transcript),
                    }
                    events.append(
                        _event(
                            timestamp=timestamp,
                            event_type="semantic.claude.child.file.declared",
                            relation="DECLARED_TARGET",
                            source=call,
                            target=target_file,
                            attributes=call_attributes,
                        )
                    )
    for ordinal, result_index, tool_use_id, is_error in results:
        call_info = calls_by_id.get(tool_use_id)
        if call_info is None:
            continue
        tool_name, _, _, _, _ = call_info
        child_payload = {
            **payload,
            "tool_name": tool_name,
            "tool_use_id": tool_use_id,
        }
        call = _tool_call_entity(child_payload, tool_name)
        tool = _tool_entity(tool_name)
        result_attributes = {
            **evidence,
            "transcript_result_record_ordinal": ordinal,
            "transcript_tool_result_index": result_index,
            "provider_reported_failure": is_error,
        }
        events.append(
            _event(
                timestamp=timestamp,
                event_type=(
                    "semantic.claude.child.tool.failed"
                    if is_error
                    else "semantic.claude.child.tool.succeeded"
                ),
                relation="TOOL_CALL_FAILED" if is_error else "TOOL_CALL_SUCCEEDED",
                source=call,
                target=tool,
                attributes=result_attributes,
            )
        )

    existing = _existing_edge_keys(sidecar)
    seen = set(existing)
    deduplicated: list[dict[str, Any]] = []
    for event in events:
        key = _edge_key(event)
        if key is not None and key in seen:
            continue
        if key is not None:
            seen.add(key)
        deduplicated.append(event)
    return deduplicated
