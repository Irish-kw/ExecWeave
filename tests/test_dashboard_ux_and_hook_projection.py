from __future__ import annotations

import json
from pathlib import Path

from execweave.live import _LIVE_HTML as LIVE_HTML, _LiveState, _inject_final_theme
from execweave.viewer_projection import (
    is_internal_hook_runtime_event,
    project_viewer_graph,
    strip_internal_hook_execution_graph,
)


def _hook_process(process_id: str, name: str, *cmdline: str) -> dict[str, object]:
    return {
        "id": process_id,
        "type": "process",
        "name": name,
        "attributes": {"cmdline": list(cmdline)},
    }


def test_dashboard_controls_are_pinned_and_logs_can_jump_to_graph_nodes() -> None:
    assert "#theme-toggle{position:fixed;top:15px;right:16px" in LIVE_HTML
    assert "#camera-hint{display:none}" in LIVE_HTML
    assert "Double-click to jump to the corresponding graph node" in LIVE_HTML
    assert "row.ondblclick=()=>" in LIVE_HTML
    assert "focusNode(item.nodeId)" in LIVE_HTML
    assert "function focusNode(id)" in LIVE_HTML
    assert "focusRawLogEvent(JSON.parse(raw))" in LIVE_HTML


def test_final_theme_toggle_is_pinned_to_the_top_right() -> None:
    themed = _inject_final_theme("<html><head><style></style></head><body></body></html>")
    assert "#execweave-theme-toggle{position:fixed;right:14px;top:14px;" in themed
    assert "right:14px;bottom:14px;" not in themed


def test_internal_hook_processes_are_hidden_but_provider_tools_remain() -> None:
    codex = {
        "id": "process:codex",
        "type": "process",
        "name": "codex.exe",
        "attributes": {"cmdline": ["codex"]},
    }
    hook_shell = _hook_process(
        "process:hook-shell",
        "powershell.exe",
        "powershell.exe",
        "-Command",
        "execweave-codex-hook --auto",
    )
    hook_exe = _hook_process(
        "process:hook-exe",
        "execweave-codex-hook.exe",
        "execweave-codex-hook.exe",
        "--auto",
    )
    hook_python = _hook_process(
        "process:hook-python",
        "python.exe",
        "python.exe",
        "execweave-codex-hook.exe",
        "--auto",
    )
    tool = {"id": "tool:codex:Bash", "type": "tool", "name": "Bash"}
    graph = {
        "graph_schema_version": "0.2",
        "session_id": "hook-filter",
        "event_count": 4,
        "node_count": 5,
        "edge_count": 4,
        "nodes": [codex, hook_shell, hook_exe, hook_python, tool],
        "edges": [
            {
                "id": "codex-hook",
                "source": "process:codex",
                "target": "process:hook-shell",
                "relation": "SPAWNED",
            },
            {
                "id": "hook-exe",
                "source": "process:hook-shell",
                "target": "process:hook-exe",
                "relation": "SPAWNED",
            },
            {
                "id": "hook-python",
                "source": "process:hook-exe",
                "target": "process:hook-python",
                "relation": "SPAWNED",
            },
            {
                "id": "provider-tool",
                "source": "process:codex",
                "target": "tool:codex:Bash",
                "relation": "USES_TOOL",
            },
        ],
    }

    projected = project_viewer_graph(graph)

    assert {node["id"] for node in projected["nodes"]} == {
        "process:codex",
        "tool:codex:Bash",
    }
    assert [edge["id"] for edge in projected["edges"]] == ["provider-tool"]
    projection = projected["viewer_projection"]
    assert projection["kind"] == "internal_hook_processes"
    assert projection["internal_hook_node_count"] == 3
    assert projection["internal_hook_edge_count"] == 3


def test_materialized_execution_graph_filter_keeps_real_agent_nodes() -> None:
    class Item:
        def __init__(self, item_id: str) -> None:
            self.id = item_id

    class FakeGraph:
        def __init__(self) -> None:
            self.nodes = [Item("process:codex"), Item("process:hook"), Item("tool:codex:Bash")]
            self.edges = [Item("codex-hook"), Item("provider-tool")]

        def to_dict(self) -> dict[str, object]:
            return {
                "nodes": [
                    {"id": "process:codex", "type": "process", "name": "codex.exe"},
                    _hook_process(
                        "process:hook",
                        "execweave-codex-hook.exe",
                        "execweave-codex-hook.exe",
                        "--auto",
                    ),
                    {"id": "tool:codex:Bash", "type": "tool", "name": "Bash"},
                ],
                "edges": [
                    {
                        "id": "codex-hook",
                        "source": "process:codex",
                        "target": "process:hook",
                        "relation": "SPAWNED",
                    },
                    {
                        "id": "provider-tool",
                        "source": "process:codex",
                        "target": "tool:codex:Bash",
                        "relation": "USES_TOOL",
                    },
                ],
            }

    graph = strip_internal_hook_execution_graph(FakeGraph())

    assert [node.id for node in graph.nodes] == ["process:codex", "tool:codex:Bash"]
    assert [edge.id for edge in graph.edges] == ["provider-tool"]


def test_internal_hook_runtime_detector_does_not_hide_provider_tool_events() -> None:
    hook_event = {
        "source": {"id": "process:codex", "type": "process", "name": "codex.exe"},
        "target": _hook_process(
            "process:hook",
            "powershell.exe",
            "powershell.exe",
            "-Command",
            "execweave-codex-hook --auto",
        ),
        "relation": "SPAWNED",
    }
    tool_event = {
        "source": {"id": "agent:codex", "type": "agent", "name": "OpenAI Codex"},
        "target": {"id": "tool:codex:webrun", "type": "tool", "name": "webrun"},
        "relation": "USES_TOOL",
    }

    assert is_internal_hook_runtime_event(hook_event) is True
    assert is_internal_hook_runtime_event(tool_event) is False




def test_process_that_only_mentions_hook_name_is_not_hidden() -> None:
    event = {
        "source": {"id": "session:s1", "type": "session", "name": "s1"},
        "target": _hook_process(
            "process:grep",
            "grep",
            "grep",
            "execweave-codex-hook",
            "README.md",
        ),
        "relation": "LAUNCHED",
    }

    assert is_internal_hook_runtime_event(event) is False


def test_live_raw_log_history_excludes_hook_process_noise(tmp_path: Path) -> None:
    event_path = tmp_path / "events.jsonl"
    hook_event = {
        "schema_version": "0.2",
        "event_id": "hook-1",
        "session_id": "s1",
        "timestamp": "2026-08-27T00:00:01Z",
        "sequence": 1,
        "event_type": "process.started",
        "relation": "SPAWNED",
        "source": {
            "id": "process:codex",
            "type": "process",
            "name": "codex.exe",
            "attributes": {"cmdline": ["codex"]},
        },
        "target": _hook_process(
            "process:hook",
            "powershell.exe",
            "powershell.exe",
            "-Command",
            "execweave-codex-hook --auto",
        ),
        "attributes": {"backend": "portable", "attribution": "polling", "causal": False},
    }
    network_event = {
        "schema_version": "0.2",
        "event_id": "network-2",
        "session_id": "s1",
        "timestamp": "2026-08-27T00:00:02Z",
        "sequence": 2,
        "event_type": "network.connection",
        "relation": "CONNECTED_TO",
        "source": {
            "id": "process:codex",
            "type": "process",
            "name": "codex.exe",
            "attributes": {"cmdline": ["codex"]},
        },
        "target": {
            "id": "endpoint:20.27.177.116:443",
            "type": "network_endpoint",
            "name": "20.27.177.116:443",
        },
        "attributes": {
            "backend": "portable",
            "attribution": "process_polling",
            "causal": True,
        },
    }
    event_path.write_text(
        json.dumps(hook_event) + "\n" + json.dumps(network_event) + "\n",
        encoding="utf-8",
    )

    state = _LiveState("s1", event_path)
    payload = state.live_update(-1)

    assert [entry["event"]["event_id"] for entry in payload["raw_events"]] == ["network-2"]
    node_ids = {node["id"] for node in payload["graph"]["nodes"]}
    assert "process:hook" not in node_ids
    assert "endpoint:20.27.177.116:443" in node_ids



def test_live_raw_log_history_excludes_unlabeled_hook_descendants(tmp_path: Path) -> None:
    event_path = tmp_path / "events.jsonl"
    events = [
        {
            "schema_version": "0.2",
            "event_id": "hook-1",
            "session_id": "s1",
            "timestamp": "2026-08-27T00:00:01Z",
            "sequence": 1,
            "event_type": "process.started",
            "relation": "SPAWNED",
            "source": {"id": "process:codex", "type": "process", "name": "codex.exe"},
            "target": _hook_process(
                "process:hook",
                "execweave-codex-hook.exe",
                "execweave-codex-hook.exe",
                "--auto",
            ),
            "attributes": {"backend": "portable", "attribution": "polling"},
        },
        {
            "schema_version": "0.2",
            "event_id": "child-2",
            "session_id": "s1",
            "timestamp": "2026-08-27T00:00:02Z",
            "sequence": 2,
            "event_type": "process.started",
            "relation": "SPAWNED",
            "source": {"id": "process:hook", "type": "process", "name": "hook"},
            "target": {
                "id": "process:python",
                "type": "process",
                "name": "python.exe",
                "attributes": {"cmdline": ["python.exe", "helper.py"]},
            },
            "attributes": {"backend": "portable", "attribution": "polling"},
        },
        {
            "schema_version": "0.2",
            "event_id": "child-network-3",
            "session_id": "s1",
            "timestamp": "2026-08-27T00:00:03Z",
            "sequence": 3,
            "event_type": "network.connection",
            "relation": "CONNECTED_TO",
            "source": {"id": "process:python", "type": "process", "name": "python.exe"},
            "target": {
                "id": "endpoint:127.0.0.1:50000",
                "type": "network_endpoint",
                "name": "127.0.0.1:50000",
            },
            "attributes": {"backend": "portable", "attribution": "process_polling"},
        },
        {
            "schema_version": "0.2",
            "event_id": "real-4",
            "session_id": "s1",
            "timestamp": "2026-08-27T00:00:04Z",
            "sequence": 4,
            "event_type": "network.connection",
            "relation": "CONNECTED_TO",
            "source": {"id": "process:codex", "type": "process", "name": "codex.exe"},
            "target": {
                "id": "endpoint:20.27.177.116:443",
                "type": "network_endpoint",
                "name": "20.27.177.116:443",
            },
            "attributes": {"backend": "portable", "attribution": "process_polling"},
        },
    ]
    event_path.write_text(
        "".join(json.dumps(event) + "\n" for event in events),
        encoding="utf-8",
    )

    state = _LiveState("s1", event_path)
    payload = state.live_update(-1)

    assert [entry["event"]["event_id"] for entry in payload["raw_events"]] == ["real-4"]


def test_antigravity_hook_helper_is_hidden_from_viewer_projection() -> None:
    graph = {
        "graph_schema_version": "0.2",
        "session_id": "antigravity-hook-filter",
        "event_count": 1,
        "node_count": 2,
        "edge_count": 1,
        "nodes": [
            {
                "id": "process:agy",
                "type": "process",
                "name": "agy",
                "attributes": {"cmdline": ["agy"]},
            },
            _hook_process(
                "process:antigravity-hook",
                "execweave-antigravity-hook",
                "execweave-antigravity-hook",
                "--auto",
                "--event",
                "PostToolUse",
            ),
        ],
        "edges": [
            {
                "id": "agy-hook",
                "source": "process:agy",
                "target": "process:antigravity-hook",
                "relation": "SPAWNED",
            }
        ],
    }

    projected = project_viewer_graph(graph)

    assert [node["id"] for node in projected["nodes"]] == ["process:agy"]
    assert projected["edges"] == []
