"""CAMEL Workforce adapter over authoritative callback/model boundaries."""

from __future__ import annotations

import importlib.metadata
from typing import Any

from .base import AdapterCapabilities, AdapterContext, AgentRecord, EntityRef, FrameworkAdapter, FrameworkCompatibility, MessageRecord, ModelCallRecord, ProcessRef, TaskRecord


class CAMELAdapter(FrameworkAdapter):
    framework_name = "camel"
    capabilities = AdapterCapabilities(
        events=("AGENT_CREATED", "AGENT_STARTED", "AGENT_STOPPED", "TASK_CREATED", "TASK_ASSIGNED", "TASK_STARTED", "TASK_UPDATED", "TASK_COMPLETED", "TASK_FAILED", "TASK_CONTENT_RECORDED", "MESSAGE_SENT", "MESSAGE_RECEIVED", "MESSAGE_UNROUTED", "MODEL_REQUEST", "MODEL_RESPONSE", "MODEL_FAILURE"),
        content_modes=("metadata_only", "content_ref_only", "prompt_only", "prompt_and_response"),
        authoritative_surfaces=("camel.societies.workforce.WorkforceCallback", "camel.models.BaseModelBackend.run", "camel.models.BaseModelBackend.arun"),
        known_limitations=("WorkforceCallback LogEvent does not expose the emitting worker or recipient; those log messages are explicitly marked MESSAGE_UNROUTED and correlated to the observed process instead of being assigned to a guessed agent.", "A created worker is not treated as assigned until CAMEL reports a task assignment."),
    )

    def __init__(self, context: AdapterContext) -> None:
        super().__init__(context)
        self._agents: dict[str, EntityRef] = {}
        self._tasks: dict[str, EntityRef] = {}
        self._active_tasks_by_agent: dict[str, EntityRef] = {}
        self._message_counter = 0

    @classmethod
    def compatibility(cls) -> FrameworkCompatibility:
        try:
            version = importlib.metadata.version("camel-ai")
        except importlib.metadata.PackageNotFoundError:
            version = None
        status = "verified" if version in {"0.2.84", "0.2.91a7"} else ("warn" if version else "unknown")
        return FrameworkCompatibility(framework=cls.framework_name, detected_version=version, tested_versions=("0.2.84", "0.2.91a7"), compatibility_status=status, capabilities=cls.capabilities, known_limitations=cls.capabilities.known_limitations)

    def agent_created(self, native_id: str | int, *, name: str | None = None, role: str | None = None, process: ProcessRef | None = None, parent: EntityRef | None = None, **attributes: Any) -> EntityRef:
        agent = self.agent(native_id, name=name, role=role, provider="camel", **attributes)
        self._agents[str(native_id)] = agent
        self.context.record_agent(AgentRecord(agent, role=role, process=process, parent_agent=parent, attributes=attributes))
        return agent

    def agent_started(self, agent: EntityRef, **attributes: Any) -> None:
        self.emit("AGENT_STARTED", "AGENT_STARTED", source=agent, attributes=attributes)

    def agent_stopped(self, agent: EntityRef, **attributes: Any) -> None:
        self.emit("AGENT_STOPPED", "AGENT_STOPPED", source=agent, attributes=attributes)

    def task_event(self, event_type: str, native_id: str | int, *, name: str | None = None, owner: EntityRef | None = None, parent: EntityRef | None = None, content: str | None = None, content_kind: str = "task_prompt", **attributes: Any) -> EntityRef:
        existing = self._tasks.get(str(native_id))
        if existing is not None and name is None and content is None and not attributes:
            task = existing
        else:
            entity_attributes = dict(attributes)
            if content is not None and self.context.capture_policy.mode in {
                "prompt_only",
                "prompt_and_response",
            }:
                entity_attributes.setdefault("task_prompt", content)
            task = self.task(native_id, name=name, provider="camel", **entity_attributes)
        self._tasks[str(native_id)] = task
        self.context.record_task(
            TaskRecord(
                task,
                owner=owner,
                parent_task=parent,
                content=content,
                content_kind=content_kind,
                attributes=attributes,
            ),
            event_type=event_type,
        )
        return task

    def task_created(self, native_id: str | int, **kwargs: Any) -> EntityRef:
        return self.task_event("TASK_CREATED", native_id, **kwargs)

    def task_assigned(self, task: EntityRef, agent: EntityRef, **attributes: Any) -> None:
        self._active_tasks_by_agent[agent.id] = task
        self.emit("TASK_ASSIGNED", "ASSIGNED_TO", source=task, target=agent, attributes=attributes)

    def active_task_for(self, agent: EntityRef | None) -> EntityRef | None:
        """Return the latest provider-observed task assigned to an agent."""
        return self._active_tasks_by_agent.get(agent.id) if agent is not None else None

    def task_started(self, task: EntityRef, agent: EntityRef | None = None, **attributes: Any) -> None:
        self.emit("TASK_STARTED", "TASK_STARTED", source=agent or task, target=task, attributes=attributes)

    def task_updated(self, task: EntityRef, **attributes: Any) -> None:
        self.emit("TASK_UPDATED", "TASK_UPDATED", source=task, attributes=attributes)

    def task_completed(self, task: EntityRef, agent: EntityRef | None = None, **attributes: Any) -> None:
        self.emit("TASK_COMPLETED", "TASK_COMPLETED", source=agent or task, target=task, attributes=attributes)

    def task_failed(self, task: EntityRef, agent: EntityRef | None = None, **attributes: Any) -> None:
        self.emit("TASK_FAILED", "TASK_FAILED", source=agent or task, target=task, attributes=attributes)

    def message(self, message_id: str | int, source: EntityRef | None, target: EntityRef | None, *, content: str | None = None, role: str | None = None, task: EntityRef | None = None, received: bool = False, **attributes: Any) -> EntityRef:
        message = self.entity("message", message_id, name="CAMEL message", attributes={"provider": "camel"})
        self.context.record_message(MessageRecord(message, source, target, role=role, task=task, content=content, direction="received" if received else "sent", attributes=attributes))
        return message

    def message_unrouted(self, message: EntityRef, *, callback_name: str, missing_sender: bool, missing_recipient: bool, reason: str = "callback_payload_missing_agent_boundary") -> None:
        """Keep callback messages visible without inventing an agent route.

        CAMEL's WorkforceCallback log surface can emit a message without a
        worker or recipient.  The process is the only authoritative boundary
        available in that case, so record that boundary explicitly rather
        than leaving the message looking like a dropped graph node.
        """
        process = self.context.process
        if process is None:
            return
        self.emit(
            "MESSAGE_UNROUTED",
            "OBSERVED_AT_PROCESS",
            source=message,
            target=process.to_entity(),
            attributes={
                "callback_name": callback_name,
                "routing_status": "unrouted",
                "routing_reason": reason,
                "missing_sender": missing_sender,
                "missing_recipient": missing_recipient,
                "routing_basis": "authoritative_process_boundary",
            },
        )

    def model_call(self, call_id: str | int, agent: EntityRef | None, model_id: str | int, *, model_name: str | None = None, request: Any | None = None, response: Any | None = None, status: str = "request", task: EntityRef | None = None, **attributes: Any) -> EntityRef:
        model = self.model(model_id, name=model_name, provider="camel", **attributes)
        call = self.entity("model_call", call_id, name="CAMEL model call", attributes={"provider": "camel"})
        self.context.record_model_call(ModelCallRecord(call, agent, model, request=request, response=response, content_kind="model_request" if status == "request" else "model_response", status=status, task=task, attributes=attributes))
        return call

    def workforce_callback(self) -> Any:
        """Build a callback compatible with the installed CAMEL Workforce."""
        module = __import__("camel.societies.workforce.workforce_callback", fromlist=["WorkforceCallback"])
        base = module.WorkforceCallback
        methods = {name: _callback_method(name, self) for name in getattr(base, "__abstractmethods__", frozenset())}
        for name in ("log_worker_created", "log_task_created", "log_task_assigned", "log_task_started", "log_task_updated", "log_task_completed", "log_task_failed"):
            methods[name] = _callback_method(name, self)
        return type("ExecWeaveCAMELWorkforceCallback", (base,), methods)()

    def _callback_event(self, name: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
        payload = _payload(args, kwargs)
        if name in {"log_message", "log_stream_chunk"}:
            content = _string(_value(payload, "message", "text"))
            native_message_id = _value(payload, "message_id", "id", "task_id", "worker_id")
            self._message_counter += 1
            message_id = (
                native_message_id
                if isinstance(native_message_id, (str, int)) and str(native_message_id)
                else f"{self.framework_name}-message-{self._message_counter}"
            )
            worker_id = _value(payload, "worker_id", "agent_id")
            source = self._agents.get(str(worker_id)) if worker_id is not None else None
            target_id = _value(payload, "target_worker_id", "recipient_worker_id", "target_agent_id", "recipient_agent_id", "receiver_id")
            target = self._agents.get(str(target_id)) if target_id is not None else None
            message = self.message(
                message_id,
                source,
                target,
                content=content,
                role="stream" if name == "log_stream_chunk" else "log",
                attributes={
                    "callback_name": name,
                    "event_type": _value(payload, "event_type"),
                    "metadata": _value(payload, "metadata"),
                    "message_id_source": "provider" if native_message_id is not None else "execweave_derived",
                },
            )
            if source is None or target is None:
                self.message_unrouted(
                    message,
                    callback_name=name,
                    missing_sender=source is None,
                    missing_recipient=target is None,
                )
            return message
        if name == "log_task_decomposed":
            parent_key = _native(payload, "parent_task_id", "task_id", "id")
            parent = self._tasks.get(str(parent_key)) or self.task_created(parent_key)
            subtasks = _value(payload, "subtask_ids")
            for subtask_key in subtasks if isinstance(subtasks, list) else []:
                self.task_event("TASK_CREATED", subtask_key, parent=parent)
            return self.task_updated(parent, callback_name=name, subtask_ids=subtasks)
        if name == "log_worker_deleted":
            worker_key = _native(payload, "worker_id", "id", "name")
            agent = self._agents.get(str(worker_key)) or self.agent_created(worker_key)
            return self.agent_stopped(agent, reason=_value(payload, "reason"))
        if name == "log_all_tasks_completed":
            task_key = _value(payload, "task_id")
            if task_key is not None:
                task = self._tasks.get(str(task_key)) or self.task_created(task_key)
                return self.task_completed(task, callback_name=name)
            return self.emit("TASK_COMPLETED", "ALL_TASKS_COMPLETED", attributes={"callback_name": name})
        if name == "log_worker_created":
            return self.agent_created(_native(payload, "worker_id", "id", "name"), name=_string(_value(payload, "name", "role")), role=_string(_value(payload, "role", "worker_type")))
        if name == "log_task_created":
            task_key = _native(payload, "task_id", "id", "name")
            existing = self._tasks.get(str(task_key))
            if existing is not None:
                return existing
            return self.task_created(task_key, name=_string(_value(payload, "name", "description")))
        if name == "log_task_assigned":
            task_key = _native(payload, "task_id", "id", "name")
            task = self._tasks.get(str(task_key)) or self.task_created(task_key)
            worker_value = kwargs.get("worker") or kwargs.get("agent") or payload
            agent_key = _native(worker_value, "worker_id", "agent_id", "id", "name")
            agent = self._agents.get(str(agent_key)) or self.agent_created(agent_key, name=_string(_value(worker_value, "name", "role")))
            return self.task_assigned(task, agent)
        task_value = kwargs.get("task") or payload
        task_key = _native(task_value, "task_id", "id", "name")
        task = self._tasks.get(str(task_key)) or self.task_created(task_key)
        if name == "log_task_started":
            return self.task_started(task)
        if name == "log_task_updated":
            return self.task_updated(task, callback_name=name)
        if name == "log_task_completed":
            return self.task_completed(task)
        if name == "log_task_failed":
            return self.task_failed(task)
        return self.emit("TASK_UPDATED", "CALLBACK_OBSERVED", attributes={"callback_name": name, "argument_count": len(args)})


def _callback_method(name: str, adapter: CAMELAdapter):
    def callback(*args: Any, **kwargs: Any) -> Any:
        return adapter._callback_event(name, args, kwargs)
    return callback


def _payload(args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
    if args:
        return args[-1]
    for value in reversed(args):
        if isinstance(value, (dict, str, int)):
            return value
    for key in ("task", "worker", "agent", "model", "message", "task_id", "worker_id"):
        if key in kwargs:
            return kwargs[key]
    return kwargs


def _value(value: Any, *keys: str) -> Any:
    if isinstance(value, dict):
        for key in keys:
            if key in value:
                return value[key]
    for key in keys:
        candidate = getattr(value, key, None)
        if candidate is not None:
            return candidate
    return value if isinstance(value, (str, int, float, bool)) else None


def _native(value: Any, *keys: str) -> str | int:
    candidate = _value(value, *keys)
    return candidate if isinstance(candidate, (str, int)) and str(candidate) else str(candidate)


def _string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
