from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


def main() -> int:
    payload = {
        "session_id": "ci-claude-record-session",
        "prompt_id": "ci-prompt",
        "cwd": str(Path.cwd()),
        "permission_mode": "default",
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_use_id": "ci-record-tool-use",
        "tool_input": {"command": "echo execweave-claude-record-smoke"},
    }
    if not os.environ.get("EXECWEAVE_SEMANTIC_SIDECAR"):
        raise SystemExit("run-bound semantic sidecar environment was not inherited")
    subprocess.run(
        ["execweave-claude-hook"],
        input=json.dumps(payload),
        text=True,
        check=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
