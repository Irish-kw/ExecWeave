#!/usr/bin/env python3
"""PreToolUse hook for Claude Code: route every Bash tool call through the lane launcher.

Reads the hook JSON on stdin; for tool_name == "Bash" prints an `allow` decision whose `updatedInput.command` is
    python3 lane_exec.py --sock $EW_LANE_SOCK --call-id <tool_use_id> -- bash -c '<original command>'
so the command runs in its own call lane (the launcher takes the requester's identity from the kernel).
Other tools are left untouched (they run inside the agent process).  If anything fails the call is left
unwrapped, which the experiment counts as launcher bypass.
"""
import json
import os
import shlex
import sys

LANE_EXEC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "exec_client.py")


def main() -> int:
    try:
        data = json.load(sys.stdin)
        if data.get("tool_name") != "Bash":
            return 0
        sock = os.environ["EW_LANE_SOCK"]
        ti = dict(data.get("tool_input") or {})
        orig = ti["command"]
        ti["command"] = (f"/usr/bin/python3 {shlex.quote(os.path.normpath(LANE_EXEC))} --sock {shlex.quote(sock)} "
                         f"--call-id {shlex.quote(data['tool_use_id'])} -- bash -c {shlex.quote(orig)}")
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow", "updatedInput": ti}}))
    except Exception as exc:  # noqa: BLE001
        print(f"lane_hook: not wrapping: {type(exc).__name__}: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
