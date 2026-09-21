"""Bounded publication of an in-process finalization result, not a new audit.

The receipt records what the existing verifier checked at export time. Publishing
it performs no filesystem reads and does not assert that files remain unchanged.
"""

from __future__ import annotations

import re
from typing import Any

_HASH = re.compile(r"[0-9a-f]{64}")
_PRIMARY = ("graph.json", "conversations.json", "viewer.html")


def summarize_finalization(report: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema_version": "0.1",
        "scope": "recorded_finalization_result",
        "state": "unavailable",
        "reason": "no_finalization_report",
        "verified_file_count": None,
        "unique_file_count": None,
        "error_count": None,
        "diagnostics": [],
        "rechecked_now": False,
    }
    if not isinstance(report, dict):
        return result
    if report.get("schema_version") != "0.2":
        result["reason"] = "unsupported_finalization_schema"
        return result
    state = report.get("state")
    if state in ("recording", "exporting"):
        result.update(state=state, reason="export_not_terminal")
        return result
    if state not in ("complete", "incomplete", "failed"):
        result["reason"] = "invalid_finalization_state"
        return result
    content = report.get("content_integrity")
    content = content if isinstance(content, dict) else {}
    for key in ("verified_file_count", "unique_file_count", "error_count"):
        value = content.get(key)
        result[key] = value if type(value) is int and 0 <= value <= 2**53 - 1 else None
    errors = content.get("errors")
    if isinstance(errors, list):
        for entry in errors[:20]:
            code = entry.get("code") if isinstance(entry, dict) else None
            if isinstance(code, str) and re.fullmatch(r"[a-z_]{1,80}", code):
                result["diagnostics"].append(code)
    if state != "complete":
        result.update(state=state, reason="recorded_export_failure")
        return result

    # A contradictory/incomplete receipt cannot be promoted merely by state=complete.
    artifacts, indexes = report.get("artifacts"), content.get("index_files")
    valid = (
        isinstance(artifacts, dict)
        and isinstance(indexes, dict)
        and report.get("missing") == []
        and report.get("artifact_errors") == {}
        and content.get("schema_version") == "0.1"
        and content.get("scope") == "declared_graph_and_conversation_content"
        and content.get("state") == "complete"
        and result["error_count"] == 0
        and result["verified_file_count"] is not None
        and result["verified_file_count"] == result["unique_file_count"]
        and content.get("reference_count_truncated") is False
        and content.get("errors_truncated") is False
        and errors == []
        and isinstance(content.get("verified_files"), dict)
        and len(content["verified_files"]) == result["verified_file_count"]
    )
    if valid:
        for name in _PRIMARY:
            item = artifacts.get(name)
            if not isinstance(item, dict):
                valid = False
                break
            size, digest = item.get("size_bytes"), item.get("sha256")
            if (
                type(size) is not int
                or size <= 0
                or not isinstance(digest, str)
                or not _HASH.fullmatch(digest)
            ):
                valid = False
            if name != "viewer.html" and indexes.get(name) != item:
                valid = False
    if not valid:
        result.update(state="unavailable", reason="inconsistent_finalization_report")
    else:
        result.update(state="complete", reason="recorded_export_verification")
    return result
