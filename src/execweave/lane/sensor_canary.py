"""Start-up canary for the kernel sensor: is every CPU observed?  (root)

    python3 sensor_canary.py OUTDIR [SENSOR.bt]          # starts its own sensor, runs the canary, prints JSON, exit 1 if a CPU is not observed
    from sensor_canary import canary; canary(sensor_log_path)   # against a sensor that is already running (any script that records write-intent openat with the path)

Why: on a GitHub-hosted Ubuntu runner (kernel 7.0.0-1017-azure, 2 vCPU) the probes on the per-syscall tracepoints ran only for calls made on CPU 0 and nothing
reported it (evidence/effect_coverage, loss_cpu_runner).  A sensor that silently misses CPUs turns effects into "unattributed" and looks healthy.  The canary pins one short
write per CPU (taskset) to a unique path, waits, and checks that the sensor log contains that path; the verdict names the CPUs that were not observed.
The path is unique per call of canary() (random), so a stale log cannot satisfy it."""
from __future__ import annotations

import json
import os
import secrets
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent


def online_cpus() -> list[int]:
    try:
        return sorted(os.sched_getaffinity(0))
    except AttributeError:
        return list(range(os.cpu_count() or 1))


def canary(sensor_log: str | os.PathLike, workdir: str = "/tmp", settle_s: float = 1.5) -> dict:
    """Pin one write per CPU; return {"cpus": [...], "observed": [...], "missing": [...], "path_prefix": ...}."""
    tag = secrets.token_hex(6)
    d = Path(workdir) / f"ewcanary-{tag}"
    d.mkdir(mode=0o755)
    cpus = online_cpus()
    for c in cpus:
        subprocess.run(["taskset", "-c", str(c), "sh", "-c", f": > {d}/cpu{c}_{tag}"], check=False)
    time.sleep(settle_s)
    text = Path(sensor_log).read_text(errors="replace")
    observed = [c for c in cpus if f"{d}/cpu{c}_{tag}" in text]
    shutil.rmtree(d, ignore_errors=True)
    return {"cpus": cpus, "observed": observed, "missing": [c for c in cpus if c not in observed], "path_prefix": f"ewcanary-{tag}"}


def main() -> int:
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    src = sys.argv[2] if len(sys.argv) > 2 else str(HERE / "lane_sensor_native_v2.bt")
    if Path(src).name != "lane_sensor_native_v2.bt":
        raise SystemExit(f"sensor {src!r} refused: the only ExecWeave sensor is lane_sensor_native_v2.bt")
    from execweave.lane import sensor_nonce
    log = out / "sensor.log"
    script = sensor_nonce.script_with_nonce(src, log)
    sp = subprocess.Popen(["bpftrace", "-B", "none", script], stdout=open(log, "ab"), stderr=open(out / "sensor.stderr", "wb"), env={**os.environ, "BPFTRACE_MAX_STRLEN": "200"})
    t_end = time.monotonic() + 40
    while time.monotonic() < t_end and "sensor_start" not in log.read_text(errors="replace") and sp.poll() is None:
        time.sleep(0.1)
    res = {"kernel": os.uname().release, "sensor_script": Path(src).name, "sensor_started": sp.poll() is None}
    if res["sensor_started"]:
        res.update(canary(log))
    sp.send_signal(signal.SIGINT)
    try:
        sp.wait(timeout=20)
    except subprocess.TimeoutExpired:
        sp.kill()
    res["verdict"] = "all CPUs observed" if res.get("sensor_started") and not res.get("missing") else "PARTIAL or not started"
    (out / "sensor_canary.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1))
    return 0 if res["verdict"] == "all CPUs observed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
