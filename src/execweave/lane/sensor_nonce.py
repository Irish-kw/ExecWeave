"""Per-run record nonce for the bpftrace lane sensor (fix of 2026-10-29).

The sensor prints argv verbatim after an execve header, so an argument that contains a newline followed by a JSON object made an unprivileged process
able to write a line that parsed as a genuine sensor record, with any cgroup id (found by a simulated reviewer, reproduced by us).  Every record the
sensor prints now starts with a 128-bit nonce that exists only in a root-only copy of the script and in a root-only file next to the log; the parser
accepts a JSON line as a record only if it carries the nonce.  The log itself is created mode 0600 so a running agent cannot read the nonce from it.

    script = script_with_nonce(SRC_BT, sensor_log)      # before starting bpftrace
    subprocess.Popen(["bpftrace", "-B", "none", script], stdout=open(sensor_log, "ab"), ...)
"""
from __future__ import annotations

import os
import secrets
from pathlib import Path

RUN_DIR = Path("/run/ewsensor")
MARK = 'printf("{\\"ev\\"'


def script_with_nonce(src: str | os.PathLike, log_path: str | os.PathLike) -> str:
    nonce = secrets.token_hex(16)
    text = Path(src).read_text()
    n = text.count(MARK)
    if n < 8:
        raise RuntimeError(f"sensor script has {n} record printf statements; expected at least 8")
    text = text.replace(MARK, f'printf("{nonce}{{\\"ev\\"')
    RUN_DIR.mkdir(mode=0o700, exist_ok=True)
    os.chmod(RUN_DIR, 0o700)
    script = RUN_DIR / f"sensor-{secrets.token_hex(8)}.bt"
    fd = os.open(script, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(text)
    log_path = Path(log_path)
    fd = os.open(str(log_path) + ".nonce", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(nonce)
    fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.close(fd)
    return str(script)


def nonce_for(log_path: str | os.PathLike) -> str | None:
    p = Path(str(log_path) + ".nonce")
    try:
        return p.read_text().strip() or None
    except OSError:
        return None


def detect(log_path: str | os.PathLike) -> str | None:
    """Nonce of a sensor log: from ``<log>.nonce`` if present, else from the first line, which the sensor's BEGIN block prints before any traced
    program runs (so a traced program cannot place a line before it)."""
    n = nonce_for(log_path)
    if n:
        return n
    import re
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as fh:
            first = fh.readline()
    except OSError:
        return None
    m = re.match(r'^([0-9a-f]{32})\{"ev":"sensor_start"', first)
    return m.group(1) if m else None


def strip(line: str, nonce: str | None) -> str | None:
    """Return the record text of a line, or None if the line is not a record (an unprefixed JSON line in a nonce log is rejected)."""
    if nonce is None:
        return line if line.startswith('{"ev":') else None
    if line.startswith(nonce + '{"ev":'):
        return line[len(nonce):]
    return None
