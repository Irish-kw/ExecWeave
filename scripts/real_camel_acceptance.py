"""Run a real CAMEL Workforce + Ollama adapter acceptance.

This script is intentionally framework-native: lifecycle records come from
CAMEL's WorkforceCallback and model records come from the BaseModelBackend
run/arun boundary. It does not infer semantics from stdout or the graph.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

# ruff: noqa: E402
import psutil

from execweave.framework_adapters import (
    AdapterContext,
    CAMELAdapter,
    ContentCapturePolicy,
    ProcessRef,
)
from camel.models import OllamaModel


def _json_default(value: Any) -> str:
    return str(value)


class ObservedOllamaModel(OllamaModel):
    """CAMEL model backend wrapper that records the authoritative model boundary."""

    def __init__(self, *, model_type: str, url: str, adapter: CAMELAdapter, agent_holder: dict[str, Any]):
        self._adapter = adapter
        self._agent_holder = agent_holder
        self._counter = 0
        super().__init__(
            model_type=model_type,
            model_config_dict={"temperature": 0, "max_tokens": 128, "stream": False},
            url=url,
            timeout=120,
            max_retries=1,
        )

    def _begin(self, messages: list[Any]) -> str:
        self._counter += 1
        call_id = f"camel-ollama-call-{self._counter}"
        self._adapter.model_call(
            call_id,
            self._agent_holder.get("ref"),
            str(self.model_type),
            status="request",
            request=json.loads(json.dumps(messages, ensure_ascii=False, default=_json_default)),
            request_message_count=len(messages),
            task=self._adapter.active_task_for(self._agent_holder.get("ref")),
            endpoint=self._url,
            boundary="camel.BaseModelBackend.run",
        )
        return call_id

    def _finish(self, call_id: str, result: Any, *, failure: BaseException | None = None) -> None:
        self._adapter.model_call(
            call_id,
            self._agent_holder.get("ref"),
            str(self.model_type),
            status="failure" if failure is not None else "response",
            response=json.loads(json.dumps(result, ensure_ascii=False, default=_json_default)) if failure is None else None,
            response_observed=failure is None,
            failure_type=type(failure).__name__ if failure is not None else None,
            result_type=type(result).__name__ if result is not None else None,
            task=self._adapter.active_task_for(self._agent_holder.get("ref")),
            boundary="camel.BaseModelBackend.run",
        )

    def run(self, messages: list[Any], response_format: Any = None, tools: Any = None) -> Any:
        call_id = self._begin(messages)
        try:
            result = super().run(messages, response_format=response_format, tools=tools)
        except BaseException as exc:
            self._finish(call_id, None, failure=exc)
            raise
        self._finish(call_id, result)
        return result

    async def arun(self, messages: list[Any], response_format: Any = None, tools: Any = None) -> Any:
        call_id = self._begin(messages)
        try:
            result = await super().arun(messages, response_format=response_format, tools=tools)
        except BaseException as exc:
            self._finish(call_id, None, failure=exc)
            raise
        self._finish(call_id, result)
        return result

def _records(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--endpoint", default="http://127.0.0.1:12345/v1")
    parser.add_argument("--model", default="llama3.1:8b")
    args = parser.parse_args()

    from camel.agents import ChatAgent
    from camel.societies import Workforce
    from camel.tasks import Task
    from camel.tasks.task import TaskState

    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    sidecar = output / "semantic.jsonl"
    process = psutil.Process(os.getpid())
    process_ref = ProcessRef(process.pid, process.create_time(), sys.executable)
    context = AdapterContext(
        framework="camel",
        run_id="camel-real-ollama-12345",
        session_id="camel-real-ollama-12345",
        sidecar=sidecar,
        content_root=output,
        capture_policy=ContentCapturePolicy("prompt_and_response"),
        process=process_ref,
    )
    adapter = CAMELAdapter(context)
    callback = adapter.workforce_callback()

    coordinator_holder: dict[str, Any] = {}
    planner_holder: dict[str, Any] = {}
    coordinator = adapter.agent_created(
        "coordinator", name="CAMEL Workforce Coordinator", role="coordinator", process=process_ref
    )
    planner = adapter.agent_created(
        "task-planner", name="CAMEL Task Planner", role="planner", process=process_ref
    )
    coordinator_holder["ref"] = coordinator
    planner_holder["ref"] = planner

    coordinator_model = ObservedOllamaModel(
        model_type=args.model, url=args.endpoint, adapter=adapter, agent_holder=coordinator_holder
    )
    planner_model = ObservedOllamaModel(
        model_type=args.model, url=args.endpoint, adapter=adapter, agent_holder=planner_holder
    )
    coordinator_agent = ChatAgent(
        system_message="Assign each pipeline task to the best worker. Return only valid structured assignments.",
        model=coordinator_model,
        max_iteration=1,
    )
    planner_agent = ChatAgent(
        system_message="Plan the task briefly and return a concise actionable result.",
        model=planner_model,
        max_iteration=1,
    )
    workforce = Workforce(
        "CAMEL ExecWeave real acceptance workforce",
        coordinator_agent=coordinator_agent,
        task_agent=planner_agent,
        callbacks=[callback],
        default_model=planner_model,
        task_timeout_seconds=120,
        use_structured_output_handler=True,
    )

    worker_holders: list[dict[str, Any]] = []
    for description in ("evidence worker", "summary worker"):
        holder: dict[str, Any] = {}
        worker_holders.append(holder)
        worker_model = ObservedOllamaModel(
            model_type=args.model, url=args.endpoint, adapter=adapter, agent_holder=holder
        )
        worker = ChatAgent(
            system_message=f"You are the {description}. Return one concise sentence.",
            model=worker_model,
            max_iteration=1,
        )
        workforce.add_single_agent_worker(description, worker)
        node = workforce._children[-1]
        holder["ref"] = adapter.entity("agent", node.node_id, name=description, attributes={"provider": "camel"})

    pipeline_prompts = [
        f"Write one concise factual sentence explaining that this acceptance uses the local Ollama endpoint at {args.endpoint}.",
        f"Write one concise factual sentence explaining that the model under test is {args.model}.",
    ]
    workforce.add_parallel_pipeline_tasks(
        pipeline_prompts,
        auto_depend=False,
        task_id_prefix="camel-real",
    ).pipeline_build()
    root = Task(content="Run the two independent acceptance checks and report completion.", id="camel-real-root")
    root_ref = adapter.task_created(
        root.id,
        name=root.content,
        owner=coordinator,
        content=root.content,
        lifecycle_source="execweave_workforce_entrypoint",
        ownership_basis="configured_coordinator",
    )
    for index, prompt in enumerate(pipeline_prompts):
        adapter.task_created(
            f"camel-real_{index}_0",
            name=prompt,
            content=prompt,
            content_kind="task_prompt",
            task_source="workforce_pipeline_definition",
        )
    adapter.task_assigned(
        root_ref,
        coordinator,
        assignment_source="execweave_workforce_entrypoint",
    )
    adapter.task_started(
        root_ref,
        coordinator,
        lifecycle_source="execweave_workforce_entrypoint",
    )

    try:
        result = workforce.process_task(root)
        result_state = result.state.value if isinstance(result.state, TaskState) else str(result.state)
        result_payload = {"id": result.id, "state": result_state, "result_present": bool(result.result)}
        if str(result_state).upper() == "DONE":
            adapter.task_completed(
                root_ref,
                coordinator,
                lifecycle_source="execweave_workforce_entrypoint",
            )
        else:
            adapter.task_failed(
                root_ref,
                coordinator,
                lifecycle_source="execweave_workforce_entrypoint",
                state=result_state,
            )
    except BaseException as exc:
        adapter.task_failed(
            root_ref,
            coordinator,
            lifecycle_source="execweave_workforce_entrypoint",
            error_type=type(exc).__name__,
        )
        result_payload = {"state": "EXCEPTION", "exception": type(exc).__name__, "message": str(exc)}
        raise
    finally:
        try:
            workforce.stop()
        except Exception:
            pass

    records = _records(sidecar)
    event_types = [record["event_type"] for record in records]
    expected = [
        {"ground_truth_id": "coordinator", "ground_truth_type": "agent", "expected_node": coordinator.id, "expected_relation": "AGENT_CREATED"},
        {"ground_truth_id": "task-planner", "ground_truth_type": "agent", "expected_node": planner.id, "expected_relation": "AGENT_CREATED"},
        {"ground_truth_id": "camel-real-root", "ground_truth_type": "task", "expected_node": "camel-real-root", "expected_relation": "TASK_CREATED"},
    ]
    (output / "ground_truth.jsonl").write_text(
        "".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in expected),
        encoding="utf-8",
    )
    summary = {
        "framework": "camel",
        "framework_version": "0.2.91a7",
        "model": args.model,
        "endpoint": args.endpoint,
        "result": result_payload,
        "task_done": str(result_payload.get("state", "")).upper() == "DONE",
        "event_count": len(records),
        "event_types": event_types,
        "agent_created_count": event_types.count("AGENT_CREATED"),
        "model_request_count": event_types.count("MODEL_REQUEST"),
        "model_response_count": event_types.count("MODEL_RESPONSE"),
        "task_assigned_count": event_types.count("TASK_ASSIGNED"),
        "process_pid": process.pid,
        "capture_mode": "prompt_and_response",
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=_json_default), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
