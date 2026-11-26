#!/usr/bin/env python3
"""Live check of the lane backend on a real host (manual; not part of the pytest suite).

The lane backend needs Linux, root, bpftrace and an unprivileged agent account; hosted CI runners provide none of these as
the test process, so this check runs only when a person runs it.  It starts a real lane session in which a small agent
routes three shell calls through the launch client, then checks that the ledger verifies and that the attribution names
exactly those three calls.

    sudo python3 scripts/lane_live_check.py --agent-user USER

Exit status 0 when every check passes, 1 when one fails, 2 when the host cannot run the lane backend.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

from execweave.lane import runner as lane_runner


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--agent-user", required=True, help="unprivileged account that runs the agent")
    a = ap.parse_args()
    try:
        lane_runner.check_available()
    except lane_runner.LaneUnavailable as exc:
        print(f"lane backend unavailable on this host: {exc}", file=sys.stderr)
        return 2
    tmp_path = Path(tempfile.mkdtemp(prefix="execweave-lane-live-"))
    os.chmod(tmp_path, 0o755)
    shutil.chown(tmp_path, user=a.agent_user)
    agent = tmp_path / "agent.py"
    agent.write_text(
        "import os, subprocess, sys\n"
        "for i in range(3):\n"
        "    subprocess.run([sys.executable, os.environ['EW_LANE_EXEC'], '--sock', os.environ['EW_LANE_SOCK'],\n"
        "                    '--call-id', f'call-{i}', '--', '/bin/sh', '-c', 'true'], check=True)\n",
        encoding="utf-8",
    )
    os.chmod(agent, 0o644)
    result = lane_runner.run_session([sys.executable, str(agent)], agent_user=a.agent_user, watch_root=tmp_path,
                                     output_root=tmp_path / "runs")
    attribution = json.loads(result.attribution.read_text(encoding="utf-8"))
    checks = {
        "agent exited 0": result.return_code == 0,
        "ledger valid": attribution["ledger"]["valid"] is True,
        "exactly the three routed calls": sorted(attribution["tool_calls"]) == ["call-0", "call-1", "call-2"],
    }
    for name, ok in checks.items():
        print(("PASS " if ok else "FAIL ") + name)
    print(f"outputs: {tmp_path}")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
