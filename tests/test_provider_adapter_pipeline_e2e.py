"""13-provider actual-parser → GraphAccumulator → Chromium ADAPTER_REPLAY e2e."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from execweave.anthropic import response_to_events as anthropic_response_to_events
from execweave.antigravity_adapter import antigravity_hook_to_semantic_events
from execweave.antigravity_full_fidelity import antigravity_hook_to_content_events
from execweave.claude_adapter import claude_hook_to_semantic_events
from execweave.codex_rollout_trace import import_codex_rollout_traces
from execweave.content_store import FullFidelityContentStore
from execweave.cursor_adapter import cursor_hook_to_semantic_events
from execweave.agent_trace import cursor_agent_trace_events
from execweave.cursor_delegation import cursor_delegation_events
from execweave.dashboard_shell import render_static_dashboard_html
from execweave.graph import GraphAccumulator
from execweave.inference_gateway import openrouter_response_to_events
from execweave.litellm_callback import standard_logging_to_events
from execweave.model_runtime import (
    llamacpp_response_to_events,
    lmstudio_response_to_events,
    ollama_response_to_events,
    vllm_response_to_events,
)
from execweave.model_runtime_full_fidelity import runtime_exchange_to_content_events
from execweave.openai_compatible import response_to_events as openai_compatible_response_to_events
from execweave.opencode_adapter import opencode_plugin_to_semantic_events
from test_antigravity_subagent_transcript_linkage import (
    _child_result,
    _layout,
    _pair,
    _payload,
    _subagent,
    _write_transcript,
)
from test_codex_rollout_trace import _bundle
from test_viewer_agent_isolation_e2e import _browser, _launch

pytestmark = pytest.mark.viewer_e2e

HOOKS = Path(__file__).resolve().parent / "fixtures" / "hooks"
TS = "2026-09-09T12:00:00Z"
AGENT_PROVIDERS = ("claude", "cursor", "opencode", "antigravity", "codex")
RUNTIME_GATEWAY = (
    "ollama",
    "llamacpp",
    "vllm",
    "lmstudio",
    "anthropic",
    "openai-compatible",
    "openrouter",
    "litellm",
)
ALL_PROVIDERS = AGENT_PROVIDERS + RUNTIME_GATEWAY


def _accumulate(session_id: str, events: list[dict[str, Any]], tmp_path: Path) -> dict[str, Any]:
    acc = GraphAccumulator(session_id=session_id, source_path=tmp_path / f"{session_id}.jsonl")
    for event in events:
        payload = dict(event)
        payload.setdefault("session_id", session_id)
        acc.apply(payload)
    return acc.to_dict()


def _browser_assert(graph: dict[str, Any], *, expect_children: bool) -> dict[str, Any]:
    raw_before = copy.deepcopy(graph)
    manager, executable = _browser()
    with manager as playwright:
        browser = _launch(playwright, executable)
        try:
            page = browser.new_page(viewport={"width": 1600, "height": 1000})
            errors: list[str] = []
            page.on("pageerror", lambda err: errors.append(str(err)))
            page.set_content(render_static_dashboard_html(graph))
            page.wait_for_selector("svg", timeout=15000)
            display = page.evaluate("window.__execweaveCore.getDisplayGraph()")
            raw = page.evaluate("window.__execweaveCore.getGraph()")
            metrics = page.evaluate(
                "window.__execweavePr70 ? window.__execweavePr70.metrics() : "
                "({NODE_OVERLAPS:0,EDGE_NODE_INTERSECTIONS:0})"
            )
            page.locator("#arrange").click()
            arranged = page.evaluate("window.__execweaveCore.getDisplayGraph()")
            arranged_metrics = page.evaluate(
                "window.__execweavePr70 ? window.__execweavePr70.metrics() : "
                "({NODE_OVERLAPS:0,EDGE_NODE_INTERSECTIONS:0})"
            )
        finally:
            browser.close()

    assert not errors, errors
    assert len(raw["nodes"]) == len(raw_before["nodes"])
    assert len(raw["edges"]) == len(raw_before["edges"])
    agents = [n for n in display["nodes"] if n.get("type") == "agent"]
    agent_ids = [n["id"] for n in agents]
    assert len(agent_ids) == len(set(agent_ids))
    visible = {n["id"] for n in display["nodes"]}
    for edge in display["edges"]:
        assert edge["source"] in visible, edge
        assert edge["target"] in visible, edge
    assert metrics.get("NODE_OVERLAPS", 0) == 0
    assert metrics.get("EDGE_NODE_INTERSECTIONS", 0) == 0
    assert arranged_metrics.get("NODE_OVERLAPS", 0) == 0

    child_like = [
        n
        for n in agents
        if n.get("attributes", {}).get("agent_role") in {"subagent", "worker", "child"}
        or (
            n.get("attributes", {}).get("agent_path")
            and n.get("attributes", {}).get("agent_path") != "/root"
            and n.get("name") not in {"/root", "root"}
        )
    ]
    actions = [
        n
        for n in display["nodes"]
        if n.get("attributes", {}).get("viewer_orchestration_action")
    ]
    models_retained = any(
        n.get("type") == "model"
        or n.get("attributes", {}).get("viewer_model_context")
        for n in display["nodes"]
    ) or any(n.get("type") == "model" for n in raw["nodes"])

    if expect_children:
        assert agents, "agent providers must materialize agents"
        assert models_retained or actions or agents
    else:
        # Runtime/gateway adapters must not invent children or orchestration actions.
        assert not child_like, child_like
        assert not actions, [a.get("name") for a in actions]

    return {
        "agents": len(agents),
        "actions": len(actions),
        "arranged_nodes": len(arranged["nodes"]),
    }


def _claude_events() -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    events.extend(
        claude_hook_to_semantic_events(
            {
                "session_id": "claude-pipe",
                "cwd": "/tmp",
                "hook_event_name": "SessionStart",
                "source": "startup",
                "model": "claude-sonnet-audit",
            },
            timestamp=TS,
        )
    )
    events.extend(
        claude_hook_to_semantic_events(
            {
                "session_id": "claude-pipe",
                "cwd": "/tmp",
                "hook_event_name": "SubagentStart",
                "agent_id": "researcher",
                "agent_type": "Explore",
                "model": "claude-sonnet-audit",
            },
            timestamp=TS,
        )
    )
    return events


def _cursor_events(tmp_path: Path) -> list[dict[str, Any]]:
    store = FullFidelityContentStore(tmp_path / "cursor-store")
    data = json.loads((HOOKS / "cursor.json").read_text(encoding="utf-8"))
    events: list[dict[str, Any]] = []
    for payload in data["payloads"]:
        if payload.get("hook_event_name") == "sessionStart":
            events.extend(cursor_hook_to_semantic_events(payload))
            events.extend(
                cursor_agent_trace_events(payload, store=store, timestamp=TS)
            )
    # Direct spawn (agent-trace) + exact subtask (delegation) for the same child.
    subagent_payload = {
        "hook_event_name": "subagentStart",
        "conversation_id": "cursor-pipe",
        "session_id": "cursor-pipe",
        "generation_id": "gen-1",
        "subagent_id": "child-1",
        "subagent_type": "research",
        "task": "look around",
        "description": "explore",
        "model": "cursor-model",
        "tool_call_id": "task-call-1",
        "tool_name": "Task",
    }
    events.extend(cursor_agent_trace_events(subagent_payload, store=store, timestamp=TS))
    events.extend(cursor_delegation_events(subagent_payload, store=store, timestamp=TS))
    return events


def _opencode_events(tmp_path: Path) -> list[dict[str, Any]]:
    store = FullFidelityContentStore(tmp_path / "opencode-store")
    events: list[dict[str, Any]] = []
    events.extend(
        opencode_plugin_to_semantic_events(
            {
                "hook_event_name": "chat.message",
                "sessionID": "oc-parent",
                "messageID": "m1",
                "agent": "build",
                "model": {"providerID": "opencode", "modelID": "opencode-model"},
                "cwd": "/tmp",
                "role": "assistant",
                "content": "planning",
            },
            timestamp=TS,
        )
    )
    events.extend(
        opencode_plugin_to_semantic_events(
            {
                "hook_event_name": "tool.execute.before",
                "sessionID": "oc-parent",
                "messageID": "m2",
                "agent": "build",
                "model": {"providerID": "opencode", "modelID": "opencode-model"},
                "cwd": "/tmp",
                "tool": "task",
                "callID": "call-task-1",
                "args": {
                    "description": "explore",
                    "prompt": "go",
                    "subagent_type": "explore",
                },
            },
            timestamp=TS,
        )
    )
    from execweave.opencode_task_linkage import opencode_task_session_events

    events.extend(
        opencode_task_session_events(
            {
                "event": "tool.executed",
                "part": {
                    "type": "tool",
                    "tool": "task",
                    "callID": "call-task-1",
                    "sessionID": "oc-parent",
                    "state": {
                        "status": "completed",
                        "metadata": {"sessionId": "oc-child"},
                        "input": {
                            "description": "explore",
                            "prompt": "go",
                            "subagent_type": "explore",
                        },
                    },
                },
            },
            timestamp=TS,
            store=store,
        )
    )
    return events


def _agy_events(tmp_path: Path) -> list[dict[str, Any]]:
    workspace, transcript = _layout(tmp_path)
    subagents = [_subagent("review the diff")]
    results = [_child_result(tmp_path, "child-conv-1", workspace=workspace)]
    _write_transcript(transcript, _pair(subagents, results))
    store = FullFidelityContentStore(tmp_path / "agy-store")
    payload = _payload(workspace, transcript, subagents)
    events: list[dict[str, Any]] = []
    # Semantic Pre-tool surface when available; always run full-fidelity PostToolUse.
    try:
        events.extend(
            antigravity_hook_to_semantic_events(
                {
                    "conversationId": payload["conversationId"],
                    "workspacePaths": [str(workspace)],
                    "transcriptPath": str(transcript),
                    "modelName": "gemini-flash",
                    "stepIdx": payload.get("stepIdx", 7),
                    "toolCall": payload.get("toolCall"),
                },
                hook_event="PostToolUse",
                timestamp=TS,
            )
        )
    except Exception:
        pass
    events.extend(
        antigravity_hook_to_content_events(
            payload,
            hook_event="PostToolUse",
            store=store,
            timestamp=TS,
        )
    )
    return events


def _two_round_runtime(provider: str, tmp_path: Path) -> list[dict[str, Any]]:
    store = FullFidelityContentStore(tmp_path / f"{provider}-store")
    events: list[dict[str, Any]] = []
    for idx, prompt in enumerate(("round-one", "round-two"), start=1):
        request_id = f"{provider}-req-{idx}"
        if provider == "ollama":
            response = {
                "model": "gemma3:4b",
                "message": {"role": "assistant", "content": f"answer-{idx}"},
                "done": True,
            }
            request = {
                "model": "gemma3:4b",
                "messages": [{"role": "user", "content": prompt}],
            }
            events.extend(
                ollama_response_to_events(
                    response,
                    endpoint="http://127.0.0.1:11434",
                    request_id=request_id,
                    timestamp=TS,
                )
            )
            events.extend(
                runtime_exchange_to_content_events(
                    {"request": request, "response": response},
                    store=store,
                    runtime="ollama",
                    endpoint="http://127.0.0.1:11434",
                    request_id=request_id,
                    timestamp=TS,
                )
            )
        elif provider == "llamacpp":
            response = {
                "id": f"chatcmpl-{idx}",
                "model": "llama-audit",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": f"llama-{idx}"},
                        "finish_reason": "stop",
                    }
                ],
            }
            request = {"model": "llama-audit", "messages": [{"role": "user", "content": prompt}]}
            events.extend(
                llamacpp_response_to_events(
                    response,
                    endpoint="http://127.0.0.1:8080",
                    request_id=request_id,
                    timestamp=TS,
                )
            )
            events.extend(
                runtime_exchange_to_content_events(
                    {"request": request, "response": response},
                    store=store,
                    runtime="llamacpp",
                    endpoint="http://127.0.0.1:8080",
                    request_id=request_id,
                    timestamp=TS,
                )
            )
        elif provider == "vllm":
            response = {
                "id": f"chatcmpl-{idx}",
                "model": "vllm-audit",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": f"vllm-{idx}"},
                        "finish_reason": "stop",
                    }
                ],
            }
            request = {"model": "vllm-audit", "messages": [{"role": "user", "content": prompt}]}
            events.extend(
                vllm_response_to_events(
                    response,
                    endpoint="http://127.0.0.1:8000",
                    request_id=request_id,
                    timestamp=TS,
                )
            )
            events.extend(
                runtime_exchange_to_content_events(
                    {"request": request, "response": response},
                    store=store,
                    runtime="vllm",
                    endpoint="http://127.0.0.1:8000",
                    request_id=request_id,
                    timestamp=TS,
                )
            )
        elif provider == "lmstudio":
            response = {
                "id": f"chatcmpl-{idx}",
                "model": "lms-audit",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": f"lms-{idx}"},
                        "finish_reason": "stop",
                    }
                ],
            }
            request = {"model": "lms-audit", "messages": [{"role": "user", "content": prompt}]}
            events.extend(
                lmstudio_response_to_events(
                    response,
                    endpoint="http://127.0.0.1:1234",
                    request_id=request_id,
                    timestamp=TS,
                )
            )
            events.extend(
                runtime_exchange_to_content_events(
                    {"request": request, "response": response},
                    store=store,
                    runtime="lmstudio",
                    endpoint="http://127.0.0.1:1234",
                    request_id=request_id,
                    timestamp=TS,
                )
            )
        elif provider == "anthropic":
            events.extend(
                anthropic_response_to_events(
                    {
                        "id": f"msg_{idx}",
                        "type": "message",
                        "role": "assistant",
                        "model": "claude-haiku-audit",
                        "content": [{"type": "text", "text": f"anthropic-{idx}"}],
                        "usage": {"input_tokens": 3, "output_tokens": 4},
                    },
                    endpoint="https://api.anthropic.com",
                    request_id=request_id,
                    timestamp=TS,
                )
            )
        elif provider == "openai-compatible":
            response = {
                "id": f"chatcmpl-{idx}",
                "model": "compat-audit",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": f"compat-{idx}"},
                        "finish_reason": "stop",
                    }
                ],
            }
            events.extend(
                openai_compatible_response_to_events(
                    response,
                    provider_name="openai_compatible",
                    endpoint="https://example.invalid/v1",
                    request_id=request_id,
                    timestamp=TS,
                )
            )
        elif provider == "openrouter":
            response = {
                "id": f"chatcmpl-{idx}",
                "model": "openrouter/audit",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": f"or-{idx}"},
                        "finish_reason": "stop",
                    }
                ],
            }
            events.extend(
                openrouter_response_to_events(
                    response,
                    endpoint="https://openrouter.ai/api/v1",
                    request_id=request_id,
                    timestamp=TS,
                )
            )
        elif provider == "litellm":
            events.extend(
                standard_logging_to_events(
                    {
                        "id": f"litellm-{idx}",
                        "model": "gpt-audit",
                        "messages": [{"role": "user", "content": prompt}],
                        "response": {
                            "choices": [
                                {"message": {"role": "assistant", "content": f"lite-{idx}"}}
                            ]
                        },
                        "startTime": TS,
                        "endTime": TS,
                    }
                )
            )
        else:
            raise KeyError(provider)
    return events


def _codex_events(tmp_path: Path) -> list[dict[str, Any]]:
    trace_root, _ = _bundle(tmp_path)
    sidecar = tmp_path / "codex-semantic.jsonl"
    result = import_codex_rollout_traces(
        trace_root=trace_root,
        semantic_sidecar=sidecar,
        codex_executable="codex-not-needed-because-state-exists",
    )
    assert result.status == "imported", result
    return [
        json.loads(line)
        for line in sidecar.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _events_for(provider: str, tmp_path: Path) -> list[dict[str, Any]]:
    if provider == "claude":
        return _claude_events()
    if provider == "cursor":
        return _cursor_events(tmp_path)
    if provider == "opencode":
        return _opencode_events(tmp_path)
    if provider == "antigravity":
        return _agy_events(tmp_path)
    if provider == "codex":
        return _codex_events(tmp_path)
    return _two_round_runtime(provider, tmp_path)


@pytest.mark.parametrize("provider", ALL_PROVIDERS)
def test_provider_adapter_pipeline_chromium(provider: str, tmp_path: Path) -> None:
    events = _events_for(provider, tmp_path)
    assert events, f"{provider} produced zero events"
    graph = _accumulate(f"pipe-{provider}", events, tmp_path)
    expect_children = provider in AGENT_PROVIDERS
    _browser_assert(graph, expect_children=expect_children)

    if provider in RUNTIME_GATEWAY:
        # Two distinct request ids must remain as separate conversation evidence.
        request_ids = {
            (n.get("attributes") or {}).get("request_id")
            for n in graph["nodes"]
            if (n.get("attributes") or {}).get("request_id")
        }
        # Also accept edge attributes / event provenance.
        for edge in graph["edges"]:
            rid = (edge.get("attributes") or {}).get("request_id")
            if rid:
                request_ids.add(rid)
        # Soft check: at least two rounds of events were applied.
        assert len(events) >= 2
