"""Conservative observation assessment, separate from process/task outcomes.

No inferred writer, nonempty sidecar, or zero exit code proves capture completeness.
These assessments describe declared evidence, not an adversary-resistant archive.
"""
from __future__ import annotations

from typing import Any

SCHEMA_VERSION = "0.1"


def assess_observation(*, specialized: int, finished: bool, unknown_files: int, missing_snapshots: int,
                       short_lived_loss_possible: bool | None,
                       filesystem_enabled: bool | None,
                       warning_codes: set[str]) -> dict[str, Any]:
    reasons = set(warning_codes)
    if unknown_files:
        reasons.add("unknown_file_writer")
    if missing_snapshots:
        reasons.add("file_snapshot_not_captured")
    if short_lived_loss_possible is True:
        reasons.add("short_lived_process_loss_possible")
    elif short_lived_loss_possible is None:
        reasons.add("process_coverage_unverified")
    if filesystem_enabled is False:
        reasons.add("filesystem_collection_disabled")
    if finished and specialized == 0:
        reasons.add("zero_specialized_evidence")
    if not finished:
        reasons.add("terminal_evidence_missing")
    # Even a gap-free declared inventory does not establish end-to-end recall.
    return {
        "schema_version": SCHEMA_VERSION,
        "state": "observation_incomplete" if reasons else "not_verified",
        "reasons": sorted(reasons),
        "specialized_evidence": specialized,
        "unknown_owner_files": unknown_files,
        "files_with_uncaptured_snapshots": missing_snapshots,
        "short_lived_process_loss_possible": short_lived_loss_possible,
        "missed_process_lower_bound": None,
        "end_to_end_completeness_proven": False,
        "scope": "declared_evidence",
    }


def session_outcome(execution: dict[str, Any], observation: dict[str, Any]) -> dict[str, Any]:
    result = dict(execution)
    result["execution_state"] = execution.get("state", "unknown")
    result["observation_state"] = observation["state"]
    if execution.get("recorder_finished") is True and observation["state"] == "observation_incomplete":
        result["state"] = "observation_incomplete"
    return result
