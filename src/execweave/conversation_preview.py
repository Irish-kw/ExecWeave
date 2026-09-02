from __future__ import annotations

from pathlib import Path
from typing import Any

from .conversation_preview_antigravity import (
    conversation_preview as _antigravity_conversation_preview,
)
from .conversation_preview_claude import conversation_preview as _claude_conversation_preview
from .conversation_preview_codex import _codex_preview
from .conversation_preview_codex import conversation_preview as _codex_conversation_preview
from .conversation_preview_common import (  # noqa: F401
    _ANTIGRAVITY_USER_REQUEST_RE,
    _ASSISTANT_FINAL_KINDS,
    _ASSISTANT_RESPONSE_KINDS,
    _MAX_PREVIEW_MESSAGES,
    _MAX_PREVIEW_TEXT_CHARS,
    _PROVIDER_LABELS,
    _SUBAGENT_SUMMARY_KINDS,
    _SUBAGENT_TASK_KINDS,
    _USER_KINDS,
    _agent_identity,
    _antigravity_user_text,
    _generic_content_messages,
    _line_transcript_messages,
    _message,
    _provider_label,
    _read_value,
    _response_messages,
    _routed_agent_message,
    _source_attributes,
    _structured_messages,
    _text_parts,
    _trim_text,
    finish_transcript_preview,
)
from .conversation_preview_generic import conversation_preview as _generic_conversation_preview


def conversation_preview(
    path: str | Path,
    *,
    content_kind: str,
    provider: str,
    source: dict[str, Any] | None,
    timestamp: object = None,
    ordinal: object = None,
) -> dict[str, Any] | None:
    """Project provider-exposed run-local evidence into one dashboard conversation schema."""
    kwargs = {
        "content_kind": content_kind,
        "provider": provider,
        "source": source,
        "timestamp": timestamp,
        "ordinal": ordinal,
    }
    if content_kind.startswith("codex.conversation_transcript"):
        return _codex_conversation_preview(path, **kwargs)
    if content_kind.startswith("claude.conversation_transcript"):
        return _claude_conversation_preview(path, **kwargs)
    if content_kind.startswith("antigravity.conversation_transcript"):
        return _antigravity_conversation_preview(path, **kwargs)
    return _generic_conversation_preview(path, **kwargs)


__all__ = ["conversation_preview", "_codex_preview"]
