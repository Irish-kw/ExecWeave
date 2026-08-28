from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

GEMINI_HOOKS_REFERENCE = "https://geminicli.com/docs/hooks/reference/"

OFFICIAL_GEMINI_HOOK_EVENTS = frozenset(
    {
        "SessionStart",
        "SessionEnd",
        "BeforeAgent",
        "AfterAgent",
        "BeforeModel",
        "AfterModel",
        "BeforeToolSelection",
        "BeforeTool",
        "AfterTool",
        "PreCompress",
        "Notification",
    }
)

_ALREADY_PROJECTED_ELSEWHERE = frozenset({"SessionStart", "BeforeTool", "AfterTool"})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _entity(
    entity_type: str,
    entity_id: str,
    *,
    name: str | None = None,
    attributes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "type": entity_type,
        "id": entity_id,
        "name": name,
        "attributes": attributes or {},
    }


def _main_agent() -> dict[str, Any]:
    return _entity("agent", "agent:Gemini CLI", name="Gemini CLI")


def _session(payload: dict[str, Any]) -> dict[str, Any]:
    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        raise ValueError("Gemini official hook payload requires session_id")
    return _entity(
        "provider_session",
        f"provider-session:gemini:{session_id}",
        name=session_id,
        attributes={"provider": "gemini", "session_id": session_id},
    )


def _event(
    *,
    timestamp: str,
    event_type: str,
    relation: str,
    source: dict[str, Any],
    target: dict[str, Any],
    attributes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    merged: dict[str, Any] = {
        "backend": "semantic",
        "provider": "gemini",
        "evidence_source": "provider_hook",
        "attribution": "gemini_official_hook_contract",
        "causal": False,
        "inferred": False,
        "official_hook_contract": True,
        "official_hook_reference": GEMINI_HOOKS_REFERENCE,
    }
    if attributes:
        merged.update(attributes)
    return {
        "timestamp": timestamp,
        "event_type": event_type,
        "relation": relation,
        "source": source,
        "target": target,
        "attributes": merged,
    }


def _common(payload: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {"gemini_hook_event_name": payload.get("hook_event_name")}
    for key in ("session_id", "cwd"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            result[f"gemini_{key}"] = value
    return result


def _observation_id(payload: dict[str, Any], *, timestamp: str, phase: str) -> str:
    stable = {
        "session_id": payload.get("session_id"),
        "hook_event_name": payload.get("hook_event_name"),
        "timestamp": timestamp,
        "phase": phase,
    }
    raw = json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _observation(
    payload: dict[str, Any],
    *,
    timestamp: str,
    phase: str,
    entity_type: str,
    name: str,
    attributes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ident = _observation_id(payload, timestamp=timestamp, phase=phase)
    merged = {
        "provider": "gemini",
        "identity_semantics": "provider_hook_observation_without_stable_stage_id",
        "observation_phase": phase,
    }
    if attributes:
        merged.update(attributes)
    return _entity(
        entity_type,
        f"{entity_type}:gemini:{ident}",
        name=name,
        attributes=merged,
    )


def _llm_request(payload: dict[str, Any], hook_event: str) -> dict[str, Any]:
    request = payload.get("llm_request")
    if not isinstance(request, dict):
        raise ValueError(f"{hook_event} requires llm_request")
    return request


def _request_model(payload: dict[str, Any], hook_event: str) -> tuple[dict[str, Any], dict[str, Any]]:
    request = _llm_request(payload, hook_event)
    model_name = request.get("model")
    if not isinstance(model_name, str) or not model_name:
        raise ValueError(f"{hook_event} llm_request requires model")
    return request, _entity(
        "model",
        f"model:gemini:{model_name}",
        name=model_name,
        attributes={"provider": "gemini", "model": model_name},
    )


def _response_summary(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, Any] = {}
    candidates = value.get("candidates")
    if isinstance(candidates, list):
        result["candidate_count"] = len(candidates)
        finish_reasons = [
            candidate.get("finishReason")
            for candidate in candidates
            if isinstance(candidate, dict) and isinstance(candidate.get("finishReason"), str)
        ]
        if finish_reasons:
            result["finish_reasons"] = finish_reasons
    usage = value.get("usageMetadata")
    if isinstance(usage, dict):
        total = usage.get("totalTokenCount")
        if isinstance(total, int) and not isinstance(total, bool) and total >= 0:
            result["usage_total_token_count"] = total
    return result


def gemini_official_hook_semantic_events(
    payload: dict[str, Any],
    *,
    timestamp: str | None = None,
) -> list[dict[str, Any]]:
    """Project only semantics explicitly guaranteed by the current Gemini CLI hook contract."""

    hook_event = payload.get("hook_event_name")
    if not isinstance(hook_event, str) or not hook_event:
        raise ValueError("Gemini hook payload requires hook_event_name")
    if hook_event not in OFFICIAL_GEMINI_HOOK_EVENTS or hook_event in _ALREADY_PROJECTED_ELSEWHERE:
        return []

    provider_timestamp = payload.get("timestamp")
    observed_at = timestamp or (
        provider_timestamp if isinstance(provider_timestamp, str) and provider_timestamp else _now()
    )
    common = _common(payload)
    actor = _main_agent()

    if hook_event == "SessionEnd":
        reason = payload.get("reason")
        if reason not in {"exit", "clear", "logout", "prompt_input_exit", "other"}:
            raise ValueError("SessionEnd requires a documented reason")
        common.update(
            {
                "gemini_session_end_reason": reason,
                "best_effort_hook": True,
                "flow_control_ignored_by_provider": True,
            }
        )
        return [
            _event(
                timestamp=observed_at,
                event_type="semantic.gemini.session.ended",
                relation="OBSERVED_PROVIDER_SESSION_END",
                source=actor,
                target=_session(payload),
                attributes=common,
            )
        ]

    if hook_event == "BeforeAgent":
        prompt = payload.get("prompt")
        if not isinstance(prompt, str):
            raise ValueError("BeforeAgent requires prompt")
        common.update(
            {
                "prompt_stored_separately": True,
                "boundary_semantics": "after_user_prompt_before_agent_planning",
                "before_after_pairing_asserted": False,
            }
        )
        turn = _observation(
            payload,
            timestamp=observed_at,
            phase="before_agent",
            entity_type="agent_turn_observation",
            name="Gemini agent turn start observation",
        )
        return [
            _event(
                timestamp=observed_at,
                event_type="semantic.gemini.agent.turn_start_observed",
                relation="OBSERVED_AGENT_TURN_START",
                source=actor,
                target=turn,
                attributes=common,
            )
        ]

    if hook_event == "AfterAgent":
        prompt = payload.get("prompt")
        response = payload.get("prompt_response")
        if not isinstance(prompt, str) or not isinstance(response, str):
            raise ValueError("AfterAgent requires prompt and prompt_response")
        stop_hook_active = payload.get("stop_hook_active")
        common.update(
            {
                "prompt_stored_separately": True,
                "prompt_response_stored_separately": True,
                "stop_hook_active": bool(stop_hook_active),
                "boundary_semantics": "after_generated_turn_response_before_hook_acceptance",
                "response_can_be_rejected_and_retried_by_hook": True,
                "accepted_final_response_asserted": False,
                "before_after_pairing_asserted": False,
            }
        )
        turn = _observation(
            payload,
            timestamp=observed_at,
            phase="after_agent",
            entity_type="agent_turn_observation",
            name="Gemini agent turn end observation",
        )
        return [
            _event(
                timestamp=observed_at,
                event_type="semantic.gemini.agent.turn_end_observed",
                relation="OBSERVED_AGENT_TURN_END",
                source=actor,
                target=turn,
                attributes=common,
            )
        ]

    if hook_event == "BeforeModel":
        request, model = _request_model(payload, hook_event)
        config = request.get("config")
        common.update(
            {
                "request_stage": "before_model_hook",
                "actual_model_invocation_asserted": False,
                "request_can_be_blocked_rewritten_or_replaced_by_hook": True,
                "llm_request_stored_separately": True,
            }
        )
        if isinstance(config, dict):
            common["generation_config_keys"] = sorted(str(key) for key in config)
        return [
            _event(
                timestamp=observed_at,
                event_type="semantic.gemini.model.request_target_observed",
                relation="OBSERVED_MODEL_REQUEST_TARGET",
                source=actor,
                target=model,
                attributes=common,
            )
        ]

    if hook_event == "BeforeToolSelection":
        request, model = _request_model(payload, hook_event)
        tool_config = request.get("toolConfig")
        common.update(
            {
                "request_stage": "before_tool_selection_hook",
                "actual_model_invocation_asserted": False,
                "tool_selection_policy_can_be_rewritten_by_hook": True,
                "llm_request_stored_separately": True,
            }
        )
        if isinstance(tool_config, dict):
            mode = tool_config.get("mode")
            if isinstance(mode, str) and mode:
                common["tool_selection_mode"] = mode
            names = tool_config.get("allowedFunctionNames")
            if isinstance(names, list):
                common["allowed_function_count"] = len(names)
        return [
            _event(
                timestamp=observed_at,
                event_type="semantic.gemini.model.tool_selection_request_observed",
                relation="OBSERVED_TOOL_SELECTION_MODEL_REQUEST",
                source=actor,
                target=model,
                attributes=common,
            )
        ]

    if hook_event == "AfterModel":
        _request, model = _request_model(payload, hook_event)
        if "llm_response" not in payload:
            raise ValueError("AfterModel requires llm_response")
        common.update(
            {
                "streaming_chunk": True,
                "llm_request_stored_separately": True,
                "llm_response_stored_separately": True,
                "response_chunk_can_be_replaced_or_denied_by_hook": True,
            }
        )
        common.update(_response_summary(payload.get("llm_response")))
        chunk = _observation(
            payload,
            timestamp=observed_at,
            phase="after_model_chunk",
            entity_type="model_response_observation",
            name="Gemini model response chunk",
            attributes={"streaming_chunk": True},
        )
        return [
            _event(
                timestamp=observed_at,
                event_type="semantic.gemini.model.response_chunk_observed",
                relation="OBSERVED_MODEL_RESPONSE_CHUNK",
                source=model,
                target=chunk,
                attributes=common,
            )
        ]

    if hook_event == "Notification":
        notification_type = payload.get("notification_type")
        if notification_type != "ToolPermission":
            raise ValueError("Notification requires documented notification_type ToolPermission")
        message = payload.get("message")
        details = payload.get("details")
        if not isinstance(message, str):
            raise ValueError("Notification requires message")
        common.update(
            {
                "notification_type": notification_type,
                "message_preserved_in_full_fidelity_metadata": True,
                "observability_only": True,
                "flow_control_ignored_by_provider": True,
            }
        )
        if isinstance(details, dict):
            common["notification_detail_keys"] = sorted(str(key) for key in details)
        notification = _observation(
            payload,
            timestamp=observed_at,
            phase="notification",
            entity_type="provider_notification",
            name="Gemini tool permission notification",
        )
        return [
            _event(
                timestamp=observed_at,
                event_type="semantic.gemini.notification.observed",
                relation="OBSERVED_NOTIFICATION",
                source=actor,
                target=notification,
                attributes=common,
            )
        ]

    if hook_event == "PreCompress":
        trigger = payload.get("trigger")
        if trigger not in {"auto", "manual"}:
            raise ValueError("PreCompress requires trigger auto or manual")
        common.update(
            {
                "compaction_trigger": trigger,
                "pre_post_pairing_asserted": False,
                "advisory_only": True,
                "async_hook": True,
                "compression_can_be_blocked_or_modified_by_hook": False,
            }
        )
        compression = _observation(
            payload,
            timestamp=observed_at,
            phase="pre_compress",
            entity_type="context_compaction",
            name="Gemini pre-compression observation",
            attributes={"trigger": trigger},
        )
        return [
            _event(
                timestamp=observed_at,
                event_type="semantic.gemini.compaction.pre",
                relation="OBSERVED_PRE_COMPACTION",
                source=actor,
                target=compression,
                attributes=common,
            )
        ]

    return []
