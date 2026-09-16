
"""Run a real AutoGen AgentChat + Ollama adapter acceptance."""
from __future__ import annotations

# ruff: noqa: E402
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if os.environ.get("EXECWEAVE_AUTOGEN_SITE"):
    sys.path.insert(0, os.environ["EXECWEAVE_AUTOGEN_SITE"])
sys.path.insert(0, str(ROOT / "src"))

import psutil
from autogen_agentchat.agents import AssistantAgent, SocietyOfMindAgent
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_ext.models.ollama import OllamaChatCompletionClient
from autogen_ext.models.ollama._model_info import get_info

from execweave.framework_adapters import (
    AdapterContext,
    AutoGenAdapter,
    ContentCapturePolicy,
    ProcessRef,
)


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(child) for key, child in value.items()}
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return _jsonable(model_dump())
    return str(value)


class ObservedOllamaClient(OllamaChatCompletionClient):
    """Capture the official AutoGen Ollama client create boundary."""

    def __init__(self, *, model: str, host: str, adapter: AutoGenAdapter, agent_ref: Any):
        self._adapter = adapter
        self._agent_ref = agent_ref
        self._model = model
        self._counter = 0
        super().__init__(
            model=model,
            host=host,
            model_info=get_info(model),
            options={"temperature": 0, "num_predict": 160},
        )

    async def create(self, messages: Any, **kwargs: Any) -> Any:
        self._counter += 1
        call_id = f"autogen-{self._agent_ref.id}-call-{self._counter}"
        boundary = "autogen_ext.models.ollama.OllamaChatCompletionClient.create"
        # The coordinator actually consumes these peer messages in its model
        # context. Record the recipient here; a team output stream alone cannot
        # establish which agent received a broadcast.
        if self._agent_ref.attributes.get("agent_role") == "root":
            for index, message in enumerate(messages):
                sender = self._adapter._agents.get(str(getattr(message, "source", "")))
                if sender is not None and sender.id != self._agent_ref.id:
                    self._adapter.observe_message(
                        f"{call_id}-input-{index}", source=sender, target=self._agent_ref,
                        content=str(getattr(message, "content", "")), role="agent", received=True,
                        routing_source="society_of_mind_model_context",
                    )
        self._adapter.observe_model_call(
            call_id,
            agent=self._agent_ref,
            model_id=self._model,
            request={
                "messages": _jsonable(messages),
                "message_types": [type(message).__name__ for message in messages],
            },
            status="request",
            boundary=boundary,
        )
        try:
            result = await super().create(messages, **kwargs)
        except BaseException as exc:
            self._adapter.observe_model_call(
                call_id,
                agent=self._agent_ref,
                model_id=self._model,
                response={"failure_type": type(exc).__name__},
                status="failure",
                boundary=boundary,
            )
            raise
        self._adapter.observe_model_call(
            call_id,
            agent=self._agent_ref,
            model_id=self._model,
            response=_jsonable(result),
            status="response",
            boundary=boundary,
        )
        return result


async def _close(client: Any) -> None:
    close = getattr(client, "close", None)
    if close is not None:
        result = close()
        if hasattr(result, "__await__"):
            await result


async def run_acceptance(args: argparse.Namespace) -> dict[str, Any]:
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    sidecar = Path(os.environ.get("EXECWEAVE_SEMANTIC_SIDECAR") or output / "semantic.jsonl")
    process = psutil.Process(os.getpid())
    process_ref = ProcessRef(process.pid, process.create_time(), sys.executable)
    context = AdapterContext(
        framework="autogen",
        run_id=os.environ.get("EXECWEAVE_RUN_ID") or "autogen-real-ollama-12345",
        session_id=os.environ.get("EXECWEAVE_SESSION_ID") or "autogen-real-ollama-12345",
        sidecar=sidecar,
        content_root=sidecar.parent,
        capture_policy=ContentCapturePolicy("prompt_and_response"),
        process=process_ref,
    )
    adapter = AutoGenAdapter(context)
    coordinator_ref = adapter.observe_agent(
        "coordinator", name="coordinator", role="SocietyOfMindAgent", process=process_ref,
        agent_role="root", agent_path="/root",
    )
    task_prompt = (
        f"Collaborate on a factual acceptance run using the local Ollama endpoint "
        f"at {args.endpoint}. The model under test is {args.model}. "
        "Both analysts must contribute at least one sentence."
    )
    task = adapter.observe_task(
        "autogen-real-task",
        owner=coordinator_ref,
        name="AutoGen local Ollama collaboration",
        content=task_prompt,
        model=args.model,
        task_contract="two named analysts exchange factual statements",
    )
    agent_refs = {
        "evidence_agent": adapter.observe_agent(
            "evidence_agent",
            name="evidence_agent",
            role="evidence_analyst",
            process=process_ref,
        ),
        "summary_agent": adapter.observe_agent(
            "summary_agent",
            name="summary_agent",
            role="summary_analyst",
            process=process_ref,
        ),
    }
    for agent in agent_refs.values():
        context.emit(
            "TASK_ASSIGNED",
            "ASSIGNED_TO",
            source=task,
            target=agent,
            attributes={
                "assignment_source": "autogen_round_robin_group_chat",
                "broadcast": True,
            },
        )
        context.emit(
            "TASK_STARTED",
            "TASK_STARTED",
            source=agent,
            target=task,
            attributes={
                "lifecycle_source": "autogen_round_robin_group_chat",
                "broadcast": True,
            },
        )
    for agent in agent_refs.values():
        context.emit("AGENT_STARTED", "AGENT_STARTED", source=agent)

    clients = [
        ObservedOllamaClient(
            model=args.model,
            host=args.endpoint.rstrip("/"),
            adapter=adapter,
            agent_ref=agent_refs["evidence_agent"],
        ),
        ObservedOllamaClient(
            model=args.model,
            host=args.endpoint.rstrip("/"),
            adapter=adapter,
            agent_ref=agent_refs["summary_agent"],
        ),
    ]
    class ObservedAssistantAgent(AssistantAgent):
        async def on_messages_stream(self, messages, cancellation_token):
            for message in messages:
                adapter.observe_agentchat_event(
                    message, target=agent_refs[self.name], task=task, received=True,
                    routing_source="AssistantAgent.on_messages_stream",
                )
            async for event in super().on_messages_stream(messages, cancellation_token):
                yield event

    evidence_agent = ObservedAssistantAgent(
        name="evidence_agent",
        model_client=clients[0],
        system_message=(
            "You are the evidence analyst. Reply with one concise factual sentence "
            "about the requested local Ollama acceptance. Do not mention hidden reasoning."
        ),
    )
    summary_agent = ObservedAssistantAgent(
        name="summary_agent",
        model_client=clients[1],
        system_message=(
            "You are the summary analyst. Reply with one concise sentence that "
            "acknowledges the other analyst and states the model under test."
        ),
    )
    team = RoundRobinGroupChat(
        [evidence_agent, summary_agent],
        name="execweave-autogen-acceptance",
        max_turns=4,
    )
    coordinator_client = ObservedOllamaClient(
        model=args.model, host=args.endpoint.rstrip("/"), adapter=adapter, agent_ref=coordinator_ref,
    )
    clients.append(coordinator_client)
    coordinator = SocietyOfMindAgent("coordinator", team, model_client=coordinator_client)

    result = None
    stream_event_types: list[str] = []
    try:
        async for item in coordinator.run_stream(
            task=task_prompt
        ):
            event_name = type(item).__name__
            stream_event_types.append(event_name)
            if event_name == "TaskResult":
                result = item
            else:
                adapter.observe_agentchat_event(item, task=task)
        message_sources = [
            str(getattr(item, "source", ""))
            for item in (getattr(result, "messages", []) or [])
            if getattr(item, "source", None)
        ]
        task_success = result is not None and all(
            source in message_sources for source in agent_refs
        )
        context.emit(
            "TASK_COMPLETED" if task_success else "TASK_FAILED",
            "TASK_COMPLETED" if task_success else "TASK_FAILED",
            source=task,
            attributes={
                "result_present": result is not None,
                "message_count": len(getattr(result, "messages", []) or []),
                "stop_reason": getattr(result, "stop_reason", None),
                "required_agent_sources_present": task_success,
            },
        )
    except BaseException as exc:
        context.emit(
            "TASK_FAILED",
            "TASK_FAILED",
            source=task,
            attributes={"exception_type": type(exc).__name__},
        )
        raise
    finally:
        for agent in agent_refs.values():
            context.emit("AGENT_STOPPED", "AGENT_STOPPED", source=agent)
        for client in clients:
            await _close(client)

    records = [
        json.loads(line)
        for line in sidecar.read_text(encoding="utf-8").splitlines()
        if line
    ]
    event_types = [record["event_type"] for record in records]
    expected = [
        {
            "ground_truth_id": "evidence_agent",
            "ground_truth_type": "agent",
            "expected_relation": "AGENT_CREATED",
        },
        {
            "ground_truth_id": "summary_agent",
            "ground_truth_type": "agent",
            "expected_relation": "AGENT_CREATED",
        },
        {
            "ground_truth_id": "autogen-real-task",
            "ground_truth_type": "task",
            "expected_relation": "TASK_CREATED",
        },
        {
            "ground_truth_id": "autogen-model-boundary",
            "ground_truth_type": "model",
            "expected_relation": "MODEL_REQUEST+MODEL_RESPONSE",
        },
        {
            "ground_truth_id": "autogen-agentchat-stream",
            "ground_truth_type": "message",
            "expected_relation": "MESSAGE_SENT",
        },
    ]
    (output / "ground_truth.jsonl").write_text(
        "".join(
            json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n"
            for item in expected
        ),
        encoding="utf-8",
    )
    summary = {
        "framework": "autogen",
        "framework_version": "0.7.5",
        "model": args.model,
        "endpoint": args.endpoint,
        "result_present": result is not None,
        "stop_reason": getattr(result, "stop_reason", None),
        "stream_event_types": stream_event_types,
        "event_count": len(records),
        "agent_created_count": event_types.count("AGENT_CREATED"),
        "message_sent_count": event_types.count("MESSAGE_SENT"),
        "model_request_count": event_types.count("MODEL_REQUEST"),
        "model_response_count": event_types.count("MODEL_RESPONSE"),
        "model_failure_count": event_types.count("MODEL_FAILURE"),
        "task_completed_count": event_types.count("TASK_COMPLETED"),
        "task_failed_count": event_types.count("TASK_FAILED"),
        "task_success": any(
            record["event_type"] == "TASK_COMPLETED"
            and record["attributes"].get("required_agent_sources_present") is True
            for record in records
        ),
        "capture_mode": "prompt_and_response",
        "process_pid": process.pid,
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--endpoint", default="http://127.0.0.1:12345")
    parser.add_argument("--model", default="llama3.1:8b")
    args = parser.parse_args()
    summary = asyncio.run(run_acceptance(args))
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0 if summary["task_success"] and summary["model_response_count"] > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
