import json
import sys
import threading
import time
from pathlib import Path
from urllib.request import urlopen

import execweave.live as live_module
from execweave.cli import build_parser
from execweave.live import _LIVE_HTML, _LiveState, run_live
from execweave.validate import validate_event_stream


def _live_event(*, event_id: str = "event-1") -> dict[str, object]:
    return {
        "schema_version": "0.2",
        "event_id": event_id,
        "session_id": "s1",
        "timestamp": "2026-08-26T00:00:00Z",
        "sequence": 1,
        "event_type": "process.started",
        "relation": "LAUNCHED",
        "source": {"id": "session:s1", "type": "session", "name": "s1"},
        "target": {"id": "process:s1:1", "type": "process", "name": "python"},
        "attributes": {"backend": "portable", "causal": True},
    }


def test_live_cli_arguments() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "live",
            "--port",
            "8765",
            "--linger",
            "0",
            "--open",
            "--no-files",
            "--",
            "python",
            "agent.py",
        ]
    )
    assert args.subcommand == "live"
    assert args.port == 8765
    assert args.linger == 0
    assert args.open_browser is True
    assert args.no_files is True
    assert args.command == ["--", "python", "agent.py"]


def test_live_viewer_has_large_graph_and_array_safety_guards() -> None:
    assert "LARGE GRAPH PROTECTIVE MODE" in _LIVE_HTML
    assert "withinRenderBudget" in _LIVE_HTML
    assert "MAX_DOM_ELEMENTS=5000" in _LIVE_HTML
    assert "No evidence is deleted or reclassified" in _LIVE_HTML
    assert "Math.max(0,...depth.values())" not in _LIVE_HTML
    assert "Math.min(...xs)" not in _LIVE_HTML
    assert "const signature=`${data.node_count||0}:${data.edge_count||0}`" in _LIVE_HTML
    assert "${data.edge_count||0}:${data.event_count||0}" not in _LIVE_HTML
    assert "refreshEdgeLabels" in _LIVE_HTML


def test_live_state_tails_only_complete_new_jsonl_lines(tmp_path: Path) -> None:
    event_path = tmp_path / "events.jsonl"
    encoded = json.dumps(_live_event(), ensure_ascii=False).encode("utf-8")
    split = len(encoded) // 2
    event_path.write_bytes(encoded[:split])
    state = _LiveState("s1", event_path)

    before = state.snapshot()
    assert before["event_count"] == 0
    assert before["node_count"] == 0
    assert before["edge_count"] == 0

    with event_path.open("ab") as handle:
        handle.write(encoded[split:] + b"\n")

    after = state.snapshot()
    assert after["event_count"] == 1
    assert after["node_count"] == 2
    assert after["edge_count"] == 1
    assert after["edges"][0]["event_ids"] == []

    repeated = state.snapshot()
    assert repeated["event_count"] == 1
    assert repeated["node_count"] == 2
    assert repeated["edge_count"] == 1
    assert repeated["edges"][0]["count"] == 1


def test_live_state_compacts_payload_after_browser_budget(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(live_module, "VIEWER_MAX_NODES", 1)
    monkeypatch.setattr(live_module, "VIEWER_MAX_EDGES", 100)
    monkeypatch.setattr(live_module, "VIEWER_MAX_DOM_ELEMENTS", 1000)
    event_path = tmp_path / "events.jsonl"
    event_path.write_text(json.dumps(_live_event()) + "\n", encoding="utf-8")
    state = _LiveState("s1", event_path)

    payload = state.snapshot()
    assert payload["event_count"] == 1
    assert payload["node_count"] == 2
    assert payload["edge_count"] == 1
    assert payload["live_payload_compact"] is True
    assert payload["nodes"] == []
    assert payload["edges"] == []


def test_live_state_does_not_send_full_large_graph_when_finished(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(live_module, "VIEWER_MAX_NODES", 1)
    monkeypatch.setattr(live_module, "VIEWER_MAX_EDGES", 100)
    monkeypatch.setattr(live_module, "VIEWER_MAX_DOM_ELEMENTS", 1000)
    state = _LiveState("s1", tmp_path / "events.jsonl")
    graph = {
        "graph_schema_version": "0.1",
        "session_id": "s1",
        "event_count": 1,
        "node_count": 2,
        "edge_count": 1,
        "nodes": [
            {"id": "session:s1", "type": "session"},
            {"id": "process:s1:1", "type": "process"},
        ],
        "edges": [
            {
                "id": "e1",
                "source": "session:s1",
                "target": "process:s1:1",
                "relation": "LAUNCHED",
            }
        ],
    }

    state.finish(graph)
    payload = state.snapshot()
    assert payload["live_finished"] is True
    assert payload["live_payload_compact"] is True
    assert payload["node_count"] == 2
    assert payload["edge_count"] == 1
    assert payload["nodes"] == []
    assert payload["edges"] == []
    assert "LARGE GRAPH PROTECTIVE MODE" in (state.final_html() or "")


def test_live_graph_serves_snapshot_and_writes_final_artifacts(tmp_path: Path) -> None:
    announced = threading.Event()
    state: dict[str, object] = {}

    def announce(url: str) -> None:
        state["url"] = url
        announced.set()

    def worker() -> None:
        try:
            state["result"] = run_live(
                [sys.executable, "-c", "import time; time.sleep(0.45)"],
                watch_root=tmp_path,
                output_dir=tmp_path / "live-run",
                poll_interval=0.05,
                collect_filesystem=False,
                collect_network=False,
                port=0,
                open_browser=False,
                linger_seconds=0.1,
                announce=announce,
            )
        except BaseException as exc:  # surfaced in the main test thread below
            state["error"] = exc
            announced.set()

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    assert announced.wait(timeout=5), "live server did not announce its URL"
    if "error" in state:
        raise state["error"]  # type: ignore[misc]

    url = str(state["url"])
    payload: dict[str, object] | None = None
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        try:
            with urlopen(url + "graph.json", timeout=1) as response:
                payload = json.loads(response.read().decode("utf-8"))
            break
        except OSError:
            time.sleep(0.05)

    assert payload is not None
    assert payload["live_finished"] is False
    assert payload["session_id"]
    assert isinstance(payload["nodes"], list)
    assert isinstance(payload["edges"], list)

    thread.join(timeout=8)
    assert not thread.is_alive(), "live workflow did not terminate"
    if "error" in state:
        raise state["error"]  # type: ignore[misc]

    result = state["result"]
    assert result.return_code == 0  # type: ignore[union-attr]
    assert result.event_stream.exists()  # type: ignore[union-attr]
    assert result.graph.exists()  # type: ignore[union-attr]
    assert result.viewer.exists()  # type: ignore[union-attr]
    assert validate_event_stream(result.event_stream).valid is True  # type: ignore[union-attr]
