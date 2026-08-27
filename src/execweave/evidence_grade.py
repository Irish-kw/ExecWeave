from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

EVIDENCE_GRADE_SCHEMA_VERSION = "0.1"
EVIDENCE_GRADES = ("A", "B", "C", "D", "U")

_GRADE_ORDER = {grade: index for index, grade in enumerate(EVIDENCE_GRADES)}
_STRONG_ATTRIBUTIONS = {"syscall"}
_SAMPLED_ATTRIBUTIONS = {"polling", "process_polling"}
_SESSION_ATTRIBUTIONS = {"session_observation"}


def _strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return sorted({item for item in value if isinstance(item, str) and item})


def weakest_grade(grades: list[str]) -> str:
    """Return the weakest known grade without upgrading unknown provenance."""
    normalized = [grade if grade in _GRADE_ORDER else "U" for grade in grades]
    if not normalized:
        return "U"
    return max(normalized, key=lambda grade: _GRADE_ORDER[grade])


@dataclass(frozen=True)
class EdgeEvidenceGrade:
    edge_id: str
    grade: str
    reason: str
    causal: bool | None
    inferred: bool | None
    attributions: list[str]
    backends: list[str]
    inference_methods: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def grade_edge(edge: dict[str, Any]) -> EdgeEvidenceGrade:
    """Grade one graph edge from observable provenance only.

    Grades are intentionally conservative and orthogonal to behavior severity:
    A = direct causal syscall attribution
    B = direct causal sampled process attribution
    C = session-correlated or explicitly non-causal evidence
    D = explicitly inferred/heuristic evidence
    U = provenance is absent, mixed, or not yet classified

    Unknown attribution vocabulary is never upgraded automatically.
    """
    edge_id = str(edge.get("id") or "")
    causal = edge.get("causal") if isinstance(edge.get("causal"), bool) else None
    inferred = edge.get("inferred") if isinstance(edge.get("inferred"), bool) else None
    attributions = _strings(edge.get("attributions"))
    backends = _strings(edge.get("backends"))
    inference_methods = _strings(edge.get("inference_methods"))

    if inferred is True or inference_methods:
        grade = "D"
        reason = "edge is explicitly inferred or records an inference method"
    elif causal is False:
        grade = "C"
        reason = "edge is explicitly non-causal"
    elif not attributions:
        grade = "U"
        reason = "edge has no recognized attribution provenance"
    else:
        attribution_grades: list[str] = []
        for attribution in attributions:
            if attribution in _STRONG_ATTRIBUTIONS and causal is True:
                attribution_grades.append("A")
            elif attribution in _SAMPLED_ATTRIBUTIONS and causal is True:
                attribution_grades.append("B")
            elif attribution in _SESSION_ATTRIBUTIONS:
                attribution_grades.append("C")
            else:
                attribution_grades.append("U")
        grade = weakest_grade(attribution_grades)
        reason = {
            "A": "direct causal syscall attribution",
            "B": "direct causal sampled process attribution",
            "C": "session-correlated or non-causal attribution",
            "U": "attribution provenance is unknown, mixed, or not yet classified",
        }[grade]

    return EdgeEvidenceGrade(
        edge_id=edge_id,
        grade=grade,
        reason=reason,
        causal=causal,
        inferred=inferred,
        attributions=attributions,
        backends=backends,
        inference_methods=inference_methods,
    )


def annotate_finding(
    finding: dict[str, Any],
    edges_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Attach a finding-level grade using the weakest supporting edge."""
    payload = dict(finding)
    edge_ids = [
        value
        for value in finding.get("edge_ids", [])
        if isinstance(value, str) and value
    ]
    bases: list[dict[str, Any]] = []
    grades: list[str] = []

    for edge_id in edge_ids:
        edge = edges_by_id.get(edge_id)
        if edge is None:
            basis = EdgeEvidenceGrade(
                edge_id=edge_id,
                grade="U",
                reason="supporting edge is missing from the analyzed graph",
                causal=None,
                inferred=None,
                attributions=[],
                backends=[],
                inference_methods=[],
            ).to_dict()
        else:
            basis = grade_edge(edge).to_dict()
        bases.append(basis)
        grades.append(str(basis["grade"]))

    payload["evidence_grade_schema_version"] = EVIDENCE_GRADE_SCHEMA_VERSION
    payload["evidence_grade"] = weakest_grade(grades)
    payload["evidence_basis"] = bases
    return payload
