from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def main() -> int:
    output = Path("claude-hook-smoke.jsonl").resolve()
    if output.exists():
        output.unlink()

    secret = "THIS-CONTENT-MUST-NOT-BE-STORED"
    payload = {
        "session_id": "ci-claude-session",
        "prompt_id": "ci-prompt",
        "cwd": str(Path.cwd()),
        "permission_mode": "default",
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "tool_use_id": "ci-tool-use",
        "tool_input": {
            "file_path": str(Path.cwd() / "ci-hook-output.txt"),
            "content": secret,
        },
    }
    completed = subprocess.run(
        ["execweave-claude-hook", "--sidecar", str(output)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        print(completed.stderr, file=sys.stderr)
        raise SystemExit("execweave-claude-hook returned non-zero")
    if completed.stdout:
        raise SystemExit("execweave-claude-hook emitted stdout during hook handling")
    if not output.exists():
        raise SystemExit("Claude hook did not create the semantic sidecar")

    records = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    relations = [record.get("relation") for record in records]
    if relations != ["REQUESTED_TOOL_CALL", "USES_TOOL", "DECLARED_TARGET"]:
        raise SystemExit(f"unexpected Claude hook relations: {relations}")
    if secret in output.read_text(encoding="utf-8"):
        raise SystemExit("Claude Write content leaked into semantic sidecar")

    config = subprocess.run(
        ["execweave-claude-hook", "--print-config"],
        text=True,
        capture_output=True,
        check=True,
    )
    parsed = json.loads(config.stdout)
    required = {
        "SessionStart",
        "PreToolUse",
        "PostToolUse",
        "PostToolUseFailure",
        "SubagentStart",
        "SubagentStop",
    }
    if set(parsed.get("hooks", {})) != required:
        raise SystemExit("generated Claude hook config is incomplete")

    print("Claude hook command smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
