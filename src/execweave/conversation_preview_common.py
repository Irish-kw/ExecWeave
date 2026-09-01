from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .agent_topology import (
    COMPLETENESS_PROVIDER_TRANSCRIPT,
    THREAD_ID_EXECWEAVE_DERIVED,
    resolve_agent_topology,
)

_MAX_PREVIEW_MESSAGES = 80
_MAX_PREVIEW_TEXT_CHARS = 6000

_PROVIDER_LABELS = {
    "claude": "Claude Code",
    "codex": "OpenAI Codex",
    "cursor": "Cursor",
    "opencode": "OpenCode",
    "gemini": "Gemini CLI",
    "antigravity": "Antigravity",
    "anthropic": "Anthropic",
    "openrouter": "OpenRouter",
    "litellm": "LiteLLM",
    "ollama": "Ollama",
    "llamacpp": "llama.cpp",
    "vllm": "vLLM",
    "lmstudio": "LM Studio",
    "openai-compatible": "OpenAI-compatible",
    "openai_compatible": "OpenAI-compatible",
}

_USER_KINDS = (
    "user_prompt",
    "user_message",
    "request_prompt",
    "prompt_submission_candidate",
)
_ASSISTANT_FINAL_KINDS = (
    "assistant_final_response",
    "subagent_final_response",
    "completed_text",
)
_ASSISTANT_RESPONSE_KINDS = (
    "assistant_response",
    "assistant_display",
)
_SUBAGENT_TASK_KINDS = (
    "subagent_task",
    "subagent_description",
    "subtask_prompt",
    "subtask_description",
)
_SUBAGENT_SUMMARY_KINDS = ("subagent_summary", "subagent_final_response")


def _trim_text(value: str) -> str:
    value = value.strip()
    if len(value) <= _MAX_PREVIEW_TEXT_CHARS:
        return value
    return value[: _MAX_PREVIEW_TEXT_CHARS - 1] + "…"


def _read_value(path: Path) -> Any:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None
    if path.suffix.lower() == ".json":
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text
    return text


def _provider_label(provider: str) -> str:
    normalized = provider.strip().lower()
    return _PROVIDER_LABELS.get(normalized, provider or "Provider")


def _source_attributes(source: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(source, dict):
        return {}
    attrs = source.get("attributes")
    return attrs if isinstance(attrs, dict) else {}


def _agent_identity(provider: str, source: dict[str, Any] | None) -> dict[str, Any]:
    """Project one agent node into the conversation schema, provenance intact.

    Root/child classification comes from :func:`resolve_agent_topology`, which
    requires positive provider evidence before calling anything a child. An agent
    ExecWeave cannot place is root, not a fabricated subagent.
    """
    source = source if isinstance(source, dict) else {}
    attrs = _source_attributes(source)
    source_id = source.get("id")
    source_name = source.get("name")
    source_id_text = source_id if isinstance(source_id, str) else ""
    provider_label = _provider_label(provider)
    provider_key = provider.lower() or "provider"

    topology = resolve_agent_topology(source)
    agent_path = topology.agent_path
    is_root = topology.is_root

    native_label = (
        attrs.get("agent_nickname")
        or attrs.get("agent_type")
        or attrs.get("subagent_type")
        or attrs.get("native_agent_name")
        or source_name
    )
    if is_root:
        agent_label = provider_label
    elif isinstance(native_label, str) and native_label.strip():
        agent_label = native_label.strip()
    else:
        agent_label = agent_path.rsplit("/", 1)[-1] or "Agent"

    if is_root:
        thread_id = f"{provider_key}:root"
        parent_thread_id = None
    else:
        thread_id = f"{provider_key}:{source_id_text or agent_path}"
        parent_thread_id = f"{provider_key}:root"

    return {
        "thread_id": thread_id,
        "thread_id_source": THREAD_ID_EXECWEAVE_DERIVED,
        "parent_thread_id": parent_thread_id,
        "agent_label": agent_label,
        "provider_label": provider_label,
        "agent_nickname": (
            attrs.get("agent_nickname")
            if isinstance(attrs.get("agent_nickname"), str)
            else None
        ),
        **topology.to_dict(),
    }


def _message(
    *,
    timestamp: object,
    ordinal: object,
    kind: str,
    sender: str | None,
    recipient: str | None,
    text: str | None,
    phase: str | None = None,
    task_name: str | None = None,
    content_state: str = "plaintext",
) -> dict[str, Any]:
    return {
        "timestamp": timestamp if isinstance(timestamp, str) else None,
        "ordinal": (
            ordinal
            if isinstance(ordinal, int) and not isinstance(ordinal, bool)
            else None
        ),
        "kind": kind,
        "sender": sender,
        "recipient": recipient,
        "text": _trim_text(text) if isinstance(text, str) and text.strip() else None,
        "content_state": content_state,
        "phase": phase,
        "task_name": task_name,
    }


def _text_parts(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
                continue
            if not isinstance(item, dict):
                continue
            item_type = str(item.get("type") or "").lower()
            if item_type in {
                "text",
                "input_text",
                "output_text",
                "text_delta",
                "message",
            }:
                text = item.get("text") or item.get("content")
                if isinstance(text, str) and text:
                    parts.append(text)
        return "\n".join(parts).strip()
    if isinstance(value, dict):
        for key in ("text", "content", "message", "output_text"):
            text = value.get(key)
            if isinstance(text, str) and text:
                return text.strip()
        content = value.get("content")
        if isinstance(content, list):
            return _text_parts(content)
    return ""


def _structured_messages(
    value: object,
    *,
    timestamp: object,
    ordinal: object,
    agent_path: str,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    if isinstance(value, dict):
        if isinstance(value.get("message"), dict):
            candidates.append(value["message"])
        elif any(key in value for key in ("role", "content", "text")):
            candidates.append(value)
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                if isinstance(item.get("message"), dict):
                    candidates.append(item["message"])
                elif any(key in item for key in ("role", "content", "text")):
                    candidates.append(item)

    messages: list[dict[str, Any]] = []
    for item in candidates:
        role = str(item.get("role") or "").lower()
        if role in {"system", "developer", "tool", "function"}:
            continue
        text = _text_parts(item.get("content")) or _text_parts(item.get("text"))
        if not text:
            continue
        if role in {"user", "human"}:
            messages.append(
                _message(
                    timestamp=timestamp,
                    ordinal=ordinal,
                    kind="user_message",
                    sender="user",
                    recipient=agent_path,
                    text=text,
                )
            )
        elif role in {"assistant", "model", "agent"}:
            messages.append(
                _message(
                    timestamp=timestamp,
                    ordinal=ordinal,
                    kind="assistant_message",
                    sender=agent_path,
                    recipient=None,
                    text=text,
                    phase="response",
                )
            )
    return messages


_ANTIGRAVITY_USER_REQUEST_RE = re.compile(
    r"<USER_REQUEST>\s*(?P<body>.*?)\s*</USER_REQUEST>",
    re.DOTALL,
)


def _antigravity_user_text(text: str) -> str:
    """Return the actual user request, excluding Antigravity's metadata envelope."""
    match = _ANTIGRAVITY_USER_REQUEST_RE.search(text)
    return match.group("body").strip() if match is not None else text.strip()


def _line_transcript_messages(
    path: Path,
    *,
    timestamp: object,
    ordinal: object,
    agent_path: str,
    antigravity: bool = False,
) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return []
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue

        if antigravity:
            role = str(record.get("source") or "").strip().lower()
            record_type = str(record.get("type") or "").strip().lower()
            text = _text_parts(record.get("content") or record.get("text"))
            record_timestamp = record.get("created_at") or record.get("timestamp") or timestamp
            step_index = record.get("step_index")
            record_ordinal = (
                step_index
                if isinstance(step_index, int) and not isinstance(step_index, bool)
                else (ordinal if isinstance(ordinal, int) else 0) + index
            )

            # Current Antigravity uses USER_EXPLICIT / USER_INPUT for real user turns.
            # Keep the older USER/HUMAN spelling for archived compatibility.
            if role in {"user_explicit", "user", "human"} and record_type in {
                "user_input",
                "user_message",
                "",
            }:
                if text:
                    messages.append(
                        _message(
                            timestamp=record_timestamp,
                            ordinal=record_ordinal,
                            kind="user_message",
                            sender="user",
                            recipient=agent_path,
                            text=_antigravity_user_text(text),
                        )
                    )
                continue

            # PLANNER_RESPONSE is Antigravity's user-visible model surface. GENERIC
            # records are tool/runtime results (define_subagent, manage_subagents,
            # schedule, send_message acknowledgements, ...), so they must never be
            # eligible for the conversation Final response card.
            if role in {"model", "assistant"} and record_type == "planner_response":
                if text:
                    messages.append(
                        _message(
                            timestamp=record_timestamp,
                            ordinal=record_ordinal,
                            kind="assistant_message",
                            sender=agent_path,
                            recipient=None,
                            text=text,
                            phase="planner_response",
                        )
                    )
                continue
            continue

        record_timestamp = record.get("timestamp") or timestamp
        record_ordinal = record.get("ordinal")
        if not isinstance(record_ordinal, int):
            record_ordinal = (ordinal if isinstance(ordinal, int) else 0) + index
        record_type = str(record.get("type") or "").lower()
        payload = record.get("message")
        if isinstance(payload, dict):
            role = str(payload.get("role") or record_type).lower()
            text = _text_parts(payload.get("content"))
        else:
            role = record_type
            text = _text_parts(record.get("content") or record.get("text"))
        if not text:
            continue
        if role in {"user", "human"}:
            messages.append(
                _message(
                    timestamp=record_timestamp,
                    ordinal=record_ordinal,
                    kind="user_message",
                    sender="user",
                    recipient=agent_path,
                    text=text,
                )
            )
        elif role in {"assistant", "model"}:
            messages.append(
                _message(
                    timestamp=record_timestamp,
                    ordinal=record_ordinal,
                    kind="assistant_message",
                    sender=agent_path,
                    recipient=None,
                    text=text,
                    phase="response",
                )
            )
    return messages


def _response_messages(
    value: object,
    *,
    timestamp: object,
    ordinal: object,
    agent_path: str,
) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        direct = value.get("message")
        if isinstance(direct, dict):
            messages = _structured_messages(
                direct,
                timestamp=timestamp,
                ordinal=ordinal,
                agent_path=agent_path,
            )
            if messages:
                return messages
        choices = value.get("choices")
        if isinstance(choices, list):
            nested = [
                choice.get("message")
                for choice in choices
                if isinstance(choice, dict) and isinstance(choice.get("message"), dict)
            ]
            messages = _structured_messages(
                nested,
                timestamp=timestamp,
                ordinal=ordinal,
                agent_path=agent_path,
            )
            if messages:
                return messages
        output = value.get("output")
        if isinstance(output, list):
            messages = _structured_messages(
                output,
                timestamp=timestamp,
                ordinal=ordinal,
                agent_path=agent_path,
            )
            if messages:
                return messages
        text = _text_parts(value.get("content"))
        if text:
            return [
                _message(
                    timestamp=timestamp,
                    ordinal=ordinal,
                    kind="assistant_message",
                    sender=agent_path,
                    recipient=None,
                    text=text,
                    phase="response",
                )
            ]
    text = _text_parts(value)
    if text:
        return [
            _message(
                timestamp=timestamp,
                ordinal=ordinal,
                kind="assistant_message",
                sender=agent_path,
                recipient=None,
                text=text,
                phase="response",
            )
        ]
    return []


def _routed_agent_message(
    value: object,
    *,
    timestamp: object,
    ordinal: object,
    agent_path: str,
) -> list[dict[str, Any]]:
    if not isinstance(value, dict):
        return []
    text = _text_parts(value.get("text") or value.get("content") or value.get("message"))
    if not text:
        return []
    sender = value.get("sender")
    recipient = value.get("recipient")
    kind = value.get("kind")
    phase = value.get("phase")
    task_name = value.get("task_name")
    content_state = value.get("content_state")
    return [
        _message(
            timestamp=timestamp,
            ordinal=ordinal,
            kind=kind if isinstance(kind, str) and kind else "agent_message",
            sender=sender if isinstance(sender, str) and sender else agent_path,
            recipient=recipient if isinstance(recipient, str) and recipient else None,
            text=text,
            phase=phase if isinstance(phase, str) and phase else None,
            task_name=task_name if isinstance(task_name, str) and task_name else None,
            content_state=(
                content_state
                if isinstance(content_state, str) and content_state
                else "plaintext"
            ),
        )
    ]


def _generic_content_messages(
    value: object,
    *,
    content_kind: str,
    timestamp: object,
    ordinal: object,
    identity: dict[str, Any],
) -> list[dict[str, Any]]:
    kind = content_kind.lower()
    agent_path = str(identity["agent_path"])

    if (
        "assistant_content_blocks" in kind
        or "response_object" in kind
        or "standard_logging_response" in kind
        or kind == "inference_gateway.openrouter.response"
    ):
        return _response_messages(
            value,
            timestamp=timestamp,
            ordinal=ordinal,
            agent_path=agent_path,
        )

    if "request_messages" in kind or "assistant_messages" in kind:
        structured = _structured_messages(
            value,
            timestamp=timestamp,
            ordinal=ordinal,
            agent_path=agent_path,
        )
        if structured:
            return structured

    if "request_input" in kind or "inference_message" in kind or "user_message_parts" in kind:
        structured = _structured_messages(
            value,
            timestamp=timestamp,
            ordinal=ordinal,
            agent_path=agent_path,
        )
        if structured:
            return structured

    if "agent_message" in kind:
        routed = _routed_agent_message(
            value,
            timestamp=timestamp,
            ordinal=ordinal,
            agent_path=agent_path,
        )
        if routed:
            return routed

    text = _text_parts(value)
    if not text:
        return []

    if any(token in kind for token in _USER_KINDS):
        return [
            _message(
                timestamp=timestamp,
                ordinal=ordinal,
                kind=(
                    "user_prompt_candidate"
                    if "prompt_submission_candidate" in kind
                    else "user_message"
                ),
                sender="user",
                recipient=agent_path,
                text=text,
            )
        ]

    if "agent_response_candidate" in kind:
        return [
            _message(
                timestamp=timestamp,
                ordinal=ordinal,
                kind="assistant_response_candidate",
                sender=agent_path,
                recipient=None,
                text=text,
                phase="candidate",
            )
        ]

    if any(token in kind for token in _ASSISTANT_FINAL_KINDS):
        child = not bool(identity.get("is_root"))
        return [
            _message(
                timestamp=timestamp,
                ordinal=ordinal,
                kind="subagent_final_response" if child else "assistant_message",
                sender=agent_path,
                recipient="/root" if child else None,
                text=text,
                phase="final_answer",
            )
        ]

    if any(token in kind for token in _ASSISTANT_RESPONSE_KINDS):
        return [
            _message(
                timestamp=timestamp,
                ordinal=ordinal,
                kind="assistant_message",
                sender=agent_path,
                recipient=None,
                text=text,
                phase="response",
            )
        ]

    if "agent_message" in kind:
        return [
            _message(
                timestamp=timestamp,
                ordinal=ordinal,
                kind="agent_message",
                sender=agent_path,
                recipient=None,
                text=text,
            )
        ]

    if any(token in kind for token in _SUBAGENT_TASK_KINDS):
        return [
            _message(
                timestamp=timestamp,
                ordinal=ordinal,
                kind="task",
                sender="/root",
                recipient=agent_path,
                text=text,
            )
        ]

    if any(token in kind for token in _SUBAGENT_SUMMARY_KINDS):
        return [
            _message(
                timestamp=timestamp,
                ordinal=ordinal,
                kind="assistant_summary",
                sender=agent_path,
                recipient="/root",
                text=text,
            )
        ]

    return []


def finish_transcript_preview(
    identity: dict[str, Any],
    messages: list[dict[str, Any]],
    *,
    preserve_history: bool = False,
) -> dict[str, Any] | None:
    if not messages:
        return None
    truncated = not preserve_history and len(messages) > _MAX_PREVIEW_MESSAGES
    if truncated:
        messages = messages[:10] + messages[-(_MAX_PREVIEW_MESSAGES - 10) :]
    return {
        **identity,
        "conversation_completeness": COMPLETENESS_PROVIDER_TRANSCRIPT,
        "message_count": len(messages),
        "messages_truncated": truncated,
        "messages": messages,
    }
