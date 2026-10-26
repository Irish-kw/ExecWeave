from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from execweave.claude_hook_contract import PASSIVE_CLAUDE_HOOK_EVENTS


def main() -> int:
    output = Path("claude-hook-smoke.jsonl").resolve()
    if output.exists():
        output.unlink()
    content_root = output.parent / "content" / "sha256"

    secret = "THIS-CONTENT-MUST-BE-STORED-FULL-FIDELITY"
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
    expected = [
        "REQUESTED_TOOL_CALL",
        "USES_TOOL",
        "DECLARED_TARGET",
        "OBSERVED_PROVIDER_METADATA",
        "HAS_TOOL_INPUT",
    ]
    if relations != expected:
        raise SystemExit(f"unexpected Claude hook relations: {relations}")
    if secret in output.read_text(encoding="utf-8"):
        raise SystemExit("Claude Write content was inlined into semantic sidecar")
    if not content_root.exists():
        raise SystemExit("Claude full-fidelity content store was not created")
    if not any(secret.encode("utf-8") in path.read_bytes() for path in content_root.iterdir()):
        raise SystemExit("Claude Write content was not preserved in full-fidelity content store")

    config = subprocess.run(
        ["execweave-claude-hook", "--print-config"],
        text=True,
        capture_output=True,
        check=True,
    )
    parsed = json.loads(config.stdout)
    configured_events = set(parsed.get("hooks", {}))
    if configured_events != set(PASSIVE_CLAUDE_HOOK_EVENTS):
        missing = sorted(set(PASSIVE_CLAUDE_HOOK_EVENTS) - configured_events)
        unexpected = sorted(configured_events - set(PASSIVE_CLAUDE_HOOK_EVENTS))
        raise SystemExit(
            "generated Claude hook config drifted from passive official contract: "
            f"missing={missing}, unexpected={unexpected}"
        )

    print("Claude hook command smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
