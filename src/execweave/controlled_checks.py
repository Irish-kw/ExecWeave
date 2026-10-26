"""Execute fixed acceptance predicates on captured bytes and sign the result.

Only explicit CLI selections authorize reads. No artifact code, report command,
plugin, regular expression or external URL is executed. Trust in a signature
requires an independently selected verifier profile and its approved policy hash.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .task_artifacts import (
    FORMAT as ARTIFACT_FORMAT,
    MAX_FILE_BYTES,
    MAX_TOTAL_BYTES,
    _read_selected,
    artifact_name,
    manifest_bytes,
    validate_manifest,
)
from .task_validation import _pairs, _read, _text, task_subject

POLICY_FORMAT = "execweave.fixed-check-policy.v1"
PROFILE_FORMAT = "execweave.verifier-profile.v1"
RECEIPT_FORMAT = "execweave.controlled-checks.v1"
PAYLOAD_FORMAT = "execweave.fixed-check-execution.v1"
DOMAIN = b"ExecWeave fixed checks v1\x00"
MAX_POLICY = 128 * 1024
MAX_RECEIPT = 2 * 1024 * 1024
MAX_CHECKS = 100
HEX = re.compile(r"[0-9a-f]{64}\Z")
IDENTIFIER = re.compile(r"[A-Za-z0-9_.-]{1,96}\Z")
LIMITATION = (
    "Only approved fixed predicates on the listed captured byte buffers were evaluated. "
    "No program behavior, complete task correctness, whole directory, dependencies, "
    "atomic filesystem snapshot or hardware attestation is certified. Trust requires "
    "the verifier host and separately pinned signing key to remain under trusted control."
)


def _bad_constant(_value):
    raise ValueError("nonfinite JSON is not supported")


def strict_json(value: str | bytes, limit: int = MAX_RECEIPT, *, safe_numbers: bool = True) -> Any:
    raw = value.encode("utf-8") if isinstance(value, str) else value
    if not isinstance(raw, bytes) or len(raw) > limit:
        raise ValueError("JSON exceeds its byte limit")
    result = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_bad_constant)

    # Bound recursion and numeric semantics identically to browser JSON.
    def check(v, depth=0):
        if depth > 32:
            raise ValueError("JSON nesting exceeds 32")
        if safe_numbers and (isinstance(v, float) or (type(v) is int and abs(v) > 2**53 - 1)):
            raise ValueError("only safe JSON integers are supported")
        if isinstance(v, str):
            v.encode("utf-8")  # Refuse unpaired surrogates.
        elif isinstance(v, list):
            for item in v:
                check(item, depth + 1)
        elif isinstance(v, dict):
            for k, item in v.items():
                check(k, depth + 1)
                check(item, depth + 1)

    check(result)
    return result


def _fields(value: Any, names: set[str], what: str) -> dict:
    if not isinstance(value, dict) or set(value) != names:
        raise ValueError(f"invalid {what} fields")
    return value


def encoded(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _hex(value: Any) -> bool:
    return isinstance(value, str) and HEX.fullmatch(value) is not None


def _pointer(value: Any) -> list[str]:
    if not isinstance(value, str) or len(value) > 2048 or (value and not value.startswith("/")):
        raise ValueError("invalid JSON pointer")
    if re.search(r"~(?![01])", value):
        raise ValueError("invalid JSON pointer escape")
    parts = [] if not value else value[1:].split("/")
    if len(parts) > 32:
        raise ValueError("JSON pointer exceeds 32 steps")
    return [p.replace("~1", "/").replace("~0", "~") for p in parts]


def policy_document(raw: str | bytes) -> dict:
    policy = strict_json(raw, MAX_POLICY)
    _fields(policy, {"format", "name", "checks"}, "policy")
    if policy["format"] != POLICY_FORMAT:
        raise ValueError("unsupported fixed-check policy")
    _text(policy["name"], "policy name", 256)
    rows = policy["checks"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_CHECKS:
        raise ValueError("policy requires 1 to 100 checks; empty checks cannot pass")
    seen, paths = set(), {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("invalid check")
        op = row.get("op")
        expected_fields = {"id", "path", "op", "expected"}
        if op == "json_pointer_equals":
            expected_fields.add("pointer")
        _fields(row, expected_fields, "check")
        if (
            not isinstance(row["id"], str)
            or not IDENTIFIER.fullmatch(row["id"])
            or row["id"] in seen
        ):
            raise ValueError("check IDs must be unique portable identifiers")
        seen.add(row["id"])
        name = artifact_name(row["path"])
        if name.lower() in paths and paths[name.lower()] != name:
            raise ValueError("case-colliding policy paths")
        paths[name.lower()] = name
        expected = row["expected"]
        if op == "sha256_equals":
            if not _hex(expected):
                raise ValueError("invalid expected SHA-256")
        elif op == "utf8_contains":
            _text(expected, "expected text", 65536)
        elif op == "json_pointer_equals":
            _pointer(row["pointer"])
            if expected is not None and type(expected) not in (str, int, bool):
                raise ValueError("JSON comparison requires a scalar expected value")
            if isinstance(expected, str) and len(expected) > 65536:
                raise ValueError("expected scalar exceeds limit")
        else:
            raise ValueError("unsupported check operation; executable tests are not accepted")
    return policy


def _binding(graph: dict, task_id: str) -> tuple[dict, dict, str]:
    from .run_assessment import build_run_assessment

    assessment = build_run_assessment(graph)
    if assessment["inspection"]["state"] != "declared_graph":
        raise ValueError("complete unambiguous raw graph metadata is required")
    session = _text(graph.get("session_id"), "session ID")
    subjects = assessment["task_validation"]["external_report_subjects"]
    nodes = [n for n in graph.get("nodes", []) if isinstance(n, dict) and n.get("id") == task_id]
    if len(nodes) != 1 or sum(s["task_id"] == task_id for s in subjects) != 1:
        raise ValueError("exact native task is missing, ambiguous or outside the budget")
    subject = task_subject(nodes[0])
    scope = {"session_id": session}
    for name in ("run_id", "source_path"):
        value = graph.get(name)
        if value is not None:
            _text(value, name)
        scope[name] = value
    return scope, subject, encoded(nodes[0]).decode("utf-8")


def _crypto():
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PrivateKey,
            Ed25519PublicKey,
        )
        from cryptography.hazmat.primitives import serialization
    except ImportError as exc:
        raise ValueError("signing requires the optional execweave[validation] extra") from exc
    return Ed25519PrivateKey, Ed25519PublicKey, serialization


def _b64(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _unb64(value: Any, size: int) -> bytes:
    if not isinstance(value, str) or len(value) != 4 * ((size + 2) // 3):
        raise ValueError("invalid encoded key or signature")
    raw = base64.b64decode(value, validate=True)
    if len(raw) != size or _b64(raw) != value:
        raise ValueError("noncanonical encoded key or signature")
    return raw


def make_profile(public: bytes, policy_raw: bytes, label: str) -> dict:
    policy_document(policy_raw)
    if len(public) != 32:
        raise ValueError("an Ed25519 public key is required")
    return {
        "format": PROFILE_FORMAT,
        "label": _text(label, "verifier label", 256),
        "key_id": digest(public),
        "public_key_b64": _b64(public),
        "policy_sha256": digest(policy_raw),
    }


def validate_profile(profile: Any) -> bytes:
    _fields(profile, {"format", "label", "key_id", "public_key_b64", "policy_sha256"}, "profile")
    public = _unb64(profile["public_key_b64"], 32)
    if (
        profile["format"] != PROFILE_FORMAT
        or profile["key_id"] != digest(public)
        or not _hex(profile["policy_sha256"])
    ):
        raise ValueError("invalid pinned verifier profile")
    _text(profile["label"], "verifier label", 256)
    return public


def _predicate(row: dict, raw: bytes) -> tuple[str, str]:
    if row["op"] == "sha256_equals":
        equal = digest(raw) == row["expected"]
    else:
        try:
            text = raw.decode("utf-8")
        except UnicodeError:
            return "error", "invalid_utf8"
        if row["op"] == "utf8_contains":
            equal = row["expected"] in text
        else:
            try:
                value = strict_json(raw, MAX_FILE_BYTES)
            except (ValueError, RecursionError, UnicodeError):
                return "error", "invalid_json"
            try:
                for part in _pointer(row["pointer"]):
                    if isinstance(value, list) and re.fullmatch(r"0|[1-9][0-9]*", part):
                        value = value[int(part)]
                    elif isinstance(value, dict):
                        value = value[part]
                    else:
                        raise KeyError(part)
            except (KeyError, IndexError, ValueError):
                return "failed", "pointer_missing"
            equal = type(value) is type(row["expected"]) and value == row["expected"]
    return ("passed", "predicate_true") if equal else ("failed", "predicate_false")


def execute_checks(
    graph: dict, task_id: str, policy_raw: bytes, selections: list[str], key
) -> dict:
    """Evaluate only in-memory immutable bytes, then sign their hashes and outcomes."""
    policy = policy_document(policy_raw)
    scope, subject, task_json = _binding(graph, task_id)
    expected = {r["path"] for r in policy["checks"]}
    if not 1 <= len(selections) <= 100:
        raise ValueError("select 1 to 100 files explicitly")
    paths = {}
    for spec in selections:
        if not isinstance(spec, str) or "=" not in spec:
            raise ValueError("use RELATIVE_NAME=LOCAL_FILE selections")
        name, path = spec.split("=", 1)
        artifact_name(name)
        if not path or name in paths:
            raise ValueError("duplicate or empty file selection")
        paths[name] = path
    if set(paths) != expected:
        raise ValueError("explicit file selections must exactly match the approved policy paths")
    buffers, total = {}, 0
    for name, path in paths.items():
        raw = _read_selected(path)
        total += len(raw)
        if total > MAX_TOTAL_BYTES:
            raise ValueError("selected input bytes exceed 64 MiB")
        buffers[name] = raw
    # Hashes, checks and manifest derive from these same byte objects. There is
    # no subprocess, artifact import, shell, plugin, later reread or test report.
    entries = [
        {"path": name, "size_bytes": len(raw), "sha256": digest(raw)}
        for name, raw in sorted(buffers.items(), key=lambda item: item[0].encode("utf-8"))
    ]
    artifacts = {
        "format": ARTIFACT_FORMAT,
        "entries": entries,
        "manifest_sha256": digest(manifest_bytes(entries)),
    }
    results = []
    for row in policy["checks"]:
        outcome, reason = _predicate(row, buffers[row["path"]])
        results.append(
            {
                "id": row["id"],
                "path": row["path"],
                "op": row["op"],
                "artifact_sha256": digest(buffers[row["path"]]),
                "outcome": outcome,
                "reason": reason,
            }
        )
    payload = {
        "format": PAYLOAD_FORMAT,
        "scope": scope,
        "subject": subject,
        "task_snapshot_json": task_json,
        "policy_json": policy_raw.decode("utf-8"),
        "policy_sha256": digest(policy_raw),
        "artifacts": artifacts,
        "results": results,
        "execution_id": uuid.uuid4().hex,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "task_success_implied": False,
        "limitation": LIMITATION,
    }
    encoded_payload = encoded(payload)
    if len(encoded_payload) > MAX_RECEIPT // 2:
        raise ValueError("signed payload exceeds its limit")
    private_class, _, serialization = _crypto()
    if not isinstance(key, private_class):
        raise ValueError("Ed25519 signer required")
    public = key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    return {
        "format": RECEIPT_FORMAT,
        "key_id": digest(public),
        "payload": encoded_payload.decode("utf-8"),
        "signature_b64": _b64(key.sign(DOMAIN + encoded_payload)),
    }


def inspect_payload(payload: Any, profile: dict) -> dict:
    """Validate coverage and derive results; never trust a supplied summary."""
    _fields(
        payload,
        {
            "format",
            "scope",
            "subject",
            "task_snapshot_json",
            "policy_json",
            "policy_sha256",
            "artifacts",
            "results",
            "execution_id",
            "recorded_at",
            "task_success_implied",
            "limitation",
        },
        "signed payload",
    )
    if (
        payload["format"] != PAYLOAD_FORMAT
        or payload["task_success_implied"] is not False
        or payload["limitation"] != LIMITATION
    ):
        raise ValueError("unsupported execution semantics")
    _fields(payload["scope"], {"session_id", "run_id", "source_path"}, "scope")
    _text(payload["scope"]["session_id"], "session ID")
    for field in ("run_id", "source_path"):
        if payload["scope"][field] is not None:
            _text(payload["scope"][field], field)
    _fields(payload["subject"], {"task_id", "task_snapshot_sha256"}, "subject")
    task_raw = payload["task_snapshot_json"]
    node = strict_json(task_raw, 1024 * 1024, safe_numbers=False)
    if (
        task_subject(node) != payload["subject"]
        or digest(task_raw.encode("utf-8")) != payload["subject"]["task_snapshot_sha256"]
    ):
        raise ValueError("signed task snapshot mismatch")
    raw = payload["policy_json"].encode("utf-8")
    policy = policy_document(raw)
    if digest(raw) != payload["policy_sha256"] or digest(raw) != profile["policy_sha256"]:
        raise ValueError("policy was not independently approved by this profile")
    _text(payload["recorded_at"], "recorded time", 64)
    if not isinstance(payload["execution_id"], str) or not re.fullmatch(
        "[0-9a-f]{32}", payload["execution_id"]
    ):
        raise ValueError("invalid execution identity")
    _fields(payload["artifacts"], {"format", "entries", "manifest_sha256"}, "artifact manifest")
    manifest = validate_manifest(payload["artifacts"])
    for entry in payload["artifacts"]["entries"]:
        _fields(entry, {"path", "size_bytes", "sha256"}, "artifact entry")
    by_path = {item["path"]: item for item in manifest["entries"]}
    if set(by_path) != {row["path"] for row in policy["checks"]}:
        raise ValueError("signed artifacts do not cover exactly the approved policy")
    results = payload["results"]
    if not isinstance(results, list) or len(results) != len(policy["checks"]):
        raise ValueError("missing or additional executed checks")
    counts = {"passed": 0, "failed": 0, "error": 0}
    reasons = {
        "passed": {"predicate_true"},
        "failed": {"predicate_false", "pointer_missing"},
        "error": {"invalid_utf8", "invalid_json"},
    }
    for planned, result in zip(policy["checks"], results):
        _fields(result, {"id", "path", "op", "artifact_sha256", "outcome", "reason"}, "result")
        if (
            any(result[k] != planned[k] for k in ("id", "path", "op"))
            or result["artifact_sha256"] != by_path[planned["path"]]["sha256"]
        ):
            raise ValueError("executed check identity or byte binding mismatch")
        outcome = result["outcome"]
        if (
            not isinstance(outcome, str)
            or outcome not in counts
            or result["reason"] not in reasons[outcome]
        ):
            raise ValueError("invalid executed check outcome")
        counts[outcome] += 1
    return {
        "state": "checks_passed" if counts["passed"] == len(results) else "checks_failed",
        "counts": counts,
        "policy_name": policy["name"],
        "payload": payload,
        "whole_task_verified": False,
    }


def verify_receipt(envelope: Any, profile: dict, graph: dict, task_id: str) -> dict:
    public = validate_profile(profile)
    _fields(envelope, {"format", "key_id", "payload", "signature_b64"}, "receipt")
    if envelope["format"] != RECEIPT_FORMAT or envelope["key_id"] != profile["key_id"]:
        raise ValueError("receipt does not match the independently pinned key")
    raw = envelope["payload"].encode("utf-8")
    if len(raw) > MAX_RECEIPT // 2:
        raise ValueError("signed payload exceeds limit")
    _, public_class, _ = _crypto()
    from cryptography.exceptions import InvalidSignature

    try:
        public_class.from_public_bytes(public).verify(
            _unb64(envelope["signature_b64"], 64), DOMAIN + raw
        )
    except InvalidSignature as exc:
        raise ValueError("signature verification failed") from exc
    payload = strict_json(raw)
    result = inspect_payload(payload, profile)
    scope, subject, _ = _binding(graph, task_id)
    if payload["scope"] != scope or payload["subject"] != subject:
        raise ValueError("signed result belongs to a different execution or task snapshot")
    result["signature_verified"] = True
    return result


def _write_new(path: str, raw: bytes, mode: int = 0o600) -> None:
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0), mode)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Execute fixed byte predicates, sign results, or verify using an independently pinned profile. Never executes supplied code."
    )
    sub = parser.add_subparsers(dest="action", required=True)
    keygen = sub.add_parser(
        "keygen",
        help="Create a private signing key and a policy-pinned public profile; protect the private file.",
    )
    for name in ("private-key", "profile", "policy", "label"):
        keygen.add_argument("--" + name, required=True)
    run = sub.add_parser("run")
    for name in ("graph", "task-id", "policy", "private-key", "output"):
        run.add_argument("--" + name, required=True)
    run.add_argument("--artifact", action="append", required=True, metavar="NAME=FILE")
    verify = sub.add_parser("verify")
    for name in ("graph", "task-id", "receipt", "profile"):
        verify.add_argument("--" + name, required=True)
    args = parser.parse_args(argv)
    try:
        private_class, _, serialization = _crypto()
        if args.action == "keygen":
            policy_raw = _read(args.policy, MAX_POLICY)
            policy_document(policy_raw)
            if (
                Path(args.private_key).exists()
                or Path(args.profile).exists()
                or Path(args.private_key).resolve() == Path(args.profile).resolve()
            ):
                raise ValueError("key/profile outputs must be different new files")
            key = private_class.generate()
            public = key.public_key().public_bytes(
                serialization.Encoding.Raw, serialization.PublicFormat.Raw
            )
            profile = make_profile(public, policy_raw, args.label)
            pem = key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
            _write_new(args.private_key, pem)
            _write_new(args.profile, encoded(profile) + b"\n")
            print(
                json.dumps(
                    {
                        "key_id": profile["key_id"],
                        "policy_sha256": profile["policy_sha256"],
                        "note": "Trust the public profile through a separate approved channel; protect the private key.",
                    }
                )
            )
            return 0
        graph = strict_json(
            _read(args.graph, 64 * 1024 * 1024), 64 * 1024 * 1024, safe_numbers=False
        )
        if args.action == "verify":
            profile = strict_json(_read(args.profile, MAX_POLICY), MAX_POLICY)
            result = verify_receipt(
                strict_json(_read(args.receipt, MAX_RECEIPT)), profile, graph, args.task_id
            )
        else:
            if os.name == "posix" and os.lstat(args.private_key).st_mode & 0o077:
                raise ValueError("private key permissions must exclude group and other users")
            policy_raw = _read(args.policy, MAX_POLICY)
            key = serialization.load_pem_private_key(_read(args.private_key, 4096), password=None)
            for spec in args.artifact:
                if "=" in spec and os.path.samefile(spec.split("=", 1)[1], args.private_key):
                    raise ValueError("private key cannot be an artifact input")
            envelope = execute_checks(graph, args.task_id, policy_raw, args.artifact, key)
            public = key.public_key().public_bytes(
                serialization.Encoding.Raw, serialization.PublicFormat.Raw
            )
            profile = make_profile(public, policy_raw, "local signer")
            result = verify_receipt(envelope, profile, graph, args.task_id)
            _write_new(args.output, encoded(envelope) + b"\n")
        print(
            json.dumps(
                {
                    k: result[k]
                    for k in ("state", "counts", "signature_verified", "whole_task_verified")
                }
            )
        )
        return 0 if result["state"] == "checks_passed" else 1
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        UnicodeError,
        RecursionError,
    ) as exc:
        print(f"Controlled checks not accepted: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
