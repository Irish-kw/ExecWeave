from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

FIDELITY_SCHEMA_VERSION = "0.1"

ATTRIBUTION_MODES = {
    "syscall_attributed",
    "process_polled",
    "session_correlated",
    "absent",
}

CLAIMS = {
    "complete_process_tree",
    "process_attributed_file_access",
    "process_attributed_network",
    "short_lived_process_capture",
    "tamper_evident_evidence",
    "byte_level_dataflow",
}


def _entity_backend(entity: object) -> str | None:
    if not isinstance(entity, dict):
        return None
    attributes = entity.get("attributes")
    if not isinstance(attributes, dict):
        return None
    backend = attributes.get("backend")
    return backend if isinstance(backend, str) and backend else None


def _normalized_attribution(event_type: str, raw: object) -> str | None:
    if raw == "syscall":
        return "syscall_attributed"
    if raw in {"polling", "process_polling"}:
        return "process_polled"
    if raw == "session_observation":
        return "session_correlated"
    if event_type.startswith("semantic."):
        return "session_correlated"
    return None


def _channel_for_event(event_type: str) -> str | None:
    if event_type.startswith("process."):
        return "process"
    if event_type.startswith("filesystem."):
        return "filesystem"
    if event_type == "network.connection":
        return "network"
    if event_type.startswith("semantic."):
        return "specialized"
    return None


@dataclass
class FidelityAccumulator:
    """Bounded summary of what a stream can and cannot substantiate.

    Fidelity is intentionally orthogonal to finding severity. It describes capture
    and attribution strength, not whether an observed behavior is benign or severe.
    """

    backends: set[str] = field(default_factory=set)
    attribution_modes: dict[str, set[str]] = field(
        default_factory=lambda: {
            "process": set(),
            "filesystem": set(),
            "network": set(),
            "specialized": set(),
        }
    )
    event_type_counts: dict[str, int] = field(default_factory=dict)
    unresolved_process_references: int = 0
    event_count: int = 0

    def observe(self, event: dict[str, Any]) -> None:
        self.event_count += 1
        event_type = event.get("event_type")
        if not isinstance(event_type, str):
            event_type = "unknown"
        self.event_type_counts[event_type] = self.event_type_counts.get(event_type, 0) + 1

        attributes = event.get("attributes")
        if not isinstance(attributes, dict):
            attributes = {}
        backend = attributes.get("backend")
        if isinstance(backend, str) and backend:
            self.backends.add(backend)
        for entity in (event.get("source"), event.get("target")):
            entity_backend = _entity_backend(entity)
            if entity_backend:
                self.backends.add(entity_backend)
            if isinstance(entity, dict):
                entity_type = entity.get("type")
                entity_attributes = entity.get("attributes")
                if entity_type == "process_reference" or (
                    isinstance(entity_attributes, dict)
                    and entity_attributes.get("unresolved") is True
                ):
                    self.unresolved_process_references += 1

        channel = _channel_for_event(event_type)
        if channel is not None:
            mode = _normalized_attribution(event_type, attributes.get("attribution"))
            if mode is not None:
                self.attribution_modes[channel].add(mode)

    def to_dict(self) -> dict[str, Any]:
        modes: dict[str, list[str]] = {}
        for channel, values in self.attribution_modes.items():
            modes[channel] = sorted(values) if values else ["absent"]

        supported: set[str] = set()
        not_supported: set[str] = {
            "byte_level_dataflow",
            "tamper_evident_evidence",
            "complete_process_tree",
        }

        if "syscall_attributed" in self.attribution_modes["filesystem"]:
            supported.add("process_attributed_file_access")
        else:
            not_supported.add("process_attributed_file_access")

        if (
            "syscall_attributed" in self.attribution_modes["network"]
            or "process_polled" in self.attribution_modes["network"]
        ):
            supported.add("process_attributed_network")
        else:
            not_supported.add("process_attributed_network")

        if "portable" in self.backends or "process_polled" in self.attribution_modes["process"]:
            not_supported.add("short_lived_process_capture")
        elif "syscall_attributed" in self.attribution_modes["process"]:
            supported.add("short_lived_process_capture")
        else:
            not_supported.add("short_lived_process_capture")

        sampled = any(
            mode in {"process_polled", "session_correlated"}
            for values in self.attribution_modes.values()
            for mode in values
        )

        limitations: list[str] = [
            "ExecWeave does not establish byte-level dataflow from these observations.",
            "No current run artifact is an adversary-resistant trust anchor for its own evidence files.",
        ]
        if "portable" in self.backends:
            limitations.append(
                "Portable process/network collection is sampled and may miss short-lived activity."
            )
        if "session_correlated" in self.attribution_modes["filesystem"]:
            limitations.append(
                "Session-correlated filesystem changes do not prove which process performed the write."
            )
        if self.unresolved_process_references:
            limitations.append(
                "Some process references were unresolved; process attribution counts are lower bounds."
            )

        return {
            "fidelity_schema_version": FIDELITY_SCHEMA_VERSION,
            "backend_observed": sorted(self.backends),
            "event_count": self.event_count,
            "attribution_modes": modes,
            "sampled_evidence_present": sampled,
            "unresolved_process_references": self.unresolved_process_references,
            "claims_supported": sorted(supported),
            "claims_not_supported": sorted(not_supported),
            "limitations": limitations,
        }


def derive_fidelity(events: list[dict[str, Any]]) -> dict[str, Any]:
    accumulator = FidelityAccumulator()
    for event in events:
        accumulator.observe(event)
    return accumulator.to_dict()


def write_fidelity_report(report: dict[str, Any], path: str | Path) -> Path:
    """Write one derived fidelity declaration without mutating canonical evidence."""
    output = Path(path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and output.stat().st_size > 0:
        raise FileExistsError(f"ExecWeave fidelity artifact already exists: {output}")
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output
