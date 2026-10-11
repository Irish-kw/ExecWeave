"""Opt-in, run-scoped OpenAI Python SDK observations for custom scripts.

Usage:
    rec = OpenAIAgentRecorder(capture_mode="metadata_only")
    client = rec.wrap(OpenAI())
    with rec.agent("Planner"):
        client.responses.create(model="gpt-...", input="hello")

This is not transparent network interception. It records client calls made through
the wrapped resources. Explicit send/receive calls are required for multi-agent
routing; model output never establishes delivery by itself.
"""
from __future__ import annotations

import inspect
import os
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any
from uuid import uuid4

from .framework_adapters.base import (
    AdapterContext, AgentRecord, ContentCapturePolicy, MessageRecord,
    ModelCallRecord, ToolCallRecord,
)

_REDACTED = object()
_CREDENTIAL_KEYS = frozenset({
    "authorization", "proxy-authorization", "cookie", "set-cookie",
    "api_key", "apikey", "api-key", "x-api-key", "password",
    "token", "access_token", "refresh_token", "client_secret",
})
_ALLOWED_RESOURCES = frozenset({"responses", "chat.completions"})


def _safe(value: Any, depth: int = 0) -> Any:
    """Bounded explicit-content serializer; credential field names are excluded."""
    if depth > 6:
        return "[depth limit]"
    if value is None or type(value) in {bool, int, float}:
        return value
    if isinstance(value, str):
        return value[:32768]
    if isinstance(value, (list, tuple)):
        return [_safe(item, depth + 1) for item in value[:100]]
    if isinstance(value, dict):
        return {
            str(key)[:128]: _safe(item, depth + 1)
            for key, item in list(value.items())[:100]
            if str(key).lower().replace("-", "_") not in
            {name.replace("-", "_") for name in _CREDENTIAL_KEYS}
        }
    if hasattr(value, "model_dump"):
        try:
            return _safe(value.model_dump(mode="json"), depth + 1)
        except (TypeError, ValueError, AttributeError):
            return "[unserializable response]"
    return "[unserializable value]"


class _ResourceProxy:
    def __init__(self, raw: Any, recorder: "OpenAIAgentRecorder", path: str):
        self._raw = raw
        self._recorder = recorder
        self._path = path

    def __getattr__(self, key: str) -> Any:
        value = getattr(self._raw, key)
        next_path = self._path + "." + key
        if next_path in _ALLOWED_RESOURCES:
            return _ResourceProxy(value, self._recorder, next_path)
        if key != "create" or self._path not in _ALLOWED_RESOURCES:
            return value
        def invoke(*args: Any, **kwargs: Any) -> Any:
            call_id = self._recorder._begin(self._path, kwargs)
            try:
                result = value(*args, **kwargs)
            except BaseException as exc:
                self._recorder._failed(call_id, type(exc).__name__)
                raise

            # OpenAI's AsyncAPIResource may return an awaitable from an
            # ordinary callable (not an inspect.iscoroutinefunction).
            # A coroutine is NOT a successful response: await it before
            # emitting MODEL_RESPONSE, and classify HTTP errors accurately.
            if inspect.isawaitable(result):
                async def finish() -> Any:
                    try:
                        resolved = await result
                    except BaseException as exc:
                        self._recorder._failed(call_id, type(exc).__name__)
                        raise
                    self._recorder._done(
                        call_id, resolved, streamed=kwargs.get("stream") is True,
                    )
                    return resolved
                return finish()

            self._recorder._done(call_id, result, streamed=kwargs.get("stream") is True)
            return result
        return invoke


class _ClientProxy:
    def __init__(self, raw: Any, recorder: "OpenAIAgentRecorder"):
        self._raw = raw
        self._recorder = recorder

    def __getattr__(self, key: str) -> Any:
        value = getattr(self._raw, key)
        if key in {"responses", "chat"}:
            return _ResourceProxy(value, self._recorder, key)
        return value


class OpenAIAgentRecorder:
    """Instrument explicitly wrapped OpenAI/AsyncOpenAI clients.

    When not launched under ExecWeave, this adapter is a no-op. No API key is
    needed or read by this module; the official SDK handles authentication.
    """

    def __init__(self, *, capture_mode: str = "metadata_only", default_agent: str = "main"):
        ContentCapturePolicy(capture_mode)
        self._enabled = bool(
            os.environ.get("EXECWEAVE_SEMANTIC_SIDECAR")
            and os.environ.get("EXECWEAVE_SESSION_ID")
        )
        self._context = (AdapterContext.from_environment(
            "openai-python", capture_mode=capture_mode,
        ) if self._enabled else None)
        self._capture_mode = capture_mode
        self._default_agent = default_agent
        self._current_agent: ContextVar[str] = ContextVar(
            "execweave_openai_agent", default=default_agent,
        )
        self._agents: dict[str, Any] = {}
        self._calls: dict[str, tuple[Any, Any]] = {}
        self._tools: dict[str, tuple[Any, Any]] = {}

    def wrap(self, client: Any) -> Any:
        """Return a proxy for Responses and Chat Completions only."""
        return _ClientProxy(client, self) if self._enabled else client

    @contextmanager
    def agent(self, name: str):
        """Explicit agent ownership; contextvars isolates async tasks."""
        if not isinstance(name, str) or not name.strip():
            raise ValueError("agent name must be nonempty")
        marker = self._current_agent.set(name.strip())
        try:
            self._agent(name.strip())
            yield
        finally:
            self._current_agent.reset(marker)

    def _agent(self, name: str) -> Any:
        if not self._enabled:
            return None
        if name not in self._agents:
            assert self._context is not None
            agent = self._context.entity("agent", name, name=name, attributes={
                "conversation_scope": "framework_agent",
                "conversation_agent_id": name,
                "conversation_agent_path": "/openai-python/" + name,
                "provider": "openai",
            })
            self._context.record_agent(AgentRecord(agent, role=name))
            self._agents[name] = agent
        return self._agents[name]

    def _begin(self, resource: str, kwargs: dict[str, Any]) -> str:
        call_id = uuid4().hex
        if not self._enabled:
            return call_id
        assert self._context is not None
        agent = self._agent(self._current_agent.get())
        model_name = kwargs.get("model")
        model_name = model_name if isinstance(model_name, str) else "unknown"
        model = self._context.entity("model", model_name, name=model_name, attributes={
            "provider": "openai",
        })
        call = self._context.entity("model_call", call_id, name=resource)
        self._calls[call_id] = (agent, model)
        metadata = {"sdk_surface": resource, "provider": "openai"}
        value = _safe(kwargs) if self._capture_mode != "metadata_only" else None
        self._context.record_model_call(ModelCallRecord(
            call, agent, model, request=value, status="request", attributes=metadata,
        ))
        return call_id

    def _done(self, call_id: str, result: Any, *, streamed: bool) -> None:
        if not self._enabled or call_id not in self._calls:
            return
        assert self._context is not None
        agent, model = self._calls.pop(call_id)
        # A returned iterator is not a completed response. Never label it as such.
        if streamed:
            return
        response = _safe(result) if self._capture_mode == "prompt_and_response" else None
        call = self._context.entity("model_call", call_id, name="OpenAI model call")
        self._context.record_model_call(ModelCallRecord(
            call, agent, model, response=response, status="response",
            attributes={"provider": "openai", "response_observed": True},
        ))

    def _failed(self, call_id: str, exception_type: str) -> None:
        if not self._enabled or call_id not in self._calls:
            return
        assert self._context is not None
        agent, model = self._calls.pop(call_id)
        call = self._context.entity("model_call", call_id, name="OpenAI model call")
        self._context.record_model_call(ModelCallRecord(
            call, agent, model, status="failure",
            attributes={"provider": "openai", "error_type": exception_type[:100]},
        ))

    def sent(self, message_id: str, sender: str, recipient: str, *,
             content: str | None = None) -> None:
        self._message(message_id, sender, recipient, "sent", content)

    def received(self, message_id: str, sender: str, recipient: str, *,
                 content: str | None = None) -> None:
        self._message(message_id, sender, recipient, "received", content)

    def _message(self, message_id: str, sender: str, recipient: str,
                 phase: str, content: str | None) -> None:
        if not all(isinstance(x, str) and x.strip() for x in (message_id, sender, recipient)):
            raise ValueError("message ID, sender and recipient must be nonempty")
        if not self._enabled:
            return
        assert self._context is not None
        source, target = self._agent(sender), self._agent(recipient)
        message = self._context.entity("message", message_id, name="Agent handoff")
        self._context.record_message(MessageRecord(
            message, source, target, direction=phase,
            content=(content if self._capture_mode != "metadata_only" else None),
        ))

    def tool_started(self, name: str, *, arguments: Any = None) -> str:
        call_id = uuid4().hex
        if self._enabled:
            assert self._context is not None
            agent = self._agent(self._current_agent.get())
            tool = self._context.entity("tool", name, name=name)
            self._tools[call_id] = (agent, tool)
            call = self._context.entity("tool_call", call_id, name=name)
            self._context.record_tool_call(ToolCallRecord(
                call, agent, tool,
                arguments=_safe(arguments) if self._capture_mode != "metadata_only" else None,
                status="call",
            ))
        return call_id

    def tool_finished(self, call_id: str, *, result: Any = None,
                      failed: bool = False) -> None:
        pair = self._tools.pop(call_id, None)
        if pair is None:
            return
        assert self._context is not None
        agent, tool = pair
        call = self._context.entity("tool_call", call_id, name=tool.name)
        self._context.record_tool_call(ToolCallRecord(
            call, agent, tool,
            result=_safe(result) if self._capture_mode == "prompt_and_response" else None,
            status="failure" if failed else "result",
        ))
