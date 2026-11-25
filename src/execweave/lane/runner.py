"""Record one session under per-call lanes (Linux, root).

Steps: mount cgroup v2 and tracefs if needed, start the eBPF sensor with a per-run record nonce,
check that it observes every CPU, start the launcher, run the command in the agent lane as the
agent user, check the sensor again, stop everything, and build the event stream and the lane
attribution from the sensor log and the signed ledger.

The defaults are the evaluated configuration: the launcher requires sender pidfds and runs each
call in its own Landlock domain with signal scoping.
"""
from __future__ import annotations

import json
import os
import pwd
import signal
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import backend as lane_backend
from . import sensor_guard
from . import sensor_nonce
from . import service as lane_service

PACKAGE_DIR = Path(__file__).resolve().parent
SENSOR_SCRIPT = PACKAGE_DIR / "lane_sensor_native_v2.bt"
EXEC_CLIENT = PACKAGE_DIR / "exec_client.py"
CG_MOUNT = Path("/run/cg2")
TRACEFS = Path("/sys/kernel/tracing")
SOCK_DIR = Path("/run/execweave-lanes")


class LaneUnavailable(RuntimeError):
    """The host cannot run the lane backend."""


@dataclass
class LaneRunResult:
    session_id: str
    run_dir: Path
    return_code: int
    events: Path
    attribution: Path
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"session_id": self.session_id, "run_dir": str(self.run_dir), "return_code": self.return_code,
                "events": str(self.events), "attribution": str(self.attribution), "meta": self.meta}


def _mounted(path: Path, fstype: str) -> bool:
    try:
        with open("/proc/self/mounts", encoding="utf-8") as fh:
            for line in fh:
                parts = line.split()
                if len(parts) > 2 and parts[1] == str(path) and parts[2] == fstype:
                    return True
    except OSError:
        pass
    return False


def ensure_mounts(cg_mount: Path = CG_MOUNT) -> None:
    """Mount cgroup v2 at ``cg_mount`` and tracefs if they are not mounted (root)."""
    if not _mounted(cg_mount, "cgroup2"):
        cg_mount.mkdir(parents=True, exist_ok=True)
        r = subprocess.run(["mount", "-t", "cgroup2", "none", str(cg_mount)], capture_output=True, text=True)
        if r.returncode != 0:
            raise LaneUnavailable(f"cannot mount cgroup v2 at {cg_mount}: {r.stderr.strip()}")
    if not (TRACEFS / "events").exists():
        TRACEFS.mkdir(parents=True, exist_ok=True)
        r = subprocess.run(["mount", "-t", "tracefs", "nodev", str(TRACEFS)], capture_output=True, text=True)
        if r.returncode != 0:
            raise LaneUnavailable(f"cannot mount tracefs at {TRACEFS}: {r.stderr.strip()}")


def diagnostics() -> dict[str, Any]:
    from shutil import which
    return {
        "platform": sys.platform,
        "root": os.geteuid() == 0 if hasattr(os, "geteuid") else False,
        "bpftrace": which("bpftrace") is not None,
        "landlock_abi": lane_service.landlock_abi() if sys.platform.startswith("linux") else 0,
        "kernel": os.uname().release if hasattr(os, "uname") else None,
    }


def check_available() -> None:
    d = diagnostics()
    if not d["platform"].startswith("linux"):
        raise LaneUnavailable("the lane backend runs only on Linux")
    if not d["root"]:
        raise LaneUnavailable("the lane backend must run as root (sensor and launcher)")
    if not d["bpftrace"]:
        raise LaneUnavailable("the lane backend needs bpftrace")


def start_sensor(sensor_log: Path, sensor_err: Path) -> subprocess.Popen:
    script = sensor_nonce.script_with_nonce(str(SENSOR_SCRIPT), sensor_log)
    proc = subprocess.Popen(["bpftrace", "-B", "none", script], stdout=open(sensor_log, "ab"), stderr=open(sensor_err, "wb"),
                            env={**os.environ, "BPFTRACE_MAX_STRLEN": "200"})
    return proc


def run_session(command: list[str], *, agent_user: str, watch_root: Path, output_root: Path | None = None,
                call_isolation: str = "landlock", require_pidfd: bool = True, extra_env: dict[str, str] | None = None,
                settle_s: float = 0.5, session_id: str | None = None) -> LaneRunResult:
    """Run ``command`` as ``agent_user`` in the agent lane and record it."""
    check_available()
    ensure_mounts()
    lane_service.REQUIRE_PIDFD = bool(require_pidfd)
    pw = pwd.getpwnam(agent_user)
    uid, gid = pw.pw_uid, pw.pw_gid
    session_id = session_id or uuid.uuid4().hex
    watch_root = watch_root.expanduser().resolve()
    run_dir = (output_root or (watch_root / ".execweave" / "runs")) / session_id
    lane_dir = run_dir / "lane"
    lane_dir.mkdir(parents=True)
    for p in (run_dir.parent, run_dir, lane_dir):
        os.chmod(p, 0o755)
    SOCK_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(SOCK_DIR, 0o755)
    run_id = f"ew-{session_id[:12]}-{os.getpid()}"
    sock = SOCK_DIR / f"{run_id}.sock"

    sensor_log, sensor_err = lane_dir / "sensor.log", lane_dir / "sensor.stderr"
    sensor = start_sensor(sensor_log, sensor_err)
    guard = sensor_guard.SensorGuard(sensor_log, sensor)
    try:
        guard.start_check()
    except sensor_guard.SensorGuardError:
        sensor_guard.stop_sensor(sensor)
        raise

    svc = lane_service.LaneService(run_id=run_id, lane_dir=lane_dir, sock_path=sock, agent_uid=uid, agent_gid=gid,
                                   cg_mount=CG_MOUNT, call_isolation=call_isolation)
    svc.start()
    guard.record_start(svc)
    env = {"EW_LANE_SOCK": str(sock), "EW_LANE_EXEC": str(EXEC_CLIENT), "EXECWEAVE_SESSION_ID": session_id, **(extra_env or {})}
    mono_offset_ns = time.time_ns() - time.clock_gettime_ns(time.CLOCK_MONOTONIC)
    started_ns = time.time_ns()
    rc = -1
    try:
        root = svc.launch_root(list(command), cwd=str(watch_root), env=env)
        rc = root["proc"].wait()
        time.sleep(settle_s)          # detached children and late sensor records
        try:
            guard.finish_check(svc)
        except sensor_guard.SensorGuardError:
            pass                      # recorded in the guard verdict and, when partial, in the ledger
    finally:
        finished_ns = time.time_ns()
        svc.stop()
        sensor.send_signal(signal.SIGINT)
        try:
            sensor.wait(timeout=15)
        except subprocess.TimeoutExpired:
            sensor.kill()

    events, attribution = run_dir / "events.jsonl", run_dir / "lane_attribution.json"
    built = lane_backend.build(sensor_path=sensor_log, ledger_path=lane_dir / "ledger.jsonl", pubkey_path=lane_dir / "ledger_pub.pem",
                               session_id=session_id, mono_offset_ns=mono_offset_ns, started_ns_wall=started_ns, finished_ns_wall=finished_ns,
                               agent_name=Path(command[0]).name, command=list(command), out_events=events, out_attr=attribution)
    svc.cleanup_lanes()
    meta = {"backend": "lane", "session_id": session_id, "return_code": rc, "agent_user": agent_user, "call_isolation": call_isolation,
            "require_pidfd": bool(require_pidfd), "sensor_guard": guard.meta(), "events": built.get("events"),
            "sensor_records": built.get("sensor_records"), "lanes": built.get("lanes"), "ledger": built.get("ledger"),
            "sensor_lost_events": built.get("sensor_lost_events")}
    (run_dir / "meta.json").write_text(json.dumps(meta, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return LaneRunResult(session_id=session_id, run_dir=run_dir, return_code=rc, events=events, attribution=attribution, meta=meta)
