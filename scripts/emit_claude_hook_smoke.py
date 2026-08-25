from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    child_code = "import time; time.sleep(0.4); print('execweave-correlation-smoke')"
    executable = str(Path(sys.executable).resolve())
    payload = {
        "session_id": "ci-claude-record-session",
        "prompt_id": "ci-prompt",
        "cwd": str(Path.cwd()),
        "permission_mode": "default",
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_use_id": "ci-record-tool-use",
        "tool_input": {"command": f'"{executable}" -c "{child_code}"'},
    }
    if not os.environ.get("EXECWEAVE_SEMANTIC_SIDECAR"):
        raise SystemExit("run-bound semantic sidecar environment was not inherited")
    subprocess.run(
        ["execweave-claude-hook"],
        input=json.dumps(payload),
        text=True,
        check=True,
    )
    subprocess.run([sys.executable, "-c", child_code], check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
