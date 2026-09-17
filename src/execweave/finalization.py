"""Durable export status: session.finished is not proof that files were exported."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


REQUIRED_EXPORTS = ("graph.json", "viewer.html", "conversations.json")


def record_finalization(
    run_dir: Path, *, state: str, error: BaseException | None = None,
) -> dict[str, Any]:
    files: dict[str, Any] = {}
    for name in REQUIRED_EXPORTS:
        path = run_dir / name
        if path.is_file():
            digest = hashlib.sha256()
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            files[name] = {"size_bytes": path.stat().st_size, "sha256": digest.hexdigest()}
    missing = [name for name in REQUIRED_EXPORTS if not files.get(name, {}).get("size_bytes")]
    payload = {"schema_version": "0.1", "state": state, "artifacts": files,
               "missing": missing, "error_type": type(error).__name__ if error else None}
    if state == "complete" and missing:
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
    if state == "complete" and missing and error is None:
        raise RuntimeError("Final export is incomplete: " + ", ".join(missing))
    return payload
