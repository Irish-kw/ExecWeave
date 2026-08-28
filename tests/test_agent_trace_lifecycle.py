from __future__ import annotations

import pytest

from execweave.provider_lifecycle import provider_lifecycle_annotation


def _event(provider: str, relation: str) -> dict:
    return {
        "relation": relation,
        "source": {"type": "agent", "id": f"agent:{provider}", "attributes": {}},
        "target": {"type": "entity", "id": f"target:{relation}", "attributes": {}},
        "attributes": {"provider": provider, "backend": "semantic", "causal": False},
    }


@pytest.mark.parametrize(
    ("provider", "relation", "kind", "stage"),
    [
        ("codex", "SENT_AGENT_MESSAGE", "agent_message", "sent"),
        ("codex", "DELIVERED_AGENT_MESSAGE", "agent_message", "delivered"),
        ("opencode", "HAS_CHILD_AGENT_SESSION", "subagent", "child_session"),
        ("cursor", "PRODUCED_REASONING_TEXT", "reasoning", "provider_exposed_text"),
        ("codex", "STARTED_AGENT_TURN", "agent_turn", "started"),
        ("codex", "ISSUED_INFERENCE_IN_TURN", "agent_turn", "inference_issued"),
        ("codex", "OWNED_TERMINAL_SESSION", "terminal_session", "agent_owned"),
        ("codex", "HAS_TERMINAL_OPERATION", "terminal_session", "operation_observed"),
        ("codex", "INSTALLED_COMPACTION", "context_compaction", "installed"),
        ("codex", "HAS_COMPACTION_REQUEST_PAYLOAD", "context_compaction", "request_payload_observed"),
        ("claude", "OBSERVED_PROVIDER_SESSION_END", "provider_session", "ended"),
        ("claude", "OBSERVED_PROVIDER_SETUP", "provider_setup", "observed"),
        ("claude", "LOADED_INSTRUCTION_FILE", "instruction", "loaded"),
        ("claude", "OBSERVED_PROMPT_EXPANSION", "prompt_expansion", "observed"),
        ("claude", "OBSERVED_EXPANSION_PROMPT", "prompt_expansion", "prompt_observed"),
        ("claude", "OBSERVED_EXPANSION_ARGUMENTS", "prompt_expansion", "arguments_observed"),
        ("claude", "PERMISSION_DENIED_TOOL_CALL", "permission", "denied"),
        ("claude", "OBSERVED_PERMISSION_TOOL_INPUT", "permission", "tool_input_observed"),
        ("claude", "OBSERVED_DENIED_TOOL_INPUT", "permission", "denied_tool_input_observed"),
        ("claude", "OBSERVED_PERMISSION_DENIAL_REASON", "permission", "denial_reason_observed"),
        ("claude", "CREATED_AGENT_TASK", "agent_task", "created"),
        ("claude", "COMPLETED_AGENT_TASK", "agent_task", "completed"),
        ("claude", "HAS_TASK_SUBJECT", "agent_task", "subject_observed"),
        ("claude", "HAS_TASK_DESCRIPTION", "agent_task", "description_observed"),
        ("claude", "OBSERVED_TURN_STOP", "agent_turn", "stop_observed"),
        ("claude", "OBSERVED_TURN_FAILURE", "agent_turn", "failure_observed"),
        ("claude", "OBSERVED_BACKGROUND_TASKS", "agent_turn", "background_tasks_observed"),
        ("claude", "OBSERVED_SESSION_CRONS", "agent_turn", "session_crons_observed"),
        ("claude", "OBSERVED_TEAMMATE_IDLE", "teammate_state", "idle_observed"),
        ("claude", "OBSERVED_NOTIFICATION", "notification", "observed"),
        ("claude", "OBSERVED_NOTIFICATION_MESSAGE", "notification", "message_observed"),
        ("claude", "OBSERVED_NOTIFICATION_TITLE", "notification", "title_observed"),
        ("claude", "OBSERVED_CONFIG_CHANGE", "configuration", "changed"),
        ("claude", "CHANGED_WORKING_DIRECTORY", "working_directory", "changed"),
        ("claude", "ADDED_WORKING_DIRECTORY", "working_directory", "added"),
        ("claude", "OBSERVED_FILE_CHANGE", "file", "change_observed"),
        ("claude", "REMOVED_WORKTREE", "worktree", "removed"),
        ("claude", "OBSERVED_PRE_COMPACTION", "context_compaction", "pre_observed"),
        ("claude", "OBSERVED_COMPACTION_INSTRUCTIONS", "context_compaction", "instructions_observed"),
        ("claude", "OBSERVED_COMPACTION_SUMMARY", "context_compaction", "summary_observed"),
        ("claude", "OBSERVED_MCP_ELICITATION", "mcp_elicitation", "requested"),
        ("claude", "OBSERVED_MCP_ELICITATION_RESULT", "mcp_elicitation", "result_observed"),
        ("claude", "OBSERVED_ELICITATION_MESSAGE", "mcp_elicitation", "message_observed"),
        ("claude", "OBSERVED_ELICITATION_SCHEMA", "mcp_elicitation", "schema_observed"),
        ("claude", "OBSERVED_ELICITATION_URL", "mcp_elicitation", "url_observed"),
        ("claude", "OBSERVED_ELICITATION_CONTENT", "mcp_elicitation", "result_content_observed"),
    ],
)
def test_agent_trace_relations_have_cross_provider_lifecycle(
    provider: str,
    relation: str,
    kind: str,
    stage: str,
) -> None:
    annotation = provider_lifecycle_annotation(_event(provider, relation))
    assert annotation is not None
    assert annotation.to_dict() == {
        "schema_version": "0.1",
        "provider": provider,
        "kind": kind,
        "stage": stage,
        "evidence_semantics": "classification_only",
    }
