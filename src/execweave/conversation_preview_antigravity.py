from __future__ import annotations

from pathlib import Path
from typing import Any

from .conversation_preview_common import (
    _agent_identity,
    _line_transcript_messages,
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
    del content_kind
    source_path = Path(path).expanduser().resolve(strict=False)
    identity = _agent_identity(provider, source)
    messages = _line_transcript_messages(
        source_path,
        timestamp=timestamp,
        ordinal=ordinal,
        agent_path=str(identity["agent_path"]),
        antigravity=True,
    )
    return finish_transcript_preview(identity, messages, preserve_history=True)
