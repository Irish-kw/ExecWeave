"""Real MetaGPT Environment/Role fan-out and return, using the local Ollama.

This is a small functional collaboration, not a reproduction of the paper's
software-company benchmark. No framework source or global class is patched.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

import psutil

# This module establishes an isolated MetaGPT configuration before importing it.
from real_metagpt_acceptance import (
    Action, AdapterContext, Config, ContentCapturePolicy, Context, Message,
    MetaGPTAdapter, ObservedOllamaLLM, ProcessRef, Role, UserRequirement,
)
from metagpt.environment import Environment


async def run(args):
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    sidecar = Path(os.environ.get("EXECWEAVE_SEMANTIC_SIDECAR") or output / "semantic.jsonl")
    context = AdapterContext(
        framework="metagpt", run_id=os.environ.get("EXECWEAVE_RUN_ID") or output.name,
        session_id=os.environ.get("EXECWEAVE_SESSION_ID") or output.name,
        sidecar=sidecar, content_root=sidecar.parent,
        capture_policy=ContentCapturePolicy("prompt_and_response"),
        process=ProcessRef(os.getpid(), psutil.Process().create_time(), sys.executable),
    )
    adapter = MetaGPTAdapter(context)
    names = ("coordinator", "endpoint_worker", "model_worker")
    refs = {name: adapter.observe_role(name, name=name, process=context.process,
            **({"agent_role": "root", "agent_path": "/root"} if name == "coordinator" else {})) for name in names}
    prompt = f"Check endpoint {args.endpoint} and model {args.model}. Ask both workers for one factual sentence and summarize their replies."
    task = adapter.observe_task("team-task", owner=refs["coordinator"], content=prompt, name=prompt)
    cfg = Config.default(reload=True)
    cfg.llm.model = args.model
    cfg.llm.base_url = args.endpoint.rstrip("/") + "/api"
    cfg.llm.stream = False
    cfg.llm.max_token = 160
    cfg.llm.timeout = 120
    native_context = Context(config=cfg)
    outcomes = {}

    class CheckAction(Action):
        async def run(self, text):
            return await self._aask(text)

    class RecordedRole(Role):
        dispatch_done: bool = False

        def put_message(self, message):
            super().put_message(message)
            adapter.observe_message_delivery(message, recipient=refs[self.name], task=task)

        def publish_message(self, message):
            if message:
                adapter.observe_message_object(message, task=task, routing_source="metagpt.Role.publish_message")
            return super().publish_message(message)

        async def _act(self):
            is_root = self.name == "coordinator"
            dispatch = is_root and not self.dispatch_done
            if dispatch:
                request = f"Write one short instruction asking endpoint_worker to report the configured endpoint {args.endpoint} and model_worker to report the configured model {args.model}. Do not write code or suggest network requests."
                recipients = {"endpoint_worker", "model_worker"}
            elif is_root:
                request = "The following quoted messages are the actual worker replies. Report both configured values exactly as written, in two sentences. Do not deny receiving the messages.\n" + "\n".join(f"{m.sent_from}: {m.content}" for m in self.rc.news)
                recipients = {"user"}
            else:
                fact = args.endpoint if self.name == "endpoint_worker" else args.model
                request = "Received task:\n" + "\n".join(m.content for m in self.rc.news) + f"\nYour only job: reply with one sentence containing this exact configured value: {fact}. Do not describe code, libraries, or actions you did not perform."
                recipients = {"coordinator"}
            action = self.actions[0]
            adapter.observe_action_object(action, owner=refs[self.name], task=task, status="started")
            response = await action.run(request)
            adapter.observe_action_object(action, owner=refs[self.name], task=task, status="completed")
            self.dispatch_done = True
            if not dispatch:
                outcomes[self.name] = response
            return Message(content=response, role=self.profile, cause_by=CheckAction, sent_from=self.name, send_to=recipients)

    roles = []
    for name in names:
        llm = ObservedOllamaLLM(cfg.llm, adapter=adapter, role_ref=refs[name])
        role = RecordedRole(name=name, profile=name, goal="Complete the local acceptance check", actions=[CheckAction(name=f"check-{name}")], context=native_context, config=cfg)
        role.set_llm(llm, override=True)
        for action in role.actions:
            action.set_llm(llm, override=True)
        role._watch([UserRequirement, CheckAction])
        role._set_react_mode("by_order")
        roles.append(role)
    env = Environment(context=native_context)
    env.add_roles(roles)
    requirement = Message(content=prompt, role="user", cause_by=UserRequirement, sent_from="user", send_to={"coordinator"})
    adapter.observe_message_object(requirement, task=task)
    env.publish_message(requirement)
    await env.run(k=3)
    success = bool(all(outcomes.get(name) for name in names)
                   and args.endpoint in outcomes["endpoint_worker"]
                   and args.model in outcomes["model_worker"]
                   and args.endpoint in outcomes["coordinator"]
                   and args.model in outcomes["coordinator"])
    context.emit("TASK_COMPLETED" if success else "TASK_FAILED", "TASK_COMPLETED" if success else "TASK_FAILED", source=task)
    for ref in refs.values():
        context.emit("AGENT_STOPPED", "AGENT_STOPPED", source=ref)
    records = [json.loads(line) for line in sidecar.read_text(encoding="utf-8").splitlines()]
    summary = {"framework": "metagpt", "scenario": "native Environment with three Roles", "task_success": success,
               "agent_count": len(refs), "model_request_count": sum(r["event_type"] == "MODEL_REQUEST" for r in records),
               "message_received_count": sum(r["event_type"] == "MESSAGE_RECEIVED" for r in records), "outcomes": outcomes}
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if success else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--endpoint", default="http://127.0.0.1:12345")
    parser.add_argument("--model", default="llama3.1:8b")
    raise SystemExit(asyncio.run(run(parser.parse_args())))
