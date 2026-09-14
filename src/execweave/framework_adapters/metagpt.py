"""MetaGPT adapter for role/message/action/model/parser observability."""

from __future__ import annotations

import importlib.metadata
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
    TaskRecord,
)


class MetaGPTAdapter(FrameworkAdapter):
    framework_name = "metagpt"
    capabilities = AdapterCapabilities(
        events=(
            "AGENT_CREATED",
            "AGENT_STARTED",
            "AGENT_STOPPED",
            "TASK_CREATED",
            "TASK_STARTED",
            "TASK_COMPLETED",
            "TASK_FAILED",
            "TASK_UPDATED",
            "MESSAGE_SENT",
            "MESSAGE_RECEIVED",
            "MODEL_REQUEST",
            "MODEL_RESPONSE",
            "MODEL_FAILURE",
        ),
        content_modes=("metadata_only", "content_ref_only", "prompt_only", "prompt_and_response"),
        authoritative_surfaces=(
            "metagpt.roles.Role",
            "metagpt.actions.Action",
            "metagpt.schema.Message",
            "metagpt.provider.base_llm.BaseLLM",
        ),
        known_limitations=(
            "MetaGPT releases expose different role and provider hooks; parser failure and retry events must be supplied by the integration wrapper.",
        ),
    )

    def __init__(self, context: AdapterContext) -> None:
        super().__init__(context)
        self._roles: dict[str, EntityRef] = {}
        self._message_counter = 0

    @classmethod
    def compatibility(cls) -> FrameworkCompatibility:
        try:
            version = importlib.metadata.version("metagpt")
        except importlib.metadata.PackageNotFoundError:
            version = None
        status = "verified" if version == "1.0.0" else ("warn" if version else "unknown")
        return FrameworkCompatibility(
            framework=cls.framework_name,
            detected_version=version,
            tested_versions=("1.0.0", "0.8.x"),
            compatibility_status=status,
            capabilities=cls.capabilities,
            known_limitations=cls.capabilities.known_limitations,
        )

    def observe_role(
        self,
        native_id: str | int,
        *,
        name: str | None = None,
        role: str | None = None,
        process: Any | None = None,
        **attributes: Any,
    ) -> EntityRef:
        agent = self.agent(native_id, name=name, provider="metagpt", role=role, **attributes)
        self._roles[str(native_id)] = agent
        self.context.record_agent(AgentRecord(agent, role=role, process=process, attributes=attributes))
        return agent

    def observe_role_object(self, role_object: Any, *, process: Any | None = None, **attributes: Any) -> EntityRef:
        """Observe a current ``metagpt.roles.Role`` instance by its public fields."""
        native_id = getattr(role_object, "role_id", None) or getattr(role_object, "name", None) or type(role_object).__name__
        name = _text(getattr(role_object, "name", None)) or type(role_object).__name__
        profile = _text(getattr(role_object, "profile", None))
        return self.observe_role(native_id, name=name, role=profile, process=process, role_type=type(role_object).__name__, **attributes)

    def observe_task(
        self,
        task_id: str | int,
        *,
        owner: EntityRef | None = None,
        name: str | None = None,
        status: str = "created",
        **attributes: Any,
    ) -> EntityRef:
        task = self.task(task_id, name=name, provider="metagpt", **attributes)
        event = {
            "created": "TASK_CREATED",
            "started": "TASK_STARTED",
            "completed": "TASK_COMPLETED",
            "failed": "TASK_FAILED",
        }.get(status)
        if event is None:
            raise ValueError(f"unsupported MetaGPT task status: {status}")
        self.context.record_task(TaskRecord(task, owner=owner, attributes=attributes), event_type=event)
        return task

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
        message = self.entity("message", message_id, name="MetaGPT message", attributes={"provider": "metagpt"})
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

    def observe_message_object(self, message_object: Any, *, task: EntityRef | None = None, **attributes: Any) -> EntityRef:
        """Observe a current ``metagpt.schema.Message`` instance."""
        self._message_counter += 1
        message_id = getattr(message_object, "id", None) or f"message-{self._message_counter}"
        source_name = getattr(message_object, "sent_from", None)
        target_name = getattr(message_object, "send_to", None)
        source = self._roles.get(str(source_name)) if source_name else None
        target = self._roles.get(str(target_name)) if isinstance(target_name, str) else None
        return self.observe_message(
            message_id,
            source=source,
            target=target,
            content=_text(getattr(message_object, "content", None)),
            role=_text(getattr(message_object, "role", None)),
            task=task,
            cause_by=_text(getattr(message_object, "cause_by", None)),
            metadata=getattr(message_object, "metadata", None),
            message_type=type(message_object).__name__,
            **attributes,
        )

    def observe_action(
        self,
        action_id: str | int,
        *,
        owner: EntityRef | None,
        task: EntityRef | None = None,
        status: str = "started",
        **attributes: Any,
    ) -> EntityRef:
        action = self.entity("task", action_id, name="MetaGPT action", attributes={"provider": "metagpt", "action": True, **attributes})
        event = "TASK_STARTED" if status == "started" else "TASK_COMPLETED" if status == "completed" else "TASK_FAILED" if status == "failed" else "TASK_UPDATED"
        self.emit(event, event, source=owner, target=action, attributes={"action_id": action.id, "task_id": task.id if task else None, **attributes})
        return action

    def observe_action_object(self, action_object: Any, *, owner: EntityRef | None, task: EntityRef | None = None, status: str = "started", **attributes: Any) -> EntityRef:
        action_id = getattr(action_object, "name", None) or type(action_object).__name__
        return self.observe_action(action_id, owner=owner, task=task, status=status, action_type=type(action_object).__name__, **attributes)

    def observe_model_call(
        self,
        call_id: str | int,
        *,
        role: EntityRef | None,
        model_id: str | int,
        request: Any | None = None,
        response: Any | None = None,
        status: str = "request",
        **attributes: Any,
    ) -> EntityRef:
        model = self.model(model_id, provider="metagpt", **attributes)
        call = self.entity("model_call", call_id, name="MetaGPT model call", attributes={"provider": "metagpt"})
        self.context.record_model_call(
            ModelCallRecord(
                call,
                role,
                model,
                request=request,
                response=response,
                status=status,
                content_kind="model_request" if status == "request" else "model_response",
                attributes=attributes,
            )
        )
        return call

    def observe_parser_failure(
        self,
        failure_id: str | int,
        *,
        role: EntityRef | None,
        error: str,
        task: EntityRef | None = None,
        **attributes: Any,
    ) -> EntityRef:
        failure = self.entity("parser_failure", failure_id, name="MetaGPT structured-output parser failure", attributes={"provider": "metagpt"})
        self.emit("TASK_FAILED", "PARSER_FAILURE", source=role, target=failure, attributes={"task_id": task.id if task else None, "error": error, **attributes})
        return failure

    def observe_retry(
        self,
        retry_id: str | int,
        *,
        role: EntityRef | None,
        task: EntityRef | None = None,
        **attributes: Any,
    ) -> EntityRef:
        retry = self.entity("task", retry_id, name="MetaGPT retry", attributes={"provider": "metagpt", "retry": True})
        self.emit("TASK_UPDATED", "RETRY_REQUESTED", source=role, target=retry, attributes={"task_id": task.id if task else None, **attributes})
        return retry


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
