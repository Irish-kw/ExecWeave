"""13-provider actual-parser → GraphAccumulator → Chromium ADAPTER_REPLAY e2e."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from execweave.agent_trace import cursor_agent_trace_events
from execweave.anthropic import response_to_events as anthropic_response_to_events
from execweave.anthropic_full_fidelity import (
    exchange_to_content_events as anthropic_exchange_to_content_events,
)
from execweave.antigravity_adapter import antigravity_hook_to_semantic_events
from execweave.antigravity_full_fidelity import antigravity_hook_to_content_events
from execweave.claude_adapter import claude_hook_to_semantic_events
from execweave.codex_rollout_trace import import_codex_rollout_traces
from execweave.content_store import FullFidelityContentStore
from execweave.conversation_records import conversation_record_entries
from execweave.cursor_adapter import cursor_hook_to_semantic_events
from execweave.cursor_delegation import cursor_delegation_events
from execweave.dashboard_shell import render_static_dashboard_html
from execweave.graph import GraphAccumulator
from execweave.inference_gateway import openrouter_response_to_events
from execweave.inference_gateway_full_fidelity import (
    litellm_callback_to_content_events,
    openrouter_exchange_to_content_events,
)
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
from execweave.openai_compatible_full_fidelity import (
    exchange_to_content_events as openai_compatible_exchange_to_content_events,
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

# Fixture/parser contracts — expectations must NOT be derived from graph output.
PROVIDER_CONTRACT: dict[str, dict[str, Any]] = {
    "claude": {
        "min_agents": 2,
        "root_ids": ["agent:Claude Code"],
        "child_ids": ["agent:claude:claude-pipe:subagent:researcher"],
        "require_action": True,
        "require_flow_order": True,
        "action_kinds": {"spawn_agent"},
    },
    "cursor": {
        "min_agents": 2,
        "root_ids": ["agent:Cursor"],
        "child_ids": ["agent:cursor:cursor-pipe:subagent:child-1"],
        "require_action": True,
        "require_flow_order": True,
        "action_kinds": {"spawn_agent"},
    },
    "opencode": {
        "min_agents": 2,
        "root_ids": ["agent:opencode:session:oc-parent"],
        "child_ids": ["agent:opencode:session:oc-child"],
        "require_action": True,
        "require_flow_order": True,
        "action_kinds": {"assign_agent_task"},
    },
    "antigravity": {
        "min_agents": 2,
        "root_ids": ["agent:antigravity:conversation:parent-conversation"],
        "child_ids": ["agent:antigravity:conversation:child-conv-1"],
        "require_action": True,
        "require_flow_order": True,
        "action_kinds": {"assign_agent_task"},
    },
    "codex": {
        "min_agents": 2,
        "root_ids": ["agent:codex:rollout:rollout-test:thread:root-thread"],
        "child_ids": ["agent:codex:rollout:rollout-test:thread:child-thread"],
        "require_action": True,
        "require_flow_order": True,
        "action_kinds": {"spawn_agent", "send_input"},
    },
}


def _accumulate(session_id: str, events: list[dict[str, Any]], tmp_path: Path) -> dict[str, Any]:
    acc = GraphAccumulator(session_id=session_id, source_path=tmp_path / f"{session_id}.jsonl")
    for event in events:
        payload = dict(event)
        payload.setdefault("session_id", session_id)
        acc.apply(payload)
    return acc.to_dict()


def _browser_assert(
    graph: dict[str, Any],
    *,
    expect: dict[str, Any],
    conversation_entries: list[dict[str, Any]] | None = None,
    after_load=None,
) -> dict[str, Any]:
    raw_before = copy.deepcopy(graph)
    manager, executable = _browser()
    with manager as playwright:
        browser = _launch(playwright, executable)
        try:
            page = browser.new_page(viewport={"width": 1600, "height": 1000})
            errors: list[str] = []
            page.on("pageerror", lambda err: errors.append(str(err)))
            page.set_content(
                render_static_dashboard_html(
                    graph, conversation_entries=conversation_entries
                )
            )
            page.wait_for_selector("svg", timeout=15000)
            if after_load is not None:
                after_load(page)
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
                        kinds = expect.get("action_kinds")
                        if kinds:
                            names = {a.get("name") for a in actions}
                            assert names & set(kinds), (phase, names, kinds)
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
                        assert contexts, (phase, "expected model context for flow order")
                        assert actions, (phase, "expected action for flow order")
                        root_id = expect["root_ids"][0]
                        child_id = expect["child_ids"][0]
                        assert (
                            positions[root_id]["x"]
                            < positions[contexts[0]["id"]]["x"]
                            < positions[actions[0]["id"]]["x"]
                            < positions[child_id]["x"]
                        ), (phase, positions)
                if conversation_entries is not None:
                    static = page.evaluate("window.__execweaveStaticConversations")
                    static_blob = json.dumps(static, default=str)
                    for needle in expect.get("inspector_needles", []):
                        assert needle in static_blob, (phase, needle, static_blob[:400])
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
    relations = {e.get("relation") for e in events}
    assert "REQUESTED_SUBTASK" in relations, relations
    assert "ASSIGNED_AGENT_TASK" in relations, relations
    assert "INVOKES_MODEL" in relations or "USED_MODEL" in relations or "INVOKED_MODEL" in relations, relations
    child_id = "agent:antigravity:conversation:child-conv-1"
    assert any(
        isinstance(e.get("target"), dict) and e["target"].get("id") == child_id
        for e in events
        if e.get("relation") in {"ASSIGNED_AGENT_TASK", "HAS_CHILD_AGENT_SESSION"}
    ), events
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
            response = {
                "id": f"msg_{idx}",
                "type": "message",
                "role": "assistant",
                "model": "claude-haiku-audit",
                "content": [{"type": "text", "text": response_text}],
                "usage": {"input_tokens": 3, "output_tokens": 4},
            }
            request = {
                "model": "claude-haiku-audit",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 64,
            }
            events.extend(
                anthropic_response_to_events(
                    response,
                    endpoint="https://api.anthropic.com",
                    request_id=request_id,
                    timestamp=TS,
                )
            )
            events.extend(
                anthropic_exchange_to_content_events(
                    {"request": request, "response": response},
                    store=store,
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
            request = {
                "model": "compat-audit",
                "messages": [{"role": "user", "content": prompt}],
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
            events.extend(
                openai_compatible_exchange_to_content_events(
                    {"request": request, "response": response},
                    store=store,
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
            request = {
                "model": "openrouter/audit",
                "messages": [{"role": "user", "content": prompt}],
            }
            events.extend(
                openrouter_response_to_events(
                    response,
                    endpoint="https://openrouter.ai/api/v1",
                    request_id=request_id,
                    timestamp=TS,
                )
            )
            events.extend(
                openrouter_exchange_to_content_events(
                    {"request": request, "response": response},
                    store=store,
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
            response = {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": response_text,
                        }
                    }
                ]
            }
            standard = {
                "id": request_id,
                "model": "gpt-audit",
                "messages": [{"role": "user", "content": prompt}],
                "response": response,
                "startTime": TS,
                "endTime": TS,
            }
            events.extend(standard_logging_to_events(standard))
            events.extend(
                litellm_callback_to_content_events(
                    {
                        "standard_logging_object": standard,
                        "messages": standard["messages"],
                        "response": response,
                    },
                    response,
                    store=store,
                    timestamp=TS,
                )
            )
        else:
            raise KeyError(provider)
    return events, request_ids


def _expect_for(provider: str) -> dict[str, Any]:
    if provider in PROVIDER_CONTRACT:
        return dict(PROVIDER_CONTRACT[provider])
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


def _store_root(tmp_path: Path, provider: str) -> Path:
    return tmp_path / f"{provider}-store"


def _read_store_blob(store_root: Path) -> str:
    if not store_root.is_dir():
        return ""
    parts: list[str] = []
    for path_file in store_root.rglob("*"):
        if path_file.is_file():
            parts.append(path_file.read_text(encoding="utf-8", errors="ignore"))
    return "\n".join(parts)


def _enrich_conversation_entries(
    graph: dict[str, Any], store_root: Path
) -> list[dict[str, Any]]:
    entries = conversation_record_entries(graph, store_root)
    enriched: list[dict[str, Any]] = []
    for entry in entries:
        item = dict(entry)
        rel = store_root / str(entry.get("path") or "")
        if rel.is_file():
            try:
                item["recorded_payload"] = json.loads(
                    rel.read_text(encoding="utf-8")
                )
            except json.JSONDecodeError:
                item["recorded_payload"] = rel.read_text(encoding="utf-8", errors="ignore")
        enriched.append(item)
    return enriched


def _assert_two_round_content(
    provider: str,
    graph: dict[str, Any],
    tmp_path: Path,
    expected_request_ids: set[str],
) -> list[dict[str, Any]]:
    assert len(expected_request_ids) == 2, expected_request_ids
    id_blob = "\n".join(
        [str(n.get("id") or "") for n in graph["nodes"]]
        + [str(e.get("id") or "") for e in graph["edges"]]
        + [
            str((n.get("attributes") or {}).get("request_id") or "")
            for n in graph["nodes"]
        ]
    )
    for rid in expected_request_ids:
        assert rid in id_blob, (provider, rid, id_blob[:500])

    store_root = _store_root(tmp_path, provider)
    store_blob = _read_store_blob(store_root)
    entries = _enrich_conversation_entries(graph, store_root)
    entry_blob = json.dumps(entries, default=str)
    graph_blob = json.dumps(graph, default=str)
    combined = "\n".join([store_blob, entry_blob, graph_blob])

    assert "round-one-prompt" in combined, provider
    assert "round-two-prompt" in combined, provider
    assert f"{provider}-answer-1" in combined, provider
    assert f"{provider}-answer-2" in combined, provider

    # conversation_record_entries must retain both rounds (ordered by request id).
    req_names = [e.get("source_name") for e in entries if e.get("source_name")]
    for rid in expected_request_ids:
        assert rid in req_names or rid in entry_blob, (provider, rid, req_names)

    # Both rounds' request entities must exist in the materialized graph.
    request_nodes = [
        n for n in graph["nodes"] if n.get("type") in {"inference_request", "request"}
    ]
    assert len(request_nodes) >= 2, (provider, [n.get("id") for n in request_nodes])

    # No agent orchestration invented for runtime/gateway providers.
    agent_nodes = [n for n in graph["nodes"] if n.get("type") == "agent"]
    assert not any(
        (n.get("attributes") or {}).get("agent_role") in {"subagent", "worker", "child"}
        for n in agent_nodes
    ), agent_nodes
    return entries


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
    if provider == "antigravity":
        assert any(
            n["id"] == "agent:antigravity:conversation:child-conv-1" for n in graph["nodes"]
        )
        assert any(e.get("relation") == "ASSIGNED_AGENT_TASK" for e in graph["edges"])

    expect = _expect_for(provider)
    conversation_entries = None
    if provider in RUNTIME_GATEWAY:
        conversation_entries = _assert_two_round_content(
            provider, graph, tmp_path, expected_request_ids
        )
        expect = {
            **expect,
            "inspector_needles": [
                "round-one-prompt",
                "round-two-prompt",
                f"{provider}-answer-1",
                f"{provider}-answer-2",
            ],
        }

    _browser_assert(
        graph, expect=expect, conversation_entries=conversation_entries
    )


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


def test_negative_control_missing_metrics_api_fails_browser_assert(tmp_path: Path) -> None:
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

    def wipe_metrics(page):
        page.evaluate("window.__execweavePr70 = undefined")

    with pytest.raises(AssertionError, match="metrics API missing"):
        _browser_assert(
            graph,
            expect={"min_agents": 0, "forbid_children": True},
            after_load=wipe_metrics,
        )


def test_mutation_agy_missing_child_fails_contract(tmp_path: Path) -> None:
    events, _ = _events_for("antigravity", tmp_path)
    graph = _accumulate("mut-agy", events, tmp_path)
    graph["nodes"] = [
        n
        for n in graph["nodes"]
        if n.get("id") != "agent:antigravity:conversation:child-conv-1"
    ]
    graph["edges"] = [
        e
        for e in graph["edges"]
        if e.get("source") != "agent:antigravity:conversation:child-conv-1"
        and e.get("target") != "agent:antigravity:conversation:child-conv-1"
    ]
    with pytest.raises(AssertionError):
        _browser_assert(graph, expect=_expect_for("antigravity"))


@pytest.mark.parametrize("provider", AGENT_PROVIDERS)
def test_mutation_delete_child_fails_provider_contract(provider: str, tmp_path: Path) -> None:
    events, _ = _events_for(provider, tmp_path)
    graph = _accumulate(f"mut-child-{provider}", events, tmp_path)
    expect = _expect_for(provider)
    child_id = expect["child_ids"][0]
    graph["nodes"] = [n for n in graph["nodes"] if n.get("id") != child_id]
    graph["edges"] = [
        e
        for e in graph["edges"]
        if e.get("source") != child_id and e.get("target") != child_id
    ]
    with pytest.raises(AssertionError):
        _browser_assert(graph, expect=expect)


@pytest.mark.parametrize("provider", AGENT_PROVIDERS)
def test_mutation_delete_action_evidence_fails_provider_contract(
    provider: str, tmp_path: Path
) -> None:
    events, _ = _events_for(provider, tmp_path)
    graph = _accumulate(f"mut-action-{provider}", events, tmp_path)
    expect = _expect_for(provider)
    # Strip assignment/spawn relations so projection cannot form orchestration.
    drop = {
        "SPAWNED_SUBAGENT",
        "SPAWNED_AGENT",
        "ASSIGNED_AGENT_TASK",
        "REQUESTED_SUBTASK",
        "STARTED_AGENT_INTERACTION",
        "TARGETED_BY_AGENT_INTERACTION",
        "HAS_CHILD_AGENT_SESSION",
        "HAS_AGENT_THREAD",
        "DELIVERED_AGENT_MESSAGE",
        "SENT_AGENT_MESSAGE",
    }
    graph["edges"] = [e for e in graph["edges"] if e.get("relation") not in drop]
    with pytest.raises(AssertionError):
        _browser_assert(graph, expect=expect)


@pytest.mark.parametrize("provider", AGENT_PROVIDERS)
def test_mutation_delete_model_fails_flow_order(provider: str, tmp_path: Path) -> None:
    events, _ = _events_for(provider, tmp_path)
    graph = _accumulate(f"mut-model-{provider}", events, tmp_path)
    expect = _expect_for(provider)
    model_ids = {n["id"] for n in graph["nodes"] if n.get("type") == "model"}
    assert model_ids, provider
    graph["nodes"] = [n for n in graph["nodes"] if n.get("id") not in model_ids]
    graph["edges"] = [
        e
        for e in graph["edges"]
        if e.get("source") not in model_ids and e.get("target") not in model_ids
    ]
    with pytest.raises(AssertionError):
        _browser_assert(graph, expect=expect)


def test_mutation_corrupt_child_identity_fails(tmp_path: Path) -> None:
    events, _ = _events_for("cursor", tmp_path)
    graph = _accumulate("mut-corrupt-child", events, tmp_path)
    expect = _expect_for("cursor")
    child_id = expect["child_ids"][0]
    for node in graph["nodes"]:
        if node.get("id") == child_id:
            node["id"] = "agent:cursor:cursor-pipe:subagent:WRONG"
            node.setdefault("attributes", {})["agent_role"] = "root"
    for edge in graph["edges"]:
        if edge.get("source") == child_id:
            edge["source"] = "agent:cursor:cursor-pipe:subagent:WRONG"
        if edge.get("target") == child_id:
            edge["target"] = "agent:cursor:cursor-pipe:subagent:WRONG"
    with pytest.raises(AssertionError):
        _browser_assert(graph, expect=expect)


def test_mutation_arrange_intersection_fails_browser_assert(tmp_path: Path) -> None:
    events, _ = _events_for("opencode", tmp_path)
    graph = _accumulate("mut-intersect", events, tmp_path)
    expect = _expect_for("opencode")

    def force_intersection(page):
        page.evaluate(
            """() => {
              const real = window.__execweavePr70.metrics.bind(window.__execweavePr70);
              window.__execweavePr70.metrics = () => {
                const m = real();
                // Only poison Arrange: first call stays clean, later calls fail.
                if (window.__ewArrangePoison) {
                  return Object.assign({}, m, {EDGE_NODE_INTERSECTIONS: 2});
                }
                window.__ewArrangePoison = true;
                return m;
              };
            }"""
        )

    with pytest.raises(AssertionError):
        _browser_assert(graph, expect=expect, after_load=force_intersection)


@pytest.mark.parametrize(
    "provider",
    ["ollama", "anthropic", "openai-compatible", "openrouter", "litellm"],
)
def test_mutation_delete_second_round_content_fails(provider: str, tmp_path: Path) -> None:
    events, request_ids = _two_round_runtime(provider, tmp_path)
    graph = _accumulate(f"mut-round2-{provider}", events, tmp_path)
    store_root = _store_root(tmp_path, provider)
    # Delete round-two content files while leaving two request ids in the graph.
    for path_file in list(store_root.rglob("*")):
        if not path_file.is_file():
            continue
        body = path_file.read_text(encoding="utf-8", errors="ignore")
        if "round-two-prompt" in body or f"{provider}-answer-2" in body:
            path_file.unlink()
    with pytest.raises(AssertionError):
        _assert_two_round_content(provider, graph, tmp_path, request_ids)
