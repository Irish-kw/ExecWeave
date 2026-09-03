"""Regression coverage for the real ExecWeave v0.7.2 Codex multi-agent artifact.

The evidence in ``tests/fixtures/codex_multi_agent`` is taken from a real Codex
``gpt-5.6-terra`` run that spawned four collaborating subagents. The run's graph
carried five agents while ``conversations.json`` carried a single ``/root`` entry
that had absorbed every child's returns.

Two independent defects produced that collapse, and both are covered here:

* Codex reports a subagent stop with the child rollout on ``agent_transcript_path``
  while ``transcript_path`` still points at the parent session rollout. Selecting
  the parent meant no child rollout was ever archived, so child conversations never
  reached preview generation at all.
* A parent rollout physically records the delegations it issues and the returns its
  children send. Those records were materialized as parent-owned messages, so the
  root thread stood in for agents that had their own identity.

The fixtures enter the pipeline at the raw provider surface: the recorded Codex
hook payloads and the recorded rollout JSONL, not hand-built preview objects.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from execweave.agent_topology import (
    EVIDENCE_CROSS_AGENT_ROUTING,
    resolve_agent_topology,
)
from execweave.content_store import FullFidelityContentStore
from execweave.conversation_archive import codex_conversation_archive_events
from execweave.conversation_records import conversation_record_entries

FIXTURES = Path(__file__).parent / "fixtures" / "codex_multi_agent"
SESSION_ID = "01a04cea-0a14-71e0-8c32-4aeafda0f039"
CHILDREN = {
    "01a04cea-67b2-7683-9f6b-cd644497b862": "/root/rain_forecast",
    "01a04cea-7a7b-7620-9485-3c9ef4e0b343": "/root/official_alerts",
    "01a04cea-8b3c-7182-8d14-2627b03d8c0d": "/root/hydrology",
    "01a04cea-fe38-7cf3-bf61-ff7ebf2de646": "/root/forecast_consensus",
}
EXPECTED_PATHS = {"/root", *CHILDREN.values()}


def _hook_payloads() -> list[dict[str, Any]]:
    return json.loads((FIXTURES / "hook-payloads.json").read_text(encoding="utf-8"))


def _child_rollout_records(agent_id: str, agent_path: str) -> list[dict[str, Any]]:
    """Rebuild a Codex child rollout in the shape ``session_meta`` declares.

    Codex forks a child thread with ``fork_turns: all``, so the child rollout
    physically replays the parent's history before its own turn begins and marks the
    boundary with ``subagent_history_start_ordinal``. Only records at or after that
    boundary belong to the child.
    """
    leaf = agent_path.rsplit("/", 1)[-1]

    def message(role: str, text: str, *, phase: str | None = None, user: bool = False) -> dict:
        payload: dict[str, Any] = {
            "type": "message",
            "role": role,
            "content": [
                {"type": "input_text" if role == "user" else "output_text", "text": text}
            ],
        }
        if phase is not None:
            payload["phase"] = phase
        if user:
            payload["internal_chat_message_metadata_passthrough"] = {
                "content_item_kinds": ["user.text"]
            }
        return {
            "timestamp": "2026-08-29T09:47:20.000Z",
            "type": "response_item",
            "payload": payload,
        }

    inherited = [
        message("user", "USER TASK: run five agents", user=True),
        message("assistant", "ROOT COMMENTARY: splitting into independent views", phase="commentary"),
    ]
    own = [
        message("user", f"TASK FOR {leaf}"),
        message("assistant", f"{leaf} PRIVATE REASONING", phase="commentary"),
        message("assistant", f"{leaf} FINAL RESPONSE", phase="final_answer"),
    ]
    meta = {
        "timestamp": "2026-08-29T09:47:10.000Z",
        "type": "session_meta",
        "payload": {
            "id": agent_id,
            "session_id": agent_id,
            "cwd": "/workspace/execweave-fixture",
            "originator": "codex-tui",
            "cli_version": "0.150.1",
            "source": {
                "subagent": {
                    "thread_spawn": {
                        "agent_path": agent_path,
                        "agent_nickname": leaf,
                        "parent_thread_id": SESSION_ID,
                    }
                }
            },
            "subagent_history_start_ordinal": 1 + len(inherited),
        },
    }
    return [meta, *inherited, *own]


@pytest.fixture()
def codex_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Stage the recorded run on this platform's filesystem and archive it as Codex would."""
    codex_home = tmp_path / "codex-home"
    sessions = codex_home / "sessions" / "2026" / "08" / "29"
    sessions.mkdir(parents=True)
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    def staged(recorded: str) -> str:
        return str(sessions / Path(recorded.replace("\\", "/")).name)

    payloads = [
        {
            key: staged(value) if key.endswith("transcript_path") else value
            for key, value in payload.items()
        }
        for payload in _hook_payloads()
    ]

    main = next(p for p in payloads if p["hook_event_name"] == "SessionEnd")
    Path(main["transcript_path"]).write_text(
        (FIXTURES / "rollout-main.jsonl").read_text(encoding="utf-8"), encoding="utf-8"
    )
    for payload in payloads:
        agent_id = payload.get("agent_id")
        child_path = payload.get("agent_transcript_path")
        if not agent_id or not child_path:
            continue
        Path(child_path).write_text(
            "".join(
                json.dumps(record, ensure_ascii=False) + "\n"
                for record in _child_rollout_records(agent_id, CHILDREN[agent_id])
            ),
            encoding="utf-8",
        )

    run_root = tmp_path / "run"
    store = FullFidelityContentStore(run_root)
    events: list[dict[str, Any]] = []
    for index, payload in enumerate(payloads):
        events.extend(
            codex_conversation_archive_events(
                payload, store=store, timestamp=f"2026-08-29T09:4{index}:00Z"
            )
        )
    return {"events": events, "run_root": run_root, "payloads": payloads}


def _graph(events: list[dict[str, Any]]) -> dict[str, Any]:
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    for index, event in enumerate(events):
        for entity in (event["source"], event["target"]):
            nodes.setdefault(entity["id"], entity)
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


def _threads(codex_run: dict[str, Any]) -> dict[str, dict[str, Any]]:
    entries = conversation_record_entries(_graph(codex_run["events"]), codex_run["run_root"])
    threads: dict[str, dict[str, Any]] = {}
    for entry in entries:
        preview = entry.get("conversation_preview")
        if isinstance(preview, dict) and preview.get("agent_path"):
            threads[str(preview["agent_path"])] = preview
    return threads


def _texts(preview: dict[str, Any]) -> str:
    return "\n".join(
        str(message.get("text") or "") for message in preview.get("messages") or []
    )


def test_subagent_stop_archives_the_child_rollout_not_the_parent(
    codex_run: dict[str, Any],
) -> None:
    """Codex names the child rollout on agent_transcript_path; the parent is a decoy."""
    stops = [p for p in codex_run["payloads"] if p["hook_event_name"] == "SubagentStop"]
    assert len(stops) == 4
    for payload in stops:
        assert payload["transcript_path"] != payload["agent_transcript_path"]

    subagent_events = [
        event
        for event in codex_run["events"]
        if event["target"]["attributes"]["content_kind"]
        == "codex.conversation_transcript.subagent"
    ]
    assert len(subagent_events) == 4
    for event in subagent_events:
        assert event["attributes"]["observed_field"] == "agent_transcript_path"
        topology = resolve_agent_topology(event["source"])
        assert topology.is_root is False
        assert topology.agent_path in CHILDREN.values()
        # Codex publishes the child's path on its own rollout session_meta.
        assert topology.agent_path_source == "provider_declared"


def test_every_observable_codex_agent_gets_its_own_conversation(
    codex_run: dict[str, Any],
) -> None:
    threads = _threads(codex_run)
    assert set(threads) == EXPECTED_PATHS
    for path in EXPECTED_PATHS:
        assert threads[path]["messages"], f"{path} materialized no messages"
    assert threads["/root"]["is_root"] is True
    for path in CHILDREN.values():
        assert threads[path]["is_root"] is False


def test_conversation_identities_agree_with_graph_agent_identities(
    codex_run: dict[str, Any],
) -> None:
    """conversation agent paths must be a subset of observable graph agent paths."""
    graph = _graph(codex_run["events"])
    graph_paths = {
        resolve_agent_topology(node).agent_path
        for node in graph["nodes"]
        if node["type"] == "agent"
    }
    threads = _threads(codex_run)
    assert set(threads) <= graph_paths
    assert graph_paths == EXPECTED_PATHS

    graph_threads = {
        node["attributes"]["agent_id"]
        for node in graph["nodes"]
        if node["type"] == "agent" and node["attributes"].get("agent_id")
    }
    assert graph_threads == set(CHILDREN)
    assert {threads[path]["thread_id"] for path in CHILDREN.values()} == set(CHILDREN)


def test_child_private_content_never_leaves_its_own_conversation(
    codex_run: dict[str, Any],
) -> None:
    threads = _threads(codex_run)
    for path in CHILDREN.values():
        leaf = path.rsplit("/", 1)[-1]
        private = f"{leaf} PRIVATE REASONING"
        assert private in _texts(threads[path])
        assert private not in _texts(threads["/root"]), "root absorbed child private content"
        for other in EXPECTED_PATHS - {path}:
            assert private not in _texts(threads[other]), f"{private} leaked into {other}"


def test_inherited_parent_history_is_not_child_owned_conversation(
    codex_run: dict[str, Any],
) -> None:
    """fork_turns=all replays the parent's turns into the child rollout as context."""
    threads = _threads(codex_run)
    inherited = "USER TASK: run five agents"
    assert inherited in _texts(threads["/root"])
    for path in CHILDREN.values():
        assert inherited not in _texts(threads[path])


def test_root_keeps_routing_evidence_without_absorbing_child_conversations(
    codex_run: dict[str, Any],
) -> None:
    threads = _threads(codex_run)
    root = threads["/root"]

    delegated = {
        message["recipient"]
        for message in root["messages"]
        if message.get("kind") == "task" and message.get("sender") == "/root"
    }
    assert delegated == set(CHILDREN.values())

    returned = {
        message["sender"]
        for message in root["messages"]
        if message.get("kind") == "final_answer" and message.get("recipient") == "/root"
    }
    assert returned == set(CHILDREN.values())

    own = [m for m in root["messages"] if m.get("sender") in {"/root", "user"}]
    assert any(m.get("kind") == "user_message" for m in own)
    assert any(m.get("kind") == "assistant_message" for m in own)

    for path in CHILDREN.values():
        child = threads[path]
        assert any(
            message.get("kind") == "task" and message.get("recipient") == path
            for message in child["messages"]
        ), f"{path} never records the task it received"
        assert any(
            message.get("sender") == path and message.get("phase") == "final_answer"
            for message in child["messages"]
        ), f"{path} never records its own final response"
        # Root may keep the return routing record, but not the child's whole thread.
        assert len(child["messages"]) > len(
            [m for m in root["messages"] if m.get("sender") == path]
        )


def test_main_rollout_alone_still_materializes_every_delegated_agent() -> None:
    """The shipped artifact archived only the main rollout, yet named five agents.

    Even with no child rollout available, the parent transcript carries explicit
    delegation and final-return routing records naming each child. Those records are
    the child's own conversational evidence and must not be published as root's.
    """
    from execweave.codex_conversation import codex_rollout_previews

    previews = codex_rollout_previews(FIXTURES / "rollout-main.jsonl")
    by_path = {preview["agent_path"]: preview for preview in previews}
    assert set(by_path) == EXPECTED_PATHS

    for agent_id, path in CHILDREN.items():
        child = by_path[path]
        assert child["thread_id"] == agent_id, "child thread identity must match the graph"
        assert child["parent_thread_id"] == SESSION_ID
        assert child["evidence_scope"] == EVIDENCE_CROSS_AGENT_ROUTING
        senders = {message["sender"] for message in child["messages"]}
        assert senders <= {"/root", path}, f"{path} carries a foreign agent's messages"

    for path in CHILDREN.values():
        other_leaves = {p.rsplit("/", 1)[-1] for p in CHILDREN.values() if p != path}
        text = _texts(by_path[path])
        for leaf in other_leaves:
            assert leaf not in text, f"{leaf} content leaked into {path}"


def test_merged_child_thread_reads_in_observation_order(codex_run: dict[str, Any]) -> None:
    """A child thread assembled from its own rollout plus the parent's routing records.

    Ordinals index one transcript, so they cannot order a thread whose evidence spans
    two. The merged thread must still read chronologically.
    """
    threads = _threads(codex_run)
    for path in CHILDREN.values():
        messages = threads[path]["messages"]
        assert len(messages) > 3, "child thread did not merge both evidence sources"
        stamps = [str(message.get("timestamp") or "") for message in messages]
        assert stamps == sorted(stamps), f"{path} is out of observation order"


def test_no_subagent_topology_is_invented_without_delegation_evidence(
    tmp_path: Path,
) -> None:
    """Naming another agent is not evidence of having spawned it.

    A rollout that merely receives a peer message observes the sender's name, not the
    sender's execution context. Deriving a thread from that would invent topology the
    provider never exposed, so only a delegation this rollout actually issued counts.
    """
    from execweave.codex_conversation import codex_rollout_previews

    rollout = tmp_path / "rollout-solo.jsonl"
    records = [
        {
            "timestamp": "2026-08-29T09:00:00Z",
            "ordinal": 0,
            "type": "session_meta",
            "payload": {"id": "solo-thread", "session_id": "solo-thread"},
        },
        {
            "timestamp": "2026-08-29T09:00:01Z",
            "ordinal": 1,
            "type": "response_item",
            "payload": {
                "type": "agent_message",
                "author": "/root/peer",
                "recipient": "/root",
                "content": [
                    {
                        "type": "input_text",
                        "text": "Message Type: MESSAGE\nTask name: /root\nSender: /root/peer\nPayload:\npeer note",
                    }
                ],
            },
        },
    ]
    rollout.write_text(
        "".join(json.dumps(record) + "\n" for record in records), encoding="utf-8"
    )

    previews = codex_rollout_previews(rollout)
    assert [preview["agent_path"] for preview in previews] == ["/root"]
    assert any(
        message["sender"] == "/root/peer" for message in previews[0]["messages"]
    ), "inbound peer routing must still be observable on the receiving thread"


def test_non_codex_providers_never_gain_derived_threads(tmp_path: Path) -> None:
    """The agent-local fan-out is Codex rollout evidence only; other providers are untouched."""
    from execweave.conversation_preview import conversation_preview

    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        json.dumps(
            {
                "type": "assistant",
                "message": {"content": [{"type": "text", "text": "hello from /root/other"}]},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    for content_kind, provider in (
        ("claude.conversation_transcript.main", "claude"),
        ("antigravity.conversation_transcript", "antigravity"),
        ("cursor.assistant_final_response", "cursor"),
        ("opencode.assistant_response", "opencode"),
        ("inference_gateway.openrouter.response", "openrouter"),
        ("openai_compatible.assistant_response", "openai-compatible"),
    ):
        preview = conversation_preview(
            transcript,
            content_kind=content_kind,
            provider=provider,
            source={"id": f"agent:{provider}", "type": "agent", "attributes": {}},
            timestamp="2026-08-29T09:00:00Z",
            ordinal=0,
        )
        if preview is None:
            continue
        assert "derived_agent_previews" not in preview, content_kind


def test_routing_only_child_is_not_labelled_a_full_transcript() -> None:
    """The shipped run archived no child rollout, only the parent's routing records.

    A thread carrying a delegation and a final answer looks like a complete short
    conversation. Saying so would overclaim: the child's own work was never captured.
    """
    from execweave.codex_conversation import codex_rollout_previews

    previews = codex_rollout_previews(FIXTURES / "rollout-main.jsonl")
    by_path = {preview["agent_path"]: preview for preview in previews}
    for path in CHILDREN.values():
        assert by_path[path]["evidence_scope"] == EVIDENCE_CROSS_AGENT_ROUTING


def test_routing_only_and_transcript_backed_threads_are_distinguishable(
    codex_run: dict[str, Any],
) -> None:
    """When the child rollout IS archived, the merged thread earns the stronger label."""
    from execweave.agent_topology import COMPLETENESS_PROVIDER_TRANSCRIPT

    threads = _threads(codex_run)
    assert threads["/root"]["conversation_completeness"] == COMPLETENESS_PROVIDER_TRANSCRIPT
    for path in CHILDREN.values():
        assert (
            threads[path]["conversation_completeness"] == COMPLETENESS_PROVIDER_TRANSCRIPT
        ), f"{path} archived its own rollout and should not read as routing-only"
