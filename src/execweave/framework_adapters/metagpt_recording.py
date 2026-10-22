"""Instance-scoped observation of MetaGPT logical calls and HTTP attempts.

No MetaGPT import is required by the SDK. Mix this into an OllamaLLM subclass.
The installed requestor must expose ``arequest_raw(..., session, ...)``; its
session is wrapped, so capture occurs after JSON serialization, at request().
"""

from __future__ import annotations

import inspect
import json
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from .base import EntityRef


def snapshot(value: Any) -> Any:
    """Copy JSON without silently stringifying unsupported prompt objects."""
    return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))


@dataclass
class _Call:
    id: str
    attempts: int = 0
    responses: int = 0


class _Session:
    def __init__(self, session, recorder):
        self._session = session
        self._recorder = recorder

    def __getattr__(self, name):
        return getattr(self._session, name)

    async def request(self, **kwargs):
        recorder = self._recorder
        call = recorder._call_context.get()
        if call is None:
            raise RuntimeError("HTTP request outside an observed model invocation")
        # Inspect only the serialized body, never headers, API keys or URL queries.
        payload = json.loads(kwargs["data"])
        call.attempts += 1
        recorder._provider_attempt_count += 1
        attempt_id = f"{call.id}-attempt-{call.attempts}"
        timeout = kwargs.get("timeout")
        recorder._stage(
            call,
            "http_transport",
            {
                "provider_payload": payload,
                "transport_stream": recorder._transport_stream.get(),
                "request_timeout": {
                    key: getattr(timeout, key, None)
                    for key in ("total", "connect", "sock_read", "sock_connect")
                },
            },
            provider_attempt_id=attempt_id,
            transport_status="attempted",
        )
        try:
            result = await self._session.request(**kwargs)
        except BaseException as exc:
            recorder._provider_failure_count += 1
            recorder._stage(
                call,
                "http_transport_outcome",
                None,
                provider_attempt_id=attempt_id,
                transport_status="failed",
                failure_type=type(exc).__name__,
            )
            raise
        call.responses += 1
        recorder._provider_response_count += 1
        recorder._stage(
            call,
            "http_transport_outcome",
            None,
            provider_attempt_id=attempt_id,
            transport_status="response_received",
            http_status=result.status,
        )
        return result


class OllamaRecordingMixin:
    """Keep caller arguments, processed messages and wire payload distinct.

    MODEL_REQUEST/RESPONSE/FAILURE retain their logical-call meaning. Additive
    MODEL_CONTENT_RECORDED stage events carry separate provider attempt IDs.
    A response_received attempt means HTTP headers arrived, not model success.
    """

    def __init__(self, config, *, adapter, role_ref, **kwargs):
        self._adapter = adapter
        self._role_ref = role_ref
        self._instance_id = uuid4().hex
        self._counter = self._request_count = self._response_count = self._failure_count = 0
        self._provider_attempt_count = self._provider_response_count = (
            self._provider_failure_count
        ) = 0
        self._call_context = ContextVar(f"metagpt_call_{id(self)}", default=None)
        self._last_call_outcome = ContextVar(f"metagpt_outcome_{id(self)}", default=None)
        self._transport_stream = ContextVar(f"metagpt_stream_{id(self)}", default=False)
        super().__init__(config, **kwargs)
        original_request = self.client.arequest
        request_signature = inspect.signature(original_request)

        async def observed_request(*args, **kw):
            bound = request_signature.bind(*args, **kw)
            token = self._transport_stream.set(bound.arguments.get("stream", False))
            try:
                return await original_request(*args, **kw)
            finally:
                self._transport_stream.reset(token)

        self.client.arequest = observed_request
        original = self.client.arequest_raw
        signature = inspect.signature(original)
        if "session" not in signature.parameters:
            raise TypeError("Unsupported MetaGPT HTTP requestor: missing session boundary")

        async def observed_raw(*args, **kw):
            bound = signature.bind(*args, **kw)
            bound.arguments["session"] = _Session(bound.arguments["session"], self)
            return await original(*bound.args, **bound.kwargs)

        self.client.arequest_raw = observed_raw

    def _stage(self, call, stage, value, **attributes):
        context = self._adapter.context
        kind = f"metagpt.{stage}_request"
        reference = (
            context.content.put_json(value, content_kind=kind) if value is not None else None
        )
        model_call = self._adapter.entity("model_call", call.id, name="MetaGPT model call")
        target = (
            EntityRef(
                "observed_content",
                f"observed-content:model:sha256:{reference.sha256}",
                reference.content_kind,
                reference.to_dict(),
            )
            if reference is not None
            else model_call
        )
        context.emit(
            "MODEL_CONTENT_RECORDED",
            f"METAGPT_{stage.upper()}",
            source=self._role_ref,
            target=target,
            attributes={
                "model_call_id": model_call.id,
                "logical_call_id": call.id,
                "capture_stage": stage,
                "provider": "ollama",
                "provider_compatibility": getattr(self, "_ollama_compatibility", "unmodified"),
                **context.content.reference_attributes(reference),
                **attributes,
            },
        )

    async def _logical(self, stage, arguments, invoke):
        self._counter += 1
        self._request_count += 1
        call = _Call(f"metagpt-{self._role_ref.id}-ollama-{self._instance_id}-call-{self._counter}")
        token = self._call_context.set(call)
        boundary = f"metagpt.provider.base_llm.BaseLLM.{stage.removesuffix('_entry')}"
        request = {"capture_stage": stage, "arguments_capture": "unavailable"}
        try:
            try:
                args = snapshot(arguments)
                request = {
                    "capture_stage": stage,
                    "aask_arguments" if stage == "aask_entry" else "acompletion_arguments": args,
                }
                # Legacy preview fields explicitly describe the caller boundary.
                msg = args.get("msg", args.get("messages", []))
                request.update(
                    messages=[{"role": "user", "content": msg}] if isinstance(msg, str) else msg,
                    system_messages=args.get("system_msgs"),
                    format_messages=args.get("format_msgs"),
                    stream=args.get("stream"),
                    system_messages_stage=stage,
                )
                if stage == "aask_entry":
                    request["system_prompt_policy"] = {
                        "enabled": getattr(self, "use_system_prompt", None),
                        "default_system_prompt": getattr(self, "system_prompt", None),
                    }
            except (TypeError, ValueError):
                # Recording must not change provider behavior for non-JSON arguments.
                request["arguments_type"] = type(arguments).__name__
            self._adapter.observe_model_call(
                call.id,
                role=self._role_ref,
                model_id=self.model,
                request=request,
                status="request",
                boundary=boundary,
                logical_call_id=call.id,
                capture_stage=stage,
                provider_compatibility=getattr(self, "_ollama_compatibility", "unmodified"),
            )
            try:
                response = await invoke()
            except BaseException as exc:
                self._failure_count += 1
                self._last_call_outcome.set((call.id, "failure"))
                self._adapter.observe_model_call(
                    call.id,
                    role=self._role_ref,
                    model_id=self.model,
                    response={"failure_type": type(exc).__name__},
                    status="failure",
                    boundary=boundary,
                    logical_call_id=call.id,
                    transport_status="not_sent" if not call.attempts else "failed",
                    provider_attempt_count=call.attempts,
                )
                raise
            self._response_count += 1
            self._last_call_outcome.set((call.id, "response"))
            self._adapter.observe_model_call(
                call.id,
                role=self._role_ref,
                model_id=self.model,
                response=response,
                status="response",
                boundary=boundary,
                logical_call_id=call.id,
                transport_status="response_received" if call.responses else "not_sent",
                provider_attempt_count=call.attempts,
            )
            return response
        finally:
            self._call_context.reset(token)

    async def aask(
        self, msg, system_msgs=None, format_msgs=None, images=None, timeout=0, stream=None
    ):
        parent = super().aask
        arguments = dict(
            msg=msg,
            system_msgs=system_msgs,
            format_msgs=format_msgs,
            images=images,
            timeout=timeout,
            stream=stream,
        )
        return await self._logical("aask_entry", arguments, lambda: parent(**arguments))

    async def acompletion_text(self, messages, stream=False, timeout=0):
        parent = super().acompletion_text

        async def invoke():
            self._stage(
                self._call_context.get(),
                "acompletion_text",
                {
                    "final_messages": snapshot(messages),
                    "system_messages": snapshot([m for m in messages if m.get("role") == "system"]),
                    "system_messages_stage": "acompletion_text",
                    "stream": stream,
                    "timeout": timeout,
                },
            )
            return await parent(messages, stream=stream, timeout=timeout)

        if self._call_context.get() is not None:
            return await invoke()
        return await self._logical(
            "acompletion_text_entry",
            dict(messages=messages, stream=stream, timeout=timeout),
            invoke,
        )

    async def acompletion(self, messages, timeout=0):
        parent = super().acompletion
        if self._call_context.get() is not None:
            return await parent(messages, timeout=timeout)
        return await self._logical(
            "acompletion_entry",
            dict(messages=messages, timeout=timeout),
            lambda: parent(messages, timeout=timeout),
        )


def observe_actionnode_retries(node, llm, adapter, role, task):
    """Observe the instance's actual Tenacity attempts, including recovered retries.

    Preserve upstream wait/stop/retry policies. A failure following a successful
    model return is structured-output processing; model failures are not called
    parser failures. No model request-count subtraction is used as evidence.
    """
    from types import MethodType

    original = node._aask_v1.__func__
    counts = {"attempts": 0, "retries": 0, "parser_failures": 0}
    observer_id = uuid4().hex
    old_after = original.retry.after

    def before(state):
        counts["attempts"] += 1
        state.execweave_start = llm._last_call_outcome.get()

    def after(state):
        if old_after:
            old_after(state)
        outcome = llm._last_call_outcome.get()
        if outcome != state.execweave_start and outcome is not None and outcome[1] == "response":
            counts["parser_failures"] += 1
            adapter.observe_parser_failure(
                f"actionnode-{observer_id}-parser-{counts['parser_failures']}",
                role=role,
                task=task,
                error=type(state.outcome.exception()).__name__,
                parser="metagpt.actions.action_node.ActionNode._aask_v1",
                failure_stage="structured_output_processing",
                attempt_index=state.attempt_number,
            )

    def before_sleep(state):
        counts["retries"] += 1
        adapter.observe_retry(
            f"actionnode-{observer_id}-retry-{counts['retries']}",
            role=role,
            task=task,
            retry_index=state.attempt_number,
            retry_source="metagpt.actions.action_node.ActionNode._aask_v1",
            failure_type=type(state.outcome.exception()).__name__,
        )

    node._aask_v1 = MethodType(
        original.retry_with(before=before, after=after, before_sleep=before_sleep), node
    )
    return counts
