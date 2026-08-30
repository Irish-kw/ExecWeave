from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from .evidence_availability import (
    AVAILABLE,
    COMPLETE_FROM_SURFACE,
    DECRYPTABILITY_UNKNOWN,
    EVIDENCE_DIRECT_OBSERVATION,
    EVIDENCE_NO_DATA,
    NO_LOCAL_DECRYPTOR_OBSERVED,
    NOT_OBSERVED,
    OPAQUE_ENCRYPTED,
    OPAQUE_SIGNED,
    REDACTED,
    SUMMARY,
    UNKNOWN,
    FieldEvidence,
)

REQUIRED_FIELDS = (
    "system",
    "prompt",
    "messages",
    "tool_definitions",
    "tool_arguments",
    "tool_results",
    "assistant_output",
    "reasoning",
    "usage",
)

TIER_REQUIRED = "A"
TIER_OPTIONAL = "B"


@dataclass(frozen=True)
class CapabilityInventoryEntry:
    client: str
    provider: str
    auth_modes: tuple[str, ...]
    surfaces: tuple[str, ...]
    transport_mode: str
    tier: str
    required_fields: tuple[str, ...] = REQUIRED_FIELDS

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


REQUIRED_CAPABILITY_INVENTORY = (
    CapabilityInventoryEntry(
        client="codex-cli",
        provider="openai",
        auth_modes=("api_key", "subscription"),
        surfaces=("agent",),
        transport_mode="direct",
        tier=TIER_REQUIRED,
    ),
    CapabilityInventoryEntry(
        client="claude-code",
        provider="anthropic",
        auth_modes=("api_key", "subscription"),
        surfaces=("agent",),
        transport_mode="direct",
        tier=TIER_REQUIRED,
    ),
    CapabilityInventoryEntry(
        client="gemini-cli",
        provider="google",
        auth_modes=("api_key",),
        surfaces=("agent",),
        transport_mode="direct",
        tier=TIER_REQUIRED,
    ),
    CapabilityInventoryEntry(
        client="cursor-agent",
        provider="cursor_or_upstream",
        auth_modes=("subscription",),
        surfaces=("agent",),
        transport_mode="direct",
        tier=TIER_REQUIRED,
    ),
    CapabilityInventoryEntry(
        client="opencode",
        provider="configured_upstream",
        auth_modes=("api_key",),
        surfaces=("agent",),
        transport_mode="direct",
        tier=TIER_REQUIRED,
    ),
    CapabilityInventoryEntry(
        client="ollama",
        provider="local",
        auth_modes=("local",),
        surfaces=("chat", "generate"),
        transport_mode="local_runtime",
        tier=TIER_REQUIRED,
    ),
)

OPTIONAL_CAPABILITY_INVENTORY = (
    CapabilityInventoryEntry(
        client="cursor",
        provider="cursor_or_upstream",
        auth_modes=("subscription",),
        surfaces=("autocomplete", "tab"),
        transport_mode="direct",
        tier=TIER_OPTIONAL,
    ),
    CapabilityInventoryEntry(
        client="lmstudio",
        provider="local",
        auth_modes=("local",),
        surfaces=("chat",),
        transport_mode="local_runtime",
        tier=TIER_OPTIONAL,
    ),
    CapabilityInventoryEntry(
        client="llamacpp",
        provider="local",
        auth_modes=("local",),
        surfaces=("chat", "completion"),
        transport_mode="local_runtime",
        tier=TIER_OPTIONAL,
    ),
    CapabilityInventoryEntry(
        client="vllm",
        provider="local",
        auth_modes=("local",),
        surfaces=("chat", "completion"),
        transport_mode="local_runtime",
        tier=TIER_OPTIONAL,
    ),
)

CAPABILITY_INVENTORY = REQUIRED_CAPABILITY_INVENTORY + OPTIONAL_CAPABILITY_INVENTORY


@dataclass(frozen=True)
class CapabilityObservation:
    client: str
    client_version: str | None
    provider: str
    auth_mode: str
    surface: str
    transport_mode: str
    field: str
    availability: str
    decryptability: str
    evidence_source: str
    evidence_strength: str
    tier: str
    notes: str | None = None

    def __post_init__(self) -> None:
        FieldEvidence(
            field=self.field,
            availability=self.availability,
            decryptability=self.decryptability,
            evidence_source=self.evidence_source,
            evidence_strength=self.evidence_strength,
            notes=self.notes,
        )

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class _Match:
    field: str
    availability: str
    decryptability: str
    path: str
    notes: str | None = None


_AVAILABILITY_PRIORITY = {
    COMPLETE_FROM_SURFACE: 100,
    AVAILABLE: 90,
    SUMMARY: 80,
    REDACTED: 70,
    OPAQUE_ENCRYPTED: 60,
    OPAQUE_SIGNED: 50,
    UNKNOWN: 0,
}

_TOOL_CALL_TYPES = frozenset(
    {"function_call", "tool_call", "tool_use", "function", "custom_tool_call"}
)


def inventory_as_dict() -> dict[str, object]:
    return {
        "schema_version": 1,
        "required_fields": list(REQUIRED_FIELDS),
        "entries": [entry.to_dict() for entry in CAPABILITY_INVENTORY],
    }


def inventory_entry(client: str) -> CapabilityInventoryEntry:
    normalized = client.strip().lower()
    matches = [entry for entry in CAPABILITY_INVENTORY if entry.client == normalized]
    if len(matches) != 1:
        raise ValueError(f"unknown or ambiguous capability client: {client}")
    return matches[0]


def _records(path: Path) -> tuple[list[Any], list[str]]:
    errors: list[str] = []
    if path.suffix.lower() == ".jsonl":
        values: list[Any] = []
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            return [], [f"{type(exc).__name__}: unable to read artifact"]
        except UnicodeDecodeError:
            return [], ["UnicodeDecodeError: artifact is not UTF-8"]
        for number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                values.append(json.loads(line))
            except json.JSONDecodeError as exc:
                errors.append(f"line {number}: {exc.msg}")
        return values, errors
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [], [f"{type(exc).__name__}: unable to read artifact"]
    except UnicodeDecodeError:
        return [], ["UnicodeDecodeError: artifact is not UTF-8"]
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        return [], [f"JSONDecodeError: {exc.msg}"]
    return [value], errors


def _walk(value: Any, path: str = "$") -> Iterable[tuple[str, Any]]:
    yield path, value
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _walk(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk(child, f"{path}[{index}]")


def _nonempty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, (str, list, dict, tuple)):
        return bool(value)
    return True


def _redacted(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    normalized = value.strip().lower()
    return normalized in {"[redacted]", "<redacted>", "redacted"}


def _match(field: str, path: str, value: Any) -> _Match:
    availability = REDACTED if _redacted(value) else AVAILABLE
    return _Match(field, availability, DECRYPTABILITY_UNKNOWN, path)


def _reasoning_matches(path: str, payload: Any) -> list[_Match]:
    if not _nonempty(payload):
        return []
    if not isinstance(payload, dict):
        return [_match("reasoning", path, payload)]

    matches: list[_Match] = []
    encrypted = payload.get("encrypted_content")
    if isinstance(encrypted, str) and encrypted:
        matches.append(
            _Match(
                "reasoning",
                OPAQUE_ENCRYPTED,
                DECRYPTABILITY_UNKNOWN,
                f"{path}.encrypted_content",
                notes="encrypted reasoning payload observed",
            )
        )
    summary = payload.get("summary")
    if _nonempty(summary):
        matches.append(
            _Match(
                "reasoning",
                SUMMARY,
                DECRYPTABILITY_UNKNOWN,
                f"{path}.summary",
                notes="provider-exposed reasoning summary observed",
            )
        )
    signature = payload.get("signature")
    if _nonempty(signature):
        matches.append(
            _Match(
                "reasoning",
                OPAQUE_SIGNED,
                DECRYPTABILITY_UNKNOWN,
                f"{path}.signature",
                notes="reasoning signature observed",
            )
        )
    for key in ("content", "text", "thinking"):
        if key in payload and _nonempty(payload[key]):
            matches.append(_match("reasoning", f"{path}.{key}", payload[key]))

    # A readable container with an unknown provider-specific shape is still directly
    # observable, but only use the weak ``available`` state when no more precise form
    # (encrypted, summary, signature, or plaintext field) was identified.
    return matches or [_match("reasoning", path, payload)]


def _has_tool_call_context(value: dict[str, Any], item_type: object) -> bool:
    return (
        item_type in _TOOL_CALL_TYPES
        or ("name" in value and "arguments" in value)
        or ("call_id" in value and "arguments" in value)
        or ("tool_call_id" in value and "arguments" in value)
    )


def _matches_for_object(path: str, value: dict[str, Any]) -> list[_Match]:
    matches: list[_Match] = []
    role = value.get("role")
    item_type = value.get("type")

    # Preserve provider role semantics. A provider-declared developer message is a
    # message, not evidence that a system-role field existed.
    if role == "system" and _nonempty(value.get("content")):
        matches.append(_match("system", f"{path}.content", value["content"]))
    if role in {"user", "assistant", "system", "developer", "tool", "function"}:
        if "content" in value:
            matches.append(_match("messages", f"{path}.content", value.get("content")))
    if role == "assistant" and _nonempty(value.get("content")):
        matches.append(_match("assistant_output", f"{path}.content", value["content"]))
    if role in {"tool", "function"} and _nonempty(value.get("content")):
        matches.append(_match("tool_results", f"{path}.content", value["content"]))

    for key in ("system", "system_prompt", "system_instruction", "systemInstruction"):
        if key in value and _nonempty(value[key]):
            matches.append(_match("system", f"{path}.{key}", value[key]))
    for key in ("prompt", "user_prompt"):
        if key in value and _nonempty(value[key]):
            matches.append(_match("prompt", f"{path}.{key}", value[key]))
    for key in ("messages", "contents"):
        if key in value and _nonempty(value[key]):
            matches.append(_match("messages", f"{path}.{key}", value[key]))
    for key in ("tools", "functions", "tool_definitions", "toolDeclarations"):
        if key in value and _nonempty(value[key]):
            matches.append(_match("tool_definitions", f"{path}.{key}", value[key]))

    for key in ("tool_input", "function_args", "functionArguments"):
        if key in value and _nonempty(value[key]):
            matches.append(_match("tool_arguments", f"{path}.{key}", value[key]))
    if (
        "arguments" in value
        and _nonempty(value["arguments"])
        and _has_tool_call_context(value, item_type)
    ):
        matches.append(_match("tool_arguments", f"{path}.arguments", value["arguments"]))

    for key in ("tool_response", "tool_result", "function_response", "functionResponse"):
        if key in value and _nonempty(value[key]):
            matches.append(_match("tool_results", f"{path}.{key}", value[key]))
    for key in ("output_text", "completion", "response_text"):
        if key in value and _nonempty(value[key]):
            matches.append(_match("assistant_output", f"{path}.{key}", value[key]))

    if item_type in {"reasoning", "thinking"}:
        matches.extend(_reasoning_matches(path, value))
    for key in ("reasoning", "thinking"):
        if key in value:
            matches.extend(_reasoning_matches(f"{path}.{key}", value[key]))

    if "usage" in value and _nonempty(value["usage"]):
        matches.append(_match("usage", f"{path}.usage", value["usage"]))
    token_keys = {
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "prompt_tokens",
        "completion_tokens",
        "reasoning_tokens",
    }
    if token_keys.intersection(value):
        matches.append(_match("usage", path, value))
    return matches


def _collect_matches(records: Iterable[Any]) -> tuple[dict[str, list[_Match]], str | None]:
    by_field: dict[str, list[_Match]] = {field: [] for field in REQUIRED_FIELDS}
    version: str | None = None
    for record_index, record in enumerate(records):
        for path, value in _walk(record, path=f"$[{record_index}]"):
            if not isinstance(value, dict):
                continue
            if version is None:
                for key in ("cli_version", "client_version"):
                    candidate = value.get(key)
                    if isinstance(candidate, str) and candidate.strip():
                        version = candidate.strip()
                        break
            for match in _matches_for_object(path, value):
                by_field[match.field].append(match)
    return by_field, version


def _best_match(matches: list[_Match]) -> _Match | None:
    if not matches:
        return None
    return max(matches, key=lambda match: _AVAILABILITY_PRIORITY.get(match.availability, 0))


def _artifact_label(path: Path | None) -> str:
    if path is None:
        return "no_data"
    return path.name or "artifact"


def _append_note(existing: str | None, extra: str | None) -> str | None:
    if not extra:
        return existing
    return f"{existing}; {extra}" if existing else extra


def _observation(
    entry: CapabilityInventoryEntry,
    *,
    auth_mode: str,
    surface: str,
    field: str,
    client_version: str | None,
    match: _Match | None,
    artifact: Path | None,
    reason: str | None,
    parse_warning: str | None,
    codex_no_local_decryptor_observed: bool,
) -> CapabilityObservation:
    label = _artifact_label(artifact)
    if match is None:
        source = "probe:no_data" if artifact is None else f"artifact:{label}"
        return CapabilityObservation(
            client=entry.client,
            client_version=client_version,
            provider=entry.provider,
            auth_mode=auth_mode,
            surface=surface,
            transport_mode=entry.transport_mode,
            field=field,
            availability=NOT_OBSERVED,
            decryptability=DECRYPTABILITY_UNKNOWN,
            evidence_source=source,
            evidence_strength=EVIDENCE_NO_DATA,
            tier=entry.tier,
            notes=_append_note(reason or "field not observed in supplied artifact", parse_warning),
        )

    decryptability = match.decryptability
    notes = _append_note(match.notes, parse_warning)
    if (
        entry.client == "codex-cli"
        and field == "reasoning"
        and match.availability == OPAQUE_ENCRYPTED
        and codex_no_local_decryptor_observed
    ):
        decryptability = NO_LOCAL_DECRYPTOR_OBSERVED
        notes = _append_note(
            notes,
            "no ExecWeave Codex decryptor marker observed by repository source audit",
        )
    return CapabilityObservation(
        client=entry.client,
        client_version=client_version,
        provider=entry.provider,
        auth_mode=auth_mode,
        surface=surface,
        transport_mode=entry.transport_mode,
        field=field,
        availability=match.availability,
        decryptability=decryptability,
        evidence_source=f"artifact:{label}#{match.path}",
        evidence_strength=EVIDENCE_DIRECT_OBSERVATION,
        tier=entry.tier,
        notes=notes,
    )


def probe_artifact(
    entry: CapabilityInventoryEntry,
    artifact: str | Path | None,
    *,
    auth_mode: str,
    surface: str,
    codex_no_local_decryptor_observed: bool = False,
) -> list[CapabilityObservation]:
    if auth_mode not in entry.auth_modes:
        raise ValueError(f"unsupported auth mode for {entry.client}: {auth_mode}")
    if surface not in entry.surfaces:
        raise ValueError(f"unsupported surface for {entry.client}: {surface}")

    path = Path(artifact).expanduser() if artifact is not None else None
    if path is None or not path.is_file():
        reason = "artifact not supplied" if path is None else "artifact not found"
        return [
            _observation(
                entry,
                auth_mode=auth_mode,
                surface=surface,
                field=field,
                client_version=None,
                match=None,
                artifact=path,
                reason=reason,
                parse_warning=None,
                codex_no_local_decryptor_observed=codex_no_local_decryptor_observed,
            )
            for field in entry.required_fields
        ]

    records, errors = _records(path)
    matches, version = _collect_matches(records)
    parse_warning = f"artifact parse warning: {'; '.join(errors)}" if errors else None
    observations: list[CapabilityObservation] = []
    for field in entry.required_fields:
        match = _best_match(matches[field])
        observations.append(
            _observation(
                entry,
                auth_mode=auth_mode,
                surface=surface,
                field=field,
                client_version=version,
                match=match,
                artifact=path,
                reason=None,
                parse_warning=parse_warning,
                codex_no_local_decryptor_observed=codex_no_local_decryptor_observed,
            )
        )
    return observations


def not_observed_matrix(reason: str = "artifact not supplied") -> list[CapabilityObservation]:
    observations: list[CapabilityObservation] = []
    for entry in CAPABILITY_INVENTORY:
        for auth_mode in entry.auth_modes:
            for surface in entry.surfaces:
                for field in entry.required_fields:
                    observations.append(
                        CapabilityObservation(
                            client=entry.client,
                            client_version=None,
                            provider=entry.provider,
                            auth_mode=auth_mode,
                            surface=surface,
                            transport_mode=entry.transport_mode,
                            field=field,
                            availability=NOT_OBSERVED,
                            decryptability=DECRYPTABILITY_UNKNOWN,
                            evidence_source="probe:no_data",
                            evidence_strength=EVIDENCE_NO_DATA,
                            tier=entry.tier,
                            notes=reason,
                        )
                    )
    return observations


def matrix_as_dict(observations: Iterable[CapabilityObservation]) -> dict[str, object]:
    rows = [observation.to_dict() for observation in observations]
    return {
        "schema_version": 1,
        "required_fields": list(REQUIRED_FIELDS),
        "rows": rows,
    }
