"""AutoGen adapter over authoritative message/runtime/model callbacks."""

from __future__ import annotations

import importlib.metadata
import json
from typing import Any

from .base import (
    AdapterCapabilities,
    AdapterContext,
    AgentRecord,
    EntityRef,
    FrameworkAdapter,
    FrameworkCompatibility,
    MessageRecord,
    ModelCallRecord,
    ToolCallRecord,
)


class AutoGenAdapter(FrameworkAdapter):
    framework_name = "autogen"
    capabilities = AdapterCapabilities(
        events=(
            "AGENT_CREATED",
            "AGENT_STARTED",
            "AGENT_STOPPED",
            "MESSAGE_SENT",
            "MESSAGE_RECEIVED",
            "MODEL_REQUEST",
            "MODEL_RESPONSE",
            "MODEL_FAILURE",
            "TOOL_CALL",
            "TOOL_RESULT",
            "TOOL_FAILURE",
        ),
        content_modes=("metadata_only", "content_ref_only", "prompt_only", "prompt_and_response"),
        authoritative_surfaces=(
            "autogen_core.AgentId",
            "autogen_core.RoutedAgent",
            "autogen_agentchat.messages",
            "autogen_core.logging.LLMCallEvent",
        ),
        known_limitations=(
            "AutoGen APIs vary between autogen-core and autogen-agentchat; callers must pass the authoritative event payload.",
        ),
    )

    def __init__(self, context: AdapterContext) -> None:
        super().__init__(context)
        self._agents: dict[str, EntityRef] = {}
        self._event_counter = 0
        self._model_call_counter = 0

    @classmethod
    def compatibility(cls) -> FrameworkCompatibility:
        version = None
        for distribution in ("autogen-agentchat", "autogen-core", "pyautogen"):
            try:
                version = importlib.metadata.version(distribution)
                break
            except importlib.metadata.PackageNotFoundError:
                continue
        status = "verified" if version == "0.7.5" else ("warn" if version else "unknown")
        return FrameworkCompatibility(
            framework=cls.framework_name,
            detected_version=version,
            tested_versions=("0.7.5", "0.4.x"),
            compatibility_status=status,
            capabilities=cls.capabilities,
            known_limitations=cls.capabilities.known_limitations,
        )

    def observe_agent(
        self,
        native_id: str | int,
        *,
        name: str | None = None,
        role: str | None = None,
        process: Any | None = None,
        **attributes: Any,
    ) -> EntityRef:
        agent = self.agent(native_id, name=name, provider="autogen", role=role, **attributes)
        self._agents[str(native_id)] = agent
        self.context.record_agent(AgentRecord(agent, role=role, process=process, attributes=attributes))
        return agent

    def observe_message(
        self,
        message_id: str | int,
        *,
        source: EntityRef | None,
        target: EntityRef | None,
        content: str | None = None,
        role: str | None = None,
        task: EntityRef | None = None,
        received: bool = False,
        **attributes: Any,
    ) -> EntityRef:
        message = self.entity("message", message_id, name="AutoGen message", attributes={"provider": "autogen"})
        self.context.record_message(
            MessageRecord(
                message,
                source,
                target,
                role=role,
                task=task,
                content=content,
                direction="received" if received else "sent",
                attributes=attributes,
            )
        )
        return message

    def observe_model_call(
        self,
        call_id: str | int,
        *,
        agent: EntityRef | None,
        model_id: str | int,
        request: Any | None = None,
        response: Any | None = None,
        status: str = "request",
        **attributes: Any,
    ) -> EntityRef:
        model = self.model(model_id, provider="autogen", **attributes)
        call = self.entity("model_call", call_id, name="AutoGen model call", attributes={"provider": "autogen"})
        self.context.record_model_call(
            ModelCallRecord(
                call,
                agent,
                model,
                request=request,
                response=response,
                status=status,
                content_kind="model_request" if status == "request" else "model_response",
                attributes=attributes,
            )
        )
        return call

    def observe_tool_call(
        self,
        call_id: str | int,
        *,
        agent: EntityRef | None,
        tool_id: str | int,
        arguments: Any | None = None,
        result: Any | None = None,
        status: str = "call",
        **attributes: Any,
    ) -> EntityRef:
        tool = self.tool(tool_id, provider="autogen", **attributes)
        call = self.entity("tool_call", call_id, name="AutoGen tool call", attributes={"provider": "autogen"})
        self.context.record_tool_call(
            ToolCallRecord(
                call,
                agent,
                tool,
                arguments=arguments,
                result=result,
                status=status,
                attributes=attributes,
            )
        )
        return call

    def observe_agentchat_event(
        self,
        event: Any,
        *,
        source: EntityRef | None = None,
        target: EntityRef | None = None,
        task: EntityRef | None = None,
        received: bool = False,
        **attributes: Any,
    ) -> EntityRef | list[EntityRef]:
        """Observe one item yielded by ``Agent.run_stream`` or a team stream."""
        self._event_counter += 1
        event_name = type(event).__name__
        event_id = getattr(event, "id", None) or f"event-{self._event_counter}"
        source_name = getattr(event, "source", None)
        if source is None and source_name is not None:
            source = self._agents.get(str(source_name)) or self.observe_agent(
                str(source_name), name=str(source_name)
            )
        target_name = getattr(event, "target", None) or getattr(event, "recipient", None)
        if target is None and target_name is not None:
            target = self._agents.get(str(target_name)) or self.observe_agent(
                str(target_name), name=str(target_name)
            )
        content = getattr(event, "content", None)
        if event_name == "ThoughtEvent":
            return self.observe_message(
                event_id,
                source=source,
                target=target,
                content=None,
                role="internal_reasoning",
                task=task,
                received=received,
                event_type=event_name,
                content_suppressed_by_policy=True,
                **attributes,
            )
        if event_name == "ToolCallRequestEvent":
            results = []
            for call in content if isinstance(content, list) else []:
                call_id = getattr(call, "id", None) or f"{event_id}-tool"
                tool_name = getattr(call, "name", None) or "autogen-tool"
                results.append(
                    self.observe_tool_call(
                        call_id,
                        agent=source,
                        tool_id=tool_name,
                        arguments=_jsonable(getattr(call, "arguments", None)),
                        status="call",
                        event_type=event_name,
                        **attributes,
                    )
                )
            return results
        if event_name == "ToolCallExecutionEvent":
            results = []
            for result in content if isinstance(content, list) else []:
                call_id = getattr(result, "call_id", None) or f"{event_id}-tool"
                tool_name = getattr(result, "name", None) or "autogen-tool"
                status = "failure" if bool(getattr(result, "is_error", False)) else "result"
                results.append(
                    self.observe_tool_call(
                        call_id,
                        agent=source,
                        tool_id=tool_name,
                        result=_jsonable(getattr(result, "content", None)),
                        status=status,
                        event_type=event_name,
                        **attributes,
                    )
                )
            return results
        return self.observe_message(
            event_id,
            source=source,
            target=target,
            content=_text(content),
            role=event_name,
            task=task,
            received=received,
            event_type=event_name,
            metadata=_jsonable(getattr(event, "metadata", None)),
            **attributes,
        )

    def observe_model_event(
        self,
        event: Any,
        *,
        agent: EntityRef | None = None,
        model_id: str | int = "autogen-model",
        **attributes: Any,
    ) -> list[EntityRef]:
        """Observe an ``autogen_core.logging`` LLMCall/stream event."""
        payload = getattr(event, "kwargs", None)
        if not isinstance(payload, dict):
            payload = vars(event) if hasattr(event, "__dict__") else {}
        agent_id = payload.get("agent_id")
        if agent is None and agent_id:
            agent = self._agents.get(str(agent_id)) or self.observe_agent(str(agent_id), name=str(agent_id))
        self._model_call_counter += 1
        call_id = payload.get("call_id") or f"llm-{self._model_call_counter}"
        event_type = str(payload.get("type") or type(event).__name__)
        merged = {"event_type": event_type, **attributes}
        request = _jsonable(payload.get("messages"))
        response = _jsonable(payload.get("response"))
        observed: list[EntityRef] = []
        if request is not None:
            observed.append(
                self.observe_model_call(
                    call_id,
                    agent=agent,
                    model_id=model_id,
                    request=request,
                    status="request",
                    **merged,
                )
            )
        if response is not None:
            observed.append(
                self.observe_model_call(
                    call_id,
                    agent=agent,
                    model_id=model_id,
                    response=response,
                    status="response",
                    prompt_tokens=payload.get("prompt_tokens"),
                    completion_tokens=payload.get("completion_tokens"),
                    **merged,
                )
            )
        return observed

    def observe_tool_event(
        self,
        event: Any,
        *,
        agent: EntityRef | None = None,
        **attributes: Any,
    ) -> EntityRef:
        """Observe an ``autogen_core.logging.ToolCallEvent``."""
        payload = getattr(event, "kwargs", None)
        if not isinstance(payload, dict):
            payload = vars(event) if hasattr(event, "__dict__") else {}
        agent_id = payload.get("agent_id")
        if agent is None and agent_id:
            agent = self._agents.get(str(agent_id)) or self.observe_agent(str(agent_id), name=str(agent_id))
        return self.observe_tool_call(
            payload.get("call_id") or f"tool-{self._event_counter + 1}",
            agent=agent,
            tool_id=payload.get("tool_name") or "autogen-tool",
            arguments=_jsonable(payload.get("arguments")),
            result=_jsonable(payload.get("result")),
            status="result",
            event_type=str(payload.get("type") or type(event).__name__),
            **attributes,
        )


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(child) for key, child in value.items()}
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return _jsonable(model_dump())
    to_dict = getattr(value, "dict", None)
    if callable(to_dict):
        return _jsonable(to_dict())
    return str(value)


def _text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(_jsonable(value), ensure_ascii=False, sort_keys=True)
