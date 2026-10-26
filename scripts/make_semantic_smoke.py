from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a small semantic sidecar from a CI runtime stream")
    parser.add_argument("runtime", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    events = [
        json.loads(line)
        for line in args.runtime.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    started = next(event for event in events if event.get("event_type") == "session.started")
    process_event = next(event for event in events if event.get("event_type") == "process.started")
    agent = started.get("source")
    process = process_event.get("target")
    if not isinstance(agent, dict) or not isinstance(process, dict):
        raise RuntimeError("runtime smoke stream does not contain agent/process entities")
    process_attributes = process.get("attributes") or {}
    pid = process_attributes.get("pid") if isinstance(process_attributes, dict) else None
    if not isinstance(pid, int):
        raise RuntimeError("runtime smoke process entity does not contain a PID")
    timestamp = process_event.get("timestamp")
    if not isinstance(timestamp, str):
        raise RuntimeError("runtime smoke process event does not contain a timestamp")

    tool = {
        "type": "tool",
        "id": "tool:ci:Shell",
        "name": "Shell",
        "attributes": {"provider": "ci-smoke"},
    }
    records = [
        {
            "timestamp": timestamp,
            "event_type": "semantic.tool.called",
            "relation": "CALLED_TOOL",
            "source": agent,
            "target": tool,
            "attributes": {"causal": True, "attribution": "ci_semantic_hook"},
        },
        {
            "timestamp": timestamp,
            "event_type": "semantic.tool.process",
            "relation": "SPAWNED_PROCESS",
            "source": tool,
            "target": {
                "type": "process_reference",
                "id": f"process-pid:{pid}",
                "name": str(pid),
                "attributes": {"pid": pid},
            },
            "attributes": {"causal": True, "attribution": "ci_semantic_hook"},
        },
        {
            "timestamp": timestamp,
            "event_type": "semantic.mcp.called",
            "relation": "CALLED_MCP",
            "source": agent,
            "target": {
                "type": "mcp_server",
                "id": "mcp:ci:example",
                "name": "Example MCP",
                "attributes": {},
            },
            "attributes": {"causal": True, "attribution": "ci_semantic_hook"},
        },
    ]
    args.output.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
