from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit
from urllib.request import url2pathname

_TRANSCRIPT_NAMES = {"transcript.jsonl", "transcript_full.jsonl"}
_RESULT_PREFIX = "Created the following subagents:"
_MAX_TRANSCRIPT_BYTES = 2 * 1024 * 1024


def _canonical_path(value: str) -> Path | None:
    try:
        path = Path(value).expanduser()
        if not path.is_absolute():
            return None
        return path.resolve(strict=False)
    except (OSError, RuntimeError, ValueError):
        return None


def _canonical_file_uri_path(value: str) -> Path | None:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    if parsed.scheme != "file" or parsed.netloc or parsed.query or parsed.fragment:
        return None
    try:
        raw_path = url2pathname(unquote(parsed.path))
    except ValueError:
        return None
    path = _canonical_path(raw_path)
    if path is None:
        return None
    try:
        if path.as_uri() != value:
            return None
    except ValueError:
        return None
    return path


def _transcript_root(path: Path, conversation_id: str) -> Path | None:
    try:
        if path.name not in _TRANSCRIPT_NAMES:
            return None
        logs = path.parent
        generated = logs.parent
        conversation = generated.parent
        brain = conversation.parent
    except (IndexError, RuntimeError):
        return None
    if logs.name != "logs" or generated.name != ".system_generated":
        return None
    if brain.name != "brain" or conversation.name != conversation_id:
        return None
    return brain.parent


def validated_transcript_path(payload: dict[str, Any]) -> Path | None:
    """Return the canonical parent transcript only for the verified Antigravity brain layout."""
    conversation_id = payload.get("conversationId")
    transcript_raw = payload.get("transcriptPath")
    if not isinstance(conversation_id, str) or not conversation_id:
        return None
    if not isinstance(transcript_raw, str) or not transcript_raw:
        return None
    transcript = _canonical_path(transcript_raw)
    if transcript is None or _transcript_root(transcript, conversation_id) is None:
        return None
    return transcript


def _read_records(path: Path) -> list[dict[str, Any]] | None:
    try:
        size = path.stat().st_size
        if size <= 0:
            return []
        with path.open("rb") as handle:
            handle.seek(-1, 2)
            if handle.read(1) != b"\n":
                return None
            start = max(0, size - _MAX_TRANSCRIPT_BYTES)
            handle.seek(start)
            data = handle.read()
    except OSError:
        return None
    if start:
        boundary = data.find(b"\n")
        if boundary < 0:
            return None
        data = data[boundary + 1 :]
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return None
    records: list[dict[str, Any]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            return None
        if not isinstance(record, dict):
            return None
        records.append(record)
    return records


def _request_specs(value: object) -> list[dict[str, Any]] | None:
    if not isinstance(value, list) or not value:
        return None
    specs: list[dict[str, Any]] = []
    # Current Antigravity includes Model in each invoke_subagent spec.
    # Keep the allow-list strict while accepting that live-verified field.
    allowed = {"Model", "Prompt", "Role", "TypeName", "Workspace"}
    for raw in value:
        if not isinstance(raw, dict) or not set(raw).issubset(allowed):
            return None
        prompt = raw.get("Prompt")
        role = raw.get("Role")
        type_name = raw.get("TypeName")
        if not isinstance(prompt, str) or not prompt:
            return None
        if not isinstance(role, str) or not role:
            return None
        if not isinstance(type_name, str) or not type_name:
            return None
        model = raw.get("Model")
        if model is not None and (not isinstance(model, str) or not model):
            return None
        workspace = raw.get("Workspace")
        if workspace is not None and (not isinstance(workspace, str) or not workspace):
            return None
        specs.append(dict(raw))
    return specs


def _parse_result_content(value: object) -> list[dict[str, Any]] | None:
    if not isinstance(value, str) or not value.startswith(_RESULT_PREFIX):
        return None
    rest = value[len(_RESULT_PREFIX) :]
    decoder = json.JSONDecoder()
    index = 0
    results: list[dict[str, Any]] = []
    while True:
        while index < len(rest) and rest[index].isspace():
            index += 1
        if index >= len(rest):
            break
        try:
            decoded, end = decoder.raw_decode(rest, index)
        except json.JSONDecodeError:
            return None
        if not isinstance(decoded, dict):
            return None
        results.append(decoded)
        index = end
    return results or None


def _workspace_path(value: str) -> Path | None:
    if value.startswith("file:"):
        return _canonical_file_uri_path(value)
    return _canonical_path(value)


def _expected_workspace(
    spec: dict[str, Any],
    parent_workspaces: list[Path],
) -> Path | None:
    raw = spec.get("Workspace")
    if raw is None or raw == "inherit":
        return parent_workspaces[0] if parent_workspaces else None
    if not isinstance(raw, str):
        return None
    return _workspace_path(raw)


def _result_workspace_matches(result: dict[str, Any], expected: Path) -> bool:
    raw_uris = result.get("workspaceUris")
    if raw_uris is None:
        return True
    if not isinstance(raw_uris, list) or not raw_uris:
        return False
    paths: list[Path] = []
    for raw in raw_uris:
        if not isinstance(raw, str):
            return False
        path = _canonical_file_uri_path(raw)
        if path is None:
            return False
        paths.append(path)
    return expected in paths


def _matching_request(record: dict[str, Any], specs: list[dict[str, Any]]) -> bool:
    if record.get("source") != "MODEL":
        return False
    if record.get("type") != "PLANNER_RESPONSE" or record.get("status") != "DONE":
        return False
    calls = record.get("tool_calls")
    if not isinstance(calls, list) or len(calls) != 1:
        return False
    call = calls[0]
    if not isinstance(call, dict) or call.get("name") != "invoke_subagent":
        return False
    args = call.get("args")
    if not isinstance(args, dict):
        return False
    return args.get("Subagents") == specs


def _matching_result(record: dict[str, Any]) -> list[dict[str, Any]] | None:
    if record.get("source") != "MODEL" or record.get("status") != "DONE":
        return None
    # Older builds labelled the immediate result INVOKE_SUBAGENT; the current
    # live wire labels that same record GENERIC. GENERIC is accepted only if its
    # payload passes _parse_result_content's exact provider prefix/schema checks.
    if record.get("type") not in {"INVOKE_SUBAGENT", "GENERIC"}:
        return None
    return _parse_result_content(record.get("content"))


def sanitize_agent_path_leaf(value: str) -> str | None:
    """Turn a provider Role/TypeName into a single path leaf under /root."""
    leaf = " ".join(value.replace("\\", "-").replace("/", "-").split())
    return leaf or None


def derived_child_agent_path(spec: dict[str, Any], child_id: str) -> str:
    """Prefer Role, then TypeName, then the provider conversation id."""
    for key in ("Role", "TypeName"):
        raw = spec.get(key)
        if isinstance(raw, str) and raw:
            leaf = sanitize_agent_path_leaf(raw)
            if leaf is not None:
                return f"/root/{leaf}"
    leaf = sanitize_agent_path_leaf(child_id)
    return f"/root/{leaf}" if leaf is not None else "/root/agent"


def read_transcript_records(path: Path) -> list[dict[str, Any]]:
    """Read a complete archived or live transcript without the live-hook tail cap."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return []
    records: list[dict[str, Any]] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            records.append(record)
    return records


def transcript_subagent_links(
    records: list[dict[str, Any]] | None,
    *,
    parent_id: str,
) -> list[dict[str, Any]]:
    """Join invoke_subagent request+result pairs already present in one transcript.

    ``validated_subagent_links`` additionally proves the hook payload pointed at the
    live brain file (workspace URIs, logAbsoluteUri layout). Once that file has been
    copied into the run, those live-path checks are gone. The remaining provider
    fact is the unique request/result pair naming child conversation ids.
    Ambiguous or malformed transcripts still abstain.
    """
    if not isinstance(parent_id, str) or not parent_id or not records:
        return []
    candidates: list[tuple[list[dict[str, Any]], list[dict[str, Any]], int]] = []
    for index, record in enumerate(records[:-1]):
        calls = record.get("tool_calls")
        if not isinstance(calls, list) or len(calls) != 1:
            continue
        call = calls[0]
        if not isinstance(call, dict) or call.get("name") != "invoke_subagent":
            continue
        args = call.get("args")
        if not isinstance(args, dict):
            continue
        specs = _request_specs(args.get("Subagents"))
        if specs is None or not _matching_request(record, specs):
            continue
        results = _matching_result(records[index + 1])
        if results is None:
            continue
        step = record.get("step_index")
        step_index = (
            step if isinstance(step, int) and not isinstance(step, bool) and step >= 0 else index
        )
        candidates.append((specs, results, step_index))
    if len(candidates) != 1:
        return []
    specs, results, step_index = candidates[0]
    if len(results) != len(specs):
        return []
    seen: set[str] = set()
    links: list[dict[str, Any]] = []
    for subagent_index, (spec, result) in enumerate(zip(specs, results, strict=True)):
        child_id = result.get("conversationId")
        if not isinstance(child_id, str) or not child_id:
            return []
        if child_id == parent_id or child_id in seen:
            return []
        seen.add(child_id)
        links.append(
            {
                "subagent_index": subagent_index,
                "conversation_id": child_id,
                "step_index": step_index,
                "spec": spec,
                "agent_path": derived_child_agent_path(spec, child_id),
            }
        )
    return links


def validated_subagent_links(
    payload: dict[str, Any],
    *,
    args: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return exact request-index -> child IDs only for a validated parent transcript pair.

    The transcript record layout is a live-verified Antigravity implementation wire, not a
    public stable schema. Every validation failure therefore abstains rather than infers.
    """
    parent_id = payload.get("conversationId")
    if not isinstance(parent_id, str) or not parent_id:
        return []
    transcript = validated_transcript_path(payload)
    if transcript is None:
        return []
    app_data_root = _transcript_root(transcript, parent_id)
    if app_data_root is None:
        return []

    specs = _request_specs(args.get("Subagents"))
    if specs is None:
        return []

    raw_parent_workspaces = payload.get("workspacePaths")
    if not isinstance(raw_parent_workspaces, list) or not raw_parent_workspaces:
        return []
    parent_workspaces: list[Path] = []
    for raw in raw_parent_workspaces:
        if not isinstance(raw, str):
            return []
        path = _canonical_path(raw)
        if path is None:
            return []
        parent_workspaces.append(path)

    records = _read_records(transcript)
    if records is None:
        return []

    candidates: list[list[dict[str, Any]]] = []
    for index, record in enumerate(records[:-1]):
        if not _matching_request(record, specs):
            continue
        results = _matching_result(records[index + 1])
        if results is not None:
            candidates.append(results)
    if len(candidates) != 1:
        return []
    results = candidates[0]
    if len(results) != len(specs):
        return []

    seen: set[str] = set()
    links: list[dict[str, Any]] = []
    for subagent_index, (spec, result) in enumerate(zip(specs, results, strict=True)):
        child_id = result.get("conversationId")
        log_uri = result.get("logAbsoluteUri")
        if not isinstance(child_id, str) or not child_id:
            return []
        if child_id == parent_id or child_id in seen:
            return []
        seen.add(child_id)
        if not isinstance(log_uri, str) or not log_uri:
            return []
        child_transcript = _canonical_file_uri_path(log_uri)
        if child_transcript is None:
            return []
        child_root = _transcript_root(child_transcript, child_id)
        if child_root is None or child_root != app_data_root:
            return []

        expected = _expected_workspace(spec, parent_workspaces)
        if expected is None or not _result_workspace_matches(result, expected):
            return []
        links.append(
            {
                "subagent_index": subagent_index,
                "conversation_id": child_id,
            }
        )
    return links
