from __future__ import annotations

from pathlib import Path
from typing import Any

from .conversation_preview_common import (
    _agent_identity,
    _generic_content_messages,
    _read_value,
    finish_transcript_preview,
)


def conversation_preview(
    path: str | Path,
    *,
    content_kind: str,
    provider: str,
    source: dict[str, Any] | None,
    timestamp: object = None,
    ordinal: object = None,
) -> dict[str, Any] | None:
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
