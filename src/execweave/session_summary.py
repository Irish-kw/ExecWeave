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
        # Bounded occurrence-level delivery telemetry; absence of a receive event
        # is not proof that the recipient did not actually receive the message.
        self._message_phases: dict[tuple[str, str, str], set[str]] = {}
        self._message_overflow = False

    @property
    def observation(self) -> dict[str, Any]:
        finished = self.outcome.get("recorder_finished") is True
        unconfirmed = sorted(
            (message_id, sender, recipient)
            for (message_id, sender, recipient), phases in self._message_phases.items()
            if "sent" in phases and "received" not in phases
        )
        warnings = set(self._warning_codes)
        if finished and unconfirmed:
            warnings.add("message_receive_not_observed")
        if self._message_overflow:
            warnings.add("message_delivery_inventory_truncated")
        assessment = assess_observation(
            specialized=self.counts["specialized"],
            finished=finished,
            unknown_files=len(self._unknown_files),
            missing_snapshots=len(self._missing_snapshots),
            short_lived_loss_possible=self._short_lived_loss_possible,
            filesystem_enabled=self._filesystem_enabled,
            warning_codes=warnings,
        )
        if self._message_phases or self._message_overflow:
            assessment["message_delivery"] = {
                "basis": "explicit_message_sent_and_received_events",
                "unconfirmed_count": len(unconfirmed),
                "unconfirmed": [
                    {"message_id": mid, "sender_id": sender,
                     "recipient_id": recipient, "state": "receive_not_observed"}
                    for mid, sender, recipient in unconfirmed[:20]
                ],
                "truncated": self._message_overflow or len(unconfirmed) > 20,
                "delivery_failure_proven": False,
            }
        return assessment

    def observe(self, event: dict[str, Any]) -> None:
        attributes = event.get("attributes")
        attributes = attributes if isinstance(attributes, dict) else {}
        kind = str(event.get("event_type") or "")
        backend = attributes.get("backend")
        semantic = (kind.startswith("semantic.")
                    or (isinstance(backend, str) and backend in {"semantic", "model_runtime"})
                    or attributes.get("attribution") == "semantic_sidecar")
        self.counts["specialized" if semantic else "os_runtime"] += 1
        if kind in {"MESSAGE_SENT", "MESSAGE_RECEIVED"}:
            source, target = event.get("source"), event.get("target")
            message_id = attributes.get("message_id")
            # Inferred/viewer-only routing cannot establish a native send or
            # receipt, even when it happens to carry an occurrence-like ID.
            scopes = (event, attributes, source, target)
            native = all(
                scope.get(flag) is None or scope.get(flag) is False
                for scope in scopes if isinstance(scope, dict)
                for flag in ("inferred", "viewer_only")
            )
            for entity in (source, target):
                entity_attributes = entity.get("attributes") if isinstance(entity, dict) else None
                if isinstance(entity_attributes, dict):
                    native = native and all(
                        entity_attributes.get(flag) is None or entity_attributes.get(flag) is False
                        for flag in ("inferred", "viewer_only")
                    )
            if (native and isinstance(message_id, str) and 0 < len(message_id) <= 2048
                    and isinstance(source, dict) and source.get("type") == "agent"
                    and isinstance(target, dict) and target.get("type") == "agent"):
                sender, recipient = source.get("id"), target.get("id")
                if (isinstance(sender, str) and 0 < len(sender) <= 2048
                        and isinstance(recipient, str) and 0 < len(recipient) <= 2048
                        and sender != recipient
                        and attributes.get("sender_agent_id", sender) == sender
                        and attributes.get("recipient_agent_id", recipient) == recipient
                        and attributes.get("session_id", event.get("session_id")) == event.get("session_id")
                        and not attributes.get("inferred") and not attributes.get("viewer_only")):
                    key = (message_id, sender, recipient)
                    if key in self._message_phases:
                        self._message_phases[key].add("sent" if kind == "MESSAGE_SENT" else "received")
                    elif len(self._message_phases) < 10_000:
                        self._message_phases[key] = {"sent" if kind == "MESSAGE_SENT" else "received"}
                    else:
                        self._message_overflow = True
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
