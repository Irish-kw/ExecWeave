"""Opt-in native OpenAI Agents SDK trace bridge.

Consumes SDK tracing callbacks, not HTTP traffic or inferred OS effects.
The module remains importable without the optional openai-agents package.
"""
from __future__ import annotations

import hashlib
import threading
from collections import Counter
from typing import Any

from .framework_adapters.base import (
    AdapterContext, AgentRecord, ContentCapturePolicy, MessageRecord,
    TaskRecord,
    ModelCallRecord, ToolCallRecord,
)

try:
    from agents.tracing import TracingProcessor
except ImportError:  # Optional dependency: pip install execweave[agents]
    TracingProcessor = object

_BLOCKED = frozenset({
    "authorization", "api_key", "apikey", "password", "token",
    "access_token", "refresh_token", "client_secret", "cookie",
    "reasoning", "chain_of_thought", "hidden_reasoning", "private_reasoning",
})


def _safe(value: Any, depth: int = 0) -> Any:
    """Serialize explicitly exposed content with bounded depth/size.

    Keys suggesting credentials or hidden reasoning are never retained.
    Arbitrary object repr() and exception messages are never stored.
    """
    if depth > 6:
        return "[depth limit]"
    if value is None or type(value) in (bool, int, float):
        return value
    if isinstance(value, str):
        return value[:32768]
    if isinstance(value, (tuple, list)):
        return [_safe(item, depth + 1) for item in value[:100]]
    if isinstance(value, dict):
        if value.get("type") in {"reasoning", "chain_of_thought", "hidden_reasoning"}:
            return "[reasoning omitted]"
        return {
            str(k)[:128]: _safe(v, depth + 1)
            for k, v in list(value.items())[:100]
            if str(k).lower().replace("-", "_") not in _BLOCKED
        }
    if hasattr(value, "model_dump"):
        try:
            return _safe(value.model_dump(mode="json"), depth + 1)
        except (AttributeError, TypeError, ValueError):
            return "[unserializable SDK value]"
    return "[unsupported content type]"


def _name(value: Any, default: str) -> str:
    return value[:160] if isinstance(value, str) and value.strip() else default


class AgentsSDKTraceProcessor(TracingProcessor):
    """Synchronous SDK processor producing run-bound canonical evidence.

    No recorder is enabled unless ExecWeave supplied both session and sidecar.
    A function-tool result is framework-reported and *not* proof of an OS effect.
    """

    def __init__(self, *, capture_mode: str = "metadata_only") -> None:
        import os

        ContentCapturePolicy(capture_mode)
        self.enabled = bool(
            os.environ.get("EXECWEAVE_SESSION_ID")
            and os.environ.get("EXECWEAVE_SEMANTIC_SIDECAR")
        )
        self.context = (
            AdapterContext.from_environment("openai-agents-sdk", capture_mode=capture_mode)
            if self.enabled else None
        )
        self.capture_mode = capture_mode
        self.callback_errors = 0
        self._lock = threading.RLock()
        self._runs: dict[str, dict[str, Any]] = {}

    def _state(self, trace_id: str) -> dict[str, Any]:
        return self._runs.setdefault(trace_id, {
            "owners": {}, "parents": {}, "models": {}, "model_input_at_start": {},
            "tasks": {}, "seen": set(),
            "started": set(), "ended": set(), "counts": Counter(),
            "unattributed": 0,
        })

    @staticmethod
    def _owner_from_ancestors(state: dict[str, Any], parent_id: str | None):
        """Find the nearest SDK-observed agent through intermediate task/turn spans.

        An unobserved parent stays unattributed; names in turn metadata are not
        silently promoted into authoritative agent identities.
        """
        cursor = parent_id
        seen: set[str] = set()
        while cursor is not None and cursor not in seen:
            seen.add(cursor)
            owner = state["owners"].get(cursor)
            if owner is not None:
                return owner
            cursor = state["parents"].get(cursor)
        return None

    def _agent(self, trace_id: str, agent_name: str):
        assert self.context is not None
        return self.context.entity(
            "agent", f"{trace_id}:{agent_name}", name=agent_name,
            attributes={
                "conversation_scope": "framework_agent",
                "conversation_agent_path": f"/openai-agents-sdk/{agent_name}",
                "provider": "openai-agents-sdk",
            },
        )

    def _identity(self, span: Any) -> dict[str, Any]:
        """Stable evidence pointer, without user-controlled payloads."""
        return {
            "sdk_trace_id": str(span.trace_id),
            "sdk_span_id": str(span.span_id),
            "sdk_parent_span_id": str(span.parent_id) if span.parent_id else None,
            "evidence_source": "agents_sdk_tracing_callback",
            "process_effect_verified": False,
        }

    def on_trace_start(self, trace: Any) -> None:
        self._guard(self._trace_start, trace)

    def _trace_start(self, trace: Any) -> None:
        if not self.enabled:
            return
        assert self.context is not None
        with self._lock:
            trace_id = str(trace.trace_id)
            self._state(trace_id)
            task = self.context.entity("task", f"trace:{trace_id}", name="SDK trace")
            group_id = getattr(trace, "group_id", None)
            attrs = {
                "sdk_trace_id": trace_id,
                "evidence_source": "agents_sdk_tracing_callback",
                "task_category": "sdk_trace",
                "span_completion_is_not_task_success": True,
            }
            if isinstance(group_id, str) and group_id:
                attrs["sdk_group_sha256"] = hashlib.sha256(
                    group_id.encode("utf-8")
                ).hexdigest()
            self.context.record_task(TaskRecord(task, attributes=attrs))

    def on_trace_end(self, trace: Any) -> None:
        self._guard(self._trace_end, trace)

    def _trace_end(self, trace: Any) -> None:
        if not self.enabled:
            return
        assert self.context is not None
        with self._lock:
            trace_id = str(trace.trace_id)
            state = self._runs.pop(trace_id, None)
            if state is None:
                return
            task = self.context.entity("task", f"trace:{trace_id}", name="SDK trace")
            self.context.emit(
                "TASK_UPDATED", "OBSERVATION_COVERAGE", source=task,
                attributes={
                    "sdk_trace_id": trace_id,
                    "span_counts": dict(state["counts"]),
                    "unattributed_spans": state["unattributed"],
                    "unclosed_spans": len(state["started"] - state["ended"]),
                    "callback_errors": self.callback_errors,
                    "coverage_scope": "sdk_callbacks_only",
                    "runtime_effects_verified": False,
                },
            )

    def on_span_start(self, span: Any) -> None:
        self._guard(self._span_start, span)

    def _span_start(self, span: Any) -> None:
        if not self.enabled:
            return
        assert self.context is not None
        with self._lock:
            trace_id = str(span.trace_id)
            span_id = str(span.span_id)
            state = self._state(trace_id)
            if span_id in state["started"]:
                return
            state["started"].add(span_id)
            parent_id = str(span.parent_id) if span.parent_id else None
            state["parents"][span_id] = parent_id
            data = span.span_data
            kind = getattr(data, "type", "unknown")
            state["counts"][str(kind)] += 1
            owner = self._owner_from_ancestors(state, parent_id)
            if kind == "agent":
                name = _name(getattr(data, "name", None), "unnamed-agent")
                owner = self._agent(trace_id, name)
                if owner.id not in state["seen"]:
                    self.context.record_agent(AgentRecord(
                        owner, role=name,
                        attributes={"sdk_trace_id": trace_id, "source": "sdk_agent_span"},
                    ))
                    state["seen"].add(owner.id)
                self.context.emit(
                    "AGENT_STARTED", "AGENT_STARTED", source=owner,
                    attributes=self._identity(span),
                )
                # Tools listed on an AgentSpan are *available*, not executed.
                available = getattr(data, "tools", None)
                if isinstance(available, list):
                    self.context.emit(
                        "TASK_UPDATED", "AVAILABLE_TOOLS", source=owner,
                        attributes={
                            **self._identity(span),
                            "tool_names": [_name(x, "unknown") for x in available[:100]],
                            "tool_list_truncated": len(available) > 100,
                            "selection_not_inferred": True,
                        },
                    )
            state["owners"][span_id] = owner
            if kind == "task":
                task = self.context.entity("task", f"{trace_id}:{span_id}", name="SDK Runner task")
                parent_task = self.context.entity(
                    "task", f"trace:{trace_id}", name="SDK trace"
                )
                self.context.record_task(TaskRecord(
                    task, owner=owner, parent_task=parent_task,
                    attributes={
                        **self._identity(span),
                        "task_category": "sdk_runner_invocation",
                        "span_completion_is_not_task_success": True,
                    },
                ))
                self.context.emit("TASK_STARTED", "SDK_TASK_STARTED",
                                  source=owner or task, target=task,
                                  attributes=self._identity(span))
                state["tasks"][span_id] = task
            elif kind == "turn":
                self.context.emit(
                    "TASK_UPDATED", "SDK_TURN_STARTED", source=owner,
                    attributes={
                        **self._identity(span),
                        "sdk_turn_number": getattr(data, "turn", None),
                        "sdk_turn_agent_name": _name(
                            getattr(data, "agent_name", None), "unknown"
                        ),
                        "turn_completion_is_not_task_success": True,
                    },
                )
            if kind not in ("agent",) and owner is None:
                state["unattributed"] += 1
            if kind in ("generation", "response"):
                response_object = getattr(data, "response", None)
                model_name = _name(
                    getattr(data, "model", None)
                    or getattr(response_object, "model", None),
                    "unknown",
                )
                state["models"][span_id] = model_name
                observed_input = getattr(data, "input", None)
                state["model_input_at_start"][span_id] = observed_input is not None
                model = self.context.entity("model", model_name, name=model_name)
                call = self.context.entity("model_call", f"{trace_id}:{span_id}")
                self.context.record_model_call(ModelCallRecord(
                    call, owner, model,
                    request=_safe(observed_input)
                    if self.capture_mode != "metadata_only" else None,
                    attributes={
                        **self._identity(span),
                        "input_observed_at_start": observed_input is not None,
                    },
                ))
            elif kind == "function":
                name = _name(getattr(data, "name", None), "unknown-tool")
                tool = self.context.entity("tool", name, name=name)
                call = self.context.entity("tool_call", f"{trace_id}:{span_id}")
                self.context.record_tool_call(ToolCallRecord(
                    call, owner, tool,
                    arguments=_safe(getattr(data, "input", None))
                    if self.capture_mode != "metadata_only" else None,
                    attributes={**self._identity(span), "effect_attestation": "not_provided"},
                ))

    def on_span_end(self, span: Any) -> None:
        self._guard(self._span_end, span)

    def _span_end(self, span: Any) -> None:
        if not self.enabled:
            return
        assert self.context is not None
        with self._lock:
            trace_id = str(span.trace_id)
            span_id = str(span.span_id)
            state = self._state(trace_id)
            if span_id in state["ended"]:
                return
            if span_id not in state["started"]:
                # No invented start event when a callback was missed.
                state["counts"]["end_without_start"] += 1
                return
            state["ended"].add(span_id)
            data = span.span_data
            kind = getattr(data, "type", "unknown")
            owner = state["owners"].get(span_id)
            failed = getattr(span, "error", None) is not None
            evidence = {**self._identity(span), "sdk_span_error": failed}
            if kind == "agent":
                self.context.emit(
                    "AGENT_STOPPED", "AGENT_STOPPED", source=owner,
                    attributes=evidence,
                )
            elif kind == "task":
                task = state["tasks"].get(span_id)
                if task is not None:
                    self.context.emit(
                        "TASK_UPDATED", "SDK_TASK_SPAN_ENDED",
                        source=owner or task, target=task,
                        attributes={**evidence, "task_success_verified": False},
                    )
            elif kind == "turn":
                self.context.emit(
                    "TASK_UPDATED", "SDK_TURN_ENDED", source=owner,
                    attributes={**evidence, "turn_success_verified": False},
                )
            elif kind in ("generation", "response"):
                initial_model = state["models"].get(span_id, "unknown")
                call = self.context.entity("model_call", f"{trace_id}:{span_id}")
                observed_response = (
                    getattr(data, "response", None) if kind == "response"
                    else getattr(data, "output", None)
                )
                # The SDK can fill in the final model identity only when the
                # span ends. Preserve the initial unknown instead of claiming
                # that the model was known at request time.
                resolved_model = _name(
                    getattr(data, "model", None)
                    or getattr(observed_response, "model", None),
                    initial_model,
                )
                model = self.context.entity("model", resolved_model, name=resolved_model)
                # The official Responses SDK populates span_data.input
                # *after* the model call. Keep the original request boundary
                # intact and append content with its true observation stage.
                late_input = getattr(data, "input", None)
                if (
                    self.capture_mode != "metadata_only"
                    and late_input is not None
                    and not state["model_input_at_start"].get(span_id, False)
                ):
                    self.context.record_model_call(ModelCallRecord(
                        call, owner, model, request=_safe(late_input),
                        attributes={
                            **evidence,
                            "content_observed_at": "sdk_span_end",
                            "late_request_content": True,
                            "request_timestamp_not_inferred": True,
                        },
                    ))
                response = (
                    _safe(observed_response)
                    if self.capture_mode == "prompt_and_response" else None
                )
                self.context.record_model_call(ModelCallRecord(
                    call, owner, model, response=response,
                    status="failure" if failed else "response",
                    attributes={
                        **evidence,
                        "sdk_reported_model": resolved_model,
                        "sdk_initial_model": initial_model,
                        "model_identity_resolved_at_end": resolved_model != initial_model,
                    },
                ))
            elif kind == "function":
                name = _name(getattr(data, "name", None), "unknown-tool")
                tool = self.context.entity("tool", name, name=name)
                call = self.context.entity("tool_call", f"{trace_id}:{span_id}")
                response = (
                    _safe(getattr(data, "output", None))
                    if self.capture_mode == "prompt_and_response" else None
                )
                self.context.record_tool_call(ToolCallRecord(
                    call, owner, tool, result=response,
                    status="failure" if failed else "result",
                    attributes={**evidence, "effect_attestation": "not_provided"},
                ))
            elif kind == "handoff" and not failed:
                sender_name = getattr(data, "from_agent", None)
                recipient_name = getattr(data, "to_agent", None)
                if sender_name and recipient_name:
                    sender = self._agent(trace_id, sender_name)
                    recipient = self._agent(trace_id, recipient_name)
                    for agent in (sender, recipient):
                        if agent.id not in state["seen"]:
                            self.context.record_agent(AgentRecord(agent, role=agent.name))
                            state["seen"].add(agent.id)
                    message = self.context.entity("message", f"{trace_id}:{span_id}")
                    self.context.record_message(MessageRecord(
                        message, sender, recipient, direction="sent",
                        attributes={**evidence, "receive_observed": False,
                                    "handoff_proof": "sdk_handoff_span_only"},
                    ))
                else:
                    self.context.emit(
                        "MESSAGE_UNROUTED", "HANDOFF_UNROUTED",
                        attributes={**evidence, "reason": "missing_agent_identity"},
                    )

    def _guard(self, handler: Any, value: Any) -> None:
        try:
            handler(value)
        except Exception:
            # Never surface SDK payloads, exception messages or tracebacks.
            with self._lock:
                self.callback_errors += 1

    def force_flush(self) -> None:
        """Events are synchronously written to the run-bound sidecar."""

    def shutdown(self) -> None:
        """No external resources or background worker to close."""


def install_agents_sdk_tracing(*, capture_mode: str = "metadata_only") -> AgentsSDKTraceProcessor:
    """Register an additive processor before Runner.run.

    Does not disable the SDK's own tracing exporter or change its privacy policy.
    """
    try:
        from agents.tracing import add_trace_processor
    except ImportError as exc:
        raise ImportError("Install the optional 'openai-agents' package") from exc
    processor = AgentsSDKTraceProcessor(capture_mode=capture_mode)
    if processor.enabled:
        add_trace_processor(processor)
    return processor
