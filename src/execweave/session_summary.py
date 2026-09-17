"""Portable evidence counts and workload outcome derived from observed events.

Recorder completion is deliberately separate from workload success. Missing
terminal evidence is unknown, never a synthesized successful exit.
"""
from __future__ import annotations

from typing import Any


class SessionSummary:
    def __init__(self) -> None:
        self.counts = {"os_runtime": 0, "specialized": 0}
        self.outcome: dict[str, Any] = {"state": "unknown", "return_code": None}
        self.environment: dict[str, Any] = {}

    def observe(self, event: dict[str, Any]) -> None:
        attributes = event.get("attributes")
        attributes = attributes if isinstance(attributes, dict) else {}
        kind = str(event.get("event_type") or "")
        backend = attributes.get("backend")
        semantic = (kind.startswith("semantic.")
                    or (isinstance(backend, str) and backend in {"semantic", "model_runtime"})
                    or attributes.get("attribution") == "semantic_sidecar")
        self.counts["specialized" if semantic else "os_runtime"] += 1
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
