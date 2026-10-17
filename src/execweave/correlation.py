from __future__ import annotations

import hashlib
import json
import os
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .private_io import private_artifact_path, write_private_text
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
                # A tail of option flags alone (``-v``, ``--help``) says nothing
                # about which program ran, so it cannot establish compatibility.
                argv_tail_match = (
                    len(declaration.command_argv) > 1
                    and len(cmdline) == len(declaration.command_argv)
                    and tuple(cmdline[1:]) == declaration.command_argv[1:]
                    and any(not token.startswith("-") for token in cmdline[1:])
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



def _sdk_native_spawn_correlations(
    events: list[dict[str, Any]],
    *,
    session_id: str,
    max_window_ms: int,
) -> tuple[list[dict[str, Any]], int, int, int, int]:
    """Infer *non-causal* SDK function-span/native-spawn links.

    This is a deliberately weaker result than execution-context propagation:
    SDK callback PID/timestamps originate in a same-UID process sidecar,
    whereas the child spawn is independently observed by strace. A temporal
    match is not proof that the tool caused the spawn. Never classify it as
    syscall-attributed; ambiguity (including concurrent spans) abstains.
    """
    starts: dict[str, dict[str, Any]] = {}
    ends: dict[str, dict[str, Any]] = {}
    spawns: list[dict[str, Any]] = []
    for event in events:
        attrs = event.get("attributes")
        if not isinstance(attrs, dict):
            continue
        if (
            event.get("event_type") == "process.started"
            and event.get("relation") == "SPAWNED"
            and attrs.get("backend") == "strace"
            and attrs.get("attribution") == "syscall"
            and isinstance(event.get("source"), dict)
            and isinstance(event.get("target"), dict)
            and event["source"].get("type") == "process"
            and event["target"].get("type") == "process"
        ):
            spawns.append(event)
            continue
        if attrs.get("evidence_source") != "agents_sdk_tracing_callback":
            continue
        if attrs.get("framework") != "openai-agents-sdk":
            continue
        call_id = attrs.get("tool_call_id")
        pid = attrs.get("sdk_host_pid")
        if (
            not isinstance(call_id, str) or not call_id
            or not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0
            or not isinstance(attrs.get("sdk_span_id"), str)
        ):
            continue
        if event.get("event_type") == "TOOL_CALL" and event.get("relation") == "REQUESTS_TOOL_CALL":
            if call_id in starts:
                # A duplicate declaration is ambiguous; refuse to join.
                starts[call_id] = {}
            else:
                starts[call_id] = event
        elif event.get("event_type") in {"TOOL_RESULT", "TOOL_FAILURE"}:
            if call_id in ends:
                ends[call_id] = {}
            else:
                ends[call_id] = event

    considered = len(starts)
    skipped_no_match = 0
    skipped_ambiguous = 0
    candidates: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]] = []
    for call_id, start in starts.items():
        end = ends.get(call_id)
        if not start or not end:
            skipped_no_match += 1
            continue
        start_attrs = start["attributes"]
        end_attrs = end["attributes"]
        if (
            start_attrs["sdk_host_pid"] != end_attrs.get("sdk_host_pid")
            or start_attrs["sdk_span_id"] != end_attrs.get("sdk_span_id")
            or start_attrs.get("sdk_trace_id") != end_attrs.get("sdk_trace_id")
        ):
            skipped_ambiguous += 1
            continue
        begin = _event_time(start, index=1)
        finish = _event_time(end, index=1)
        if finish < begin:
            skipped_no_match += 1
            continue
        # A time window cannot be stretched merely because a tool is slow.
        limit = min(finish, begin + timedelta(milliseconds=max_window_ms))
        matching = []
        for spawn in spawns:
            native_parent = (spawn.get("source") or {}).get("attributes") or {}
            if native_parent.get("pid") != start_attrs["sdk_host_pid"]:
                continue
            when = _event_time(spawn, index=1)
            if begin <= when <= limit:
                matching.append(spawn)
        if len(matching) != 1:
            if matching:
                skipped_ambiguous += 1
            else:
                skipped_no_match += 1
            continue
        candidates.append((start, end, matching[0]))

    # Concurrent SDK spans can each claim the same process; neither may.
    process_claims: dict[str, int] = {}
    for _, _, spawn in candidates:
        pid_id = spawn["target"]["id"]
        process_claims[pid_id] = process_claims.get(pid_id, 0) + 1
    derived = []
    for start, end, spawn in candidates:
        target = spawn["target"]
        if process_claims[target["id"]] != 1:
            skipped_ambiguous += 1
            continue
        attrs = start["attributes"]
        supporting = sorted({
            value for value in (start.get("event_id"), end.get("event_id"), spawn.get("event_id"))
            if isinstance(value, str) and value
        })
        call_id = attrs["tool_call_id"]
        digest = hashlib.sha256(
            "|".join([session_id, call_id, target["id"], *supporting]).encode()
        ).hexdigest()[:24]
        parent_tid = (spawn.get("attributes") or {}).get("spawn_origin_tid")
        callback_tid = attrs.get("sdk_callback_tid")
        derived.append({
            "schema_version": SCHEMA_VERSION,
            "event_id": f"inference:sdk-native-spawn:{digest}",
            "session_id": session_id,
            "timestamp": spawn["timestamp"],
            "event_type": _EVENT_TYPE,
            "relation": _RELATION,
            "source": {
                "type": "tool_call", "id": call_id,
                "name": "SDK function span",
                "attributes": {"sdk_trace_id": attrs.get("sdk_trace_id"),
                               "sdk_span_id": attrs["sdk_span_id"]},
            },
            "target": deepcopy(target),
            "sequence": None,
            "attributes": {
                "backend": "inference",
                "attribution": "execweave_correlation",
                "evidence_source": "derived",
                "inferred": True, "causal": False,
                "process_effect_verified": False,
                "inference_method": "unique_sdk_span_host_pid_native_spawn_window",
                "confidence": 0.65,
                "confidence_semantics": "heuristic_score_not_probability",
                "candidate_count": 1,
                "sdk_trace_id": attrs.get("sdk_trace_id"),
                "sdk_span_id": attrs["sdk_span_id"],
                "tool_call_id": call_id,
                "sdk_host_pid": attrs["sdk_host_pid"],
                "sdk_callback_tid": callback_tid,
                "native_spawn_origin_tid": parent_tid,
                "same_callback_and_spawn_tid": (
                    callback_tid == parent_tid
                    if isinstance(callback_tid, int) and isinstance(parent_tid, int)
                    else None
                ),
                "max_window_ms": max_window_ms,
                "supporting_event_ids": supporting,
                "limitation": "SDK callback PID/time window is a claim, not an OS-verified tool context",
            },
        })
    return derived, considered, skipped_no_match, skipped_ambiguous, len(derived)


def correlate_tool_process(
    input_path: str | Path,
    output_path: str | Path,
    *,
    max_window_ms: int = 3000,
) -> CorrelationResult:
    if max_window_ms <= 0:
        raise ValueError("max_window_ms must be greater than zero")
    source = Path(input_path).expanduser().resolve()
    output = private_artifact_path(output_path)
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

    candidate_sets: list[tuple[_Declaration, dict[str, _Candidate]]] = []
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
        # Declarations sharing a timestamp do not bound each other; the next
        # strictly later declaration still does.
        for later in declarations[position + 1 :]:
            if later.timestamp > declaration.timestamp:
                window_end = min(window_end, later.timestamp)
                break

        candidate_sets.append(
            (
                declaration,
                _candidate_processes(
                    events,
                    declaration=declaration,
                    start=declaration.timestamp,
                    end=window_end,
                ),
            )
        )

    # A process compatible with more than one declaration is ambiguous on the
    # declaration side as well, so none of those declarations claims it.
    claims: dict[str, int] = {}
    for _, candidates in candidate_sets:
        for process_id in candidates:
            claims[process_id] = claims.get(process_id, 0) + 1

    for declaration, candidates in candidate_sets:
        if not candidates:
            skipped_no_match += 1
            continue
        if len(candidates) != 1:
            skipped_ambiguous += 1
            continue
        process_id, candidate = next(iter(candidates.items()))
        if claims[process_id] != 1:
            skipped_ambiguous += 1
            continue
        derived.append(
            _derived_event(
                declaration,
                candidate,
                session_id=session_id,
                max_window_ms=max_window_ms,
            )
        )

    sdk_derived, sdk_considered, sdk_missing, sdk_ambiguous, sdk_joined = (
        _sdk_native_spawn_correlations(
            events, session_id=session_id, max_window_ms=max_window_ms
        )
    )
    derived.extend(sdk_derived)
    skipped_no_match += sdk_missing
    skipped_ambiguous += sdk_ambiguous

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

    blob = "".join(
        json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n" for event in correlated
    )
    validation_path = output.parent / f".{output.name}.validate-{uuid4().hex}.jsonl"
    try:
        write_private_text(validation_path, blob)
        correlated_validation = validate_event_stream(
            validation_path, require_complete_session=True
        )
        if not correlated_validation.valid:
            raise ValueError(
                "correlated event stream is invalid: "
                + "; ".join(correlated_validation.errors)
            )
        write_private_text(output, blob)
    finally:
        validation_path.unlink(missing_ok=True)

    return CorrelationResult(
        session_id=session_id,
        input_event_count=len(events),
        output_event_count=len(correlated),
        tool_calls_considered=len(declarations) + sdk_considered,
        correlated_tool_calls=len(derived),
        skipped_unsupported=skipped_unsupported,
        skipped_no_match=skipped_no_match,
        skipped_ambiguous=skipped_ambiguous,
        max_window_ms=max_window_ms,
        output=str(output),
    )