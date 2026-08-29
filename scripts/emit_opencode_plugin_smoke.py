from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path


def _child_command() -> tuple[list[str], str]:
    if os.name == "nt":
        argv = ["ping", "-n", "4", "127.0.0.1"]
        return argv, "ping -n 4 127.0.0.1"
    argv = ["sleep", "3"]
    return argv, "sleep 3"


def _send(payload: dict) -> None:
    subprocess.run(
        ["execweave-opencode-hook"],
        input=json.dumps(payload),
        text=True,
        check=True,
        capture_output=True,
    )


def main() -> int:
    if not os.environ.get("EXECWEAVE_SEMANTIC_SIDECAR"):
        raise SystemExit("run-bound semantic sidecar environment was not inherited")
    cwd = str(Path.cwd())
    session_id = "ci-opencode-session"
    _send(
        {
            "hook_event_name": "chat.message",
            "sessionID": session_id,
            "messageID": "message-1",
            "agent": "build",
            "model": {"providerID": "openrouter", "modelID": "openai/gpt-5.6-sol"},
            "cwd": cwd,
        }
    )
    child_argv, command = _child_command()
    before = {
        "hook_event_name": "tool.execute.before",
        "sessionID": session_id,
        "callID": "call-1",
        "tool": "bash",
        "args": {"command": command},
        "cwd": cwd,
    }
    _send(before)
    child = subprocess.Popen(child_argv)
    time.sleep(0.5)
    code = int(child.wait())
    _send({**before, "hook_event_name": "tool.execute.after", "output": "PRIVATE_OUTPUT"})
    # Conversation evidence, so CI can assert the materialized conversations.json.
    _send(
        {
            "hook_event_name": "experimental.text.complete",
            "sessionID": session_id,
            "text": "CI OPENCODE FINAL ANSWER",
            "cwd": cwd,
        }
    )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
