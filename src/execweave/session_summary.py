"""Portable evidence counts and workload outcome derived from observed events.

Recorder completion is deliberately separate from workload success. Missing
terminal evidence is unknown, never a synthesized successful exit.
"""
from __future__ import annotations

from typing import Any

from .observation import assess_observation


class SessionSummary:
    def __init__(self) -> None:
        self.counts = {"os_runtime": 0, "specialized": 0}
        self.outcome: dict[str, Any] = {"state": "unknown", "return_code": None}
        self.environment: dict[str, Any] = {}
        self._unknown_files: set[str] = set()
        self._missing_snapshots: set[str] = set()
        self._warning_codes: set[str] = set()
        self._short_lived_loss_possible: bool | None = None
        self._filesystem_enabled: bool | None = None

    @property
    def observation(self) -> dict[str, Any]:
        return assess_observation(
            specialized=self.counts["specialized"],
            finished=self.outcome.get("recorder_finished") is True,
            unknown_files=len(self._unknown_files),
            missing_snapshots=len(self._missing_snapshots),
            short_lived_loss_possible=self._short_lived_loss_possible,
            filesystem_enabled=self._filesystem_enabled,
            warning_codes=self._warning_codes,
        )

    def observe(self, event: dict[str, Any]) -> None:
        attributes = event.get("attributes")
        attributes = attributes if isinstance(attributes, dict) else {}
        kind = str(event.get("event_type") or "")
        backend = attributes.get("backend")
        semantic = (kind.startswith("semantic.")
                    or (isinstance(backend, str) and backend in {"semantic", "model_runtime"})
                    or attributes.get("attribution") == "semantic_sidecar")
        self.counts["specialized" if semantic else "os_runtime"] += 1
        if kind == "observation.warning":
            reason = attributes.get("reason")
            if isinstance(reason, str) and reason:
                self._warning_codes.add(reason)
        if kind in {"filesystem.created", "filesystem.modified", "filesystem.moved", "filesystem.deleted"} and attributes.get("is_directory") is not True:
            target = event.get("target")
            if isinstance(target, dict) and isinstance(target.get("id"), str):
                if attributes.get("causal") is not True:
                    self._unknown_files.add(target["id"])
                snapshot = attributes.get("snapshot_state")
                if isinstance(snapshot, str) and snapshot in {"not_captured", "missing"}:
                    self._missing_snapshots.add(target["id"])
        if kind in {"session.started", "session.finished"}:
            value = attributes.get("short_lived_process_loss_possible")
            if type(value) is bool:
                self._short_lived_loss_possible = value
            value = attributes.get("filesystem_collection_enabled")
            if type(value) is bool:
                self._filesystem_enabled = value
        if kind == "session.started":
            for key in ("execweave_version", "python_executable", "python_version", "package_path", "backend"):
                value = attributes.get(key)
                if isinstance(value, str):
                    self.environment[key] = value
        if kind != "session.finished":
            return
        code = attributes.get("return_code")
        if not isinstance(code, int) or isinstance(code, bool):
            code = None
        interrupted = attributes.get("interrupted") is True
        collector_failed = attributes.get("collector_failed") is True
        state = (
            "collector_failed" if collector_failed else
            "interrupted" if interrupted else
            "succeeded" if code == 0 else
            "failed" if code is not None else "unknown"
        )
        self.outcome = {
            "state": state, "return_code": code, "interrupted": interrupted,
            "collector_failed": collector_failed, "event_id": event.get("event_id"),
            "timestamp": event.get("timestamp"), "recorder_finished": True,
        }
