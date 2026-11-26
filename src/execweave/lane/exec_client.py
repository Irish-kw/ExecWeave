#!/usr/bin/env python3
"""Run a command through the lane launcher with the caller's stdio, and exit with its status.

    lane_exec.py --sock PATH --call-id ID [--declared TEXT] -- ARGV...

Used by the PreToolUse hook of the real-agent experiment: the hook rewrites an agent's Bash command into a
lane_exec invocation, so the command runs in its own call lane while its output still reaches the agent.
Requester identity is not sent: the launcher takes it from SO_PEERCRED and the caller's cgroup.
"""
import argparse
import json
import os
import socket
import sys


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sock", required=True)
    ap.add_argument("--call-id", required=True)
    ap.add_argument("--declared", default=None)
    ap.add_argument("argv", nargs=argparse.REMAINDER)
    a = ap.parse_args()
    argv = a.argv[1:] if a.argv and a.argv[0] == "--" else a.argv
    # harness-native per-call context (Claude Code TRACEPARENT/TRACESTATE, Codex CODEX_TOOL_CALL_ID) is passed through unchanged, so
    # the native-tag baseline sees inside a lane the same variables it would see without the launcher
    env = {k: v for k, v in os.environ.items() if k in ("PATH", "LANG", "LC_ALL", "TMPDIR", "HOME", "TRACEPARENT", "TRACESTATE", "CODEX_TOOL_CALL_ID")
           or k.startswith(("EW_", "EXECWEAVE_"))}
    req = {"op": "launch", "call_id": a.call_id, "argv": argv, "declared": a.declared, "cwd": os.getcwd(), "env": env}
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect(a.sock)
    socket.send_fds(s, [(json.dumps(req) + "\n").encode()], [0, 1, 2])
    buf = b""
    while not buf.endswith(b"\n"):
        c = s.recv(65536)
        if not c:
            break
        buf += c
    r = json.loads(buf)
    if not r.get("ok"):
        print(f"lane_exec: launch refused: {r.get('error')}", file=sys.stderr)
        return 126
    s2 = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s2.connect(a.sock)
    s2.sendall((json.dumps({"op": "wait", "pid": r["pid"]}) + "\n").encode())
    buf = b""
    while not buf.endswith(b"\n"):
        c = s2.recv(65536)
        if not c:
            break
        buf += c
    w = json.loads(buf)
    return int(w.get("returncode", 1)) if w.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
