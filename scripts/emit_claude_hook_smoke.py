from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path


def _child_command() -> tuple[list[str], str]:
    if os.name == "nt":
        # Keep a non-Python process alive long enough for the portable sampler.
        argv = ["ping", "-n", "3", "127.0.0.1"]
        return argv, "ping -n 3 127.0.0.1"
    argv = ["sleep", "1.2"]
    return argv, "sleep 1.2"


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
    subprocess.run(
        ["execweave-claude-hook"],
        input=json.dumps(payload),
        text=True,
        check=True,
    )
    child = subprocess.Popen(child_argv)
    # Give the parent ExecWeave sampler several observation opportunities before wait().
    time.sleep(0.3)
    return int(child.wait())


if __name__ == "__main__":
    raise SystemExit(main())
