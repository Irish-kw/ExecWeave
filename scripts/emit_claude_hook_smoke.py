from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path


def _child_command() -> tuple[list[str], str]:
    if os.name == "nt":
        # Keep a non-Python process alive long enough for the portable sampler.
        argv = ["ping", "-n", "4", "127.0.0.1"]
        return argv, "ping -n 4 127.0.0.1"
    argv = ["sleep", "3"]
    return argv, "sleep 3"


def main() -> int:
    child_argv, declared_command = _child_command()
    payload = {
        "session_id": "ci-claude-record-session",
        "prompt_id": "ci-prompt",
        "cwd": str(Path.cwd()),
        "permission_mode": "default",
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_use_id": "ci-record-tool-use",
        "tool_input": {"command": declared_command},
    }
    if not os.environ.get("EXECWEAVE_SEMANTIC_SIDECAR"):
        raise SystemExit("run-bound semantic sidecar environment was not inherited")

    def send(body: dict) -> None:
        subprocess.run(
            ["execweave-claude-hook"], input=json.dumps(body), text=True, check=True
        )

    base = {key: payload[key] for key in ("session_id", "cwd", "permission_mode")}
    # Conversation evidence, so the run materializes a conversations.json CI can check.
    send({**base, "hook_event_name": "UserPromptSubmit", "prompt": "CI CLAUDE PROMPT"})
    send(payload)
    send({
        **base,
        "hook_event_name": "Stop",
        "stop_hook_active": False,
        "last_assistant_message": "CI CLAUDE FINAL ANSWER",
    })
    child = subprocess.Popen(child_argv)
    # Keep the emitter alive while the child is running so the portable sampler
    # gets many observation opportunities on slower hosted runners.
    time.sleep(0.5)
    return int(child.wait())


if __name__ == "__main__":
    raise SystemExit(main())
