from __future__ import annotations

from dataclasses import dataclass
from typing import Any

LIFECYCLE_SCHEMA_VERSION = "0.1"
SUPPORTED_PROVIDER_LIFECYCLES = frozenset(
    {"claude", "codex", "gemini", "antigravity", "cursor", "opencode"}
)


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
    "STARTED_PROVIDER_SESSION": ("provider_session", "started"),
    "OBSERVED_PROVIDER_SESSION_END": ("provider_session", "ended"),
    "OBSERVED_PROVIDER_SETUP": ("provider_setup", "observed"),
    "STARTED_AGENT_SESSION": ("agent_session", "started"),
    "HAS_CHILD_AGENT_SESSION": ("subagent", "child_session"),
    "HAS_AGENT_THREAD": ("subagent", "thread_observed"),
    "SPAWNED_AGENT": ("subagent", "started"),
    "ASSIGNED_AGENT_TASK": ("subagent", "task_assigned"),
    "CREATED_AGENT_TASK": ("agent_task", "created"),
    "COMPLETED_AGENT_TASK": ("agent_task", "completed"),
    "HAS_TASK_SUBJECT": ("agent_task", "subject_observed"),
    "HAS_TASK_DESCRIPTION": ("agent_task", "description_observed"),
    "SENT_AGENT_MESSAGE": ("agent_message", "sent"),
    "DELIVERED_AGENT_MESSAGE": ("agent_message", "delivered"),
    "CONSUMED_AGENT_MESSAGE": ("agent_message", "consumed"),
    "INCLUDED_AGENT_MESSAGE_IN_INFERENCE": ("agent_message", "included_in_inference"),
    "HAS_AGENT_MESSAGE_PAYLOAD": ("agent_message", "payload_observed"),
    "RETURNED_AGENT_RESULT": ("subagent", "result_returned"),
    "CLOSED_AGENT": ("subagent", "closed"),
    "SUBAGENT_STOPPED": ("subagent", "stopped"),
    "STARTED_AGENT_TURN": ("agent_turn", "started"),
    "TRIGGERED_AGENT_TURN": ("agent_turn", "triggered"),
    "OBSERVED_IN_AGENT_TURN": ("agent_turn", "item_observed"),
    "ISSUED_INFERENCE_IN_TURN": ("agent_turn", "inference_issued"),
    "STARTED_TOOL_CALL_IN_TURN": ("agent_turn", "tool_call_started"),
    "EXECUTED_CODE_CELL_IN_TURN": ("agent_turn", "code_cell_executed"),
    "OBSERVED_TURN_STOP": ("agent_turn", "stop_observed"),
    "OBSERVED_TURN_FAILURE": ("agent_turn", "failure_observed"),
    "OBSERVED_BACKGROUND_TASKS": ("agent_turn", "background_tasks_observed"),
    "OBSERVED_SESSION_CRONS": ("agent_turn", "session_crons_observed"),
    "OBSERVED_AGENT_TURN_START": ("agent_turn", "start_observed"),
    "OBSERVED_AGENT_TURN_END": ("agent_turn", "end_observed"),
    "USED_MODEL": ("model", "selected"),
    "INVOKES_MODEL": ("model", "invocation_requested"),
    "MODEL_INVOCATION_COMPLETED": ("model", "invocation_completed"),
    "SERVED_BY_MODEL": ("model", "served"),
    "SWITCHED_MODEL": ("model", "runtime_transition"),
    "OBSERVED_MODEL_REQUEST_TARGET": ("model", "request_target_observed"),
    "OBSERVED_TOOL_SELECTION_MODEL_REQUEST": ("model", "tool_selection_request_observed"),
    "OBSERVED_MODEL_RESPONSE_CHUNK": ("assistant_response", "model_stream_chunk_observed"),
    "RECEIVED_USER_PROMPT": ("prompt", "received"),
    "DELIVERED_USER_MESSAGE": ("prompt", "delivered"),
    "OBSERVED_CHAT_MESSAGE": ("prompt", "observed_message"),
    "OBSERVED_CHAT_MESSAGE_PARTS": ("prompt", "observed_parts"),
    "OBSERVED_AGENT_PROMPT": ("prompt", "observed"),
    "OBSERVED_PROMPT_EXPANSION": ("prompt_expansion", "observed"),
    "OBSERVED_EXPANSION_PROMPT": ("prompt_expansion", "prompt_observed"),
    "OBSERVED_EXPANSION_ARGUMENTS": ("prompt_expansion", "arguments_observed"),
    "OBSERVED_INFERENCE_MESSAGE": ("inference_request", "message_observed"),
    "OBSERVED_INFERENCE_PARAMETERS": ("inference_request", "parameters_observed"),
    "OBSERVED_REQUEST_HEADERS": ("inference_request", "headers_observed"),
    "OBSERVED_MODEL_CONTEXT": ("inference_request", "model_context_observed"),
    "OBSERVED_SYSTEM_PROMPT": ("inference_request", "system_prompt_observed"),
    "OBSERVED_LLM_REQUEST_BEFORE_MODEL": ("inference_request", "before_model_observed"),
    "OBSERVED_LLM_REQUEST_BEFORE_TOOL_SELECTION": (
        "inference_request",
        "before_tool_selection_observed",
    ),
    "OBSERVED_LLM_REQUEST_FOR_RESPONSE": ("inference_request", "response_request_observed"),
    "RECEIVED_LLM_RESPONSE_CHUNK": ("assistant_response", "stream_chunk"),
    "OBSERVED_AGENT_RESPONSE_CANDIDATE": ("assistant_response", "turn_candidate_observed"),
    "PRODUCED_ASSISTANT_RESPONSE": ("assistant_response", "final"),
    "PRODUCED_ASSISTANT_TEXT": ("assistant_response", "final"),
    "PRODUCED_ASSISTANT_MESSAGE": ("assistant_response", "message"),
    "OBSERVED_AGENT_THOUGHT": ("assistant_thought", "provider_labeled_observed"),
    "PRODUCED_REASONING_TEXT": ("reasoning", "provider_exposed_text"),
    "PRODUCED_REASONING_SUMMARY": ("reasoning", "provider_exposed_summary"),
    "PRODUCED_ENCODED_REASONING": ("reasoning", "provider_exposed_encoded"),
    "COMPLETED_AGENT_STEP": ("assistant_response", "step_completed"),
    "EXPOSES_TOOL": ("tool_definition", "exposed"),
    "OBSERVED_TOOL_DESCRIPTION": ("tool_definition", "description_observed"),
    "OBSERVED_TOOL_SCHEMA": ("tool_definition", "schema_observed"),
    "REQUESTED_TOOL_CALL": ("tool_call", "requested"),
    "OWNED_TOOL_CALL": ("tool_call", "agent_owned"),
    "OBSERVED_TOOL_CALL": ("tool_call", "observed"),
    "USES_TOOL": ("tool_call", "tool_selected"),
    "HAS_TOOL_INPUT": ("tool_call", "input_observed"),
    "OBSERVED_TOOL_INPUT": ("tool_call", "input_observed"),
    "OBSERVED_TOOL_INPUT_BEFORE_EXECUTION": ("tool_call", "input_observed_before_execution"),
    "OBSERVED_TOOL_INPUT_AFTER_EXECUTION": ("tool_call", "input_observed_after_execution"),
    "OBSERVED_TOOL_INPUT_FROM_PROVIDER_EVENT": ("tool_call", "event_input_observed"),
    "HAS_TOOL_OUTPUT": ("tool_call", "output_observed"),
    "RECEIVED_TOOL_OUTPUT": ("tool_call", "output_observed"),
    "RECEIVED_TOOL_OUTPUT_FROM_PROVIDER_EVENT": ("tool_call", "event_output_observed"),
    "MODEL_RECEIVED_TOOL_RESULT": ("tool_call", "model_visible_result_observed"),
    "RECEIVED_TOOL_ERROR": ("tool_call", "error_observed"),
    "OBSERVED_TOOL_ERROR": ("tool_call", "error_observed"),
    "RECEIVED_TOOL_ERROR_FROM_PROVIDER_EVENT": ("tool_call", "event_error_observed"),
    "TOOL_CALL_SUCCEEDED": ("tool_call", "succeeded"),
    "TOOL_CALL_RETURNED": ("tool_call", "returned"),
    "TOOL_CALL_FAILED": ("tool_call", "failed"),
    "TOOL_RESULT_RETURNED": ("tool_result", "returned"),
    "TOOL_RESULT_REPORTED_ERROR": ("tool_result", "provider_reported_error"),
    "REQUESTED_PERMISSION_FOR_TOOL_INPUT": ("permission", "requested"),
    "OBSERVED_PERMISSION_REQUEST": ("permission", "requested"),
    "PERMISSION_DENIED_TOOL_CALL": ("permission", "denied"),
    "OBSERVED_PERMISSION_TOOL_INPUT": ("permission", "tool_input_observed"),
    "OBSERVED_DENIED_TOOL_INPUT": ("permission", "denied_tool_input_observed"),
    "OBSERVED_PERMISSION_DENIAL_REASON": ("permission", "denial_reason_observed"),
    "DECLARED_COMMAND": ("shell_command", "declared"),
    "OWNED_AGENT_OPERATION": ("agent_operation", "agent_owned"),
    "OWNED_TERMINAL_SESSION": ("terminal_session", "agent_owned"),
    "CREATED_TERMINAL_SESSION": ("terminal_session", "created"),
    "HAS_TERMINAL_OPERATION": ("terminal_session", "operation_observed"),
    "OBSERVED_SHELL_COMMAND_BEFORE_EXECUTION": ("shell_command", "before_execution"),
    "OBSERVED_SHELL_COMMAND_AFTER_EXECUTION": ("shell_command", "after_execution"),
    "RECEIVED_SHELL_OUTPUT": ("shell_command", "output_observed"),
    "OBSERVED_COMMAND": ("shell_command", "observed"),
    "OBSERVED_COMMAND_ARGUMENTS": ("shell_command", "arguments_observed"),
    "OBSERVED_COMMAND_PARTS": ("shell_command", "parts_observed"),
    "VIA_MCP": ("mcp", "invoked"),
    "OBSERVED_MCP_SERVER_COMMAND": ("mcp", "server_command_observed"),
    "OBSERVED_MCP_TOOL_INPUT": ("mcp", "tool_input_observed"),
    "RECEIVED_MCP_TOOL_RESULT": ("mcp", "tool_result_observed"),
    "OBSERVED_MCP_ELICITATION": ("mcp_elicitation", "requested"),
    "OBSERVED_MCP_ELICITATION_RESULT": ("mcp_elicitation", "result_observed"),
    "OBSERVED_ELICITATION_MESSAGE": ("mcp_elicitation", "message_observed"),
    "OBSERVED_ELICITATION_SCHEMA": ("mcp_elicitation", "schema_observed"),
    "OBSERVED_ELICITATION_URL": ("mcp_elicitation", "url_observed"),
    "OBSERVED_ELICITATION_CONTENT": ("mcp_elicitation", "result_content_observed"),
    "OBSERVED_FILE_CONTENT_BEFORE_READ": ("file_read", "pre_read_content_observed"),
    "OBSERVED_FILE_EDITS": ("file_write", "edits_observed"),
    "OBSERVED_FILE_CHANGE": ("file", "change_observed"),
    "LOADED_INSTRUCTION_FILE": ("instruction", "loaded"),
    "SPAWNED_SUBAGENT": ("subagent", "started"),
    "RETURNED_TO": ("subagent", "returned"),
    "REQUESTED_SUBTASK": ("subagent", "task_requested"),
    "TARGETS_AGENT_PROFILE": ("subagent", "target_profile"),
    "USED_AGENT_PROFILE": ("subagent", "agent_profile"),
    "HAS_SUBTASK_PROMPT": ("subagent", "task_prompt_observed"),
    "HAS_SUBTASK_DESCRIPTION": ("subagent", "task_description_observed"),
    "OBSERVED_SUBAGENT_TASK": ("subagent", "task_observed"),
    "OBSERVED_SUBAGENT_DESCRIPTION": ("subagent", "description_observed"),
    "RECEIVED_SUBAGENT_SUMMARY": ("subagent", "summary_observed"),
    "OBSERVED_TEAMMATE_IDLE": ("teammate_state", "idle_observed"),
    "DECLARES_AGENT_TRACE_VISIBILITY": ("agent_trace_capability", "declared"),
    "OBSERVED_PROVIDER_METADATA": ("provider_metadata", "observed"),
    "OBSERVED_PROVIDER_EVENT": ("provider_event", "observed"),
    "OBSERVED_NOTIFICATION": ("notification", "observed"),
    "OBSERVED_NOTIFICATION_MESSAGE": ("notification", "message_observed"),
    "OBSERVED_NOTIFICATION_TITLE": ("notification", "title_observed"),
    "OBSERVED_CONFIG_CHANGE": ("configuration", "changed"),
    "CHANGED_WORKING_DIRECTORY": ("working_directory", "changed"),
    "ADDED_WORKING_DIRECTORY": ("working_directory", "added"),
    "REMOVED_WORKTREE": ("worktree", "removed"),
    "OBSERVED_COMPACTION_CONTEXT": ("context_compaction", "context_observed"),
    "OBSERVED_COMPACTION_PROMPT": ("context_compaction", "prompt_observed"),
    "OBSERVED_PRE_COMPACTION": ("context_compaction", "pre_observed"),
    "COMPACTED_CONTEXT": ("context_compaction", "completed"),
    "OBSERVED_COMPACTION_INSTRUCTIONS": ("context_compaction", "instructions_observed"),
    "OBSERVED_COMPACTION_SUMMARY": ("context_compaction", "summary_observed"),
    "INSTALLED_COMPACTION": ("context_compaction", "installed"),
    "INSTALLED_COMPACTION_IN_TURN": ("context_compaction", "installed_in_turn"),
    "MARKED_BY_CONVERSATION_ITEM": ("context_compaction", "marker_observed"),
    "INPUT_TO_COMPACTION": ("context_compaction", "input_observed"),
    "INSTALLED_REPLACEMENT_ITEM": ("context_compaction", "replacement_installed"),
    "COMPUTED_BY_COMPACTION_REQUEST": ("context_compaction", "request_linked"),
    "MADE_COMPACTION_REQUEST": ("context_compaction", "request_made"),
    "REQUESTED_COMPACTION_IN_TURN": ("context_compaction", "requested_in_turn"),
    "HAS_COMPACTION_REQUEST_PAYLOAD": ("context_compaction", "request_payload_observed"),
    "HAS_COMPACTION_RESPONSE_PAYLOAD": ("context_compaction", "response_payload_observed"),
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
