"""Trusted lane launcher (runs as root).

Binds agent-level principals (agent, sub-agent, tool call) to kernel principals
(cgroup v2 "lanes") at launch time, so that attribution is identity-exact instead
of inferred, and keeps a hash-chained, Ed25519-signed launch ledger that the
unprivileged agent cannot alter.

Requester identity is taken from the kernel (SO_PEERCRED pid -> /proc/<pid>/cgroup),
never from the request body: a sub-agent cannot claim to be a different agent.

Protocol: one JSON request per Unix-socket connection, one JSON reply.
  {"op":"launch","call_id":..,"argv":[...],"declared":str|null,"cwd":..,"env":{..}}
      -> {"ok":true,"pid":..,"lane":..,"lane_inode":..,"seq":..}
  {"op":"spawn_agent","agent":name,"argv":[...],"cwd":..,"env":{..}}
      -> {"ok":true,"pid":..,"lane":..,"lane_inode":..}
  {"op":"wait","pid":..}  -> {"ok":true,"returncode":..}
  {"op":"grant","for_pid":int}   (requester inside a call lane; for_pid is required)  -> {"ok":true,"token":..}      delegation capability bound to the requester's call;
      with for_pid the token can only be redeemed by that process (kernel-reported pid and start time of the redeemer must match)
  {"op":"launch_delegated","token":..,"argv":[...],"cwd":..,"env":{..}}   (requester: any lane of this run, e.g. a helper daemon)
      -> {"ok":true,"pid":..,"lane":..,"lane_inode":..,"seq":..}; the child runs in a sub-lane of the call that granted the token (single use)
"""
from __future__ import annotations

import ctypes
import fcntl
import hashlib
import json
import secrets
import os
import re as _re
import signal
import socket
import struct
import subprocess
import threading
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

# Durability knob for measurement only: EW_LEDGER_FSYNC=0 skips the per-entry fsync (default on).
LEDGER_FSYNC = os.environ.get("EW_LEDGER_FSYNC", "1") != "0"
ENV_WHITELIST_PREFIXES = ("EW_", "EXECWEAVE_")
# Input validation (2026-10-27, after review): agent names become cgroup path components and call ids become
# ledger keys, so both are validated; call ids must be unique per run.
AGENT_NAME_RE = _re.compile(r"[A-Za-z0-9_-]{1,64}")
CALL_ID_RE = _re.compile(r"[A-Za-z0-9_.:-]{1,200}")
# TRACEPARENT/TRACESTATE (Claude Code) and CODEX_TOOL_CALL_ID (Codex) are harness-native per-call context; they are passed to the child
# unchanged so that tag-based tools keep working inside a lane.  The launcher never reads them: binding comes from the request and the kernel.
ENV_WHITELIST = {"PATH", "HOME", "LANG", "LC_ALL", "PYTHONDONTWRITEBYTECODE", "TMPDIR", "TRACEPARENT", "TRACESTATE", "CODEX_TOOL_CALL_ID"}
# Nested-request namespacing (2026-10-28, after the call-id squatting finding in evidence/adaptive/plain): a launch or agent spawn requested by a
# process that is itself inside a call lane gets an id qualified by the enclosing call ("<call>~<claimed id>"), so a call cannot occupy the id of
# a call that the harness issues later.  EW_LANE_NAMESPACE_NESTED=0 restores the earlier behaviour (used to reproduce the BEFORE evidence).
NAMESPACE_NESTED = os.environ.get("EW_LANE_NAMESPACE_NESTED", "1") != "0"
SO_PASSPIDFD, SCM_PIDFD = 76, 0x04          # Linux uapi values (Python's socket module does not export them)
REQUIRE_PIDFD = os.environ.get("EW_LANE_REQUIRE_PIDFD", "0") == "1"
# Ablation switches (2026-11-03, evidence/ablation): every name below is a defence that is ON by default.  EW_LANE_ABLATE=name1,name2 (or the
# constructor argument ``ablate``) turns the named defences OFF so that their individual contribution can be measured.  A misspelt name is an error
# (a typo must not silently run the default).  Nothing here is for production use; with no switch set the behaviour is unchanged.
ABLATIONS = {
    "nest_call_ns":        "nested launch ids are qualified by the enclosing call (call-id squatting, B1)",
    "nest_agent_ns":       "nested spawn_agent ids are qualified by the enclosing call (agent binding overwrite)",
    "call_id_unique":      "a call id may be used once per run",
    "call_id_syntax":      "call ids must match [A-Za-z0-9_.:-]{1,200}",
    "agent_name_syntax":   "agent names must match [A-Za-z0-9_-]{1,64}",
    "agent_id_unique":     "an agent id may be used once per run",
    "grant_for_pid":       "a delegation grant must name the redeeming process (for_pid)",
    "for_pid_positive":    "for_pid <= 0 is refused instead of being treated as 'not bound'",
    "sender_consistency":  "a request written by more than one process is refused",
    "unencodable_precheck": "a request with text that cannot be recorded is refused before anything is spawned",
    "recordable_escape":   "text that cannot be encoded is escaped inside the ledger record instead of failing the append",
    "kill_on_failure":     "a lane whose ledger record could not be written is killed",
    "wait_owner":          "only the lane that started a process may wait for it",
    "intent_record":       "an `intent` record is written before the child is spawned",
    "spawn_failed_record": "a failed spawn leaves a `spawn_failed` record",
}


def _parse_ablate(text: str | None) -> frozenset[str]:
    names = {x.strip() for x in (text or "").split(",") if x.strip()}
    bad = sorted(names - set(ABLATIONS))
    if bad:
        raise ValueError(f"unknown ablation name(s): {bad}; known: {sorted(ABLATIONS)}")
    return frozenset(names)


ABLATE_ENV = _parse_ablate(os.environ.get("EW_LANE_ABLATE"))
# Refusal records (2026-10-29, after the record-level weaknesses found by the final-launcher testers): every refused request leaves a `rejected` record
# (a fixed reason, the sender when the kernel named one, request-supplied text only ASCII-escaped and cut to REJECT_TEXT_CAP characters).  At most
# MAX_REJECTED_RECORDS such records are written per run; later refusals are only counted (one `rejected_suppressed` marker when the cap is first hit,
# one final `rejected_suppressed` record with the total and the per-reason counts when the service stops).  EW_LANE_MAX_REJECTED overrides the cap.
try:
    MAX_REJECTED_RECORDS = max(0, int(os.environ.get("EW_LANE_MAX_REJECTED", "1000")))
except ValueError:
    MAX_REJECTED_RECORDS = 1000
REJECT_TEXT_CAP = 64
# Owner of a process that `launch_root` started: the operator (the launcher's own caller, who holds the Popen handle and waits for it directly).  It is
# not a lane path, so no requester inside or outside the run's lanes can equal it: `wait` for such a process is refused over the protocol.
OPERATOR = "<operator>"


# ---- call isolation options (hardening, 2026-10-30; all default OFF) --------------------------------------------------------------------------
# EW_LANE_CALL_ISOLATION is a comma-separated list of: pidns | uid | landlock (empty, "off" or unset: none; behaviour and records are then unchanged).
#   pidns     each call (launch / launch_delegated) starts in its own PID namespace with a private /proc, so other calls' processes and the harness are
#             neither visible nor addressable by pid.  The call's processes are placed in the call's cgroup BEFORE the namespace is entered.  The
#             namespace's init (host-side root process) keeps running until the last process of the call is gone, so background jobs behave as before.
#   uid       each call runs under its own uid taken from EW_LANE_UID_POOL ("50000-50063" or "a,b,c"), with the shared group EW_LANE_UID_GID (default: the
#             agent gid) and umask EW_LANE_UID_UMASK (default 002, applied to every lane in this mode, the agent root included).  A uid is reused only
#             when the lane that held it has no process left (cgroup.events populated 0).  EW_LANE_UID_GIT_SAFE=1 adds GIT_CONFIG_* (safe.directory=*).
#   landlock  each call is confined to its own Landlock domain with the signal scope (and, with EW_LANE_LANDLOCK_ABSTRACT=1, the abstract-unix-socket
#             scope): signals and ptrace-class access (ptrace, /proc/<pid>/mem, process_vm_*, pidfd_getfd) reach only processes of the same domain.
# An unknown value or an option the host cannot provide stops LaneService.__init__ (fail closed).  See prototypes/lanes_hardening/README.md.
ISOLATION_MODES = ("pidns", "uid", "landlock")
warnings.filterwarnings("ignore", message=r"This process .* is multi-threaded", category=DeprecationWarning)    # os.fork in the pidns option (single-threaded child follows)
_libc = ctypes.CDLL(None, use_errno=True)
CLONE_NEWNS, CLONE_NEWPID = 0x00020000, 0x20000000
MS_NOSUID, MS_NODEV, MS_NOEXEC, MS_REC, MS_PRIVATE = 2, 4, 8, 0x4000, 1 << 18
LANDLOCK_SCOPE_ABSTRACT_UNIX_SOCKET, LANDLOCK_SCOPE_SIGNAL = 1, 2
SYS_LANDLOCK_CREATE_RULESET, SYS_LANDLOCK_RESTRICT_SELF = 444, 446
MAX_FD = 0x7FFFFFFF


class IsolationUnavailable(RuntimeError):
    """A requested isolation option is not available on this host (or could not be set up for this call)."""


def parse_isolation(value: str | None) -> frozenset[str]:
    modes = {m.strip() for m in (value or "").replace("+", ",").split(",") if m.strip()}
    modes -= {"off", "none", "0"}
    unknown = modes - set(ISOLATION_MODES)
    if unknown:
        raise IsolationUnavailable(f"unknown isolation option(s) {sorted(unknown)}; known: {list(ISOLATION_MODES)}")
    return frozenset(modes)


def parse_uid_pool(spec: str) -> list[int]:
    out: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            lo, hi = part.split("-", 1)
            out.extend(range(int(lo), int(hi) + 1))
        else:
            out.append(int(part))
    if not out or len(set(out)) != len(out) or min(out) < 1 or max(out) >= 2**31 - 1:
        raise IsolationUnavailable(f"bad EW_LANE_UID_POOL {spec!r}")
    return out


def landlock_abi() -> int:
    r = _libc.syscall(ctypes.c_long(SYS_LANDLOCK_CREATE_RULESET), None, ctypes.c_size_t(0), ctypes.c_uint32(1))   # LANDLOCK_CREATE_RULESET_VERSION
    return int(r) if r > 0 else 0


def landlock_enter(scope: int) -> None:
    """Restrict the calling process (and everything it creates) to a new Landlock domain that handles only the given scopes.  Needs ABI >= 6, and
    CAP_SYS_ADMIN or no_new_privs (the launcher is root).  No filesystem or network right is handled, so file and network access are unchanged."""
    attr = ctypes.create_string_buffer(struct.pack("QQQ", 0, 0, scope), 24)    # handled_access_fs, handled_access_net, scoped
    fd = _libc.syscall(ctypes.c_long(SYS_LANDLOCK_CREATE_RULESET), attr, ctypes.c_size_t(24), ctypes.c_uint32(0))
    if fd < 0:
        e = ctypes.get_errno()
        raise OSError(e, "landlock_create_ruleset: " + os.strerror(e))
    try:
        if _libc.syscall(ctypes.c_long(SYS_LANDLOCK_RESTRICT_SELF), ctypes.c_int(fd), ctypes.c_uint32(0)) != 0:
            e = ctypes.get_errno()
            raise OSError(e, "landlock_restrict_self: " + os.strerror(e))
    finally:
        os.close(fd)


def _libc_call(name: str, *args: Any) -> None:
    if getattr(_libc, name)(*args) != 0:
        e = ctypes.get_errno()
        raise OSError(e, f"{name}: {os.strerror(e)}")


def _close_fds_except(keep: set[int]) -> None:
    lo = 3
    for k in sorted(k for k in keep if k >= 3):
        if k > lo:
            os.closerange(lo, k)
        lo = k + 1
    os.closerange(lo, MAX_FD)


def _close_stdio() -> None:
    """Drop this process's copies of the call's stdio (no /dev/null open: that would add a write-intent open record to the call's lane)."""
    for i in range(3):
        try:
            os.close(i)
        except OSError:
            pass


class NsProc:
    """Popen-like handle (pid, wait, poll, kill, returncode) for a call that was created with os.fork in its own PID namespace."""

    def __init__(self, pid: int) -> None:
        self.pid = pid
        self.returncode: int | None = None
        self._lock = threading.Lock()

    def _reap(self, flags: int) -> None:
        try:
            p, st = os.waitpid(self.pid, flags)
        except ChildProcessError:
            self.returncode = 255
            return
        if p:
            self.returncode = os.waitstatus_to_exitcode(st)

    def poll(self) -> int | None:
        with self._lock:
            if self.returncode is None:
                self._reap(os.WNOHANG)
            return self.returncode

    def wait(self, timeout: float | None = None) -> int:
        if timeout is None:
            with self._lock:
                if self.returncode is None:
                    self._reap(0)
                return self.returncode  # type: ignore[return-value]
        end = time.monotonic() + timeout
        while self.poll() is None:
            if time.monotonic() >= end:
                raise subprocess.TimeoutExpired(str(self.pid), timeout)
            time.sleep(0.005)
        return self.returncode  # type: ignore[return-value]

    def kill(self) -> None:
        try:
            os.kill(self.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    send_signal = lambda self, sig: os.kill(self.pid, sig)   # noqa: E731


def _pidns_child(*, argv: list[str], cwd: str | None, env: dict[str, str], stdio: tuple[int, int, int] | None, log_fd: int, lane_fs: str,
                 uid: int, gid: int, umask: int | None, landlock_scope: int, errw: int) -> None:
    """Body of the forked child of a call in its own PID namespace; never returns (exec or os._exit).  Three processes take part:
      I  the forked child: host-side, root, in the call's cgroup, outside the namespace; it is the handle the launcher waits for and exits with the
         command's status as soon as the command exits.
      J  first child of I and init (pid 1) of the namespace: root, mounts the private /proc, starts the command, reaps orphans, and stays until the
         last process of the namespace has exited, so a background job started by a call outlives the call as it does without the option.
      C  the command: drops to the call's uid/gid, optionally enters its Landlock domain, and executes argv.
    The cgroup placement happens first, so I, J and C are all stamped with the call's lane.  Errors before the exec of C are written to ``errw``."""
    try:
        if stdio is not None:
            src = list(stdio)
        else:
            dn = os.open(os.devnull, os.O_RDWR)
            src = [dn, dn, log_fd]
        src = [fcntl.fcntl(fd, fcntl.F_DUPFD, 10) for fd in src]       # out of the way of 0..2
        for i, fd in enumerate(src):
            os.dup2(fd, i)
        if cwd:
            os.chdir(cwd)
        with open(os.path.join(lane_fs, "cgroup.procs"), "w") as fh:     # BEFORE the namespace is entered
            fh.write(str(os.getpid()))
        if umask is not None:
            os.umask(umask)
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)                     # as subprocess does for its children (Python ignores SIGPIPE, exec keeps it)
        signal.signal(signal.SIGXFSZ, signal.SIG_DFL)
        _libc_call("unshare", ctypes.c_int(CLONE_NEWNS | CLONE_NEWPID))
        _libc_call("mount", None, b"/", None, ctypes.c_ulong(MS_REC | MS_PRIVATE), None)      # private: the /proc mount below must not reach the host
        sr, sw = os.pipe()
        j = os.fork()
        if j:   # ---- I ----
            os.close(sw)
            _close_fds_except({sr})
            _close_stdio()
            data = b""
            while b"\n" not in data:
                chunk = os.read(sr, 64)
                if not chunk:
                    break
                data += chunk
            kind, num = (data[:1], data[1:].strip() or b"0")
            if not data:      # J died without a report (killed): follow J
                _, st = os.waitpid(j, 0)
                code = os.waitstatus_to_exitcode(st)
                kind, num = (b"S", str(-code).encode()) if code < 0 else (b"E", str(code).encode())
            if kind == b"S":
                sig = int(num)
                try:
                    signal.signal(sig, signal.SIG_DFL)
                except (OSError, ValueError):     # SIGKILL and SIGSTOP have no handler to reset
                    pass
                os.kill(os.getpid(), sig)
                time.sleep(1.0)
                os._exit(128 + sig)
            os._exit(int(num))
        # ---- J (pid 1 of the new namespace) ----
        os.close(sr)
        _libc_call("mount", b"proc", b"/proc", b"proc", ctypes.c_ulong(MS_NOSUID | MS_NODEV | MS_NOEXEC), None)
        c = os.fork()
        if c == 0:   # ---- C ----
            os.close(sw)
            if landlock_scope:
                landlock_enter(landlock_scope)
            os.setgroups([])
            os.setgid(gid)
            os.setuid(uid)
            _close_fds_except({errw})
            os.execvpe(argv[0], argv, env)
        _close_fds_except({sw})
        _close_stdio()
        sent = False
        while True:
            try:
                p, st = os.waitpid(-1, 0)
            except ChildProcessError:
                break
            if p == c and not sent:
                code = os.waitstatus_to_exitcode(st)
                os.write(sw, (f"S{-code}\n" if code < 0 else f"E{code}\n").encode())
                sent = True
        os._exit(0)
    except BaseException as exc:   # noqa: BLE001
        try:
            e = getattr(exc, "errno", None) or 0
            os.write(errw, f"{type(exc).__name__}|{e}|{exc}".encode("utf-8", "replace")[:400])
        finally:
            os._exit(255)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def proc_starttime(pid: int) -> int | None:
    try:
        data = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    rest = data[data.rfind(")") + 2:].split()
    try:
        return int(rest[19])
    except (IndexError, ValueError):
        return None


def cgroup_of(pid: int) -> str | None:
    try:
        for line in Path(f"/proc/{pid}/cgroup").read_text(encoding="utf-8").splitlines():
            if line.startswith("0::"):
                return line[3:]
    except OSError:
        return None
    return None


def ascii_cap(value: Any, limit: int = REJECT_TEXT_CAP) -> str:
    """Request-supplied value as text for a refusal record: ASCII only (non-ASCII characters and lone surrogates as backslash escapes), at most ``limit``
    characters (a cut ends in ``...``).  The escape is for reading, not reversible; the full text of a refused request is not kept."""
    if isinstance(value, str):
        text = value
    elif value is None or isinstance(value, (bool, int, float)):
        text = repr(value)
    else:
        text = f"<{type(value).__name__}>"
    esc = text[: limit + 1].encode("ascii", "backslashreplace").decode("ascii")
    return esc[: limit - 3] + "..." if len(text) > limit or len(esc) > limit else esc


def peer_cred(conn: socket.socket) -> tuple[int, int, int]:
    data = conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
    pid, uid, gid = struct.unpack("3i", data)
    return pid, uid, gid


class Ledger:
    def __init__(self, path: Path, pubkey_path: Path, *, recordable: bool = True) -> None:
        self.recordable = recordable        # False only in the ablation experiment ("recordable_escape" off)
        self.path = Path(path)
        if self.path.exists() and self.path.stat().st_size > 0:
            # a new key over an existing chain would make the earlier entries unverifiable with the public key written below
            raise FileExistsError(f"{self.path} already has entries")
        self.key = Ed25519PrivateKey.generate()
        pub = self.key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        pubkey_path.write_bytes(pub)
        self.prev = "0" * 64
        self.seq = 0
        self.lock = threading.Lock()
        self.path.touch(mode=0o600)

    @staticmethod
    def _recordable(o: Any) -> tuple[Any, bool]:
        """Copy of a record value in which every string can be encoded as UTF-8: a lone surrogate (json.loads accepts one in request text) becomes its
        backslash escape, for example the six characters ``\\ud800``.  Returns (copy, changed)."""
        if isinstance(o, str):
            try:
                o.encode("utf-8")
                return o, False
            except UnicodeEncodeError:
                return o.encode("utf-8", "backslashreplace").decode("utf-8"), True
        if isinstance(o, dict):
            out: dict[Any, Any] = {}
            changed = False
            for k, v in o.items():
                k2, c1 = Ledger._recordable(k)
                v2, c2 = Ledger._recordable(v)
                if k2 in out:
                    raise ValueError("two keys of a record are equal once escaped")
                out[k2] = v2
                changed = changed or c1 or c2
            return out, changed
        if isinstance(o, (list, tuple)):
            items = [Ledger._recordable(v) for v in o]
            return [v for v, _ in items], any(c for _, c in items)
        return o, False

    def append(self, record: dict[str, Any]) -> dict[str, Any]:
        """Append one signed entry.  Everything that can fail (escaping, serialising, signing) happens before the sequence number and the chain head change,
        so a refused append leaves no gap; text that cannot be encoded is recorded escaped, with ``text_escaped: true``, instead of losing the record."""
        with self.lock:
            clean, changed = self._recordable(record) if self.recordable else (record, False)
            rec = {"seq": self.seq + 1, "ts": now_iso(), **clean}
            if changed:
                rec["text_escaped"] = True
            payload = json.dumps(rec, sort_keys=True, ensure_ascii=False)
            if json.dumps(json.loads(payload), sort_keys=True, ensure_ascii=False) != payload:   # verify_ledger recomputes the signed text from the parsed record
                raise ValueError("record does not survive a JSON round trip")
            digest = hashlib.sha256((self.prev + payload).encode("utf-8")).hexdigest()
            sig = self.key.sign(bytes.fromhex(digest)).hex()
            entry = {"record": rec, "prev": self.prev, "hash": digest, "sig": sig}
            # ASCII-escaped line: text in a record (argv, declared) may hold U+2028/U+2029/U+0085, which str.splitlines() treats as line
            # breaks; the signed payload above is unchanged (it is recomputed from the parsed record with ensure_ascii=False)
            line = json.dumps(entry, sort_keys=True, ensure_ascii=True) + "\n"
            start = None
            try:
                with open(self.path, "a", encoding="utf-8") as fh:
                    start = os.fstat(fh.fileno()).st_size
                    fh.write(line)
                    fh.flush()
                    if LEDGER_FSYNC:
                        os.fsync(fh.fileno())
            except BaseException:
                if start is not None:      # a partly written line would corrupt the next entry: cut the file back to the last complete entry
                    try:
                        os.truncate(self.path, start)
                    except OSError:
                        pass
                raise
            self.seq += 1
            self.prev = digest
            return entry


def verify_ledger(path: Path, pubkey_path: Path, *, expected_head: str | None = None, expected_count: int | None = None,
                  pinned_pubkey_sha256: str | None = None) -> dict[str, Any]:
    """Verify hash chain and signatures.  Without ``expected_head``/``expected_count`` a ledger that was truncated at the tail still verifies
    (the remaining prefix is a valid chain); with them, truncation is reported.  ``pinned_pubkey_sha256`` (the SHA-256 of the PEM file, obtained out of
    band) rejects a ledger signed with another key, e.g. one replayed from another run."""
    pem = pubkey_path.read_bytes()
    pre_errors: list[str] = []
    if pinned_pubkey_sha256 is not None and hashlib.sha256(pem).hexdigest() != pinned_pubkey_sha256:
        pre_errors.append("public key does not match the pinned key")
    pub = serialization.load_pem_public_key(pem)
    assert isinstance(pub, Ed25519PublicKey)
    prev = "0" * 64
    n = 0
    errors: list[str] = list(pre_errors)
    for line_no, line in enumerate(path.read_bytes().decode("utf-8", errors="replace").split("\n"), start=1):  # "\n" only (not splitlines())
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            entry["record"], entry["prev"], entry["hash"], entry["sig"]
        except (json.JSONDecodeError, KeyError, TypeError):
            errors.append(f"line {line_no}: malformed entry")
            continue
        payload = json.dumps(entry["record"], sort_keys=True, ensure_ascii=False)
        digest = hashlib.sha256((prev + payload).encode("utf-8")).hexdigest()
        if entry["prev"] != prev:
            errors.append(f"line {line_no}: prev mismatch")
        if entry["hash"] != digest:
            errors.append(f"line {line_no}: hash mismatch")
        try:
            pub.verify(bytes.fromhex(entry["sig"]), bytes.fromhex(entry["hash"]))
        except Exception:  # noqa: BLE001
            errors.append(f"line {line_no}: bad signature")
        prev = entry["hash"]
        n += 1
    if expected_count is not None and n != expected_count:
        errors.append(f"entry count {n} != expected {expected_count}")
    if expected_head is not None and prev != expected_head:
        errors.append("head hash differs from the expected head")
    return {"entries": n, "valid": not errors, "errors": errors, "head": prev}


class LaneService:
    def __init__(self, *, run_id: str, lane_dir: Path, sock_path: Path, agent_uid: int, agent_gid: int,
                 cg_mount: Path = Path("/run/cg2"), child_log: Path | None = None,
                 ablate: frozenset[str] | set[str] | None = None, call_isolation: str | None = None) -> None:
        legacy = frozenset() if NAMESPACE_NESTED else frozenset({"nest_call_ns", "nest_agent_ns"})    # EW_LANE_NAMESPACE_NESTED=0
        self.ablate = (ABLATE_ENV if ablate is None else _parse_ablate(",".join(ablate))) | legacy
        self.run_id = run_id
        self.cg_mount = cg_mount
        self.root_fs = cg_mount / "ewlanes" / run_id          # filesystem path of the run's lane root
        self.root_rel = f"/ewlanes/{run_id}"                    # path as seen in /proc/<pid>/cgroup
        self.sock_path = sock_path
        self.agent_uid, self.agent_gid = agent_uid, agent_gid
        lane_dir.mkdir(parents=True, exist_ok=True)
        self.ledger = Ledger(lane_dir / "ledger.jsonl", lane_dir / "ledger_pub.pem", recordable="recordable_escape" not in self.ablate)
        self.child_log = open(child_log or (lane_dir / "children.stderr.log"), "ab")
        self.procs: dict[int, subprocess.Popen] = {}
        self.proc_owner: dict[int, str | None] = {}   # pid -> lane of the request that started it (OPERATOR: launch_root; the caller waits on its Popen handle)
        self.exited: dict[int, int] = {}
        self.lanes: dict[int, dict[str, Any]] = {}
        self.counter = 0
        self.lock = threading.Lock()
        self.call_ids: set[str] = set()
        self.agent_ids: set[str] = set()
        self.grants: dict[str, dict[str, Any]] = {}
        self.max_rejected = MAX_REJECTED_RECORDS       # per-run cap on `rejected` records (see _reject)
        self.rejected_written = 0
        self.rejected_suppressed = 0
        self.suppressed_by_reason: dict[str, int] = {}
        self._tls = threading.local()
        self._srv: socket.socket | None = None
        self._threads: list[threading.Thread] = []
        self.root_fs.mkdir(parents=True, exist_ok=True)
        self._init_isolation(call_isolation)

    # ---- call isolation options (all default OFF; see the block comment above ISOLATION_MODES) ------------------------------------------------
    def _init_isolation(self, call_isolation: str | None) -> None:
        self.isolation = parse_isolation(call_isolation if call_isolation is not None else os.environ.get("EW_LANE_CALL_ISOLATION"))
        self.lane_uid: dict[str, int] = {}               # lane_fs of a call -> the uid it runs under (uid option)
        self._uid_holders: dict[int, dict[str, Any]] = {}
        self._uid_cursor = 0
        self.uid_pool: list[int] = []
        self.uid_gid, self.uid_umask, self.uid_git_safe = self.agent_gid, None, False
        self.landlock_scope = 0
        if not self.isolation:
            return
        if "uid" in self.isolation:
            self.uid_pool = parse_uid_pool(os.environ.get("EW_LANE_UID_POOL", "50000-50063"))
            if self.agent_uid in self.uid_pool:
                raise IsolationUnavailable("EW_LANE_UID_POOL contains the agent uid")
            self.uid_gid = int(os.environ.get("EW_LANE_UID_GID", str(self.agent_gid)))
            self.uid_umask = int(os.environ.get("EW_LANE_UID_UMASK", "002"), 8)
            self.uid_git_safe = os.environ.get("EW_LANE_UID_GIT_SAFE", "0") == "1"
        if "landlock" in self.isolation:
            abi = landlock_abi()
            if abi < 6:
                raise IsolationUnavailable(f"landlock option needs Landlock ABI >= 6 (signal scope); this kernel reports ABI {abi}")
            self.landlock_scope = LANDLOCK_SCOPE_SIGNAL | (LANDLOCK_SCOPE_ABSTRACT_UNIX_SOCKET if os.environ.get("EW_LANE_LANDLOCK_ABSTRACT", "0") == "1" else 0)
        self._isolation_probe()
        self.ledger.append({"op": "isolation_config", "modes": sorted(self.isolation),
                            **({"uid_pool": [self.uid_pool[0], self.uid_pool[-1], len(self.uid_pool)], "uid_gid": self.uid_gid, "uid_umask": oct(self.uid_umask),
                                "uid_git_safe": self.uid_git_safe} if "uid" in self.isolation else {}),
                            **({"landlock_abi": landlock_abi(), "landlock_scope": self.landlock_scope} if "landlock" in self.isolation else {})})

    def _isolation_probe(self) -> None:
        """Fail closed at start-up: run each requested mechanism once in a throw-away child (no lane, no ledger record)."""
        pid = os.fork()
        if pid == 0:
            try:
                if "pidns" in self.isolation:
                    _libc_call("unshare", ctypes.c_int(CLONE_NEWNS | CLONE_NEWPID))
                    _libc_call("mount", None, b"/", None, ctypes.c_ulong(MS_REC | MS_PRIVATE), None)
                    j = os.fork()
                    if j == 0:
                        try:
                            _libc_call("mount", b"proc", b"/proc", b"proc", ctypes.c_ulong(MS_NOSUID | MS_NODEV | MS_NOEXEC), None)
                            n = sum(1 for x in os.listdir("/proc") if x.isdigit())
                            os._exit(0 if n <= 2 and os.getpid() == 1 else 3)
                        except BaseException:   # noqa: BLE001
                            os._exit(2)
                    _, st = os.waitpid(j, 0)
                    if st != 0:
                        os._exit(4)
                if "landlock" in self.isolation:
                    landlock_enter(self.landlock_scope)
                if "uid" in self.isolation:
                    os.setgroups([])
                    os.setgid(self.uid_gid)
                    os.setuid(self.uid_pool[0])
                os._exit(0)
            except BaseException:   # noqa: BLE001
                os._exit(1)
        _, st = os.waitpid(pid, 0)
        if st != 0:
            raise IsolationUnavailable(f"isolation option(s) {sorted(self.isolation)} cannot be set up on this host (probe status {st})")

    def _lane_populated(self, lane_fs: str) -> bool:
        try:
            for line in Path(lane_fs, "cgroup.events").read_text().splitlines():
                if line.startswith("populated"):
                    return line.split()[1] == "1"
        except OSError:
            return False
        return False

    def _alloc_call_uid(self, lane_fs: str) -> int:
        with self.lock:
            n = len(self.uid_pool)
            for k in range(n):
                uid = self.uid_pool[(self._uid_cursor + k) % n]
                h = self._uid_holders.get(uid)
                if h is None or (h["started"] and not self._lane_populated(h["lane_fs"])):
                    self._uid_holders[uid] = {"lane_fs": lane_fs, "started": False}
                    self._uid_cursor = (self._uid_cursor + k + 1) % n
                    self.lane_uid[lane_fs] = uid
                    return uid
        raise IsolationUnavailable(f"no free call uid in the pool of {n}")

    def note_sensor_state(self, state: str, **fields: Any) -> dict[str, Any]:
        """Signed record of the sensor's state, written by the session driver (see sensor_guard.py): ``partial`` (CPUs not observed by the start-up or
        end-of-session canary; the operator allowed the run to continue) or ``ok``.  Returns the ledger entry."""
        if state not in ("partial", "ok"):
            raise ValueError(f"unknown sensor state {state!r}")
        return self.ledger.append({"op": f"sensor_{state}", **fields})

    # ---- lanes ------------------------------------------------------------
    def _new_lane(self, parent_fs: Path, name: str, kind: str, **meta: Any) -> dict[str, Any]:
        lane_fs = parent_fs / name
        lane_fs.mkdir(parents=False, exist_ok=False)
        inode = os.stat(lane_fs).st_ino
        rel = "/" + str(lane_fs.relative_to(self.cg_mount))
        info = {"lane": rel, "lane_fs": str(lane_fs), "lane_inode": inode, "kind": kind, **meta}
        with self.lock:
            self.lanes[inode] = info
        return info

    def _sanitize_env(self, requested: dict[str, str] | None) -> dict[str, str]:
        env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": "/tmp/agenthome", "PYTHONDONTWRITEBYTECODE": "1", "LANG": "C.UTF-8"}
        for k, v in (requested or {}).items():
            if k in ENV_WHITELIST or k.startswith(ENV_WHITELIST_PREFIXES):
                env[k] = str(v)
        if getattr(self, "uid_git_safe", False):    # uid option: the repository belongs to the agent uid, git refuses other owners without this
            env.update({"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "safe.directory", "GIT_CONFIG_VALUE_0": "*"})
        return env

    def _spawn(self, lane: dict[str, Any], argv: list[str], cwd: str | None, env: dict[str, str],
               stdio: tuple[int, int, int] | None = None, owner: str | None = None, isolate: bool = False, uid_from: str | None = None):
        lane_fs = lane["lane_fs"]
        iso = self.isolation if isolate else frozenset()      # isolation applies to calls (launch, launch_delegated), not to the agent root or sub-agents
        uid, gid, umask = self.agent_uid, self.agent_gid, (self.uid_umask if "uid" in self.isolation else None)
        scope = self.landlock_scope if "landlock" in iso else 0
        proc = None
        try:
            if "uid" in iso:
                uid, gid = (self.lane_uid[uid_from] if uid_from in self.lane_uid else self._alloc_call_uid(lane_fs)), self.uid_gid
                if uid_from in self.lane_uid:
                    self.lane_uid[lane_fs] = uid
                # pool uids have no passwd entry: a name per uid keeps tools that derive a per-user directory from the login name (pytest: /tmp/pytest-of-<name>) apart
                env = {**env, "USER": env.get("USER") or f"ewcall{uid}", "LOGNAME": env.get("LOGNAME") or f"ewcall{uid}"}
            if "pidns" in iso:
                proc = self._spawn_pidns(lane_fs, argv, cwd, env, stdio, uid, gid, umask, scope)
            else:
                def preexec() -> None:
                    with open(os.path.join(lane_fs, "cgroup.procs"), "w") as fh:
                        fh.write(str(os.getpid()))
                    if umask is not None:
                        os.umask(umask)
                    if scope:
                        landlock_enter(scope)
                    os.setgroups([])
                    os.setgid(gid)
                    os.setuid(uid)

                if stdio is not None:  # file descriptors received from the requester (SCM_RIGHTS): stdin, stdout, stderr
                    proc = subprocess.Popen(argv, cwd=cwd, env=env, preexec_fn=preexec, stdin=stdio[0], stdout=stdio[1],
                                            stderr=stdio[2], close_fds=True)
                else:
                    proc = subprocess.Popen(argv, cwd=cwd, env=env, preexec_fn=preexec, stdout=subprocess.DEVNULL,
                                            stderr=self.child_log, close_fds=True)
        except Exception as exc:  # noqa: BLE001
            # a request whose spawn failed (bad cwd, missing executable) consumed its id; leave a trace instead of a silent gap
            if "spawn_failed_record" not in self.ablate:
                self.ledger.append({"op": "spawn_failed", **(getattr(self._tls, "ctx", None) or {}), "lane": lane["lane"], "error": type(exc).__name__,
                                    "argv_sha256": hashlib.sha256("\0".join(argv).encode()).hexdigest()})
            self._tls.refusal_recorded = True
            if "uid" in iso:
                with self.lock:
                    for k, h in list(self._uid_holders.items()):
                        if h["lane_fs"] == lane_fs:
                            del self._uid_holders[k]
                    self.lane_uid.pop(lane_fs, None)
            try:
                os.rmdir(lane_fs)
            except OSError:
                pass
            raise
        if iso:
            lane["isolation"] = {"modes": sorted(iso), **({"call_uid": uid, "call_gid": gid} if "uid" in iso else {})}
        if "uid" in iso:
            with self.lock:
                if uid in self._uid_holders and self._uid_holders[uid]["lane_fs"] == lane_fs:
                    self._uid_holders[uid]["started"] = True
        with self.lock:
            self.procs[proc.pid] = proc
            self.proc_owner[proc.pid] = owner or ((getattr(self._tls, "ctx", None) or {}).get("requester") or {}).get("lane")
        self._tls.lane = lane
        return proc

    def _spawn_pidns(self, lane_fs: str, argv: list[str], cwd: str | None, env: dict[str, str], stdio: tuple[int, int, int] | None,
                     uid: int, gid: int, umask: int | None, scope: int) -> NsProc:
        er, ew = os.pipe()
        log_fd = self.child_log.fileno()
        pid = os.fork()
        if pid == 0:
            try:
                os.close(er)
                _pidns_child(argv=argv, cwd=cwd, env=env, stdio=stdio, log_fd=log_fd, lane_fs=lane_fs, uid=uid, gid=gid, umask=umask, landlock_scope=scope, errw=ew)
            finally:
                os._exit(255)
        os.close(ew)
        msg = b""
        while True:
            chunk = os.read(er, 4096)
            if not chunk:
                break
            msg += chunk
        os.close(er)
        if msg:
            try:
                os.waitpid(pid, 0)
            except ChildProcessError:
                pass
            name, _, rest = msg.decode("utf-8", "replace").partition("|")
            err, _, text = rest.partition("|")
            exc_type = {"FileNotFoundError": FileNotFoundError, "PermissionError": PermissionError, "NotADirectoryError": NotADirectoryError}.get(name, OSError)
            raise exc_type(int(err or 0), text)
        return NsProc(pid)

    def launch_root(self, argv: list[str], *, cwd: str, env: dict[str, str], trusted_env: dict[str, str] | None = None,
                    stdout_path: str | None = None) -> dict[str, Any]:
        """``trusted_env`` entries bypass the agent-request whitelist (set by the root operator only, never ledgered)."""
        lane = self._new_lane(self.root_fs, "root", "agent", agent="agent:orchestrator")
        self.agent_ids.add("agent:orchestrator")
        full_env = {**self._sanitize_env(env), **(trusted_env or {})}
        if stdout_path:
            with open(stdout_path, "wb") as out:
                os.chown(stdout_path, self.agent_uid, self.agent_gid)
                proc = self._spawn(lane, argv, cwd, full_env, stdio=(os.open(os.devnull, os.O_RDONLY), out.fileno(), self.child_log.fileno()), owner=OPERATOR)
        else:
            proc = self._spawn(lane, argv, cwd, full_env, owner=OPERATOR)
        entry = self.ledger.append({"op": "launch_root", "requester": {"pid": os.getpid(), "uid": 0, "lane": None},
                                    "lane": lane["lane"], "lane_inode": lane["lane_inode"], "agent": "agent:orchestrator",
                                    "child_pid": proc.pid, "child_starttime": proc_starttime(proc.pid), "argv": argv,
                                    "argv_sha256": hashlib.sha256("\0".join(argv).encode()).hexdigest()})
        return {"ok": True, "pid": proc.pid, "lane": lane["lane"], "lane_inode": lane["lane_inode"], "seq": entry["record"]["seq"], "proc": proc}

    # ---- request handling --------------------------------------------------
    def _requester_lane(self, pid: int) -> tuple[str, Path] | None:
        rel = getattr(self._tls, "req_cg", None) or cgroup_of(pid)
        if not rel or not (rel == self.root_rel or rel.startswith(self.root_rel + "/")):
            # experiment mode (set_external_requester): the sub-agents of the running Claude Code session cannot be placed in a lane, so requests from
            # outside the run's lanes are attributed to one designated agent lane.  This removes requester identity (agent binding) from the
            # guarantees; call-level binding (every launched command and its descendants in the call's own cgroup) is unaffected.
            if getattr(self, "external_requester", None):
                return self.external_requester
            return None
        return rel, self.cg_mount / rel.lstrip("/")

    def set_external_requester(self, lane_rel: str) -> None:
        self.external_requester = (lane_rel, self.cg_mount / lane_rel.lstrip("/"))

    def _handle(self, conn: socket.socket) -> None:
        pid = uid = gid = -1
        pidfd = -1
        senders: set[tuple[int, int, int]] = set()
        buf = b""
        fds: list[int] = []
        stage = "receive"
        self._tls.refusal_recorded = False
        self._tls.req_cg = self._tls.req_start = self._tls.lane = None
        try:
            # The requester is the process that *sent the request message* (SCM_CREDENTIALS, attached by the kernel at send time), not the process that
            # connected: a connection (or a descriptor for it) handed to another process does not carry the connector's identity.
            conn.setsockopt(socket.SOL_SOCKET, socket.SO_PASSCRED, 1)
            try:   # Linux >= 6.5: the kernel also passes a pidfd of the sender, which pins its identity against pid reuse
                conn.setsockopt(socket.SOL_SOCKET, SO_PASSPIDFD, 1)
            except OSError:
                pass
            while not buf.endswith(b"\n"):
                chunk, anc, _flags, _addr = conn.recvmsg(65536, socket.CMSG_SPACE(4 * 4) + socket.CMSG_SPACE(struct.calcsize("3i")) + socket.CMSG_SPACE(4))
                for level, typ, data in anc:
                    if level == socket.SOL_SOCKET and typ == socket.SCM_RIGHTS:
                        fds.extend(struct.unpack(f"{len(data) // 4}i", data[: len(data) - len(data) % 4]))
                    elif level == socket.SOL_SOCKET and typ == socket.SCM_CREDENTIALS:
                        creds = struct.unpack("3i", data[:12])
                        if pid < 0:
                            pid, uid, gid = creds
                        elif creds != (pid, uid, gid):
                            # the kernel never merges data of different senders into one read, so a later chunk with other credentials means
                            # the request was written by more than one process (e.g. a connection handed over mid-request): refuse it, since
                            # the identity of the first chunk would otherwise be applied to text another process wrote
                            senders.add(creds)
                    elif level == socket.SOL_SOCKET and typ == SCM_PIDFD and pidfd < 0:
                        pidfd = struct.unpack("i", data[:4])[0]
                    elif level == socket.SOL_SOCKET and typ == SCM_PIDFD:
                        os.close(struct.unpack("i", data[:4])[0])
                if not chunk:
                    break
                buf += chunk
            stage = "parse"
            if pid < 0:
                self._reject_unparsed("request carried no sender credentials", pid, uid, buf)
                raise PermissionError("request carried no sender credentials")
            if senders and "sender_consistency" not in self.ablate:
                self._reject({"op": "rejected", "reason": "request written by more than one process",
                              "senders": [{"pid": p, "uid": u} for p, u, _g in sorted(senders | {(pid, uid, gid)})[:16]]})
                raise PermissionError("request written by more than one process")
            # Read the sender's lane and start time, then confirm through the pidfd that the sender is still the same live process: a pid that was
            # reused between the send and this lookup would otherwise lend the request another process's lane.
            self._tls.req_cg = cgroup_of(pid)
            self._tls.req_start = proc_starttime(pid)
            if pidfd >= 0:
                try:
                    signal.pidfd_send_signal(pidfd, 0)
                except ProcessLookupError:
                    self._reject_unparsed("requester exited before its identity could be confirmed", pid, uid, buf)
                    raise PermissionError("requester exited before its identity could be confirmed") from None
                finally:
                    os.close(pidfd)
                    pidfd = -1
            elif REQUIRE_PIDFD:
                self._reject_unparsed("kernel did not provide a sender pidfd", pid, uid, buf)
                raise PermissionError("kernel did not provide a sender pidfd")
            try:
                req = json.loads(buf.decode("utf-8"))
            except (UnicodeDecodeError, ValueError, RecursionError) as exc:
                self._reject_unparsed("request could not be parsed as JSON", pid, uid, buf, error=type(exc).__name__)
                raise
            if not isinstance(req, dict):
                self._reject_unparsed("request is not a JSON object", pid, uid, buf)
                raise ValueError("request is not a JSON object")
            stage = "dispatch"
            reply = self._dispatch(req, pid, uid, fds)
        except Exception as exc:  # noqa: BLE001
            lane = getattr(self._tls, "lane", None)
            if lane is not None and "kill_on_failure" not in self.ablate:        # a process was started for this request but its ledger record may be missing: do not leave it running unrecorded
                self._kill_lane(lane)
            reply = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
            if not self._tls.refusal_recorded:     # a failure that no branch recorded (a malformed field, a receive error): the request still leaves a record
                try:
                    self._reject_unparsed("request failed: " + type(exc).__name__, pid, uid, buf, stage=stage)
                except Exception:  # noqa: BLE001
                    pass
        for fd in fds:                 # descriptors received with a request are closed whether the request was served or refused
            try:
                os.close(fd)
            except OSError:
                pass
        if pidfd >= 0:
            try:
                os.close(pidfd)
            except OSError:
                pass
        try:
            conn.sendall((json.dumps(reply, sort_keys=True) + "\n").encode("utf-8"))
        finally:
            conn.close()

    def _sender(self, pid: int, uid: int) -> dict[str, Any]:
        """The sender as the kernel names it (pid, uid) and the lane or cgroup it is in, for a refusal record."""
        requester = self._requester_lane(pid)
        lane = requester[0] if requester else (getattr(self._tls, "req_cg", None) or cgroup_of(pid))
        return {"pid": pid, "uid": uid, "lane": ascii_cap(lane, 200) if lane else None}

    def _reject(self, record: dict[str, Any]) -> None:
        """Append a `rejected` record, or only count the refusal once ``max_rejected`` records have been written in this run (a flood of refusals must not
        grow the ledger without bound).  The first suppressed refusal writes a `rejected_suppressed` marker; stop() writes the final count."""
        self._tls.refusal_recorded = True
        with self.lock:
            if self.rejected_written < self.max_rejected:
                self.rejected_written += 1
                first = None
            else:
                self.rejected_suppressed += 1
                reason = ascii_cap(record.get("reason"), 80)
                if reason not in self.suppressed_by_reason and len(self.suppressed_by_reason) >= 64:
                    reason = "other"
                self.suppressed_by_reason[reason] = self.suppressed_by_reason.get(reason, 0) + 1
                first = self.rejected_suppressed == 1
        if first is None:
            self.ledger.append(record)
        elif first:
            self.ledger.append({"op": "rejected_suppressed", "final": False, "limit": self.max_rejected})

    def _reject_unparsed(self, reason: str, pid: int, uid: int, buf: bytes, **extra: Any) -> None:
        """Refusal record for a request that was refused before dispatch: a fixed reason, the sender if the kernel named one, and only the size and hash
        of what was received (the request text itself is not kept)."""
        rec: dict[str, Any] = {"op": "rejected", "reason": reason, "stage": "parse", "request_bytes": len(buf), "request_sha256": hashlib.sha256(buf).hexdigest(), **extra}
        if pid >= 0:
            rec["requester"] = self._sender(pid, uid)
        self._reject(rec)

    def _dispatch(self, req: dict[str, Any], pid: int, uid: int, fds: list[int] | None = None) -> dict[str, Any]:
        self._tls.refusal_recorded = False
        reply = self._dispatch_op(req, pid, uid, fds)
        if not reply.get("ok") and not self._tls.refusal_recorded:
            # a refusal that no branch recorded itself (argv missing, bad pid, ...): no request ends without a record
            self._reject({"op": "rejected", "reason": ascii_cap(reply.get("error"), 80), "stage": "dispatch", "request_op": ascii_cap(req.get("op")),
                          "requester": self._sender(pid, uid)})
        return reply

    def _dispatch_op(self, req: dict[str, Any], pid: int, uid: int, fds: list[int] | None = None) -> dict[str, Any]:
        op = req.get("op")
        if op == "wait":
            try:
                wpid = int(req["pid"])
            except (KeyError, TypeError, ValueError, OverflowError):
                return {"ok": False, "error": "bad pid"}
            proc = self.procs.get(wpid)
            if proc is None:
                return {"ok": False, "error": "unknown pid"}
            owner = self.proc_owner.get(wpid)
            requester = self._requester_lane(pid)
            # Only the lane that started a process may wait for it.  The agent root belongs to the operator (OPERATOR, which is no lane path), so no
            # requester, inside or outside the run's lanes, can wait for it over the protocol; the operator waits on the Popen handle launch_root returns.
            if "wait_owner" not in self.ablate and (requester is None or requester[0] != owner):
                self._reject({"op": "rejected", "reason": "wait from a lane other than the requester's", "request_op": "wait", "child_pid": wpid,
                              **({"owner": "operator"} if owner == OPERATOR else {}),
                              "requester": self._sender(pid, uid)})
                return {"ok": False, "error": "only the requesting lane may wait for this process"}
            rc = proc.wait()
            with self.lock:
                first = wpid not in self.exited
                self.exited[wpid] = rc
            if first:  # one exit record per process, however often it is waited for
                self.ledger.append({"op": "exit", "child_pid": proc.pid, "returncode": rc})
            return {"ok": True, "returncode": rc}
        requester = self._requester_lane(pid)
        if requester is None:
            self._reject({"op": "rejected", "reason": "requester not in a lane of this run", "requester": self._sender(pid, uid), "request_op": ascii_cap(op)})
            return {"ok": False, "error": "requester is not inside a lane of this run"}
        req_rel, req_fs = requester
        # ctx is copied into a `spawn_failed` record: it names the requester and the operation, and each branch below adds the id it validated (never the claimed one)
        self._tls.ctx = {"requester": {"pid": pid, "uid": uid, "lane": req_rel}, "request_op": op}
        if op == "grant":
            call_lane = self._call_lane_of(req_rel)
            if call_lane is None:
                self._reject({"op": "rejected", "reason": "grant requester is not inside a call lane", "requester": {"pid": pid, "uid": uid, "lane": req_rel}})
                return {"ok": False, "error": "grant requires a requester inside a call lane"}
            token = secrets.token_hex(16)
            if req.get("for_pid") is None and "grant_for_pid" not in self.ablate:       # an unbound token can be redeemed by any process of the run and then charges the granting call: not offered
                self._reject({"op": "rejected", "reason": "grant without for_pid", "requester": {"pid": pid, "uid": uid, "lane": req_rel}})
                return {"ok": False, "error": "for_pid is required"}
            for_pid = int(req["for_pid"]) if req.get("for_pid") is not None else None
            if for_pid is not None and for_pid <= 0:
                if "for_pid_positive" not in self.ablate:
                    return {"ok": False, "error": "for_pid must be a positive pid"}
                for_pid = None                   # earlier behaviour: 0 meant "not bound"
            for_start = proc_starttime(for_pid) if for_pid is not None else None
            if for_pid is not None and for_start is None:
                return {"ok": False, "error": "for_pid is not a live process"}
            with self.lock:
                self.grants[token] = {"call_id": call_lane["call_id"], "lane": call_lane["lane"], "lane_fs": call_lane["lane_fs"], "ts": time.monotonic(), "used": False,
                                      "for_pid": for_pid, "for_start": for_start}
            self.ledger.append({"op": "grant", "requester": {"pid": pid, "uid": uid, "lane": req_rel}, "call_id": call_lane["call_id"], "lane": call_lane["lane"],
                                "for_pid": for_pid, "for_starttime": for_start,
                                "token_sha256": hashlib.sha256(token.encode()).hexdigest()})
            return {"ok": True, "token": token}
        # the requester's *agent* lane is the nearest ancestor lane of kind agent (its own lane if it is an agent process)
        agent_lane = self._agent_lane_of(req_rel)
        argv = [str(a) for a in req.get("argv") or []]
        if not argv:
            return {"ok": False, "error": "argv required"}
        if "unencodable_precheck" not in self.ablate and self._unencodable(req):
            self._reject({"op": "rejected", "reason": "request contains text that cannot be recorded", "request_op": ascii_cap(op), "requester": {"pid": pid, "uid": uid, "lane": req_rel}})
            return {"ok": False, "error": "request contains text that cannot be recorded"}
        env = self._sanitize_env(req.get("env"))
        cwd = req.get("cwd") or "/"
        with self.lock:
            self.counter += 1
            n = self.counter
        enclosing_any = self._call_lane_of(req_rel)
        enclosing = None if "nest_call_ns" in self.ablate else enclosing_any
        if op == "launch":
            claimed = str(req.get("call_id") or f"call:{n}")
            call_id = f"{enclosing['call_id']}~{claimed}" if enclosing else claimed
            with self.lock:
                bad = (("call_id_syntax" not in self.ablate and not CALL_ID_RE.fullmatch(claimed))
                       or ("call_id_unique" not in self.ablate and call_id in self.call_ids))
                if not bad:
                    self.call_ids.add(call_id)
            if bad:
                self._reject({"op": "rejected", "reason": "invalid or duplicate call id", "call_id": ascii_cap(call_id, 200),
                              "requester": {"pid": pid, "uid": uid, "lane": req_rel}})
                return {"ok": False, "error": "invalid or duplicate call id"}
            # a failed spawn is recorded with the same (qualified) id the launch record would have carried, not with the id the request claimed
            self._tls.ctx.update(call_id=call_id, **({"nested_in": enclosing["call_id"], "claimed_call_id": claimed} if enclosing else {}))
            lane = self._new_lane(req_fs, f"c-{n}", "call", call_id=call_id, agent=agent_lane["agent"] if agent_lane else None,
                                  declared=req.get("declared"), argv=argv, nested_in=enclosing["call_id"] if enclosing else None)
            stdio = tuple(fds[:3]) if fds and len(fds) >= 3 else None
            self._intent("launch", lane, req_rel, pid, uid, argv, call_id)
            proc = self._spawn(lane, argv, cwd, env, stdio=stdio, isolate=True)  # type: ignore[arg-type]
            entry = self.ledger.append({"op": "launch", "requester": {"pid": pid, "uid": uid, "lane": req_rel, "agent": agent_lane["agent"] if agent_lane else None},
                                        "call_id": call_id, "declared": req.get("declared"), "argv": argv,
                                        **({"nested_in": enclosing["call_id"], "claimed_call_id": claimed} if enclosing else {}),
                                        "argv_sha256": hashlib.sha256("\0".join(argv).encode()).hexdigest(),
                                        "lane": lane["lane"], "lane_inode": lane["lane_inode"], "child_pid": proc.pid,
                                        "child_starttime": proc_starttime(proc.pid), **({"isolation": lane["isolation"]} if lane.get("isolation") else {})})
            return {"ok": True, "pid": proc.pid, "lane": lane["lane"], "lane_inode": lane["lane_inode"], "seq": entry["record"]["seq"]}
        if op == "launch_delegated":
            token = str(req.get("token") or "")
            with self.lock:
                g = self.grants.get(token)
                ok = g is not None and not g["used"] and time.monotonic() - g["ts"] < self.GRANT_TTL_S
                if ok and g["for_pid"] is not None:  # redeemer binding: only the process named at grant time (same pid and start time) may redeem
                    ok = pid == g["for_pid"] and (getattr(self._tls, "req_start", None) or proc_starttime(pid)) == g["for_start"]
                if ok:
                    g["used"] = True
            if not ok:
                self._reject({"op": "rejected", "reason": "invalid, used, expired or wrongly redeemed delegation token", "requester": {"pid": pid, "uid": uid, "lane": req_rel},
                              "token_sha256": hashlib.sha256(token.encode("utf-8", "surrogatepass")).hexdigest()})
                return {"ok": False, "error": "invalid, used, expired or wrongly redeemed delegation token"}
            self._tls.ctx["call_id"] = g["call_id"]      # the granting call, as in the launch_delegated record's on_behalf_of
            lane = self._new_lane(Path(g["lane_fs"]), f"d-{n}", "delegated", call_id=g["call_id"], agent=agent_lane["agent"] if agent_lane else None, argv=argv)
            stdio = tuple(fds[:3]) if fds and len(fds) >= 3 else None
            self._intent("launch_delegated", lane, req_rel, pid, uid, argv, g["call_id"])
            proc = self._spawn(lane, argv, cwd, env, stdio=stdio, isolate=True, uid_from=g["lane_fs"])  # type: ignore[arg-type]
            entry = self.ledger.append({"op": "launch_delegated", "requester": {"pid": pid, "uid": uid, "lane": req_rel, "agent": agent_lane["agent"] if agent_lane else None},
                                        "on_behalf_of": {"call_id": g["call_id"], "lane": g["lane"]}, "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
                                        "argv": argv, "argv_sha256": hashlib.sha256("\0".join(argv).encode()).hexdigest(),
                                        "lane": lane["lane"], "lane_inode": lane["lane_inode"], "child_pid": proc.pid, "child_starttime": proc_starttime(proc.pid),
                                        **({"isolation": lane["isolation"]} if lane.get("isolation") else {})})
            return {"ok": True, "pid": proc.pid, "lane": lane["lane"], "lane_inode": lane["lane_inode"], "seq": entry["record"]["seq"]}
        if op == "spawn_agent":
            name = str(req.get("agent") or f"agent{n}")
            if "agent_name_syntax" not in self.ablate and not AGENT_NAME_RE.fullmatch(name):
                self._reject({"op": "rejected", "reason": "invalid agent name", "agent": ascii_cap(name, 64),
                              "requester": {"pid": pid, "uid": uid, "lane": req_rel}})
                return {"ok": False, "error": "invalid agent name"}
            enclosing_a = None if "nest_agent_ns" in self.ablate else enclosing_any
            agent_id = f"agent:{name}@{enclosing_a['call_id']}" if enclosing_a else f"agent:{name}"
            with self.lock:
                dup = "agent_id_unique" not in self.ablate and agent_id in self.agent_ids
                self.agent_ids.add(agent_id)
            if dup:
                self._reject({"op": "rejected", "reason": "duplicate agent id", "agent": ascii_cap(agent_id, 200), "requester": {"pid": pid, "uid": uid, "lane": req_rel}})
                return {"ok": False, "error": "duplicate agent id"}
            self._tls.ctx["agent"] = agent_id
            lane = self._new_lane(req_fs, f"a-{name}", "agent", agent=agent_id, parent_agent=agent_lane["agent"] if agent_lane else None)
            self._intent("spawn_agent", lane, req_rel, pid, uid, argv, None, agent=agent_id)
            proc = self._spawn(lane, argv, cwd, env)
            entry = self.ledger.append({"op": "spawn_agent", "requester": {"pid": pid, "uid": uid, "lane": req_rel, "agent": agent_lane["agent"] if agent_lane else None},
                                        "agent": agent_id, "argv": argv, "lane": lane["lane"], "lane_inode": lane["lane_inode"],
                                        "child_pid": proc.pid, "child_starttime": proc_starttime(proc.pid)})
            return {"ok": True, "pid": proc.pid, "lane": lane["lane"], "lane_inode": lane["lane_inode"], "seq": entry["record"]["seq"]}
        self._reject({"op": "rejected", "reason": "unknown op", "request_op": ascii_cap(op), "requester": {"pid": pid, "uid": uid, "lane": req_rel}})
        return {"ok": False, "error": f"unknown op {op!r}"}

    GRANT_TTL_S = 120.0

    def _intent(self, op: str, lane: dict[str, Any], req_rel: str, pid: int, uid: int, argv: list[str], call_id: str | None, **extra: Any) -> None:
        """Record-before-effect: the lane and what will run in it are in the signed ledger before the child exists, so a crash of the launcher between
        spawn and the launch record cannot leave a running process whose lane the ledger does not name."""
        if "intent_record" in self.ablate:
            return
        self.ledger.append({"op": "intent", "for_op": op, "lane": lane["lane"], "lane_inode": lane["lane_inode"], "call_id": call_id,
                            "requester": {"pid": pid, "uid": uid, "lane": req_rel}, "argv_sha256": hashlib.sha256("\0".join(argv).encode()).hexdigest(), **extra})

    @staticmethod
    def _unencodable(req: dict[str, Any]) -> bool:
        """True if a request carries text that cannot be written to the ledger (for example a lone surrogate).  Checked before anything is spawned, so that
        a started process always has its ledger record."""
        try:
            json.dumps({k: req.get(k) for k in ("call_id", "declared", "argv", "cwd", "env", "agent")}, sort_keys=True, ensure_ascii=False, allow_nan=False).encode("utf-8")
        except (UnicodeEncodeError, TypeError, ValueError):
            return True
        return False

    def _kill_lane(self, lane: dict[str, Any]) -> None:
        """Terminate every process of a lane (used when the ledger append that must follow a spawn fails)."""
        lane_fs = lane["lane_fs"]
        try:
            with open(os.path.join(lane_fs, "cgroup.kill"), "w") as fh:
                fh.write("1")
        except OSError:
            try:
                for line in open(os.path.join(lane_fs, "cgroup.procs")).read().split():
                    os.kill(int(line), 9)
            except OSError:
                pass

    def _call_lane_of(self, rel: str) -> dict[str, Any] | None:
        best = None
        for info in self.lanes.values():
            if info["kind"] == "call" and (rel == info["lane"] or rel.startswith(info["lane"] + "/")):
                if best is None or len(info["lane"]) > len(best["lane"]):
                    best = info
        return best

    def _agent_lane_of(self, rel: str) -> dict[str, Any] | None:
        best = None
        for info in self.lanes.values():
            if info["kind"] == "agent" and (rel == info["lane"] or rel.startswith(info["lane"] + "/")):
                if best is None or len(info["lane"]) > len(best["lane"]):
                    best = info
        return best

    # ---- lifecycle --------------------------------------------------------
    def start(self) -> None:
        if self.sock_path.exists():
            self.sock_path.unlink()
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_PASSCRED, 1)  # accepted connections inherit it: every message carries the *sender's* credentials
        srv.bind(str(self.sock_path))
        os.chmod(self.sock_path, 0o666)
        srv.listen(64)
        srv.settimeout(0.2)  # lets the accept loop observe the stop flag (closing a socket does not wake accept())
        self._srv = srv
        self._stop = threading.Event()

        def loop() -> None:
            while not self._stop.is_set():
                try:
                    conn, _ = srv.accept()
                except socket.timeout:
                    continue
                except OSError:
                    return
                conn.settimeout(None)
                t = threading.Thread(target=self._handle, args=(conn,), daemon=True)
                t.start()
                with self.lock:
                    self._threads = [x for x in self._threads if x.is_alive()]
                    self._threads.append(t)

        self._accept_thread = threading.Thread(target=loop, daemon=True)
        self._accept_thread.start()

    def stop(self) -> None:
        # Lifecycle fix (2026-10-27): before, stop() only closed the listening socket; the accept thread stayed
        # blocked forever, and repeated services in one process accumulated threads and virtual memory, which
        # made every later fork (and therefore every launch) slower.  See EXPERIMENTAL_EVIDENCE.md, launcher defect.
        if getattr(self, "_stop", None) is not None:
            self._stop.set()
        if getattr(self, "_accept_thread", None) is not None:
            self._accept_thread.join(timeout=5)
        if self._srv is not None:
            self._srv.close()
        for t in list(self._threads):
            t.join(timeout=5)
        with self.lock:
            suppressed, by_reason = self.rejected_suppressed, dict(self.suppressed_by_reason)
        if suppressed:   # refusals beyond the per-run cap were counted, not recorded one by one
            self.ledger.append({"op": "rejected_suppressed", "final": True, "limit": self.max_rejected, "count": suppressed, "by_reason": by_reason})
        self.ledger.append({"op": "service_stop"})
        self.child_log.close()
        try:
            self.sock_path.unlink()
        except OSError:
            pass

    def cleanup_lanes(self) -> None:
        for root, dirs, _files in os.walk(self.root_fs, topdown=False):
            for d in dirs:
                try:
                    os.rmdir(os.path.join(root, d))
                except OSError:
                    pass
        try:
            os.rmdir(self.root_fs)
        except OSError:
            pass

    def lanes_snapshot(self) -> dict[str, Any]:
        return {str(k): v for k, v in self.lanes.items()}
