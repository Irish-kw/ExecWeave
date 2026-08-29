from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def main() -> int:
    output = Path("codex-hook-smoke.jsonl").resolve()
    if output.exists():
        output.unlink()
    content_root = output.parent / "content" / "sha256"

    secret = "CODEX-FULL-FIDELITY-CONTENT"
    payload = {
        "session_id": "ci-codex-session",
        "turn_id": "ci-turn",
        "transcript_path": None,
        "cwd": str(Path.cwd()),
        "hook_event_name": "PreToolUse",
        "model": "gpt-5.3-codex",
        "permission_mode": "default",
        "tool_name": "Bash",
        "tool_use_id": "ci-tool-use",
        "tool_input": {"command": "echo execweave-codex-smoke", "opaque": secret},
    }
    completed = subprocess.run(
        ["execweave-codex-hook", "--sidecar", str(output)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        print(completed.stderr, file=sys.stderr)
        raise SystemExit("execweave-codex-hook returned non-zero")
    if completed.stdout:
        raise SystemExit("execweave-codex-hook emitted stdout during hook handling")
    if not output.exists():
        raise SystemExit("Codex hook did not create the semantic sidecar")

    records = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    relations = [record.get("relation") for record in records]
    expected = [
        "REQUESTED_TOOL_CALL",
        "USES_TOOL",
        "DECLARED_COMMAND",
        "OBSERVED_PROVIDER_METADATA",
        "HAS_TOOL_INPUT",
    ]
    if relations != expected:
        raise SystemExit(f"unexpected Codex hook relations: {relations}")
    if secret in output.read_text(encoding="utf-8"):
        raise SystemExit("Codex tool input was inlined into semantic sidecar")
    if not content_root.exists():
        raise SystemExit("Codex full-fidelity content store was not created")
    if not any(secret.encode("utf-8") in path.read_bytes() for path in content_root.iterdir()):
        raise SystemExit("Codex tool input was not preserved in full-fidelity content store")

    config = subprocess.run(
        ["execweave-codex-hook", "--print-config"],
        text=True,
        capture_output=True,
        check=True,
    )
    parsed = json.loads(config.stdout)
    # Bound to the shipped event set rather than a second hardcoded copy, which had
    # drifted to expect an "Interrupt" hook ExecWeave does not register.
    from execweave.codex_hook_lifecycle import OFFICIAL_CODEX_HOOK_EVENTS

    required = set(OFFICIAL_CODEX_HOOK_EVENTS)
    if set(parsed.get("hooks", {})) != required:
        raise SystemExit(
            "generated Codex hook config does not match the official event set: "
            f"{sorted(set(parsed.get('hooks', {})) ^ required)}"
        )
    for event_name in {"PreToolUse", "PermissionRequest", "PostToolUse"}:
        if parsed["hooks"][event_name][0].get("matcher") != "*":
            raise SystemExit(f"Codex {event_name} hook is not configured for all tools")

    print("Codex hook command smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
