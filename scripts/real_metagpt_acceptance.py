
"""Run a real MetaGPT Role + ActionNode + Ollama adapter acceptance."""
from __future__ import annotations

# ruff: noqa: E402
import argparse
import atexit
import asyncio
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
_configured_root = os.environ.get("EXECWEAVE_METAGPT_CONFIG_ROOT")
if _configured_root:
    _metagpt_root = Path(_configured_root).expanduser().resolve()
else:
    _metagpt_root = Path(tempfile.mkdtemp(prefix="execweave-metagpt-"))
    (_metagpt_root / "config").mkdir(parents=True, exist_ok=True)
    (_metagpt_root / "config" / "config2.yaml").write_text(
        "llm:\n"
        "  api_key: ollama-local\n"
        "  api_type: ollama\n"
        "  base_url: http://127.0.0.1:12345/api\n"
        "  model: llama3.1:8b\n"
        "  stream: false\n"
        "  timeout: 120\n"
        "  max_token: 160\n"
        "  temperature: 0.0\n"
        "prompt_schema: raw\n",
        encoding="utf-8",
    )
    atexit.register(shutil.rmtree, _metagpt_root, ignore_errors=True)
os.environ["METAGPT_PROJECT_ROOT"] = str(_metagpt_root)

from metagpt.actions import Action
from metagpt.actions.add_requirement import UserRequirement
from metagpt.actions.action_node import ActionNode
from metagpt.config2 import Config
from metagpt.context import Context
from metagpt.provider.ollama_api import OllamaLLM
from metagpt.roles import Role
from metagpt.schema import Message

sys.path.insert(0, str(ROOT / "src"))
from execweave.framework_adapters import (
    AdapterContext,
    ContentCapturePolicy,
    MetaGPTAdapter,
    ProcessRef,
)


class ObservedOllamaLLM(OllamaLLM):
    """Capture MetaGPT's public BaseLLM.aask boundary around real Ollama calls."""

    def __init__(self, config: Any, *, adapter: MetaGPTAdapter, role_ref: Any):
        self._adapter = adapter
        self._role_ref = role_ref
        self._counter = 0
        self._request_count = 0
        self._response_count = 0
        self._failure_count = 0
        super().__init__(config)

    async def aask(self, msg: Any, system_msgs=None, format_msgs=None, images=None, timeout=0, stream=None) -> str:
        self._counter += 1
        self._request_count += 1
        call_id = f"metagpt-ollama-call-{self._counter}"
        boundary = "metagpt.provider.base_llm.BaseLLM.aask"
        self._adapter.observe_model_call(
            call_id,
            role=self._role_ref,
            model_id=self.model,
            request={
                "message_type": type(msg).__name__,
                "message_count": len(msg) if isinstance(msg, list) else 1,
                "system_message_count": len(system_msgs or []),
                "format_message_count": len(format_msgs or []),
                "stream": bool(stream) if stream is not None else bool(self.config.stream),
            },
            status="request",
            boundary=boundary,
        )
        try:
            response = await super().aask(
                msg,
                system_msgs=system_msgs,
                format_msgs=format_msgs,
                images=images,
                timeout=timeout,
                stream=stream,
            )
        except BaseException as exc:
            self._failure_count += 1
            self._adapter.observe_model_call(
                call_id,
                role=self._role_ref,
                model_id=self.model,
                response={"failure_type": type(exc).__name__},
                status="failure",
                boundary=boundary,
            )
            raise
        self._response_count += 1
        self._adapter.observe_model_call(
            call_id,
            role=self._role_ref,
            model_id=self.model,
            response={
                "response_type": type(response).__name__,
                "response_char_count": len(response) if isinstance(response, str) else None,
            },
            status="response",
            boundary=boundary,
        )
        return response


def _records(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


async def run_acceptance(args: argparse.Namespace) -> dict[str, Any]:
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    sidecar = output / "semantic.jsonl"
    process_pid = os.getpid()
    process_ref = ProcessRef(process_pid, None, sys.executable)
    context = AdapterContext(
        framework="metagpt",
        run_id="metagpt-real-ollama-12345",
        session_id="metagpt-real-ollama-12345",
        sidecar=sidecar,
        content_root=output,
        capture_policy=ContentCapturePolicy("metadata_only"),
        process=process_ref,
    )
    adapter = MetaGPTAdapter(context)
    role_ref = adapter.observe_role(
        "metagpt-acceptance-role",
        name="MetaGPT acceptance role",
        role="structured-output analyst",
        process=process_ref,
        native_class="metagpt.roles.Role",
    )
    context.emit("AGENT_STARTED", "AGENT_STARTED", source=role_ref)
    task_ref = adapter.observe_task(
        "metagpt-real-task",
        owner=role_ref,
        name="MetaGPT local Ollama structured-output acceptance",
        status="created",
        model=args.model,
    )
    context.emit("TASK_STARTED", "TASK_STARTED", source=task_ref)

    cfg = Config.default(reload=True)
    cfg.llm.model = args.model
    cfg.llm.base_url = args.endpoint.rstrip("/") + "/api"
    cfg.llm.stream = False
    cfg.llm.timeout = 120
    cfg.llm.max_token = 160
    llm = ObservedOllamaLLM(cfg.llm, adapter=adapter, role_ref=role_ref)
    metagpt_context = Context(config=cfg)
    metagpt_context._llm = llm

    node = ActionNode.from_children(
        "acceptance_result",
        [
            ActionNode(
                "endpoint",
                str,
                "State the exact local Ollama endpoint used by this run.",
                args.endpoint,
            ),
            ActionNode(
                "model",
                str,
                "State the exact model name used by this run.",
                args.model,
            ),
        ],
    )
    node.schema = "json"
    action = Action(
        name="StructuredAcceptanceAction",
        desc="Produce a structured acceptance result.",
        node=node,
        context=metagpt_context,
        config=cfg,
        llm=llm,
    )
    role = Role(
        name="MetaGPT Acceptance Role",
        profile="structured-output analyst",
        goal="Complete one local Ollama acceptance task.",
        constraints="Do not expose private reasoning.",
        actions=[action],
        context=metagpt_context,
        config=cfg,
        llm=llm,
    )
    role.set_llm(llm, override=True)
    for configured_action in role.actions:
        configured_action.set_llm(llm, override=True)
        if configured_action.node:
            configured_action.node.set_llm(llm)
    role._set_react_mode("by_order")
    adapter.observe_action_object(
        action,
        owner=role_ref,
        task=task_ref,
        status="started",
        boundary="metagpt.roles.Role._act",
    )
    requirement = Message(
        id="metagpt-real-input",
        content=(
            f"Use the real local Ollama endpoint {args.endpoint} and model {args.model}. "
            "Return the acceptance result through the ActionNode structured-output contract."
        ),
        role="user",
        cause_by=UserRequirement,
        sent_from="user",
    )
    adapter.observe_message_object(requirement, task=task_ref, boundary="metagpt.roles.Role.run")

    result = None
    exception_payload: dict[str, Any] | None = None
    parser_failure = False
    retry_count = 0
    try:
        result = await role.run(with_message=requirement)
        if isinstance(result, Message):
            adapter.observe_message_object(
                result,
                task=task_ref,
                boundary="metagpt.roles.Role.run.return",
            )
        parsed = getattr(node, "instruct_content", None)
        action_status = "completed" if parsed is not None else "failed"
        adapter.observe_action_object(
            action,
            owner=role_ref,
            task=task_ref,
            status=action_status,
            boundary="metagpt.actions.action_node.ActionNode.fill",
            structured_output_present=parsed is not None,
        )
        task_success = parsed is not None and isinstance(result, Message)
        task_event = "TASK_COMPLETED" if task_success else "TASK_FAILED"
    except BaseException as exc:
        exception_payload = {
            "type": type(exc).__name__,
            "message": str(exc)[:300],
        }
        parser_failure = llm._response_count > 0 and getattr(node, "instruct_content", None) is None
        retry_count = max(0, llm._request_count - 1)
        if parser_failure:
            adapter.observe_parser_failure(
                "metagpt-parser-failure-1",
                role=role_ref,
                task=task_ref,
                error=type(exc).__name__,
                parser="metagpt.actions.action_node.ActionNode._aask_v1",
                retry_attempts=retry_count,
            )
            for index in range(1, retry_count + 1):
                adapter.observe_retry(
                    f"metagpt-retry-{index}",
                    role=role_ref,
                    task=task_ref,
                    retry_index=index,
                    retry_source="metagpt.actions.action_node.ActionNode._aask_v1",
                )
        adapter.observe_action_object(
            action,
            owner=role_ref,
            task=task_ref,
            status="failed",
            boundary="metagpt.actions.action_node.ActionNode.fill",
            parser_failure=parser_failure,
        )
        task_success = False
        task_event = "TASK_FAILED"
    context.emit(
        task_event,
        task_event,
        source=task_ref,
        attributes={
            "result_present": result is not None,
            "parser_failure": parser_failure,
            "retry_count": retry_count,
            "exception_type": exception_payload["type"] if exception_payload else None,
            "model_request_count": llm._request_count,
            "model_response_count": llm._response_count,
        },
    )
    context.emit("AGENT_STOPPED", "AGENT_STOPPED", source=role_ref)

    records = _records(sidecar)
    event_types = [record["event_type"] for record in records]
    expected = [
        {
            "ground_truth_id": "metagpt-acceptance-role",
            "ground_truth_type": "agent",
            "expected_relation": "AGENT_CREATED",
        },
        {
            "ground_truth_id": "metagpt-real-task",
            "ground_truth_type": "task",
            "expected_relation": "TASK_CREATED+TASK_STARTED",
        },
        {
            "ground_truth_id": "metagpt-actionnode",
            "ground_truth_type": "action",
            "expected_relation": "TASK_STARTED+TASK_COMPLETED|TASK_FAILED",
        },
        {
            "ground_truth_id": "metagpt-ollama-boundary",
            "ground_truth_type": "model",
            "expected_relation": "MODEL_REQUEST+MODEL_RESPONSE|MODEL_FAILURE",
        },
        {
            "ground_truth_id": "metagpt-role-message",
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
        "framework": "metagpt",
        "framework_version": "1.0.0",
        "model": args.model,
        "endpoint": args.endpoint,
        "event_count": len(records),
        "event_types": event_types,
        "agent_created_count": event_types.count("AGENT_CREATED"),
        "message_sent_count": event_types.count("MESSAGE_SENT"),
        "model_request_count": event_types.count("MODEL_REQUEST"),
        "model_response_count": event_types.count("MODEL_RESPONSE"),
        "model_failure_count": event_types.count("MODEL_FAILURE"),
        "parser_failure_count": sum(
            1 for record in records if record["relation"] == "PARSER_FAILURE"
        ),
        "retry_requested_count": sum(
            1 for record in records if record["relation"] == "RETRY_REQUESTED"
        ),
        "task_completed_count": event_types.count("TASK_COMPLETED"),
        "task_failed_count": event_types.count("TASK_FAILED"),
        "task_success": task_success,
        "observability_pass": (
            event_types.count("AGENT_CREATED") >= 1
            and event_types.count("MODEL_REQUEST") >= 1
            and (
                event_types.count("MODEL_RESPONSE") >= 1
                or event_types.count("MODEL_FAILURE") >= 1
            )
            and event_types.count("MESSAGE_SENT") >= 1
        ),
        "parser_failure": parser_failure,
        "retry_count": retry_count,
        "exception": exception_payload,
        "capture_mode": "metadata_only",
        "process_pid": process_pid,
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
    return 0 if summary["observability_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
