import json
import sys
from pathlib import Path

from execweave.collector import RuntimeCollector, infer_agent_name
from execweave.sink import JsonlSink


def _read_events(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


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
        poll_interval=0.02,
        collect_filesystem=False,
        collect_network=False,
    )

    rc = collector.run([sys.executable, "-c", "import time; time.sleep(0.08)"])

    assert rc == 0
    events = _read_events(output)
    assert any(event["relation"] == "LAUNCHED" for event in events)
    assert events[0]["sequence"] == 1
    assert all(
        events[index]["sequence"] < events[index + 1]["sequence"]
        for index in range(len(events) - 1)
    )
