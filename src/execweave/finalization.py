"""Durable export status, including the content referenced by exported indexes."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .content_integrity import ArchiveReadError, audit_content_references, hash_export, _read
from .private_io import write_private_json
from .run_assessment import build_run_assessment


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
    payload["observation_assessment"] = {
        "state": "not_verified", "reasons": ["graph_assessment_unavailable"],
    }
    payload["run_assessment"] = {
        "schema_version": "0.1",
        "scope": "unavailable",
        "reason": "graph_assessment_unavailable",
    }
    payload["run_assessment_binding"] = None
    if state != "recording" and "graph.json" in files:
        try:
            fingerprint, raw = _read(run_dir, "graph.json", 64 * 1024 * 1024, collect=True)
            graph = json.loads(raw)
            if fingerprint != files["graph.json"] or not isinstance(graph, dict):
                raise ValueError("inconsistent_graph")
            assessment = graph.get("observation_assessment")
            if assessment is not None:
                if not (isinstance(assessment, dict) and assessment.get("schema_version") == "0.1"
                        and isinstance(assessment.get("state"), str)
                        and assessment["state"] in {"not_verified", "observation_incomplete"}):
                    raise ValueError("invalid_observation_assessment")
                payload["observation_assessment"] = assessment
            outcome = graph.get("session_outcome")
            if isinstance(outcome, dict):
                payload["session_outcome"] = outcome
            payload["run_assessment"] = build_run_assessment(graph)
            payload["run_assessment_binding"] = {
                "graph": dict(files["graph.json"]),
                "assessment_schema_version": payload["run_assessment"].get("schema_version"),
                "derivation": "execweave.run_assessment.build_run_assessment",
            }
        except (ArchiveReadError, ValueError, UnicodeError):
            payload["observation_assessment"] = {
                "state": "observation_incomplete", "reasons": ["graph_assessment_unreadable"],
            }
            payload["run_assessment"] = {
                "schema_version": "0.1", "scope": "unavailable",
                "reason": "graph_assessment_unreadable",
            }
            payload["run_assessment_binding"] = None
    # state=complete is retained as the archive/export axis for older readers.
    # Overall session_status must not claim success merely because bytes were exported.
    payload["session_status"] = payload["observation_assessment"]["state"]
    write_private_json(run_dir / "finalization.json", payload, replace=True)
    if state == "complete" and not complete and error is None:
        detail = ", ".join(missing) if missing else "declared content or export verification failed"
        raise RuntimeError("Final export is incomplete: " + detail)
    # A collector failure stays primary, even when the archive is incomplete.
    return payload
