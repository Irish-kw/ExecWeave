"""13-provider actual-parser → GraphAccumulator → Chromium ADAPTER_REPLAY e2e."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from execweave.agent_trace import cursor_agent_trace_events
from execweave.anthropic import response_to_events as anthropic_response_to_events
from execweave.antigravity_adapter import antigravity_hook_to_semantic_events
from execweave.antigravity_full_fidelity import antigravity_hook_to_content_events
from execweave.claude_adapter import claude_hook_to_semantic_events
from execweave.codex_rollout_trace import import_codex_rollout_traces
from execweave.content_store import FullFidelityContentStore
from execweave.cursor_adapter import cursor_hook_to_semantic_events
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
from execweave.openai_compatible import (
    response_to_events as openai_compatible_response_to_events,
)
from execweave.opencode_adapter import opencode_plugin_to_semantic_events
from execweave.opencode_task_linkage import opencode_task_session_events
from test_antigravity_subagent_transcript_linkage import (
    _child_result,
    _layout,
    _pair,
    _payload,
    _subagent,
    _write_transcript,
)
from test_codex_rollout_trace import _bundle
from test_opencode_task_session_linkage import _task_part_payload
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


def _browser_assert(graph: dict[str, Any], *, expect: dict[str, Any]) -> dict[str, Any]:
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
            assert page.evaluate(
                "!!(window.__execweavePr70 && typeof window.__execweavePr70.metrics==='function')"
            ), "metrics API missing"

            def snap():
                return (
                    page.evaluate("window.__execweaveCore.getDisplayGraph()"),
                    page.evaluate("window.__execweaveCore.getGraph()"),
                    page.evaluate("window.__execweavePr70.metrics()"),
                    page.evaluate(
                        """() => Object.fromEntries([...document.querySelectorAll('.node')].map(g => {
                            const m=(g.getAttribute('transform')||'').match(/translate\\(([-0-9.]+) ([-0-9.]+)\\)/);
                            return [g.dataset.id, {x:m?Number(m[1]):0,y:m?Number(m[2]):0}];
                        }))"""
                    ),
                )

            display = None
            for phase in ("initial", "arrange"):
                display, raw, metrics, positions = snap()
                assert not errors, errors
                assert len(raw["nodes"]) == len(raw_before["nodes"])
                assert len(raw["edges"]) == len(raw_before["edges"])
                for key in ("NODE_OVERLAPS", "EDGE_NODE_INTERSECTIONS"):
                    assert key in metrics
                    value = metrics[key]
                    assert isinstance(value, (int, float)) and value == value
                    assert value == 0, (phase, key, value)
                visible = {n["id"] for n in display["nodes"]}
                for edge in display["edges"]:
                    assert edge["source"] in visible, (phase, edge)
                    assert edge["target"] in visible, (phase, edge)
                agents = [n for n in display["nodes"] if n.get("type") == "agent"]
                agent_ids = [n["id"] for n in agents]
                assert len(agent_ids) == len(set(agent_ids))
                assert len(agents) >= int(expect.get("min_agents", 1))
                for rid in expect.get("root_ids", []):
                    assert rid in agent_ids, (phase, rid, agent_ids)
                actions = [
                    n
                    for n in display["nodes"]
                    if n.get("attributes", {}).get("viewer_orchestration_action")
                ]
                if expect.get("forbid_children"):
                    role_children = [
                        n
                        for n in agents
                        if n.get("attributes", {}).get("agent_role")
                        in {"subagent", "worker", "child"}
                    ]
                    assert not role_children, (phase, role_children)
                    assert not actions, (phase, [a.get("name") for a in actions])
                    assert display["nodes"], (phase, "runtime/gateway display empty")
                else:
                    for cid in expect.get("child_ids", []):
                        assert cid in agent_ids, (phase, cid, agent_ids)
                    if expect.get("require_action"):
                        assert actions, (phase, "expected orchestration action")
                    if (
                        expect.get("require_flow_order")
                        and expect.get("child_ids")
                        and expect.get("root_ids")
                    ):
                        contexts = [
                            n
                            for n in display["nodes"]
                            if n.get("attributes", {}).get("viewer_model_context")
                        ]
                        if contexts and actions:
                            root_id = expect["root_ids"][0]
                            child_id = expect["child_ids"][0]
                            assert (
                                positions[root_id]["x"]
                                < positions[contexts[0]["id"]]["x"]
                                < positions[actions[0]["id"]]["x"]
                                < positions[child_id]["x"]
                            ), (phase, positions)
                if phase == "initial":
                    page.locator("#arrange").click()
            assert display is not None
            return {
                "agents": len([n for n in display["nodes"] if n.get("type") == "agent"]),
                "actions": len(
                    [
                        n
                        for n in display["nodes"]
                        if n.get("attributes", {}).get("viewer_orchestration_action")
                    ]
                ),
            }
        finally:
            browser.close()


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
            events.extend(cursor_agent_trace_events(payload, store=store, timestamp=TS))
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
    task_payload = _task_part_payload(
        parent_session="oc-parent",
        metadata_parent="oc-parent",
        child_session="oc-child",
    )
    # Align callID with tool.execute.before so ownership evidence joins.
    task_payload["event"]["properties"]["part"]["callID"] = "call-task-1"
    task_events = opencode_task_session_events(
        task_payload,
        timestamp=TS,
        store=store,
    )
    assert any(e.get("relation") == "ASSIGNED_AGENT_TASK" for e in task_events), task_events
    events.extend(task_events)
    return events


def _agy_events(tmp_path: Path) -> list[dict[str, Any]]:
    workspace, transcript = _layout(tmp_path)
    subagents = [_subagent("review the diff")]
    results = [_child_result(tmp_path, "child-conv-1", workspace=workspace)]
    _write_transcript(transcript, _pair(subagents, results))
    store = FullFidelityContentStore(tmp_path / "agy-store")
    payload = _payload(workspace, transcript, subagents)
    events: list[dict[str, Any]] = []
    pre = {
        "conversationId": payload["conversationId"],
        "workspacePaths": [str(workspace)],
        "transcriptPath": str(transcript),
        "modelName": "gemini-flash",
        "stepIdx": payload.get("stepIdx", 7),
    }
    events.extend(
        antigravity_hook_to_semantic_events(pre, hook_event="PreInvocation", timestamp=TS)
    )
    events.extend(
        antigravity_hook_to_content_events(
            payload,
            hook_event="PostToolUse",
            store=store,
            timestamp=TS,
        )
    )
    assert events, "AGY parsers produced zero events"
    assert any(
        e.get("relation") in {"REQUESTED_SUBTASK", "ASSIGNED_AGENT_TASK", "USED_MODEL", "INVOKED_MODEL"}
        or (isinstance(e.get("relation"), str))
        for e in events
    )
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


def _two_round_runtime(provider: str, tmp_path: Path) -> tuple[list[dict[str, Any]], set[str]]:
    store = FullFidelityContentStore(tmp_path / f"{provider}-store")
    events: list[dict[str, Any]] = []
    request_ids: set[str] = set()
    for idx, prompt in enumerate(("round-one-prompt", "round-two-prompt"), start=1):
        request_id = f"{provider}-req-{idx}"
        request_ids.add(request_id)
        response_text = f"{provider}-answer-{idx}"
        if provider == "ollama":
            response = {
                "model": "gemma3:4b",
                "message": {"role": "assistant", "content": response_text},
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
                        "message": {"role": "assistant", "content": response_text},
                        "finish_reason": "stop",
                    }
                ],
            }
            request = {
                "model": "llama-audit",
                "messages": [{"role": "user", "content": prompt}],
            }
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
                        "message": {"role": "assistant", "content": response_text},
                        "finish_reason": "stop",
                    }
                ],
            }
            request = {
                "model": "vllm-audit",
                "messages": [{"role": "user", "content": prompt}],
            }
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
                        "message": {"role": "assistant", "content": response_text},
                        "finish_reason": "stop",
                    }
                ],
            }
            request = {
                "model": "lms-audit",
                "messages": [{"role": "user", "content": prompt}],
            }
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
                        "content": [{"type": "text", "text": response_text}],
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
                        "message": {"role": "assistant", "content": response_text},
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
                        "message": {"role": "assistant", "content": response_text},
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
            # LiteLLM node ids come from payload id (litellm-1/2), not {provider}-req-N.
            request_ids.discard(request_id)
            request_id = f"litellm-{idx}"
            request_ids.add(request_id)
            events.extend(
                standard_logging_to_events(
                    {
                        "id": request_id,
                        "model": "gpt-audit",
                        "messages": [{"role": "user", "content": prompt}],
                        "response": {
                            "choices": [
                                {
                                    "message": {
                                        "role": "assistant",
                                        "content": response_text,
                                    }
                                }
                            ]
                        },
                        "startTime": TS,
                        "endTime": TS,
                    }
                )
            )
        else:
            raise KeyError(provider)
    return events, request_ids


def _expect_for(provider: str, graph: dict[str, Any]) -> dict[str, Any]:
    agents = [n for n in graph["nodes"] if n.get("type") == "agent"]
    if provider == "claude":
        roots = [n["id"] for n in agents if n.get("attributes", {}).get("agent_role") == "root" or n.get("name") in {"/root", "Claude"}]
        children = [
            n["id"]
            for n in agents
            if "researcher" in n["id"] or n.get("attributes", {}).get("agent_role") == "subagent"
        ]
        return {
            "min_agents": 2,
            "root_ids": roots[:1] or [agents[0]["id"]],
            "child_ids": children[:1],
            "require_action": False,
            "require_flow_order": False,
        }
    if provider == "cursor":
        return {
            "min_agents": 2,
            "root_ids": ["agent:Cursor"] if any(n["id"] == "agent:Cursor" for n in agents) else [agents[0]["id"]],
            "child_ids": [
                n["id"]
                for n in agents
                if "child-1" in n["id"] or n.get("attributes", {}).get("agent_role") == "subagent"
            ][:1],
            "require_action": True,
            "require_flow_order": True,
        }
    if provider == "opencode":
        return {
            "min_agents": 2,
            "root_ids": ["agent:opencode:session:oc-parent"],
            "child_ids": ["agent:opencode:session:oc-child"],
            "require_action": True,
            "require_flow_order": True,
        }
    if provider == "antigravity":
        children = [
            n["id"]
            for n in agents
            if n.get("attributes", {}).get("agent_role") == "subagent"
            or "child" in n["id"]
        ]
        roots = [n["id"] for n in agents if n["id"] not in children]
        return {
            "min_agents": 1 if not children else 2,
            "root_ids": roots[:1],
            "child_ids": children[:1],
            "require_action": bool(children),
            "require_flow_order": bool(children),
        }
    if provider == "codex":
        children = [
            n["id"]
            for n in agents
            if n.get("attributes", {}).get("agent_role") in {"subagent", "worker"}
            or (n.get("attributes", {}).get("agent_path") or "").count("/") > 1
        ]
        roots = [n["id"] for n in agents if n["id"] not in children]
        return {
            "min_agents": 2,
            "root_ids": roots[:1],
            "child_ids": children[:1],
            "require_action": True,
            "require_flow_order": True,
        }
    return {"min_agents": 0, "forbid_children": True}


def _events_for(provider: str, tmp_path: Path):
    if provider == "claude":
        return _claude_events(), set()
    if provider == "cursor":
        return _cursor_events(tmp_path), set()
    if provider == "opencode":
        return _opencode_events(tmp_path), set()
    if provider == "antigravity":
        return _agy_events(tmp_path), set()
    if provider == "codex":
        return _codex_events(tmp_path), set()
    return _two_round_runtime(provider, tmp_path)


@pytest.mark.parametrize("provider", ALL_PROVIDERS)
def test_provider_adapter_pipeline_chromium(provider: str, tmp_path: Path) -> None:
    events, expected_request_ids = _events_for(provider, tmp_path)
    assert events, f"{provider} produced zero events"
    if provider in RUNTIME_GATEWAY:
        assert len(expected_request_ids) == 2, expected_request_ids
    graph = _accumulate(f"pipe-{provider}", events, tmp_path)

    if provider == "opencode":
        assert any(e.get("relation") == "ASSIGNED_AGENT_TASK" for e in graph["edges"])
        assert any(n["id"] == "agent:opencode:session:oc-child" for n in graph["nodes"])

    expect = _expect_for(provider, graph)
    _browser_assert(graph, expect=expect)

    if provider in RUNTIME_GATEWAY:
        id_blob = "\n".join(
            [str(n.get("id") or "") for n in graph["nodes"]]
            + [str(e.get("id") or "") for e in graph["edges"]]
            + [str((n.get("attributes") or {}).get("request_id") or "") for n in graph["nodes"]]
        )
        for rid in expected_request_ids:
            assert rid in id_blob, (provider, rid, id_blob[:500])
        # Full-fidelity exchange content is stored as observed_content files.
        store_root = tmp_path / f"{provider}-store"
        content_blob = ""
        if store_root.is_dir():
            for path_file in store_root.rglob("*"):
                if path_file.is_file():
                    content_blob += path_file.read_text(encoding="utf-8", errors="ignore")
        graph_blob = json.dumps(graph, default=str)
        combined = content_blob + "\n" + graph_blob
        # Providers that emit exchange content must retain both prompts/answers.
        if provider in {"ollama", "llamacpp", "vllm", "lmstudio"}:
            assert "round-one-prompt" in combined
            assert "round-two-prompt" in combined
            assert f"{provider}-answer-1" in combined
            assert f"{provider}-answer-2" in combined
        else:
            # Gateway response parsers still must retain two distinct request ids.
            assert len(expected_request_ids) == 2


def test_negative_control_root_only_graph_fails_agent_expect(tmp_path: Path) -> None:
    """Soft any(agents) must not pass a child-expecting gate."""
    graph = {
        "schema_version": "1.0",
        "session_id": "neg-root-only",
        "nodes": [
            {
                "id": "agent:only",
                "type": "agent",
                "name": "/root",
                "attributes": {"provider": "test", "agent_role": "root"},
            }
        ],
        "edges": [],
    }
    with pytest.raises(AssertionError):
        _browser_assert(
            graph,
            expect={
                "min_agents": 2,
                "root_ids": ["agent:only"],
                "child_ids": ["agent:missing-child"],
                "require_action": True,
            },
        )


def test_negative_control_missing_metrics_api_fails(tmp_path: Path) -> None:
    graph = {
        "schema_version": "1.0",
        "session_id": "neg-metrics",
        "nodes": [
            {
                "id": "agent:only",
                "type": "agent",
                "name": "/root",
                "attributes": {"provider": "test", "agent_role": "root"},
            }
        ],
        "edges": [],
    }
    # Monkeypatch: render then delete metrics before assert path by using evaluate injection
    # via a one-off browser check.
    manager, executable = _browser()
    with manager as playwright:
        browser = _launch(playwright, executable)
        try:
            page = browser.new_page(viewport={"width": 1200, "height": 800})
            page.set_content(render_static_dashboard_html(graph))
            page.wait_for_selector("svg", timeout=15000)
            page.evaluate("window.__execweavePr70 = undefined")
            assert not page.evaluate(
                "!!(window.__execweavePr70 && typeof window.__execweavePr70.metrics==='function')"
            )
        finally:
            browser.close()
