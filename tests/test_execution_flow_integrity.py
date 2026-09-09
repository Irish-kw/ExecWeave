"""Node-executed hardened+normalized execution-flow integrity regressions."""
from __future__ import annotations

import copy
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from execweave.viewer_execution_flow import EXECUTION_FLOW_SCRIPT
from execweave.viewer_execution_flow_provider_normalization import (
    normalize_provider_execution_flow,
)
from execweave.viewer_execution_flow_safety import harden_execution_flow_projection
from execweave.viewer_layout_v2 import LAYOUT_V2_SCRIPT

pytestmark = pytest.mark.viewer_e2e

NODE = shutil.which("node")
if NODE is None:
    raise RuntimeError("node is required for execution-flow integrity tests")


def _hardened_script() -> str:
    # Projection integrity only needs the flow script; layout is irrelevant here.
    return normalize_provider_execution_flow(
        harden_execution_flow_projection(EXECUTION_FLOW_SCRIPT)
    )


def _project(raw: dict, display: dict | None = None) -> dict:
    display = copy.deepcopy(display if display is not None else raw)
    raw_before = json.dumps(raw, sort_keys=True, default=str)
    script = _hardened_script()
    # Write the harness to a temp file: embedding the full hardened script in
    # ``node -e`` exceeds Windows CreateProcess command-line limits (WinError 206).
    parts = [
        "const fs=require('fs');",
        "const payload=JSON.parse(fs.readFileSync(0,'utf8'));",
        "global.window=global;",
        "global.document={};",
        script,
        "const api=window.__execweaveExecutionFlow;",
        "if(!api||typeof api.project!=='function'){",
        "throw new Error('execution flow project API missing');}",
        "const out=api.project(",
        "JSON.parse(JSON.stringify(payload.display)),",
        "JSON.parse(JSON.stringify(payload.raw)));",
        "process.stdout.write(JSON.stringify({display:out,raw:payload.raw}));",
    ]
    harness = "\n".join(parts)
    with tempfile.TemporaryDirectory() as tmp:
        runner = Path(tmp) / "project_flow.js"
        runner.write_text(harness, encoding="utf-8")
        proc = subprocess.run(
            [NODE, str(runner)],
            input=json.dumps({"raw": raw, "display": display}),
            capture_output=True,
            text=True,
            check=False,
        )
    if proc.returncode != 0:
        raise AssertionError(proc.stderr or proc.stdout or "node failed")
    result = json.loads(proc.stdout)
    assert json.dumps(result["raw"], sort_keys=True, default=str) == raw_before
    return result["display"]


def _edge(eid, src, tgt, rel, seq=1, **extra):
    payload = {
        "id": eid,
        "source": src,
        "target": tgt,
        "relation": rel,
        "first_sequence": seq,
        "last_sequence": seq,
        "first_seen": f"2026-09-09T10:00:{seq:02d}.000Z",
        "last_seen": f"2026-09-09T10:00:{seq:02d}.000Z",
        "event_types": [f"semantic.test.{rel.lower()}"],
        "backends": ["semantic"],
        "attributions": ["test_fixture"],
        "inferred": False,
        "viewer_only": False,
        "attributes": {"provider": "test", "evidence_source": "fixture"},
    }
    payload.update(extra)
    return payload


def _agent(aid, name, **attrs):
    return {
        "id": aid,
        "type": "agent",
        "name": name,
        "attributes": {"provider": "test", **attrs},
    }


def _model(mid, name, **attrs):
    return {
        "id": mid,
        "type": "model",
        "name": name,
        "attributes": {"provider": "test", "model_name": name, **attrs},
    }


def test_hardened_flow_end_anchor_is_unique():
    from execweave.viewer_execution_flow_safety import _FLOW_END

    html = LAYOUT_V2_SCRIPT + "\n" + EXECUTION_FLOW_SCRIPT
    assert html.count(_FLOW_END) == 1
    out = harden_execution_flow_projection(html)
    assert out.count("return finalizeFlowGeometry();") >= 1
    # Layout V2 must not have been rewritten to finalizeFlowGeometry incorrectly:
    # the unique anchor includes window.execweaveApplyExecutionFlowColumns.
    assert "window.execweaveApplyExecutionFlowColumns=execweaveApplyExecutionFlowColumns" in out


def test_duplicate_aliases_and_reverse_order_abstain_or_exact():
    # Five agents share nickname "dup"; exact id must still resolve; bare alias abstains.
    agents = [
        _agent("agent:a1", "One", nickname="dup", agent_id="a1"),
        _agent("agent:a2", "Two", nickname="dup", agent_id="a2"),
        _agent("agent:a3", "Three", nickname="dup", agent_id="a3"),
        _agent("agent:a4", "Four", nickname="dup", agent_id="a4"),
        _agent("agent:root", "/root", agent_role="root", agent_path="/root", viewer_root=True),
    ]
    # Reverse insertion order vs id order
    agents = list(reversed(agents))
    m = _model("model:m1", "shared-model")
    raw = {
        "schema_version": "1.0",
        "session_id": "alias-integrity",
        "nodes": agents + [m],
        "edges": [
            _edge("m", "agent:root", "model:m1", "USED_MODEL", 1),
            _edge("s1", "agent:root", "agent:a1", "SPAWNED_AGENT", 2),
            _edge("s2", "agent:root", "agent:a2", "SPAWNED_AGENT", 3),
        ],
    }
    display = _project(raw)
    agent_ids = [n["id"] for n in display["nodes"] if n["type"] == "agent"]
    assert agent_ids.count("agent:a1") == 1
    assert agent_ids.count("agent:a2") == 1
    assert len({n["id"] for n in display["nodes"] if n["type"] == "agent"}) == 5


def test_ambiguous_model_name_and_suffix_do_not_fuzzy_match():
    raw = {
        "schema_version": "1.0",
        "session_id": "model-suffix",
        "nodes": [
            _agent("agent:root", "/root", agent_role="root", viewer_root=True),
            _agent("agent:child", "child"),
            _model("model:gpt-5.5", "gpt-5.5"),
            _model("model:gpt-5.5-pro", "gpt-5.5-pro"),
            {
                "id": "tool-call:1",
                "type": "tool_call",
                "name": "spawn_agent",
                "attributes": {
                    "provider": "test",
                    "tool_name": "spawn_agent",
                    "model": "5.5",  # suffix-only — must abstain
                    "target_agent_id": "agent:child",
                },
            },
        ],
        "edges": [
            _edge("own", "agent:root", "tool-call:1", "REQUESTED_TOOL_CALL", 1),
            _edge("spawn", "agent:root", "agent:child", "SPAWNED_AGENT", 2),
        ],
    }
    display = _project(raw)
    actions = [
        n
        for n in display["nodes"]
        if n.get("attributes", {}).get("viewer_orchestration_action")
    ]
    # Either no model context (abstain) or not wrongly bound via suffix fuzzy match.
    for action in actions:
        mid = action.get("attributes", {}).get("model_resource_id")
        assert mid in (None, ""), action


def test_actor_tool_call_model_hint_does_not_pollute_child_lookup():
    raw = {
        "schema_version": "1.0",
        "session_id": "actor-vs-child",
        "nodes": [
            _agent("agent:root", "/root", agent_role="root", viewer_root=True),
            _agent("agent:child", "child"),
            _model("model:actor", "actor-model"),
            _model("model:child", "child-model"),
            {
                "id": "tool-call:spawn",
                "type": "tool_call",
                "name": "spawn_agent",
                "attributes": {
                    "provider": "test",
                    "tool_name": "spawn_agent",
                    "model": "actor-model",
                    "target_agent_ids": ["agent:child"],
                },
            },
        ],
        "edges": [
            _edge("am", "agent:root", "model:actor", "USED_MODEL", 1),
            _edge("cm", "agent:child", "model:child", "USED_MODEL", 2),
            _edge("req", "agent:root", "tool-call:spawn", "REQUESTED_TOOL_CALL", 3),
            _edge("spawn", "agent:root", "agent:child", "SPAWNED_AGENT", 4),
        ],
    }
    display = _project(raw)
    actions = [
        n
        for n in display["nodes"]
        if n.get("attributes", {}).get("viewer_orchestration_action")
        and n.get("name") == "spawn_agent"
    ]
    assert len(actions) == 1
    assert actions[0]["attributes"].get("model_resource_id") == "model:child"


def test_timestamp_only_action_does_not_bind_future_model_switch():
    # Action has only timestamp; switch has only a later timestamp — comparable.
    # Early timestamp action must not bind the future switch model via kind-rank.
    raw = {
        "schema_version": "1.0",
        "session_id": "moment-ts",
        "nodes": [
            _agent("agent:root", "/root", agent_role="root", viewer_root=True),
            _agent("agent:child", "child"),
            _model("model:early", "early"),
            _model("model:late", "late"),
        ],
        "edges": [
            {
                **_edge("early-m", "agent:root", "model:early", "USED_MODEL", 1),
                "first_sequence": None,
                "last_sequence": None,
                "first_seen": "2026-09-09T10:00:01.000Z",
            },
            {
                **_edge("spawn", "agent:root", "agent:child", "SPAWNED_AGENT", 2),
                "first_sequence": None,
                "last_sequence": None,
                "first_seen": "2026-09-09T10:00:02.000Z",
            },
            {
                **_edge("late-m", "agent:root", "model:late", "SWITCHED_MODEL", 3),
                "first_sequence": None,
                "last_sequence": None,
                "first_seen": "2026-09-09T10:00:09.000Z",
            },
        ],
    }
    # Remove None sequences to simulate GraphNode without first_sequence
    for edge in raw["edges"]:
        if edge.get("first_sequence") is None:
            edge.pop("first_sequence", None)
            edge.pop("last_sequence", None)
    display = _project(raw)
    actions = [
        n
        for n in display["nodes"]
        if n.get("attributes", {}).get("viewer_orchestration_action")
    ]
    assert actions
    assert all(
        a["attributes"].get("model_resource_id") != "model:late" for a in actions
    )


def test_ambiguous_owners_and_unknown_subtask_endpoints_fail_closed():
    interaction = {
        "id": "interaction:1",
        "type": "agent_interaction",
        "name": "spawn_agent",
        "attributes": {"provider": "test", "kind": "spawn_agent"},
    }
    raw = {
        "schema_version": "1.0",
        "session_id": "owners",
        "nodes": [
            _agent("agent:root", "/root", agent_role="root", viewer_root=True),
            _agent("agent:other", "other"),
            _agent("agent:child", "child"),
            interaction,
            {"id": "subtask:1", "type": "subtask", "name": "t", "attributes": {"provider": "test"}},
        ],
        "edges": [
            _edge("s1", "agent:root", "interaction:1", "STARTED_AGENT_INTERACTION", 1),
            _edge("s2", "agent:other", "interaction:1", "STARTED_AGENT_INTERACTION", 1),
            _edge("t1", "interaction:1", "agent:child", "TARGETED_BY_AGENT_INTERACTION", 2),
            _edge(
                "req",
                "agent:root",
                "subtask:1",
                "REQUESTED_SUBTASK",
                3,
                identity_exact=True,
            ),
            _edge(
                "assign",
                "subtask:1",
                "missing-agent",
                "ASSIGNED_AGENT_TASK",
                4,
                identity_exact=True,
            ),
        ],
    }
    display = _project(raw)
    actions = [
        n
        for n in display["nodes"]
        if n.get("attributes", {}).get("viewer_orchestration_action")
    ]
    # Ambiguous interaction owner + unknown assignment endpoint => no invented action.
    assert not any(a["name"] == "assign_agent_task" for a in actions)


def test_shared_model_and_tool_survive_partial_consumption():
    raw = {
        "schema_version": "1.0",
        "session_id": "shared-tool",
        "nodes": [
            _agent("agent:root", "/root", agent_role="root", viewer_root=True),
            _agent("agent:child", "child"),
            _agent("agent:other", "other"),
            _model("model:shared", "shared"),
            {
                "id": "tool:shared",
                "type": "tool",
                "name": "run",
                "attributes": {"provider": "test", "native_name": "run"},
            },
            {
                "id": "tool-call:consumed",
                "type": "tool_call",
                "name": "spawn_agent",
                "attributes": {"provider": "test", "tool_name": "spawn_agent"},
            },
            {
                "id": "tool-call:open",
                "type": "tool_call",
                "name": "run",
                "attributes": {"provider": "test", "tool_name": "run"},
            },
        ],
        "edges": [
            _edge("m1", "agent:root", "model:shared", "USED_MODEL", 1),
            _edge("m2", "agent:other", "model:shared", "USED_MODEL", 1),
            _edge("req", "agent:root", "tool-call:consumed", "REQUESTED_TOOL_CALL", 2),
            _edge("uses1", "tool-call:consumed", "tool:shared", "USES_TOOL", 3),
            _edge("spawn", "agent:root", "agent:child", "SPAWNED_AGENT", 4),
            _edge("req2", "agent:other", "tool-call:open", "REQUESTED_TOOL_CALL", 5),
            _edge("uses2", "tool-call:open", "tool:shared", "USES_TOOL", 6),
        ],
    }
    display = _project(raw)
    visible = {n["id"] for n in display["nodes"]}
    assert "tool:shared" in visible
    assert "model:shared" in visible or any(
        n.get("attributes", {}).get("model_resource_id") == "model:shared"
        for n in display["nodes"]
    )


def test_unconsumed_inferred_spawn_is_preserved():
    raw = {
        "schema_version": "1.0",
        "session_id": "inferred-keep",
        "nodes": [
            _agent("agent:root", "/root", agent_role="root", viewer_root=True),
            _agent("agent:ghost", "ghost"),
            _agent("agent:real", "real"),
            _model("model:m", "m"),
        ],
        "edges": [
            _edge("m", "agent:root", "model:m", "USED_MODEL", 1),
            _edge("real", "agent:root", "agent:real", "SPAWNED_AGENT", 2),
            {
                **_edge("inf", "agent:root", "agent:ghost", "SPAWNED_SUBAGENT", 3),
                "inferred": True,
                "backends": [],
                "event_types": [],
                "attributions": [],
                "attributes": {"inferred": True},
            },
        ],
    }
    display = _project(raw)
    assert any(
        e["relation"] == "SPAWNED_SUBAGENT"
        and e["target"] == "agent:ghost"
        and e.get("inferred") is True
        for e in display["edges"]
    )


def test_raw_json_unchanged_after_projection():
    raw = {
        "schema_version": "1.0",
        "session_id": "raw-immutable",
        "nodes": [
            _agent("agent:root", "/root", agent_role="root", viewer_root=True),
            _agent("agent:child", "child"),
            _model("model:m", "m"),
        ],
        "edges": [
            _edge("m", "agent:root", "model:m", "USED_MODEL", 1),
            _edge("s", "agent:root", "agent:child", "SPAWNED_AGENT", 2),
        ],
    }
    before = copy.deepcopy(raw)
    _project(raw)
    assert raw == before
