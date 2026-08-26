from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import execweave.cli as cli_module
import execweave.top_cli as top_cli_module
import execweave.view_cli as view_cli_module
from execweave.entry import main as entry_main
from execweave.scalability_benchmark import run_scalability_benchmark
from execweave.theme import inject_viewer_theme
from execweave.top import TerminalState, format_dashboard


class _LiveResult:
    return_code = 0

    def to_dict(self) -> dict[str, object]:
        return {"return_code": 0, "session_id": "test"}


def test_generic_live_routes_cursor_command(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_run_live(command, **kwargs):
        captured["command"] = list(command)
        captured.update(kwargs)
        return _LiveResult()

    monkeypatch.setattr(cli_module, "run_live", fake_run_live)
    result = entry_main(
        [
            "live",
            "--watch-root",
            str(tmp_path),
            "--no-files",
            "--no-network",
            "--",
            "cursor",
        ]
    )
    assert result == 0
    assert captured["command"] == ["cursor"]
    assert captured["collect_filesystem"] is False
    assert captured["collect_network"] is False


def test_top_cli_routes_one_shared_live_session(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_run_top(command, **kwargs):
        captured["command"] = list(command)
        captured.update(kwargs)
        return SimpleNamespace(return_code=7)

    monkeypatch.setattr(top_cli_module, "run_top", fake_run_top)
    result = entry_main(
        [
            "top",
            "--watch-root",
            str(tmp_path),
            "--open",
            "--no-files",
            "--",
            "codex",
        ]
    )
    assert result == 7
    assert captured["command"] == ["codex"]
    assert captured["open_browser"] is True
    assert captured["collect_filesystem"] is False


def test_terminal_dashboard_does_not_invent_missing_model_evidence() -> None:
    state = TerminalState()
    state.apply_snapshot(
        {
            "event_count": 3,
            "node_count": 2,
            "edge_count": 1,
            "nodes": [
                {"id": "agent:OpenAI Codex", "type": "agent", "name": "OpenAI Codex"},
                {"id": "session:s1", "type": "session", "name": "s1"},
            ],
            "edges": [],
        },
        0,
    )
    dashboard = format_dashboard(state, command=["codex"], width=140)
    assert "OpenAI Codex" in dashboard
    assert "runtime+semantic" in dashboard
    assert "gpt-" not in dashboard.lower()


def test_shared_theme_injection_is_idempotent() -> None:
    html = "<!doctype html><html><head><style>:root{--bg:#000}</style></head><body>x</body></html>"
    first = inject_viewer_theme(html)
    second = inject_viewer_theme(first)
    assert first == second
    assert 'id="execweave-theme-toggle"' in first
    assert "execweave-theme" in first
    assert 'data-theme="light"' in first


def test_view_cli_writes_a_theme_aware_standalone_viewer(monkeypatch, tmp_path: Path) -> None:
    graph = tmp_path / "graph.json"
    graph.write_text("{}", encoding="utf-8")
    output = tmp_path / "viewer.html"

    def fake_build(graph_path, output_path, *, open_browser=False):
        assert open_browser is False
        Path(output_path).write_text(
            "<!doctype html><html><head><style>:root{--bg:#000}</style></head><body>x</body></html>",
            encoding="utf-8",
        )
        return Path(output_path).resolve()

    monkeypatch.setattr(view_cli_module, "build_viewer_from_graph", fake_build)
    assert view_cli_module.main([str(graph), "--output", str(output)]) == 0
    rendered = output.read_text(encoding="utf-8")
    assert 'id="execweave-theme-toggle"' in rendered
    assert "execweave-theme" in rendered


def test_scalability_benchmark_keeps_event_ids_out_of_graph_state() -> None:
    result = run_scalability_benchmark(sizes=(10, 100), resource_count=5)
    points = result["points"]
    assert [point["event_count"] for point in points] == [10, 100]
    assert all(point["retained_event_ids"] == 0 for point in points)
    assert all(point["node_count"] == 6 for point in points)
    assert all(point["edge_count"] == 5 for point in points)
    assert all(point["events_per_second"] > 0 for point in points)
