from __future__ import annotations

import json
from pathlib import Path

from execweave.cli import build_parser
from execweave.live import _LiveState
from execweave.live_core import _live_page
from execweave.viewer import render_graph_html
from execweave.viewer_limits import resolve_viewer_limits
from execweave.viewer_projection import render_graph_html as render_dashboard_html


def _small_graph() -> dict[str, object]:
    return {
        "graph_schema_version": "0.2",
        "session_id": "viewer-limits",
        "event_count": 1,
        "node_count": 2,
        "edge_count": 1,
        "nodes": [
            {"id": "process:1", "type": "process", "name": "agent"},
            {"id": "file:1", "type": "file", "name": "notes.md"},
        ],
        "edges": [
            {
                "id": "edge:1",
                "source": "process:1",
                "target": "file:1",
                "relation": "CREATED",
            }
        ],
    }


def test_dashboard_limit_arguments_are_available_on_rendering_commands() -> None:
    parser = build_parser()
    for command in ("view", "record", "live"):
        args = parser.parse_args(
            [
                command,
                "--viewer-max-nodes",
                "9000",
                "--viewer-max-edges",
                "12000",
                "--viewer-max-dom-elements",
                "40000",
                *( ["graph.json"] if command == "view" else ["--", "agent"] ),
            ]
        )
        assert args.viewer_max_nodes == 9000
        assert args.viewer_max_edges == 12000
        assert args.viewer_max_dom_elements == 40000


def test_standalone_viewer_limit_override_disables_protective_mode(monkeypatch) -> None:
    monkeypatch.setenv("EXECWEAVE_VIEWER_MAX_NODES", "2")
    monkeypatch.setenv("EXECWEAVE_VIEWER_MAX_EDGES", "1")
    monkeypatch.setenv("EXECWEAVE_VIEWER_MAX_DOM_ELEMENTS", "10")

    html = render_graph_html(_small_graph())

    assert "LARGE GRAPH PROTECTIVE MODE" in html
    assert "Hard safety limits: <strong>2</strong> possible nodes" in html

    monkeypatch.setenv("EXECWEAVE_VIEWER_MAX_DOM_ELEMENTS", "14")
    html = render_graph_html(_small_graph())
    assert "LARGE GRAPH PROTECTIVE MODE" not in html


def test_dashboard_and_live_page_receive_the_same_limit_bootstrap(monkeypatch) -> None:
    monkeypatch.setenv("EXECWEAVE_VIEWER_MAX_NODES", "9000")
    monkeypatch.setenv("EXECWEAVE_VIEWER_MAX_EDGES", "12000")
    monkeypatch.setenv("EXECWEAVE_VIEWER_MAX_DOM_ELEMENTS", "40000")

    html = render_dashboard_html(_small_graph())
    live_html = _live_page("<html><script>dashboard</script></html>", 12)

    bootstrap = (
        "window.__execweaveViewerLimits={max_nodes:9000,max_edges:12000,"
        "max_dom_elements:40000};"
    )
    assert bootstrap in html
    assert bootstrap in live_html


def test_live_payload_budget_uses_startup_override(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("EXECWEAVE_VIEWER_MAX_NODES", "3")
    monkeypatch.setenv("EXECWEAVE_VIEWER_MAX_EDGES", "2")
    monkeypatch.setenv("EXECWEAVE_VIEWER_MAX_DOM_ELEMENTS", "18")
    event_path = tmp_path / "events.jsonl"
    event_path.write_text(
        json.dumps(
            {
                "schema_version": "0.2",
                "event_id": "event-1",
                "session_id": "s1",
                "timestamp": "2026-09-03T00:00:00Z",
                "sequence": 1,
                "event_type": "process.started",
                "relation": "LAUNCHED",
                "source": {"id": "session:s1", "type": "session", "name": "s1"},
                "target": {"id": "process:s1:1", "type": "process", "name": "agent"},
                "attributes": {"backend": "portable"},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    payload = _LiveState("s1", event_path).snapshot()

    assert payload["node_count"] == 2
    assert payload["nodes"]
    assert resolve_viewer_limits() == (3, 2, 18)
