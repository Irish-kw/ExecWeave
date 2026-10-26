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
        ["execweave-cursor-hook"],
        input=json.dumps(payload),
        text=True,
        check=True,
        capture_output=True,
    )


def main() -> int:
    if not os.environ.get("EXECWEAVE_SEMANTIC_SIDECAR"):
        raise SystemExit("run-bound semantic sidecar environment was not inherited")

    cwd = str(Path.cwd())
    base = {
        "conversation_id": "ci-cursor-conversation",
        "generation_id": "ci-cursor-generation",
        "session_id": "ci-cursor-session",
        "cursor_version": "ci",
        "cwd": cwd,
        "workspace_roots": [cwd],
        "model": "ci-model",
        "model_id": "ci-model-id",
    }
    _send({**base, "hook_event_name": "sessionStart"})
    # Conversation evidence, so CI can assert the materialized conversations.json.
    _send({**base, "hook_event_name": "beforeSubmitPrompt", "prompt": "CI CURSOR PROMPT"})

    child_argv, declared_command = _child_command()
    tool = {
        **base,
        "hook_event_name": "preToolUse",
        "tool_name": "Shell",
        "tool_use_id": "ci-cursor-tool-use",
        "tool_input": {"command": declared_command, "working_directory": cwd},
    }
    _send(tool)

    child = subprocess.Popen(child_argv)
    time.sleep(0.5)
    code = int(child.wait())

    _send({**tool, "hook_event_name": "postToolUse", "tool_output": "not persisted"})
    _send({**base, "hook_event_name": "afterAgentResponse", "text": "CI CURSOR FINAL ANSWER"})
    return code


if __name__ == "__main__":
    raise SystemExit(main())
