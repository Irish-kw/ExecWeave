from __future__ import annotations

from dataclasses import asdict, dataclass

AVAILABLE = "available"
COMPLETE_FROM_SURFACE = "complete_from_surface"
SUMMARY = "summary"
REDACTED = "redacted"
OPAQUE_ENCRYPTED = "opaque_encrypted"
OPAQUE_SIGNED = "opaque_signed"
NOT_EXPOSED = "not_exposed"
NOT_OBSERVED = "not_observed"
CAPTURE_DISABLED = "capture_disabled"
CAPTURE_INTERRUPTED = "capture_interrupted"
UNKNOWN = "unknown"

FIELD_AVAILABILITY = (
    AVAILABLE,
    COMPLETE_FROM_SURFACE,
    SUMMARY,
    REDACTED,
    OPAQUE_ENCRYPTED,
    OPAQUE_SIGNED,
    NOT_EXPOSED,
    NOT_OBSERVED,
    CAPTURE_DISABLED,
    CAPTURE_INTERRUPTED,
    UNKNOWN,
)

LOCALLY_DECRYPTABLE = "locally_decryptable"
NO_LOCAL_DECRYPTOR_OBSERVED = "no_local_decryptor_observed"
PROVIDER_DOCUMENTED_UNAVAILABLE = "provider_documented_unavailable"
DECRYPTABILITY_UNKNOWN = "unknown"

DECRYPTABILITY = (
    LOCALLY_DECRYPTABLE,
    NO_LOCAL_DECRYPTOR_OBSERVED,
    PROVIDER_DOCUMENTED_UNAVAILABLE,
    DECRYPTABILITY_UNKNOWN,
)

EVIDENCE_DIRECT_OBSERVATION = "direct_observation"
EVIDENCE_DIRECT_VERIFIABLE = "direct_verifiable_evidence"
EVIDENCE_PROVIDER_DOCUMENTATION = "provider_documentation"
EVIDENCE_INFERENCE = "inference"
EVIDENCE_NO_DATA = "no_data"

EVIDENCE_STRENGTH = (
    EVIDENCE_DIRECT_OBSERVATION,
    EVIDENCE_DIRECT_VERIFIABLE,
    EVIDENCE_PROVIDER_DOCUMENTATION,
    EVIDENCE_INFERENCE,
    EVIDENCE_NO_DATA,
)

_STRONG_UNAVAILABLE_EVIDENCE = frozenset(
    {EVIDENCE_DIRECT_VERIFIABLE, EVIDENCE_PROVIDER_DOCUMENTATION}
)


@dataclass(frozen=True)
class FieldEvidence:
    """One field-level availability claim, separate from conversation completeness."""

    field: str
    availability: str
    decryptability: str = DECRYPTABILITY_UNKNOWN
    evidence_source: str = ""
    evidence_strength: str = EVIDENCE_DIRECT_OBSERVATION
    notes: str | None = None

    def __post_init__(self) -> None:
        if not self.field:
            raise ValueError("field must not be empty")
        validate_availability(self.availability)
        validate_decryptability(self.decryptability, self.evidence_strength)
        if self.evidence_strength not in EVIDENCE_STRENGTH:
            raise ValueError(f"unsupported evidence strength: {self.evidence_strength}")

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def validate_availability(value: str) -> str:
    if value not in FIELD_AVAILABILITY:
        raise ValueError(f"unsupported field availability: {value}")
    return value


def validate_decryptability(value: str, evidence_strength: str) -> str:
    if value not in DECRYPTABILITY:
        raise ValueError(f"unsupported decryptability: {value}")
    if (
        value == PROVIDER_DOCUMENTED_UNAVAILABLE
        and evidence_strength not in _STRONG_UNAVAILABLE_EVIDENCE
    ):
        raise ValueError(
            "provider_documented_unavailable requires provider documentation "
            "or direct verifiable evidence"
        )
    return value


def readable_availability(*, complete_from_surface: bool) -> str:
    """Apply the fixed precedence between readable field states.

    A readable field is ``complete_from_surface`` only when the observed surface
    boundary is known and the complete value supplied by that surface was kept.
    Otherwise the weaker ``available`` state is used.
    """

    return COMPLETE_FROM_SURFACE if complete_from_surface else AVAILABLE
