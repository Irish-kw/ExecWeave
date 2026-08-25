from __future__ import annotations

import hashlib
import json
import os
import tempfile
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .schema import SCHEMA_VERSION
from .validate import validate_event_stream

_RELATION = "CORRELATED_WITH_PROCESS"
_EVENT_TYPE = "inference.tool_process.correlation"
_BUILTINS = {
    ".",
    "[",
    "alias",
    "bg",
    "break",
    "cd",
    "command",
    "continue",
    "echo",
    "eval",
    "exec",
    "exit",
    "export",
    "false",
    "fg",
    "hash",
    "jobs",
    "printf",
    "pwd",
    "read",
    "return",
    "set",
    "shift",
    "source",
    "test",
    "trap",
    "true",
    "type",
    "ulimit",
    "umask",
    "unalias",
    "unset",
    "wait",
}


@dataclass(frozen=True)
class CorrelationResult:
    session_id: str
    input_event_count: int
    output_event_count: int
    tool_calls_considered: int
    correlated_tool_calls: int
    skipped_unsupported: int
    skipped_no_match: int
    skipped_ambiguous: int
    max_window_ms: int
    output: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class _Declaration:
    event: dict[str, Any]
    timestamp: datetime
    tool_call: dict[str, Any]
    command_entity: dict[str, Any]
    command_token: str
    command_head: str
    command_argv: tuple[str, ...]


@dataclass
class _Candidate:
    process: dict[str, Any]
    latest_timestamp: datetime
    latest_timestamp_text: str
    supporting_event_ids: set[str] = field(default_factory=set)
    has_exec_match: bool = False
    has_process_exe_match: bool = False
    has_cmdline_match: bool = False
    has_argv_tail_match: bool = False

    def observe(
        self,
        event: dict[str, Any],
        *,
        timestamp: datetime,
        exec_match: bool = False,
        process_exe_match: bool = False,
        cmdline_match: bool = False,
        argv_tail_match: bool = False,
    ) -> None:
        if timestamp >= self.latest_timestamp:
            self.latest_timestamp = timestamp
            self.latest_timestamp_text = str(event.get("timestamp"))
        event_id = event.get("event_id")
        if isinstance(event_id, str) and event_id:
            self.supporting_event_ids.add(event_id)
        self.has_exec_match = self.has_exec_match or exec_match
        self.has_process_exe_match = self.has_process_exe_match or process_exe_match
        self.has_cmdline_match = self.has_cmdline_match or cmdline_match
        self.has_argv_tail_match = self.has_argv_tail_match or argv_tail_match

    def method_and_confidence(self) -> tuple[str, float]:
        if self.has_exec_match and self.has_cmdline_match:
            return "unique_exec_and_cmdline_match", 0.95
        if self.has_exec_match:
            return "unique_exec_identity_match", 0.90
        if self.has_process_exe_match and self.has_cmdline_match:
            return "unique_process_exe_and_cmdline_match", 0.90
        if self.has_process_exe_match:
            return "unique_process_exe_match", 0.85
        if self.has_cmdline_match:
            return "unique_process_cmdline_match", 0.80
        if self.has_argv_tail_match:
            return "unique_process_argv_tail_match", 0.80
        raise RuntimeError("correlation candidate has no matching evidence")


def _parse_timestamp(value: object, *, context: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{context}: timestamp must be a non-empty ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{context}: timestamp must be ISO-8601") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"line {line_number}: invalid JSON: {exc.msg}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"line {line_number}: event must be an object")
        events.append(payload)
    return events


def _clean_executable(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip().strip('"').strip("'") or None


def _normalize_executable(value: object) -> str | None:
    text = _clean_executable(value)
    if text is None:
        return None
    name = text.replace("\\", "/").rsplit("/", 1)[-1].lower()
    if name.endswith(".exe"):
        name = name[:-4]
    return name or None


def _canonical_executable_path(value: object) -> str | None:
    text = _clean_executable(value)
    if text is None:
        return None
    if "/" not in text and "\\" not in text and not Path(text).is_absolute():
        return None
    try:
        resolved = Path(text).expanduser().resolve(strict=False)
    except (OSError, RuntimeError, ValueError):
        return None
    return os.path.normcase(str(resolved))


def _same_executable_identity(candidate: object, declaration: _Declaration) -> bool:
    if _normalize_executable(candidate) == declaration.command_head:
        return True
    declared_path = _canonical_executable_path(declaration.command_token)
    candidate_path = _canonical_executable_path(candidate)
    return declared_path is not None and candidate_path is not None and declared_path == candidate_path


def _has_shell_control(command: str) -> bool:
    quote: str | None = None
    escaped = False
    index = 0
    while index < len(command):
        char = command[index]
        if escaped:
            escaped = False
            index += 1
            continue
        if quote == "'":
            if char == "'":
                quote = None
            index += 1
            continue
        if quote == '"':
            if char == '"':
                quote = None
            elif char == "\\":
                escaped = True
            index += 1
            continue
        if char in {"'", '"'}:
            quote = char
            index += 1
            continue
        if char in "\r\n;&|<>`":
            return True
        if char == "$" and index + 1 < len(command) and command[index + 1] == "(":
            return True
        if char == "\\":
            escaped = True
        index += 1
    return quote is not None


def _command_argv(command: str) -> tuple[str, ...] | None:
    if _has_shell_control(command):
        return None
    tokens: list[str] = []
    chars: list[str] = []
    quote: str | None = None
    token_started = False
    index = 0
    while index < len(command):
        char = command[index]
        if quote is not None:
            if char == quote:
                quote = None
                token_started = True
            elif (
                quote == '"'
                and char == "\\"
                and index + 1 < len(command)
                and command[index + 1] == '"'
            ):
                chars.append('"')
                token_started = True
                index += 1
            else:
                chars.append(char)
                token_started = True
        elif char.isspace():
            if token_started:
                tokens.append("".join(chars))
                chars = []
                token_started = False
        elif char in {"'", '"'}:
            quote = char
            token_started = True
        else:
            chars.append(char)
            token_started = True
        index += 1
    if quote is not None:
        return None
    if token_started:
        tokens.append("".join(chars))
    return tuple(tokens)


def _command_identity(command: str) -> tuple[str, str, tuple[str, ...]] | None:
    argv = _command_argv(command)
    if not argv:
        return None
    token = argv[0]
    if "=" in token:
        return None
    head = _normalize_executable(token)
    if head is None or head in _BUILTINS:
        return None
    return token, head, argv


def _declarations(events: list[dict[str, Any]]) -> list[_Declaration]:
    result: list[_Declaration] = []
    for index, event in enumerate(events, start=1):
        if event.get("relation") != "DECLARED_COMMAND":
            continue
        source = event.get("source")
        target = event.get("target")
        if not isinstance(source, dict) or source.get("type") != "tool_call":
            continue
        if not isinstance(target, dict) or target.get("type") != "command":
            continue
        target_attributes = target.get("attributes") or {}
        command = target_attributes.get("command") if isinstance(target_attributes, dict) else None
        if not isinstance(command, str) or not command:
            continue
        identity = _command_identity(command)
        if identity is None:
            token, head, argv = "", "", ()
        else:
            token, head, argv = identity
        result.append(
            _Declaration(
                event=event,
                timestamp=_parse_timestamp(event.get("timestamp"), context=f"event {index}"),
                tool_call=deepcopy(source),
                command_entity=deepcopy(target),
                command_token=token,
                command_head=head,
                command_argv=argv,
            )
        )
    result.sort(key=lambda item: item.timestamp)
    return result


def _result_times(events: list[dict[str, Any]]) -> dict[str, list[datetime]]:
    result: dict[str, list[datetime]] = {}
    for index, event in enumerate(events, start=1):
        if event.get("relation") not in {"TOOL_CALL_SUCCEEDED", "TOOL_CALL_FAILED"}:
            continue
        source = event.get("source")
        if not isinstance(source, dict):
            continue
        source_id = source.get("id")
        if not isinstance(source_id, str) or not source_id:
            continue
        result.setdefault(source_id, []).append(
            _parse_timestamp(event.get("timestamp"), context=f"event {index}")
        )
    for values in result.values():
        values.sort()
    return result


def _event_time(event: dict[str, Any], *, index: int) -> datetime:
    return _parse_timestamp(event.get("timestamp"), context=f"event {index}")


def _candidate_processes(
    events: list[dict[str, Any]],
    *,
    declaration: _Declaration,
    start: datetime,
    end: datetime,
) -> dict[str, _Candidate]:
    candidates: dict[str, _Candidate] = {}
    for index, event in enumerate(events, start=1):
        event_type = event.get("event_type")
        relation = event.get("relation")
        if event_type not in {"process.started", "process.exec"}:
            continue
        timestamp = _event_time(event, index=index)
        if timestamp < start or timestamp > end:
            continue

        process: dict[str, Any] | None = None
        exec_match = False
        process_exe_match = False
        cmdline_match = False
        argv_tail_match = False
        if event_type == "process.exec" and relation == "EXECUTED":
            source = event.get("source")
            target = event.get("target")
            if not isinstance(source, dict) or source.get("type") != "process":
                continue
            if not isinstance(target, dict) or target.get("type") != "executable":
                continue
            executable_value: object = target.get("name")
            executable_id = target.get("id")
            if isinstance(executable_id, str) and executable_id.startswith("executable:"):
                executable_value = executable_id[len("executable:") :]
            if not _same_executable_identity(executable_value, declaration):
                continue
            process = deepcopy(source)
            exec_match = True
        elif event_type == "process.started":
            target = event.get("target")
            if not isinstance(target, dict) or target.get("type") != "process":
                continue
            attributes = target.get("attributes") or {}
            if not isinstance(attributes, dict):
                continue
            process_exe_match = _same_executable_identity(attributes.get("exe"), declaration)
            cmdline = attributes.get("cmdline")
            if isinstance(cmdline, list) and cmdline and all(isinstance(item, str) for item in cmdline):
                cmdline_match = _same_executable_identity(cmdline[0], declaration)
                argv_tail_match = (
                    len(declaration.command_argv) > 1
                    and len(cmdline) == len(declaration.command_argv)
                    and tuple(cmdline[1:]) == declaration.command_argv[1:]
                )
            if not process_exe_match and not cmdline_match and not argv_tail_match:
                continue
            process = deepcopy(target)
        if process is None:
            continue

        process_id = process.get("id")
        if not isinstance(process_id, str) or not process_id:
            continue
        candidate = candidates.get(process_id)
        if candidate is None:
            candidate = _Candidate(
                process=process,
                latest_timestamp=timestamp,
                latest_timestamp_text=str(event.get("timestamp")),
            )
            candidates[process_id] = candidate
        candidate.observe(
            event,
            timestamp=timestamp,
            exec_match=exec_match,
            process_exe_match=process_exe_match,
            cmdline_match=cmdline_match,
            argv_tail_match=argv_tail_match,
        )
    return candidates


def _derived_event(
    declaration: _Declaration,
    candidate: _Candidate,
    *,
    session_id: str,
    max_window_ms: int,
) -> dict[str, Any]:
    method, confidence = candidate.method_and_confidence()
    support = set(candidate.supporting_event_ids)
    declaration_event_id = declaration.event.get("event_id")
    if isinstance(declaration_event_id, str) and declaration_event_id:
        support.add(declaration_event_id)

    process_id = str(candidate.process.get("id"))
    tool_call_id = str(declaration.tool_call.get("id"))
    digest_source = "|".join(
        [session_id, tool_call_id, process_id, method, *sorted(support)]
    ).encode("utf-8", errors="replace")
    digest = hashlib.sha256(digest_source).hexdigest()[:24]
    delta_ms = max(
        0.0,
        (candidate.latest_timestamp - declaration.timestamp).total_seconds() * 1000.0,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "event_id": f"inference:tool-process:{digest}",
        "session_id": session_id,
        "timestamp": candidate.latest_timestamp_text,
        "event_type": _EVENT_TYPE,
        "relation": _RELATION,
        "source": deepcopy(declaration.tool_call),
        "target": deepcopy(candidate.process),
        "sequence": None,
        "attributes": {
            "backend": "inference",
            "attribution": "execweave_correlation",
            "evidence_source": "derived",
            "causal": False,
            "inferred": True,
            "inference_method": method,
            "confidence": confidence,
            "confidence_semantics": "heuristic_score_not_probability",
            "candidate_count": 1,
            "declared_command_head": declaration.command_head,
            "declared_command_token": declaration.command_token,
            "tool_call_id": tool_call_id,
            "command_entity_id": declaration.command_entity.get("id"),
            "time_delta_ms": round(delta_ms, 3),
            "max_window_ms": max_window_ms,
            "supporting_event_ids": sorted(support),
        },
    }


def correlate_tool_process(
    input_path: str | Path,
    output_path: str | Path,
    *,
    max_window_ms: int = 3000,
) -> CorrelationResult:
    if max_window_ms <= 0:
        raise ValueError("max_window_ms must be greater than zero")
    source = Path(input_path).expanduser().resolve()
    output = Path(output_path).expanduser().resolve()
    if output.exists() and output.stat().st_size > 0:
        raise FileExistsError(f"ExecWeave correlation output already exists: {output}")

    validation = validate_event_stream(source, require_complete_session=True)
    if not validation.valid:
        raise ValueError("invalid input event stream: " + "; ".join(validation.errors))
    events = _load_jsonl(source)
    session_id = validation.session_ids[0]
    declarations = _declarations(events)
    results = _result_times(events)
    derived: list[dict[str, Any]] = []
    skipped_unsupported = 0
    skipped_no_match = 0
    skipped_ambiguous = 0

    for position, declaration in enumerate(declarations):
        if not declaration.command_head:
            skipped_unsupported += 1
            continue

        window_end = declaration.timestamp + timedelta(milliseconds=max_window_ms)
        tool_call_id = declaration.tool_call.get("id")
        if isinstance(tool_call_id, str):
            for result_time in results.get(tool_call_id, []):
                if result_time >= declaration.timestamp:
                    window_end = min(window_end, result_time)
                    break
        if position + 1 < len(declarations):
            next_time = declarations[position + 1].timestamp
            if next_time > declaration.timestamp:
                window_end = min(window_end, next_time)

        candidates = _candidate_processes(
            events,
            declaration=declaration,
            start=declaration.timestamp,
            end=window_end,
        )
        if not candidates:
            skipped_no_match += 1
            continue
        if len(candidates) != 1:
            skipped_ambiguous += 1
            continue
        derived.append(
            _derived_event(
                declaration,
                next(iter(candidates.values())),
                session_id=session_id,
                max_window_ms=max_window_ms,
            )
        )

    starts = [event for event in events if event.get("event_type") == "session.started"]
    finishes = [event for event in events if event.get("event_type") == "session.finished"]
    if len(starts) != 1 or len(finishes) != 1:
        raise ValueError("input event stream must contain exactly one session start and finish")

    body = [
        deepcopy(event)
        for event in events
        if event.get("event_type") not in {"session.started", "session.finished"}
    ]
    decorated: list[tuple[datetime, int, int, dict[str, Any]]] = []
    for index, event in enumerate(body):
        decorated.append((_event_time(event, index=index + 1), 0, index, event))
    for index, event in enumerate(derived):
        decorated.append((_event_time(event, index=index + 1), 1, index, event))
    decorated.sort(key=lambda item: (item[0], item[1], item[2]))

    correlated = [deepcopy(starts[0]), *[item[3] for item in decorated], deepcopy(finishes[0])]
    for sequence, event in enumerate(correlated, start=1):
        event["sequence"] = sequence

    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=".execweave-correlate-",
        suffix=".jsonl",
        dir=output.parent,
    )
    os.close(fd)
    temp_path = Path(temp_name)
    try:
        temp_path.write_text(
            "".join(
                json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n"
                for event in correlated
            ),
            encoding="utf-8",
        )
        correlated_validation = validate_event_stream(temp_path, require_complete_session=True)
        if not correlated_validation.valid:
            raise ValueError(
                "correlated event stream is invalid: "
                + "; ".join(correlated_validation.errors)
            )
        temp_path.replace(output)
    finally:
        if temp_path.exists():
            temp_path.unlink()

    return CorrelationResult(
        session_id=session_id,
        input_event_count=len(events),
        output_event_count=len(correlated),
        tool_calls_considered=len(declarations),
        correlated_tool_calls=len(derived),
        skipped_unsupported=skipped_unsupported,
        skipped_no_match=skipped_no_match,
        skipped_ambiguous=skipped_ambiguous,
        max_window_ms=max_window_ms,
        output=str(output),
    )