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
