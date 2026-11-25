"""Sensor guard: refuse to run a session on a sensor that does not observe every CPU, and check again at the end of the session.  (root)

Why: on a GitHub-hosted Ubuntu runner (kernel 7.0.0-1017-azure, 2 vCPU) the probes on the per-syscall tracepoints ran only for calls made on CPU 0 and nothing
reported it (evidence/effect_coverage/README.md, "Sensor loss on the second Linux environment"); the effects of the other CPU's calls became unattributed and the
session looked healthy.  sensor_canary.py detects this but was not wired into the drivers.  This module wraps sensor start for the drivers:

    guard = sensor_guard.SensorGuard(sensor_log, sensor_proc)
    try:
        guard.start_check()                   # waits for `sensor_start`, then runs a pinned probe on every online CPU (taskset) and looks for it in the sensor log
    except sensor_guard.SensorGuardError:     # FAIL CLOSED: a CPU is not observed (or the sensor did not start / died)
        sensor_guard.stop_sensor(sensor_proc); raise
    svc.start(); guard.record_start(svc)      # EW_SENSOR_ALLOW_PARTIAL=1 only: a signed `sensor_partial` ledger record names the unobserved CPUs
    ...agent runs...
    guard.finish_check(svc)                   # drift check before svc.stop(): same canary again (also a record if CPUs are missing)
    meta["sensor_guard"] = guard.meta()       # verdicts of both checks

Modes (environment):
  default                        fail closed: any CPU not observed at start -> SensorPartialError (the session does not start)
  EW_SENSOR_ALLOW_PARTIAL=1      a partial sensor is accepted when at least one CPU is observed; the ledger gets `sensor_partial` (phase start, and end if still/newly
                                 partial) naming the unobserved CPUs.  A sensor that did not start, died, or observed no CPU is never accepted.
  EW_SENSOR_GUARD=0|off          guard disabled (previous behaviour); meta records `"enabled": false`.
  EW_SENSOR_SETTLE_S             seconds to wait for the sensor log to show the canary records of a CPU before calling it missing (default 2.0)

The canary cannot show that every event of an observed CPU is delivered (a sensor can still lose events under load); it shows that the two per-syscall probes the effect view
depends on, the write-intent open and the execve probe, run on every online CPU.  Each CPU runs a small script pinned there: it creates a file with a unique name (open_write
record) and then execs /bin/true with a unique argument (execve record).  The unique strings appear in the script file, never in the argv of the unpinned launcher of the
script, so a probe that is lost on a CPU cannot be satisfied by the other probe's record of the same run (sensor_canary.py passes the path in the argv of `sh -c`, which the
execve probe also prints; on a host where only one of the two probes is lost it would not notice).  The canary's own processes are root-owned and outside every lane, so no
call is credited with them."""
from __future__ import annotations

import os
import secrets
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable


class SensorGuardError(RuntimeError):
    def __init__(self, msg: str, verdict: dict[str, Any] | None = None) -> None:
        super().__init__(msg)
        self.verdict = verdict or {}


class SensorStartError(SensorGuardError):
    """The sensor did not print `sensor_start`, or exited."""


class SensorPartialError(SensorGuardError):
    """At least one online CPU is not observed by the sensor (fail closed)."""


def online_cpus() -> list[int]:
    """CPUs that are online according to /sys/devices/system/cpu/online ("0-3", "0,2-3"); falls back to os.cpu_count()."""
    try:
        text = Path("/sys/devices/system/cpu/online").read_text().strip()
        out: list[int] = []
        for part in text.split(","):
            if "-" in part:
                lo, hi = part.split("-")
                out.extend(range(int(lo), int(hi) + 1))
            elif part:
                out.append(int(part))
        if out:
            return sorted(out)
    except (OSError, ValueError):
        pass
    return list(range(os.cpu_count() or 1))


PROBES = ("open_write", "execve")


def pinned_probe(cpu: int, d: Path, tag: str) -> dict[str, str] | None:
    """Run, pinned to ``cpu``, a script that creates one file (write-intent openat) and then execs /bin/true with a unique argument (execve).  Returns the strings to
    look for in the sensor log per probe, or None if the CPU cannot be used (taskset failed)."""
    open_path, token, script = d / f"open{cpu}_{tag}", f"ewtok{cpu}x{tag}", d / f"run{cpu}_{tag}.sh"
    script.write_text(f"#!/bin/sh\n: > '{open_path}'\nexec /bin/true {token}\n")
    script.chmod(0o755)
    try:
        r = subprocess.run(["taskset", "-c", str(cpu), str(script)], capture_output=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return {"open_write": str(open_path), "execve": token} if r.returncode == 0 else None


def run_canary(sensor_log: str | os.PathLike, *, cpus: list[int] | None = None, workdir: str = "/tmp", settle_s: float = 2.0, poll_s: float = 0.05,
               writer: Callable[[int, Path, str], dict[str, str] | None] = pinned_probe, phase: str = "start") -> dict[str, Any]:
    """Run the pinned probe on every CPU and check that the sensor log shows its records.  Returns {"phase", "cpus", "observed" (CPUs for which both probes were seen),
    "missing" (the others), "missing_by_probe", "untestable", "path_prefix", "seconds"}.  Only log bytes written after the call started are examined and the strings are
    unique per call, so a stale log cannot satisfy it.  Returns as soon as everything is seen."""
    t0 = time.monotonic()
    tag = secrets.token_hex(6)
    d = Path(workdir) / f"ewcanary-{tag}"
    d.mkdir(mode=0o755)
    cpus = list(cpus) if cpus is not None else online_cpus()
    log = Path(sensor_log)
    try:
        offset = log.stat().st_size
    except OSError as exc:
        shutil.rmtree(d, ignore_errors=True)
        raise SensorGuardError(f"sensor log not readable: {exc}") from exc
    untestable: list[int] = []
    want: dict[int, dict[str, str]] = {}
    for c in cpus:
        try:
            w = writer(c, d, tag)
        except Exception:   # noqa: BLE001
            w = None
        if w:
            want[c] = w
        else:
            untestable.append(c)
    buf = ""
    deadline = time.monotonic() + settle_s
    while True:
        try:
            with open(log, "rb") as fh:
                fh.seek(offset)
                buf = fh.read().decode("utf-8", "replace")
        except OSError:
            pass
        seen = {(c, k) for c, w in want.items() for k, needle in w.items() if needle in buf}
        total = sum(len(w) for w in want.values())
        if len(seen) == total or time.monotonic() >= deadline:
            break
        time.sleep(poll_s)
    shutil.rmtree(d, ignore_errors=True)
    by_probe = {k: [c for c in cpus if (c, k) not in seen] for k in PROBES}
    missing = [c for c in cpus if any(c in by_probe[k] for k in PROBES)]
    return {"phase": phase, "cpus": cpus, "observed": [c for c in cpus if c not in missing], "missing": missing,
            "missing_by_probe": {k: v for k, v in by_probe.items() if v}, "untestable": untestable, "path_prefix": f"ewcanary-{tag}", "seconds": round(time.monotonic() - t0, 2)}


def stop_sensor(proc: subprocess.Popen | None, timeout: float = 20.0) -> None:
    if proc is None or proc.poll() is not None:
        return
    proc.send_signal(signal.SIGINT)
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()


class SensorGuard:
    def __init__(self, sensor_log: str | os.PathLike, sensor_proc: subprocess.Popen | None = None, *, allow_partial: bool | None = None, enabled: bool | None = None,
                 cpus: list[int] | None = None, workdir: str = "/tmp", settle_s: float | None = None, start_timeout: float = 30.0,
                 writer: Callable[[int, Path, str], dict[str, str] | None] = pinned_probe, log: Callable[[str], None] | None = None) -> None:
        self.sensor_log = Path(sensor_log)
        self.proc = sensor_proc
        self.allow_partial = (os.environ.get("EW_SENSOR_ALLOW_PARTIAL") == "1") if allow_partial is None else allow_partial
        self.enabled = (os.environ.get("EW_SENSOR_GUARD", "1").lower() not in ("0", "off", "no", "false")) if enabled is None else enabled
        self.cpus = cpus
        self.workdir = workdir
        self.settle_s = float(os.environ.get("EW_SENSOR_SETTLE_S", "2.0")) if settle_s is None else settle_s
        self.start_timeout = start_timeout
        self.writer = writer
        self.log = log or (lambda m: print(f"sensor_guard: {m}", file=sys.stderr, flush=True))
        self.start: dict[str, Any] | None = None
        self.end: dict[str, Any] | None = None

    # ---- start ---------------------------------------------------------------------------------------------------------------------------
    def _wait_sensor_start(self) -> None:
        t_end = time.monotonic() + self.start_timeout
        while True:
            try:
                if "sensor_start" in self.sensor_log.read_text(errors="replace"):
                    return
            except OSError:
                pass
            if self.proc is not None and self.proc.poll() is not None:
                raise SensorStartError(f"sensor exited with status {self.proc.returncode} before printing sensor_start")
            if time.monotonic() >= t_end:
                raise SensorStartError(f"sensor did not print sensor_start within {self.start_timeout:.0f} s")
            time.sleep(0.05)

    def start_check(self) -> dict[str, Any]:
        """Wait for the sensor and run the per-CPU canary.  Raises SensorStartError / SensorPartialError (fail closed) unless the guard is disabled, or
        EW_SENSOR_ALLOW_PARTIAL=1 and at least one CPU is observed."""
        if not self.enabled:
            self.start = {"phase": "start", "skipped": True}
            return self.start
        self._wait_sensor_start()
        v = run_canary(self.sensor_log, cpus=self.cpus, workdir=self.workdir, settle_s=self.settle_s, writer=self.writer, phase="start")
        self.start = v
        if v["missing"]:
            msg = (f"the sensor does not observe CPU(s) {v['missing']} of {v['cpus']} "
                   f"({'not usable for the canary: ' + str(v['untestable']) if v['untestable'] else 'probe(s) not seen: ' + str(v['missing_by_probe'])})")
            if self.allow_partial and v["observed"]:
                self.log(f"WARNING {msg}; continuing because EW_SENSOR_ALLOW_PARTIAL=1 (effects of calls on those CPUs will be unattributed)")
            else:
                raise SensorPartialError("refusing to run: " + msg + ("" if v["observed"] else " (no CPU observed)") +
                                         "; set EW_SENSOR_ALLOW_PARTIAL=1 to accept a partial sensor, EW_SENSOR_GUARD=0 to disable the guard", v)
        return v

    def _note(self, svc: Any, v: dict[str, Any], **extra: Any) -> None:
        svc.note_sensor_state("partial", phase=v["phase"], cpus=v["cpus"], observed=v["observed"], unobserved=v["missing"], untestable=v["untestable"],
                              missing_by_probe=v.get("missing_by_probe", {}), canary=v["path_prefix"], allow_partial=self.allow_partial, **extra)

    def record_start(self, svc: Any) -> None:
        """After svc.start(): a signed `sensor_partial` record if the start check found unobserved CPUs (only possible with EW_SENSOR_ALLOW_PARTIAL=1)."""
        if self.start and self.start.get("missing"):
            self._note(svc, self.start)

    # ---- end ----------------------------------------------------------------------------------------------------------------------------
    def finish_check(self, svc: Any = None) -> dict[str, Any]:
        """Drift check at the end of the session (call before svc.stop()): the sensor must still be running and still observe the CPUs it observed at the start.
        Never raises: the session is over; the verdict goes to meta and, when CPUs are unobserved, to the ledger."""
        if not self.enabled:
            self.end = {"phase": "end", "skipped": True}
            return self.end
        alive = self.proc is None or self.proc.poll() is None
        try:
            v = run_canary(self.sensor_log, cpus=self.cpus or (self.start or {}).get("cpus"), workdir=self.workdir, settle_s=self.settle_s, writer=self.writer, phase="end")
        except SensorGuardError as exc:
            v = {"phase": "end", "cpus": [], "observed": [], "missing": [], "missing_by_probe": {}, "untestable": [], "path_prefix": None, "seconds": 0.0, "error": str(exc)}
        v["sensor_alive"] = alive
        started_missing = set((self.start or {}).get("missing") or [])
        v["drift"] = sorted(set(v["missing"]) - started_missing)
        self.end = v
        if v["missing"] or not alive or v.get("error"):
            self.log(f"WARNING end-of-session check: unobserved CPU(s) {v['missing']}, sensor alive: {alive}" + (f", new since start: {v['drift']}" if v["drift"] else ""))
            if svc is not None and v["cpus"]:
                try:
                    self._note(svc, v, sensor_alive=alive, drift=v["drift"])
                except Exception as exc:   # noqa: BLE001
                    self.log(f"could not write the end-of-session record: {type(exc).__name__}: {exc}")
        return v

    # ---- result -------------------------------------------------------------------------------------------------------------------------
    @property
    def ok(self) -> bool:
        if not self.enabled:
            return True
        s, e = self.start or {}, self.end or {}
        return bool(s) and not s.get("missing") and not e.get("missing") and e.get("sensor_alive", True) and not e.get("error")

    def meta(self) -> dict[str, Any]:
        """For the session's meta.json."""
        if not self.enabled:
            return {"enabled": False}
        return {"enabled": True, "mode": "allow_partial" if self.allow_partial else "fail_closed", "ok": self.ok,
                "partial_at_start": (self.start or {}).get("missing", []), "unobserved_at_end": (self.end or {}).get("missing", []),
                "drift_cpus": (self.end or {}).get("drift", []), "sensor_alive_at_end": (self.end or {}).get("sensor_alive"),
                "start": self.start, "end": self.end}


if __name__ == "__main__":   # python3 sensor_guard.py SENSOR_LOG   (against a running sensor)
    g = SensorGuard(sys.argv[1], allow_partial=False)
    try:
        print(g.start_check())
    except SensorGuardError as exc:
        print(f"REFUSED: {exc}\n{exc.verdict}")
        raise SystemExit(1)
