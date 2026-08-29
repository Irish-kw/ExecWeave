from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def emit(payload: dict) -> None:
    result = subprocess.run(
        ["execweave-gemini-hook"],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=True,
    )
    if json.loads(result.stdout or "{}") != {}:
        raise RuntimeError("Gemini hook must return an empty JSON object")


def main() -> int:
    cwd = Path.cwd()
    base = {
        "cwd": str(cwd),
        "session_id": "gemini-ci-session",
        "transcript_path": str(cwd / "not-read-by-execweave.json"),
    }
    emit({**base, "hook_event_name": "SessionStart", "timestamp": now(), "source": "startup"})
    if os.name == "nt":
        command = "ping -n 3 127.0.0.1"
    else:
        command = "sleep 1.2"
    tool_input = {"command": command}
    emit({**base, "hook_event_name": "BeforeTool", "timestamp": now(), "tool_name": "run_shell_command", "tool_input": tool_input})
    subprocess.run(command, shell=True, check=True)
    emit({**base, "hook_event_name": "AfterTool", "timestamp": now(), "tool_name": "run_shell_command", "tool_input": tool_input, "tool_response": {"returnDisplay": "redacted by test", "error": None}})
    # Conversation evidence, so CI can assert the materialized conversations.json.
    emit({**base, "hook_event_name": "AfterAgent", "timestamp": now(), "prompt": "CI GEMINI PROMPT", "prompt_response": "CI GEMINI FINAL ANSWER"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
