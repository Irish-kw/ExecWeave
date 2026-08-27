from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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


def _agent() -> dict[str, Any]:
    return _entity("agent", "agent:Antigravity", name="Antigravity")


def _common(payload: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "backend": "semantic",
        "attribution": "antigravity_hook",
        "evidence_source": "provider_hook",
        "provider": "antigravity",
        "causal": False,
    }
    mapping = {
        "conversationId": "antigravity_conversation_id",
        "transcriptPath": "antigravity_transcript_path",
        "artifactDirectoryPath": "antigravity_artifact_directory_path",
        "modelName": "antigravity_model_name",
        "stepIdx": "antigravity_step_index",
        "invocationNum": "antigravity_invocation_number",
        "initialNumSteps": "antigravity_initial_num_steps",
    }
    for source, target in mapping.items():
        value = payload.get(source)
        if isinstance(value, (str, int, float, bool)) and value != "":
            out[target] = value
    roots = payload.get("workspacePaths")
    if isinstance(roots, list):
        out["antigravity_workspace_paths"] = [
            value for value in roots if isinstance(value, str) and value
        ]
    return out


def _event(
    *,
    timestamp: str,
    event_type: str,
    relation: str,
    source: dict[str, Any],
    target: dict[str, Any],
    payload: dict[str, Any],
    attributes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    merged = _common(payload)
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


def _conversation(payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    value = payload.get("conversationId")
    conversation_id = value if isinstance(value, str) and value else "unknown"
    return conversation_id, _entity(
        "provider_session",
        f"provider-session:antigravity:{conversation_id}",
        name=conversation_id,
        attributes={"provider": "antigravity"},
    )


def _model(payload: dict[str, Any]) -> dict[str, Any] | None:
    model_name = payload.get("modelName")
    if not isinstance(model_name, str) or not model_name:
        return None
    return _entity(
        "model",
        f"model:antigravity:{model_name}",
        name=model_name,
        attributes={"provider": "antigravity", "model_name": model_name},
    )


def _tool_call(payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    tool_call = payload.get("toolCall")
    if not isinstance(tool_call, dict):
        raise ValueError("Antigravity PostToolUse payload has no toolCall object")
    name = tool_call.get("name")
    if not isinstance(name, str) or not name:
        raise ValueError("Antigravity PostToolUse payload has no toolCall.name")
    args = tool_call.get("args")
    canonical_args = args if isinstance(args, dict) else {}
    conversation_id, _ = _conversation(payload)
    step = payload.get("stepIdx")
    raw = json.dumps(
        [conversation_id, step, name, canonical_args],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:24]
    call = _entity(
        "tool_call",
        f"tool-call:antigravity:{conversation_id}:{digest}",
        name=name,
        attributes={
            "provider": "antigravity",
            "tool_name": name,
            "step_index": step,
        },
    )
    tool = _entity(
        "tool",
        f"tool:antigravity:{name}",
        name=name,
        attributes={"provider": "antigravity", "native_name": name},
    )
    return call, tool, canonical_args


def _command_entity(args: dict[str, Any]) -> dict[str, Any] | None:
    value = args.get("CommandLine")
    if not isinstance(value, str) or not value:
        value = args.get("command")
    if not isinstance(value, str) or not value:
        return None
    digest = hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()
    label = " ".join(value.replace("\x00", "").split())
    if len(label) > 160:
        label = label[:157] + "..."
    return _entity(
        "command",
        f"command:sha256:{digest}",
        name=label,
        attributes={"command": value, "declared_by_provider_hook": True},
    )


def _file_entity(payload: dict[str, Any], args: dict[str, Any]) -> dict[str, Any] | None:
    value = None
    for key in ("TargetFile", "AbsolutePath", "FilePath", "path", "file_path"):
        candidate = args.get(key)
        if isinstance(candidate, str) and candidate:
            value = candidate
            break
    if value is None:
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        roots = payload.get("workspacePaths")
        if isinstance(roots, list) and roots and isinstance(roots[0], str):
            path = Path(roots[0]) / path
    try:
        normalized = path.resolve(strict=False)
    except OSError:
        normalized = path.absolute()
    return _entity(
        "file",
        f"file:{normalized}",
        name=normalized.name or str(normalized),
        attributes={"provider": "antigravity", "declared_by_provider_hook": True},
    )


def antigravity_hook_to_semantic_events(
    payload: dict[str, Any],
    *,
    hook_event: str,
    timestamp: str | None = None,
) -> list[dict[str, Any]]:
    observed_at = timestamp or _now()
    _, conversation = _conversation(payload)

    if hook_event == "PreInvocation":
        events = [
            _event(
                timestamp=observed_at,
                event_type="semantic.antigravity.session.observed",
                relation="STARTED_PROVIDER_SESSION",
                source=_agent(),
                target=conversation,
                payload=payload,
            )
        ]
        model = _model(payload)
        if model is not None:
            events.append(
                _event(
                    timestamp=observed_at,
                    event_type="semantic.antigravity.model.invocation.requested",
                    relation="INVOKES_MODEL",
                    source=conversation,
                    target=model,
                    payload=payload,
                )
            )
        return events

    if hook_event == "PostInvocation":
        model = _model(payload)
        if model is None:
            return []
        return [
            _event(
                timestamp=observed_at,
                event_type="semantic.antigravity.model.invocation.completed",
                relation="MODEL_INVOCATION_COMPLETED",
                source=conversation,
                target=model,
                payload=payload,
            )
        ]

    if hook_event != "PostToolUse":
        return []

    call, tool, args = _tool_call(payload)
    error = payload.get("error")
    has_error = isinstance(error, str) and bool(error.strip())
    events = [
        _event(
            timestamp=observed_at,
            event_type="semantic.antigravity.tool.observed",
            relation="REQUESTED_TOOL_CALL",
            source=_agent(),
            target=call,
            payload=payload,
        ),
        _event(
            timestamp=observed_at,
            event_type="semantic.antigravity.tool.selected",
            relation="USES_TOOL",
            source=call,
            target=tool,
            payload=payload,
        ),
    ]
    command = _command_entity(args)
    if command is not None:
        events.append(
            _event(
                timestamp=observed_at,
                event_type="semantic.antigravity.command.declared",
                relation="DECLARED_COMMAND",
                source=call,
                target=command,
                payload=payload,
            )
        )
    file_entity = _file_entity(payload, args)
    if file_entity is not None:
        events.append(
            _event(
                timestamp=observed_at,
                event_type="semantic.antigravity.file.declared",
                relation="DECLARED_TARGET",
                source=call,
                target=file_entity,
                payload=payload,
            )
        )
    result_id = hashlib.sha256(
        f"{call['id']}\0{error if has_error else 'ok'}".encode("utf-8", errors="replace")
    ).hexdigest()[:24]
    result = _entity(
        "tool_result",
        f"tool-result:antigravity:{result_id}",
        name=f"{tool['name']} result",
        attributes={"provider": "antigravity", "provider_reported_error": has_error},
    )
    events.append(
        _event(
            timestamp=observed_at,
            event_type=(
                "semantic.antigravity.tool.reported_error"
                if has_error
                else "semantic.antigravity.tool.returned"
            ),
            relation="TOOL_RESULT_REPORTED_ERROR" if has_error else "TOOL_RESULT_RETURNED",
            source=tool,
            target=result,
            payload=payload,
            attributes={"provider_reported_error": has_error},
        )
    )
    return events


def append_semantic_records(path: str | Path, records: list[dict[str, Any]]) -> Path:
    output = Path(path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if not records:
        return output
    blob = "".join(
        json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        for record in records
    )
    lock_dir = output.with_name(output.name + ".lock")
    deadline = time.monotonic() + 5.0
    while True:
        try:
            lock_dir.mkdir()
            break
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise TimeoutError(f"timed out waiting for semantic sidecar lock: {lock_dir}")
            time.sleep(0.01)
    try:
        with output.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(blob)
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        try:
            lock_dir.rmdir()
        except OSError:
            pass
    return output


def read_hook_payload(stream: Any = None) -> dict[str, Any]:
    source = stream if stream is not None else sys.stdin
    raw = source.read()
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("Antigravity hook stdin is empty")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Antigravity hook stdin is invalid JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Antigravity hook stdin must be one JSON object")
    return payload
