import json
import sys
import threading
import time
from pathlib import Path
from urllib.request import urlopen

from execweave.cli import build_parser
from execweave.live import run_live
from execweave.validate import validate_event_stream


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
