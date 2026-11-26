#!/usr/bin/env python3
"""preToolUse hook for the Cursor CLI (cursor-agent): route every Shell tool call through the lane launcher.

Registered in <workspace>/.cursor/hooks.json as a `preToolUse` hook with matcher `Shell` (the tool name Cursor reports for terminal commands).
Cursor feeds the hook JSON on stdin: {"tool_name": "Shell", "tool_input": {"command", "cwd", "timeout"}, "tool_use_id", "conversation_id",
"generation_id", ...}.  The hook answers {"permission": "allow", "updated_input": {...tool_input with the command replaced...}}, where the new
command is
    python3 lane_cursor_hook.py --launch -- --sock $EW_LANE_SOCK --call-id <tool_use_id> --declared cursor:<conversation_id> -- bash -c '<export EW_TOOL_CALL_ID=...; original>'
`--launch` mode (matrix v2) first writes one measurement record (see below) and then replaces itself (os.execv) by `python3 lane_exec.py <the same arguments>`, so the
command runs in its own call lane exactly as before (the launcher takes the requester's identity from the kernel).  Other tools are left untouched.
If anything fails the call is left unwrapped, which the experiment counts as launcher bypass (stderr note only; exit code 0 = fail-open, as
the Claude hook).  `tool_use_id` is Cursor's hook-side id; it differs from the `call_id` of the stream-json tool_call events (see cli_facts/cursor.md).

Measurement records (native-tag baseline), written only when MX_HOOK_LOG names a file (the driver sets it; the variable does not start with EW_, so
lane_exec does not forward it into the lanes):
  kind "hook"    one per preToolUse invocation: ids in the hook input, names of the CURSOR_* variables in the hook's environment
  kind "launch"  one per wrapped command, taken in the process Cursor starts for the command (the environment the unwrapped command would have had):
                 values of the per-call-looking variables (CURSOR_*, TRACEPARENT, ...), all variable names, and the names that lane_exec.py + the launcher's
                 whitelist would forward into the call lane (computed with the same rules; read from lane_exec.py / lane_service.py, not observed inside the lane)
"""
import json
import os
import re
import shlex
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
LANE_EXEC = os.environ.get("EW_LANE_EXEC") or os.path.normpath(os.path.join(HERE, "..", "exec_client.py"))
LOG = os.environ.get("MX_HOOK_LOG")
# lane_exec.py forwards: PATH LANG LC_ALL TMPDIR HOME TRACEPARENT TRACESTATE CODEX_TOOL_CALL_ID and EW_*/EXECWEAVE_*; lane_service._sanitize_env keeps
# ENV_WHITELIST = {PATH HOME LANG LC_ALL PYTHONDONTWRITEBYTECODE TMPDIR TRACEPARENT TRACESTATE CODEX_TOOL_CALL_ID} and the prefixes EW_/EXECWEAVE_
CLIENT_PASS = {"PATH", "LANG", "LC_ALL", "TMPDIR", "HOME", "TRACEPARENT", "TRACESTATE", "CODEX_TOOL_CALL_ID"}
SERVICE_PASS = {"PATH", "HOME", "LANG", "LC_ALL", "PYTHONDONTWRITEBYTECODE", "TMPDIR", "TRACEPARENT", "TRACESTATE", "CODEX_TOOL_CALL_ID"}
PREFIX = ("EW_", "EXECWEAVE_")
INTEREST = re.compile(r"^(CURSOR_|TRACEPARENT$|TRACESTATE$|CODEX_|OTEL_|CLAUDE|ANTIGRAVITY_(AGENT|CONVERSATION_ID|TRAJECTORY_ID)$|__CURSOR)")
SECRETISH = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD|AUTH|COOKIE|CSRF)", re.I)


def log(rec: dict) -> None:
    if not LOG:
        return
    try:
        with open(LOG, "a") as fh:
            fh.write(json.dumps({"t_ns": time.time_ns(), "pid": os.getpid(), "ppid": os.getppid(), **rec}, sort_keys=True) + "\n")
    except OSError:
        pass


def forwarded(names) -> list[str]:
    return sorted(n for n in names if n in CLIENT_PASS and n in SERVICE_PASS or (n.startswith(PREFIX)))


def env_view() -> dict:
    env = os.environ
    vals = {k: ("<redacted>" if SECRETISH.search(k) else v[:200]) for k, v in env.items() if INTEREST.match(k)}
    return {"env_names": sorted(env), "env_values_selected": vals, "forwarded_names": forwarded(env)}


def lane_id(raw) -> str:
    """Lane call id for a hook `tool_use_id`.  Fix of 2026-10-29 (first live run, task_free3): for background shell calls Cursor's hook id has the form of the stream id
    (`call-<uuid>-<n>` NEWLINE `fc_<uuid>_0`), which the launcher rejects (call ids are [A-Za-z0-9_.:-]{1,200}), so the wrapped command never ran.  Characters outside the
    allowed set become `_`; ordinary ids (uuid) are unchanged."""
    return re.sub(r"[^A-Za-z0-9_.:-]", "_", str(raw))[:200]


def wrap(data: dict, sock: str) -> dict:
    ti = dict(data.get("tool_input") or {})
    orig = ti["command"]
    cid = lane_id(data["tool_use_id"])
    conv = str(data.get("conversation_id") or "")
    inner = f"export EW_TOOL_CALL_ID={cid}; {orig}"
    ti["command"] = (f"/usr/bin/python3 {shlex.quote(os.path.join(HERE, 'cursor.py'))} --launch -- --sock {shlex.quote(sock)} --call-id {shlex.quote(cid)} "
                     f"--declared {shlex.quote('cursor:' + conv)} -- bash -c {shlex.quote(inner)}")
    return {"permission": "allow", "updated_input": ti}


def launch(rest: list[str]) -> int:
    cid = rest[rest.index("--call-id") + 1] if "--call-id" in rest else None
    log({"kind": "launch", "call_id": cid, **env_view()})
    os.execv("/usr/bin/python3", ["/usr/bin/python3", LANE_EXEC, *rest])
    return 127


def main() -> int:
    if len(sys.argv) > 2 and sys.argv[1] == "--launch" and sys.argv[2] == "--":
        return launch(sys.argv[3:])
    try:
        data = json.load(sys.stdin)
        log({"kind": "hook", "tool_name": data.get("tool_name"), "tool_use_id": data.get("tool_use_id"), "lane_id": lane_id(data.get("tool_use_id") or ""), "conversation_id": data.get("conversation_id"),
             "generation_id": data.get("generation_id"), "input_keys": sorted(data), "cursor_env_names": sorted(k for k in os.environ if k.startswith("CURSOR_")),
             "command": ((data.get("tool_input") or {}).get("command") or "")[:2000]})
        if data.get("tool_name") != "Shell":
            print("{}")
            return 0
        print(json.dumps(wrap(data, os.environ["EW_LANE_SOCK"])))
    except Exception as exc:  # noqa: BLE001
        print(f"lane_cursor_hook: not wrapping: {type(exc).__name__}: {exc}", file=sys.stderr)
        print("{}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
