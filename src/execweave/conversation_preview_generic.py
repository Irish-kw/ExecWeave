from __future__ import annotations

from pathlib import Path
from typing import Any

from .agent_topology import COMPLETENESS_PROVIDER_TRANSCRIPT
from .conversation_preview_lines import _structured_messages
from .conversation_preview_transcript import (
    _ASSISTANT_FINAL_KINDS,
    _ASSISTANT_RESPONSE_KINDS,
    _MAX_PREVIEW_MESSAGES,
    _SUBAGENT_SUMMARY_KINDS,
    _SUBAGENT_TASK_KINDS,
    _USER_KINDS,
    _message,
    _text_parts,
)


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
            messages = _structured_messages(direct, timestamp=timestamp, ordinal=ordinal, agent_path=agent_path)
            if messages:
                return messages
        choices = value.get("choices")
        if isinstance(choices, list):
            nested = [choice.get("message") for choice in choices if isinstance(choice, dict) and isinstance(choice.get("message"), dict)]
            messages = _structured_messages(nested, timestamp=timestamp, ordinal=ordinal, agent_path=agent_path)
            if messages:
                return messages
        output = value.get("output")
        if isinstance(output, list):
            messages = _structured_messages(output, timestamp=timestamp, ordinal=ordinal, agent_path=agent_path)
            if messages:
                return messages
        text = _text_parts(value.get("content"))
        if text:
            return [_message(timestamp=timestamp, ordinal=ordinal, kind="assistant_message", sender=agent_path, recipient=None, text=text, phase="response")]
    text = _text_parts(value)
    if text:
        return [_message(timestamp=timestamp, ordinal=ordinal, kind="assistant_message", sender=agent_path, recipient=None, text=text, phase="response")]
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
    return [_message(
        timestamp=timestamp,
        ordinal=ordinal,
        kind=kind if isinstance(kind, str) and kind else "agent_message",
        sender=sender if isinstance(sender, str) and sender else agent_path,
        recipient=recipient if isinstance(recipient, str) and recipient else None,
        text=text,
        phase=phase if isinstance(phase, str) and phase else None,
        task_name=task_name if isinstance(task_name, str) and task_name else None,
        content_state=content_state if isinstance(content_state, str) and content_state else "plaintext",
    )]


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
    if "assistant_content_blocks" in kind or "response_object" in kind or "standard_logging_response" in kind or kind == "inference_gateway.openrouter.response":
        return _response_messages(value, timestamp=timestamp, ordinal=ordinal, agent_path=agent_path)
    if "request_messages" in kind or "assistant_messages" in kind or "request_input" in kind or "inference_message" in kind or "user_message_parts" in kind:
        structured = _structured_messages(value, timestamp=timestamp, ordinal=ordinal, agent_path=agent_path)
        if structured:
            return structured
    if "agent_message" in kind:
        routed = _routed_agent_message(value, timestamp=timestamp, ordinal=ordinal, agent_path=agent_path)
        if routed:
            return routed
    text = _text_parts(value)
    if not text:
        return []
    if any(token in kind for token in _USER_KINDS):
        return [_message(timestamp=timestamp, ordinal=ordinal, kind=("user_prompt_candidate" if "prompt_submission_candidate" in kind else "user_message"), sender="user", recipient=agent_path, text=text)]
    if "agent_response_candidate" in kind:
        return [_message(timestamp=timestamp, ordinal=ordinal, kind="assistant_response_candidate", sender=agent_path, recipient=None, text=text, phase="candidate")]
    if any(token in kind for token in _ASSISTANT_FINAL_KINDS):
        child = not bool(identity.get("is_root"))
        return [_message(timestamp=timestamp, ordinal=ordinal, kind="subagent_final_response" if child else "assistant_message", sender=agent_path, recipient="/root" if child else None, text=text, phase="final_answer")]
    if any(token in kind for token in _ASSISTANT_RESPONSE_KINDS):
        return [_message(timestamp=timestamp, ordinal=ordinal, kind="assistant_message", sender=agent_path, recipient=None, text=text, phase="response")]
    if "agent_message" in kind:
        return [_message(timestamp=timestamp, ordinal=ordinal, kind="agent_message", sender=agent_path, recipient=None, text=text)]
    if any(token in kind for token in _SUBAGENT_TASK_KINDS):
        return [_message(timestamp=timestamp, ordinal=ordinal, kind="task", sender="/root", recipient=agent_path, text=text)]
    if any(token in kind for token in _SUBAGENT_SUMMARY_KINDS):
        return [_message(timestamp=timestamp, ordinal=ordinal, kind="assistant_summary", sender=agent_path, recipient="/root", text=text)]
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


def conversation_preview(
    path: str | Path,
    *,
    content_kind: str,
    provider: str,
    source: dict[str, Any] | None,
    timestamp: object = None,
    ordinal: object = None,
) -> dict[str, Any] | None:
    from .conversation_preview_common import _agent_identity, _read_value

    source_path = Path(path).expanduser().resolve(strict=False)
    identity = _agent_identity(provider, source)
    value = _read_value(source_path)
    messages = _generic_content_messages(
        value,
        content_kind=content_kind,
        timestamp=timestamp,
        ordinal=ordinal,
        identity=identity,
    )
    return finish_transcript_preview(identity, messages, preserve_history=False)
