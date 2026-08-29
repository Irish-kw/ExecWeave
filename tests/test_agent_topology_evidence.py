"""Agent topology must come from provider evidence, never from naming conventions.

ExecWeave previously classified an agent as a child whenever its node id was absent
from a hardcoded allowlist of provider display names. A single-agent OpenCode run was
therefore published as ``/root/<session-id>`` with ``is_root: False`` and a
``parent_thread_id`` naming a parent that never existed.

Absence of evidence is not evidence of a parent. These tests pin the inverted rule:
an agent is root unless the provider positively established a parent, and every
relationship that does exist carries the provenance of the fact that established it.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from execweave import agent_topology
from execweave.agent_trace import cursor_subagent, opencode_session_agent
from execweave.content_evidence import content_observation_event
from execweave.content_store import FullFidelityContentStore
from execweave.conversation_records import conversation_record_entries
from execweave.opencode_task_linkage import opencode_task_session_events

VIEWER_TREE = Path(__file__).resolve().parents[1] / "src" / "execweave" / "viewer_conversation_tree.py"


def _graph_with_content(
    run_root: Path,
    sources: list[tuple[dict[str, Any], str, str]],
) -> dict[str, Any]:
    """Archive one conversation value per source and return the resulting graph."""
    store = FullFidelityContentStore(run_root)
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    for index, (source, content_kind, value) in enumerate(sources):
        reference = store.put_text(value, content_kind=content_kind)
        event = content_observation_event(
            timestamp=f"2026-08-29T00:0{index}:00Z",
            provider=str((source.get("attributes") or {}).get("provider") or "unknown"),
            source=source,
            reference=reference,
            relation="PRODUCED_ASSISTANT_RESPONSE",
            observed_field="text",
            evidence_source="provider_plugin",
            attribution="provider_hook",
        )
        nodes.setdefault(event["source"]["id"], event["source"])
        nodes.setdefault(event["target"]["id"], event["target"])
        edges.append(
            {
                "source": event["source"]["id"],
                "target": event["target"]["id"],
                "relation": event["relation"],
                "first_sequence": index,
                "last_sequence": index,
                "first_seen": event["timestamp"],
                "last_seen": event["timestamp"],
            }
        )
    return {"nodes": list(nodes.values()), "edges": edges}


def _threads(graph: dict[str, Any], run_root: Path) -> dict[str, dict[str, Any]]:
    threads: dict[str, dict[str, Any]] = {}
    for entry in conversation_record_entries(graph, run_root):
        preview = entry.get("conversation_preview")
        if isinstance(preview, dict) and preview.get("agent_path"):
            threads[str(preview["agent_path"])] = preview
    return threads


# ── 1. OpenCode single root ──────────────────────────────────────────────────


def test_opencode_single_session_is_root_not_a_fabricated_child(tmp_path: Path) -> None:
    """The exact shape that shipped broken: one session, no parent evidence at all."""
    graph = _graph_with_content(
        tmp_path,
        [(opencode_session_agent("ses_abc123"), "opencode.assistant_response", "root answer")],
    )
    threads = _threads(graph, tmp_path)

    assert set(threads) == {"/root"}
    root = threads["/root"]
    assert root["is_root"] is True
    assert root["parent_thread_id"] is None
    assert root["parent_agent_path"] is None
    assert "/root/ses_abc123" not in threads
    # A session id is not a parent link, so the root position is provider-reported
    # while "/root" itself stays ExecWeave's canonical rendering.
    assert root["topology_state"] == agent_topology.TOPOLOGY_PROVIDER_REPORTED
    assert root["agent_path_source"] == agent_topology.PATH_EXECWEAVE_DERIVED
    assert root["topology_evidence"] == agent_topology.EVIDENCE_PROVIDER_SESSION_ROOT


def test_child_declaration_wins_regardless_of_event_order() -> None:
    """Event order is not guaranteed, so a parent declaration must never be lost.

    A session's completion evidence can be observed before the task metadata that
    names its parent. Root and child declarations are namespaced apart so the
    first-write-wins node merge cannot let absence of evidence beat evidence.
    """
    root_attrs = agent_topology.root_topology()
    child_attrs = agent_topology.subagent_topology(
        evidence=agent_topology.EVIDENCE_PARENT_SESSION_ID, parent_scope_id="ses_parent"
    )
    assert not set(root_attrs) & (set(child_attrs) - {agent_topology.ATTR_ROLE})

    root_first = {**root_attrs, **child_attrs}
    child_first = dict(child_attrs)
    for key, value in root_attrs.items():
        child_first.setdefault(key, value)

    for attrs in (root_first, child_first):
        resolved = agent_topology.resolve_agent_topology(
            {"id": "agent:opencode:session:ses_child", "type": "agent",
             "attributes": {**attrs, "session_id": "ses_child"}}
        )
        assert resolved.is_root is False
        assert resolved.agent_path == "/root/ses_child"
        assert resolved.parent_relation_source == (
            agent_topology.EVIDENCE_PARENT_SESSION_ID
        )


# ── 2. OpenCode explicit child ───────────────────────────────────────────────


def _opencode_task_payload() -> dict[str, Any]:
    """A task-tool event whose own metadata names the parent session."""
    return {
        "hook_event_name": "event",
        "event": {
            "type": "message.part.updated",
            "properties": {
                "part": {
                    "type": "tool",
                    "tool": "task",
                    "sessionID": "ses_parent",
                    "callID": "call_1",
                    "state": {
                        "status": "completed",
                        "input": {"subagent_type": "explorer"},
                        "metadata": {
                            "parentSessionId": "ses_parent",
                            "sessionId": "ses_child",
                        },
                    },
                }
            },
        },
    }


def test_opencode_child_requires_provider_parent_session_id() -> None:
    events = opencode_task_session_events(
        _opencode_task_payload(), timestamp="2026-08-29T00:00:00Z"
    )
    assert events, "provider parentSessionId evidence should produce linkage events"
    child = next(
        node
        for event in events
        for node in (event["source"], event["target"])
        if node.get("id") == "agent:opencode:session:ses_child"
    )
    attrs = child["attributes"]
    assert attrs[agent_topology.ATTR_ROLE] == agent_topology.AGENT_ROLE_SUBAGENT
    assert attrs[agent_topology.ATTR_PARENT_SCOPE] == "ses_parent"
    assert attrs[agent_topology.ATTR_PARENT_EVIDENCE] == (
        agent_topology.EVIDENCE_PARENT_SESSION_ID
    )
    # The provider reported the relationship but never published a path, so no
    # child path is declared and the canonical one stays ExecWeave's rendering.
    assert agent_topology.ATTR_CHILD_PATH not in attrs
    resolved = agent_topology.resolve_agent_topology(child)
    assert resolved.topology_state == agent_topology.TOPOLOGY_PROVIDER_REPORTED
    assert resolved.agent_path_source == agent_topology.PATH_EXECWEAVE_DERIVED


def test_opencode_child_materializes_under_root_with_provenance(tmp_path: Path) -> None:
    events = opencode_task_session_events(
        _opencode_task_payload(), timestamp="2026-08-29T00:00:00Z"
    )
    child_node = next(
        node
        for event in events
        for node in (event["source"], event["target"])
        if node.get("id") == "agent:opencode:session:ses_child"
    )
    graph = _graph_with_content(
        tmp_path,
        [
            (opencode_session_agent("ses_parent"), "opencode.assistant_response", "parent answer"),
            (child_node, "opencode.assistant_response", "child answer"),
        ],
    )
    threads = _threads(graph, tmp_path)

    assert threads["/root"]["is_root"] is True
    child = threads["/root/ses_child"]
    assert child["is_root"] is False
    assert child["parent_agent_path"] == "/root"
    assert child["parent_relation_source"] == agent_topology.EVIDENCE_PARENT_SESSION_ID
    # The canonical path must not masquerade as something OpenCode published.
    assert child["agent_path_source"] == agent_topology.PATH_EXECWEAVE_DERIVED
    assert child["provider_native_id"] == "ses_child"


# ── 3. Unknown agent source ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    "attributes",
    [
        {"provider": "acme"},
        {"provider": "acme", "session_id": "sess-9"},
        {"provider": "acme", "conversation_id": "conv-9"},
        {"provider": "acme", "agent_nickname": "Scout"},
        {"provider": "acme", "agent_id": "opaque-native-id"},
    ],
    ids=["bare", "session-id", "conversation-id", "nickname", "opaque-agent-id"],
)
def test_unfamiliar_agent_without_parent_evidence_is_root(
    tmp_path: Path, attributes: dict[str, Any]
) -> None:
    """None of these facts establishes a parent, so none may produce a child."""
    source = {
        "id": "agent:acme:whatever-shape",
        "type": "agent",
        "name": "Acme Agent",
        "attributes": attributes,
    }
    threads = _threads(
        _graph_with_content(tmp_path, [(source, "acme.assistant_response", "answer")]),
        tmp_path,
    )
    assert set(threads) == {"/root"}
    assert threads["/root"]["is_root"] is True
    assert threads["/root"]["parent_agent_path"] is None
    assert threads["/root"]["topology_evidence"] == (
        agent_topology.EVIDENCE_NO_PARENT_EVIDENCE
    )


def test_source_type_agent_alone_is_never_child_evidence() -> None:
    topology = agent_topology.resolve_agent_topology(
        {"id": "agent:unknown", "type": "agent", "attributes": {"provider": "x"}}
    )
    assert topology.is_root is True
    assert topology.parent_agent_path is None
    assert topology.topology_state == agent_topology.TOPOLOGY_DERIVED


# ── 5. Graph ↔ conversation agreement ────────────────────────────────────────


def test_conversation_paths_are_a_subset_of_graph_agent_paths(tmp_path: Path) -> None:
    events = opencode_task_session_events(
        _opencode_task_payload(), timestamp="2026-08-29T00:00:00Z"
    )
    child_node = next(
        node
        for event in events
        for node in (event["source"], event["target"])
        if node.get("id") == "agent:opencode:session:ses_child"
    )
    graph = _graph_with_content(
        tmp_path,
        [
            (opencode_session_agent("ses_parent"), "opencode.assistant_response", "parent"),
            (child_node, "opencode.assistant_response", "child"),
        ],
    )
    graph_paths = {
        agent_topology.resolve_agent_topology(node).agent_path
        for node in graph["nodes"]
        if node.get("type") == "agent"
    }
    conversation_paths = set(_threads(graph, tmp_path))
    assert conversation_paths <= graph_paths

    entries = [
        entry
        for entry in conversation_record_entries(graph, tmp_path)
        if isinstance(entry.get("conversation_preview"), dict)
    ]
    graph_ids = {node["id"] for node in graph["nodes"] if node.get("type") == "agent"}
    assert {entry["source_id"] for entry in entries} <= graph_ids

    by_path = _threads(graph, tmp_path)
    for path, preview in by_path.items():
        parent = preview.get("parent_agent_path")
        if parent is not None:
            assert parent in by_path, f"{path} names a parent with no conversation"


# ── 6. Provider-neutral: no fabricated topology anywhere ─────────────────────


def _root_only_sources() -> list[tuple[str, dict[str, Any], str]]:
    return [
        (
            "claude",
            {"id": "agent:Claude Code", "type": "agent", "name": "Claude Code",
             "attributes": {"provider": "claude", "session_id": "sess-1"}},
            "claude.assistant_final_response",
        ),
        (
            "cursor",
            {"id": "agent:Cursor", "type": "agent", "name": "Cursor",
             "attributes": {"provider": "cursor", "conversation_id": "conv-1"}},
            "cursor.assistant_final_response",
        ),
        (
            "opencode",
            opencode_session_agent("ses_solo"),
            "opencode.assistant_response",
        ),
        (
            "antigravity",
            {"id": "agent:antigravity:conversation:conv-7", "type": "agent",
             "name": "Antigravity conversation",
             "attributes": {"provider": "antigravity", "conversation_id": "conv-7"}},
            "antigravity.assistant_response",
        ),
        (
            "gemini",
            {"id": "agent:Gemini CLI", "type": "agent", "name": "Gemini CLI",
             "attributes": {"provider": "gemini", "session_id": "g-1"}},
            "gemini.assistant_final_response",
        ),
        (
            "openrouter",
            {"id": "agent:openrouter", "type": "agent", "name": "OpenRouter",
             "attributes": {"provider": "openrouter", "session_id": "or-1"}},
            "inference_gateway.openrouter.response",
        ),
    ]


@pytest.mark.parametrize(
    "provider,source,content_kind",
    _root_only_sources(),
    ids=[case[0] for case in _root_only_sources()],
)
def test_root_only_providers_never_gain_fabricated_topology(
    tmp_path: Path, provider: str, source: dict[str, Any], content_kind: str
) -> None:
    threads = _threads(
        _graph_with_content(tmp_path / provider, [(source, content_kind, "answer")]),
        tmp_path / provider,
    )
    assert set(threads) == {"/root"}, f"{provider} fabricated {sorted(threads)}"
    preview = threads["/root"]
    assert preview["is_root"] is True
    assert preview["parent_thread_id"] is None
    assert preview["parent_agent_path"] is None


def test_claude_subagent_path_is_not_presented_as_provider_declared(tmp_path: Path) -> None:
    """Claude exposes an agent id, never an agent path. Say so."""
    from execweave.claude_delegation import _subagent

    child = _subagent({"session_id": "sess-1", "agent_id": "7", "agent_type": "Explore"})
    assert child is not None
    threads = _threads(
        _graph_with_content(tmp_path, [(child, "claude.subagent_final_response", "done")]),
        tmp_path,
    )
    preview = next(iter(threads.values()))
    assert preview["is_root"] is False
    assert preview["agent_path_source"] == agent_topology.PATH_EXECWEAVE_DERIVED
    assert preview["topology_state"] == agent_topology.TOPOLOGY_PROVIDER_REPORTED
    assert preview["parent_relation_source"] == (
        agent_topology.EVIDENCE_SUBAGENT_LIFECYCLE_HOOK
    )


def test_cursor_subagent_keeps_provider_reported_relationship(tmp_path: Path) -> None:
    child = cursor_subagent(
        {"session_id": "sess-1", "subagent_id": "child-1", "subagent_type": "Explore"}
    )
    assert child is not None
    threads = _threads(
        _graph_with_content(tmp_path, [(child, "cursor.subagent_summary", "summary")]),
        tmp_path,
    )
    preview = next(iter(threads.values()))
    assert preview["is_root"] is False
    assert preview["parent_relation_source"] == (
        agent_topology.EVIDENCE_SUBAGENT_LIFECYCLE_HOOK
    )
    assert preview["agent_path_source"] == agent_topology.PATH_EXECWEAVE_DERIVED


# ── Backward compatibility with pre-provenance artifacts ─────────────────────


def test_legacy_artifact_paths_are_preserved_but_never_upgraded() -> None:
    """A v0.7.2 artifact recorded paths without provenance. Keep them, claim nothing."""
    legacy = agent_topology.resolve_agent_topology(
        {
            "id": "agent:codex:s:subagent:a",
            "type": "agent",
            "attributes": {"provider": "codex", "agent_path": "/root/legacy_child"},
        }
    )
    assert legacy.agent_path == "/root/legacy_child"
    assert legacy.is_root is False
    assert legacy.agent_path_source == agent_topology.PATH_LEGACY_UNKNOWN
    assert legacy.topology_state == agent_topology.TOPOLOGY_UNRESOLVED
    assert legacy.topology_evidence == agent_topology.EVIDENCE_LEGACY_ARTIFACT


def test_legacy_root_path_still_resolves_as_root() -> None:
    legacy = agent_topology.resolve_agent_topology(
        {"id": "agent:OpenAI Codex", "type": "agent", "attributes": {"agent_path": "/root"}}
    )
    assert legacy.is_root is True
    assert legacy.parent_agent_path is None


# ── 7. Viewer must not relabel a child as root ───────────────────────────────


def test_viewer_root_selection_has_no_first_record_fallback() -> None:
    source = VIEWER_TREE.read_text(encoding="utf-8")
    assert "records[0]" not in source, (
        "falling back to the first record relabels an arbitrary child as run root"
    )
    assert "No root agent identified" in source


@pytest.mark.skipif(shutil.which("node") is None, reason="node is unavailable")
def test_viewer_root_selection_returns_null_without_a_root(tmp_path: Path) -> None:
    """Execute the real shipped function rather than asserting on its source text."""
    source = VIEWER_TREE.read_text(encoding="utf-8")
    start = source.index("function execweaveConversationRootRecord(records)")
    end = source.index("}", source.index("return", start)) + 1
    script = tmp_path / "root_record.js"
    script.write_text(
        source[start:end]
        + """
const childOnly = [{key: 'thread:a', path: '/root/ses_abc123', isRoot: false}];
const withRoot = [{key: 'thread:a', path: '/root/child', isRoot: false},
                  {key: 'thread:b', path: '/root', isRoot: true}];
console.log(JSON.stringify({
  childOnly: execweaveConversationRootRecord(childOnly),
  withRoot: (execweaveConversationRootRecord(withRoot) || {}).path,
}));
""",
        encoding="utf-8",
    )
    result = subprocess.run(
        [shutil.which("node"), str(script)], capture_output=True, text=True, check=True
    )
    payload = json.loads(result.stdout)
    assert payload["childOnly"] is None, "a lone child must not be promoted to root"
    assert payload["withRoot"] == "/root"


# ── CI must keep exercising the final conversation artifact ──────────────────

CI_WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"


def test_ci_verifies_materialized_conversations_for_every_provider_smoke() -> None:
    """Green CI with ``entry_count: 0`` is how the v0.7.2 collapse shipped.

    Every provider that runs a record smoke must also assert the conversations that
    smoke produced, or the pipeline can silently stop materializing them again.
    """
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    for provider in ("claude", "cursor", "gemini", "opencode", "codex"):
        assert f"execweave-{provider}-record" in workflow, f"{provider} has no record smoke"
        assert f"check_conversation_records.py {provider}-record-smoke" in workflow, (
            f"{provider} records a run but never checks its conversations.json"
        )


def test_ci_covers_the_codex_subagent_transcript_selection() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    assert "emit_codex_hook_smoke.py" in workflow
    assert "check_codex_hook.py" in workflow
    # The child conversation only survives if agent_transcript_path was selected.
    assert "--expect-agent /root/explorer" in workflow
    assert "CI CHILD PRIVATE REASONING" in workflow

    emitter = (
        Path(__file__).resolve().parents[1] / "scripts" / "emit_codex_hook_smoke.py"
    ).read_text(encoding="utf-8")
    assert '"transcript_path": str(parent_path)' in emitter
    assert '"agent_transcript_path": str(child_path)' in emitter
