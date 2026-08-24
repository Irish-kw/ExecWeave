import json
import sys
from pathlib import Path

from execweave.collector import RuntimeCollector, infer_agent_name
from execweave.sink import JsonlSink


def _read_events(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_infer_agent_name() -> None:
    assert infer_agent_name(["claude"]) == "Claude Code"
    assert infer_agent_name(["codex"]) == "OpenAI Codex"
    assert infer_agent_name(["gemini"]) == "Gemini CLI"
    assert infer_agent_name(["custom-agent"]) == "custom-agent"


def test_runtime_collector_records_session_and_root_process(tmp_path: Path) -> None:
    output = tmp_path / "events.jsonl"
    collector = RuntimeCollector(
        session_id="test-session",
        sink=JsonlSink(output),
        watch_root=tmp_path,
        poll_interval=0.05,
        collect_filesystem=False,
        collect_network=False,
    )

    rc = collector.run([sys.executable, "-c", "import time; time.sleep(0.15)"])

    assert rc == 0
    events = _read_events(output)
    event_types = [event["event_type"] for event in events]

    assert "session.started" in event_types
    assert "process.started" in event_types
    assert "session.finished" in event_types

    root_events = [event for event in events if event["event_type"] == "process.started"]
    assert any(event["relation"] == "LAUNCHED" for event in root_events)
