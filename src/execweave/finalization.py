"""Durable export status, including the content referenced by exported indexes."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .content_integrity import ArchiveReadError, audit_content_references, hash_export


REQUIRED_EXPORTS = ("graph.json", "viewer.html", "conversations.json")


def record_finalization(
    run_dir: Path, *, state: str, error: BaseException | None = None,
) -> dict[str, Any]:
    run_dir = Path(run_dir).absolute()
    files: dict[str, Any] = {}
    artifact_errors: dict[str, str] = {}
    for name in REQUIRED_EXPORTS:
        try:
            files[name] = hash_export(run_dir, name)
        except ArchiveReadError as exc:
            artifact_errors[name] = str(exc)
    missing = [name for name in REQUIRED_EXPORTS if not files.get(name, {}).get("size_bytes")]
    integrity: dict[str, Any] = {"state": "not_checked", "reason": "export_not_terminal"}
    if state != "recording":
        integrity = audit_content_references(run_dir)
        # An index must be the same version as the primary export we hashed. This
        # does not claim that a writable archive cannot change after verification.
        for name, fingerprint in integrity["index_files"].items():
            if fingerprint != files.get(name):
                artifact_errors[name] = "changed_during_finalization"
    complete = not missing and not artifact_errors and integrity["state"] == "complete"
    payload = {
        "schema_version": "0.2", "state": state, "artifacts": files,
        "missing": missing, "error_type": type(error).__name__ if error else None,
        "artifact_errors": artifact_errors, "content_integrity": integrity,
    }
    if state == "complete" and not complete:
        payload["state"] = "incomplete"
    fd, temporary = tempfile.mkstemp(prefix=".finalization-", dir=run_dir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, run_dir / "finalization.json")
    finally:
        Path(temporary).unlink(missing_ok=True)
    if state == "complete" and not complete and error is None:
        detail = ", ".join(missing) if missing else "declared content or export verification failed"
        raise RuntimeError("Final export is incomplete: " + detail)
    # A collector failure stays primary, even when the archive is incomplete.
    return payload
