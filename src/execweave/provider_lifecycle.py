from __future__ import annotations

from dataclasses import dataclass
from typing import Any

LIFECYCLE_SCHEMA_VERSION = "0.1"
SUPPORTED_PROVIDER_LIFECYCLES = frozenset({"claude", "codex", "gemini", "cursor", "opencode"})


@dataclass(frozen=True, order=True)
class ProviderLifecycleAnnotation:
    provider: str
    kind: str
    stage: str

    def to_dict(self) -> dict[str, str]:
        return {
            "schema_version": LIFECYCLE_SCHEMA_VERSION,
            "provider": self.provider,
            "kind": self.kind,
            "stage": self.stage,
            "evidence_semantics": "classification_only",
        }


_RELATION_MAP: dict[str, tuple[str, str]] = {
    # Session / model lifecycle.
    "STARTED_PROVIDER_SESSION": ("provider_session", "started"),
    "USED_MODEL": ("model", "selected"),
    "SERVED_BY_MODEL": ("model", "served"),
    "SWITCHED_MODEL": ("model", "runtime_transition"),
    # Prompt / inference request surfaces.
    "RECEIVED_USER_PROMPT": ("prompt", "received"),
    "OBSERVED_CHAT_MESSAGE": ("prompt", "observed_message"),
    "OBSERVED_CHAT_MESSAGE_PARTS": ("prompt", "observed_parts"),
    "OBSERVED_INFERENCE_MESSAGE": ("inference_request", "message_observed"),
    "OBSERVED_INFERENCE_PARAMETERS": ("inference_request", "parameters_observed"),
    "OBSERVED_REQUEST_HEADERS": ("inference_request", "headers_observed"),
    "OBSERVED_MODEL_CONTEXT": ("inference_request", "model_context_observed"),
    "OBSERVED_SYSTEM_PROMPT": ("inference_request", "system_prompt_observed"),
    # Assistant output. Returned/displayed text is classified without implying hidden state.
    "RECEIVED_LLM_RESPONSE_CHUNK": ("assistant_response", "stream_chunk"),
    "PRODUCED_ASSISTANT_RESPONSE": ("assistant_response", "final"),
    "PRODUCED_ASSISTANT_TEXT": ("assistant_response", "final"),
    "OBSERVED_AGENT_THOUGHT": ("assistant_thought", "provider_labeled_observed"),
    # Tool definition / selection / lifecycle.
    "EXPOSES_TOOL": ("tool_definition", "exposed"),
    "OBSERVED_TOOL_DESCRIPTION": ("tool_definition", "description_observed"),
    "OBSERVED_TOOL_SCHEMA": ("tool_definition", "schema_observed"),
    "REQUESTED_TOOL_CALL": ("tool_call", "requested"),
    "USES_TOOL": ("tool_call", "tool_selected"),
    "HAS_TOOL_INPUT": ("tool_call", "input_observed"),
    "OBSERVED_TOOL_INPUT": ("tool_call", "input_observed"),
    "HAS_TOOL_OUTPUT": ("tool_call", "output_observed"),
    "RECEIVED_TOOL_OUTPUT": ("tool_call", "output_observed"),
    "MODEL_RECEIVED_TOOL_RESULT": ("tool_call", "model_visible_result_observed"),
    "RECEIVED_TOOL_ERROR": ("tool_call", "error_observed"),
    "TOOL_CALL_SUCCEEDED": ("tool_call", "succeeded"),
    "TOOL_CALL_RETURNED": ("tool_call", "returned"),
    "TOOL_CALL_FAILED": ("tool_call", "failed"),
    "TOOL_RESULT_RETURNED": ("tool_result", "returned"),
    "TOOL_RESULT_REPORTED_ERROR": ("tool_result", "provider_reported_error"),
    "REQUESTED_PERMISSION_FOR_TOOL_INPUT": ("permission", "requested"),
    "OBSERVED_PERMISSION_REQUEST": ("permission", "requested"),
    # Shell lifecycle. Observing a command before/after does not assert command success.
    "DECLARED_COMMAND": ("shell_command", "declared"),
    "OBSERVED_SHELL_COMMAND_BEFORE_EXECUTION": ("shell_command", "before_execution"),
    "OBSERVED_SHELL_COMMAND_AFTER_EXECUTION": ("shell_command", "after_execution"),
    "RECEIVED_SHELL_OUTPUT": ("shell_command", "output_observed"),
    "OBSERVED_COMMAND": ("shell_command", "observed"),
    "OBSERVED_COMMAND_ARGUMENTS": ("shell_command", "arguments_observed"),
    "OBSERVED_COMMAND_PARTS": ("shell_command", "parts_observed"),
    # MCP lifecycle. Provider hooks may expose tool/server content without proving OS causality.
    "VIA_MCP": ("mcp", "invoked"),
    "OBSERVED_MCP_SERVER_COMMAND": ("mcp", "server_command_observed"),
    "OBSERVED_MCP_TOOL_INPUT": ("mcp", "tool_input_observed"),
    "RECEIVED_MCP_TOOL_RESULT": ("mcp", "tool_result_observed"),
    # File lifecycle. These stages deliberately stop short of claiming completion.
    "OBSERVED_FILE_CONTENT_BEFORE_READ": ("file_read", "pre_read_content_observed"),
    "OBSERVED_FILE_EDITS": ("file_write", "edits_observed"),
    # Subagent/task lifecycle. Observation-only stages are distinct from linked start/stop events.
    "SPAWNED_SUBAGENT": ("subagent", "started"),
    "RETURNED_TO": ("subagent", "returned"),
    "OBSERVED_SUBAGENT_TASK": ("subagent", "task_observed"),
    "OBSERVED_SUBAGENT_DESCRIPTION": ("subagent", "description_observed"),
    "RECEIVED_SUBAGENT_SUMMARY": ("subagent", "summary_observed"),
    # Provider/plugin lifecycle surfaces.
    "OBSERVED_PROVIDER_METADATA": ("provider_metadata", "observed"),
    "OBSERVED_PROVIDER_EVENT": ("provider_event", "observed"),
    "OBSERVED_COMPACTION_CONTEXT": ("context_compaction", "context_observed"),
    "OBSERVED_COMPACTION_PROMPT": ("context_compaction", "prompt_observed"),
}


_FILE_READ_TOOLS = frozenset({"read", "read_file"})
_FILE_WRITE_TOOLS = frozenset(
    {"edit", "write", "notebookedit", "write_file", "replace", "apply_patch"}
)
_FILE_DELETE_TOOLS = frozenset({"delete", "delete_file", "remove", "unlink"})


def _provider(event: dict[str, Any]) -> str | None:
    attributes = event.get("attributes")
    if not isinstance(attributes, dict):
        return None
    value = attributes.get("provider")
    if not isinstance(value, str):
        return None
    provider = value.strip().lower()
    return provider if provider in SUPPORTED_PROVIDER_LIFECYCLES else None


def _declared_file_stage(event: dict[str, Any]) -> str | None:
    target = event.get("target")
    if not isinstance(target, dict) or target.get("type") != "file":
        return None
    source = event.get("source")
    source_attributes = source.get("attributes") if isinstance(source, dict) else None
    tool_name = source_attributes.get("tool_name") if isinstance(source_attributes, dict) else None
    if not isinstance(tool_name, str) or not tool_name:
        source_name = source.get("name") if isinstance(source, dict) else None
        tool_name = source_name if isinstance(source_name, str) else ""
    normalized = tool_name.strip().lower().replace("-", "_")
    if normalized in _FILE_READ_TOOLS:
        return "declared_read"
    if normalized in _FILE_WRITE_TOOLS:
        return "declared_write"
    if normalized in _FILE_DELETE_TOOLS:
        return "declared_delete"
    return "declared_target"


def provider_lifecycle_annotation(
    event: dict[str, Any],
) -> ProviderLifecycleAnnotation | None:
    """Classify provider evidence for cross-provider graph queries.

    This function only classifies an already-observed provider event. It never
    creates evidence, raises causal strength, links observations by timing, or
    turns a declared/returned value into proof of successful execution.
    """
    provider = _provider(event)
    if provider is None:
        return None
    relation = event.get("relation")
    if not isinstance(relation, str) or not relation:
        return None
    if relation == "DECLARED_TARGET":
        stage = _declared_file_stage(event)
        return (
            ProviderLifecycleAnnotation(provider, "file", stage)
            if stage is not None
            else None
        )
    if relation == "DISPLAYED_ASSISTANT_TEXT":
        attributes = event.get("attributes")
        final = attributes.get("final") if isinstance(attributes, dict) else None
        return ProviderLifecycleAnnotation(
            provider,
            "assistant_response",
            "final_display" if final is True else "display_chunk",
        )
    mapped = _RELATION_MAP.get(relation)
    if mapped is None:
        return None
    kind, stage = mapped
    return ProviderLifecycleAnnotation(provider, kind, stage)
