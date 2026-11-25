#!/usr/bin/env python3
"""PreToolUse hook for the Antigravity CLI (agy): route every run_command tool call through the lane launcher.

Registered in <workspace>/.agents/hooks.json:
    {"ew-lane": {"PreToolUse": [{"matcher": "run_command", "hooks": [{"type": "command", "command": "python3 .../lane_agy_hook.py"}]}]}}
agy feeds the hook JSON on stdin ({"toolCall": {"name": "run_command", "args": {"CommandLine": ...}}, "stepIdx": N, "conversationId": ..., ...}; the keys are
camelCase, see cli_facts/agy.md) and reads one JSON object from stdout.  This hook answers
    {"decision": "allow", "overwrite": {"CommandLine": "python3 lane_agy_hook.py --launch -- --sock $EW_LANE_SOCK --call-id <conversationId>:<stepIdx> --declared agy:<conv> -- bash -c '<export EW_TOOL_CALL_ID=..; original>'"},
     "permissionOverrides": ["command(<wrapped>)", "command(<original>)"]}
`overwrite` is merged shallowly into the tool arguments (documented); the call id is (conversation, step index) because the hook input holds no tool-call id.
`--launch` mode (matrix v2) writes one measurement record and then replaces itself (os.execv) by `python3 lane_exec.py <the same arguments>`; the session
setting `permissions.allow = ["command(/usr/bin/python3 <this file>)"]` (set by run_real_lane_agy.py) is what lets the wrapped form run in headless mode.
The hook runs under `sh -c` as a child of agy with agy's environment (so EW_LANE_SOCK reaches it).  Other tools are not touched (empty object).
If anything fails the call is left unwrapped (stderr note, `{}`): the experiment counts that as launcher bypass.

Measurement records (native-tag baseline), written only when MX_HOOK_LOG names a file (the variable does not start with EW_, so lane_exec does not forward it):
  kind "hook"    one per PreToolUse invocation: the ids in the hook input (conversationId, stepIdx, tool name) and the names of ANTIGRAVITY_* variables in the hook's environment
  kind "launch"  one per wrapped command, taken in the process agy's `bash -c` starts for the command (the environment the unwrapped command would have had): the
                 per-call identifier parsed from ANTIGRAVITY_SOURCE_METADATA (toolCall.id = agy's native `call_N`, stepIndex, conversationId), all variable names, and the
                 names lane_exec.py + the launcher whitelist would forward into the call lane (same rules, read from the code, not observed inside the lane)
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
CLIENT_PASS = {"PATH", "LANG", "LC_ALL", "TMPDIR", "HOME", "TRACEPARENT", "TRACESTATE", "CODEX_TOOL_CALL_ID"}
SERVICE_PASS = {"PATH", "HOME", "LANG", "LC_ALL", "PYTHONDONTWRITEBYTECODE", "TMPDIR", "TRACEPARENT", "TRACESTATE", "CODEX_TOOL_CALL_ID"}
PREFIX = ("EW_", "EXECWEAVE_")
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
    return sorted(n for n in names if (n in CLIENT_PASS and n in SERVICE_PASS) or n.startswith(PREFIX))


def native_view() -> dict:
    """Per-call identifier agy puts into the environment of the command it starts (ANTIGRAVITY_SOURCE_METADATA, JSON)."""
    raw = os.environ.get("ANTIGRAVITY_SOURCE_METADATA")
    out: dict = {"metadata_present": raw is not None}
    if raw:
        out["metadata_len"] = len(raw)
        try:
            t = json.loads(raw)["tool"]
            out.update({"conversationId": t.get("conversationId"), "stepIndex": t.get("stepIndex"), "native_call_id": (t.get("toolCall") or {}).get("id"),
                        "native_tool_name": (t.get("toolCall") or {}).get("name")})
        except (ValueError, KeyError, TypeError) as exc:
            out["parse_error"] = type(exc).__name__
    return out


def env_view() -> dict:
    env = os.environ
    vals = {k: ("<redacted>" if SECRETISH.search(k) else v[:200]) for k, v in env.items()
            if k.startswith(("ANTIGRAVITY_", "TRACEPARENT", "TRACESTATE", "CODEX_", "OTEL_")) and k != "ANTIGRAVITY_SOURCE_METADATA"}
    return {"env_names": sorted(env), "env_values_selected": vals, "forwarded_names": forwarded(env), "native": native_view()}


def wrap(data: dict, sock: str) -> dict:
    args = (data.get("toolCall") or {}).get("args") or {}
    orig = args["CommandLine"]
    cid = f"{data['conversationId']}:{data['stepIdx']}"
    inner = f"export EW_TOOL_CALL_ID={cid}; {orig}"
    wrapped = (f"/usr/bin/python3 {shlex.quote(os.path.join(HERE, 'antigravity.py'))} --launch -- --sock {shlex.quote(sock)} --call-id {shlex.quote(cid)} "
               f"--declared {shlex.quote('agy:' + str(data['conversationId']))} -- bash -c {shlex.quote(inner)}")
    return {"decision": "allow", "reason": "ew-lane: command routed through the lane launcher", "overwrite": {"CommandLine": wrapped},
            "permissionOverrides": [f"command({wrapped})", f"command({orig})"]}


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
        tc = data.get("toolCall") or {}
        log({"kind": "hook", "tool_name": tc.get("name"), "conversationId": data.get("conversationId"), "stepIdx": data.get("stepIdx"), "input_keys": sorted(data),
             "toolcall_keys": sorted(tc), "antigravity_env_names": sorted(k for k in os.environ if k.startswith("ANTIGRAVITY_")),
             "command": str((tc.get("args") or {}).get("CommandLine") or "")[:2000]})
        if tc.get("name") != "run_command":
            print("{}")
            return 0
        print(json.dumps(wrap(data, os.environ["EW_LANE_SOCK"])))
    except Exception as exc:  # noqa: BLE001
        print(f"lane_agy_hook: not wrapping: {type(exc).__name__}: {exc}", file=sys.stderr)
        print("{}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
