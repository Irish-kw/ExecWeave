from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from string import ascii_letters, digits
from typing import Any, Sequence

RULE_PACK_SCHEMA_VERSION = "0.1"

_MAX_PACK_BYTES = 256 * 1024
_MAX_RULES = 128
_MAX_MATCH_VALUES = 16
_MAX_MATCH_VALUE_CHARS = 160
_MAX_ID_CHARS = 80

_ID_CHARS = frozenset(ascii_letters + digits + "._-")
_ALLOWED_SEVERITIES = {"high", "medium", "low", "info"}
_ALLOWED_TOP_KEYS = {"rule_pack_schema_version", "id", "rules"}
_ALLOWED_RULE_KEYS = {"id", "severity", "match"}
_LIST_MATCH_KEYS = {
    "relations",
    "source_types",
    "target_types",
    "source_id_contains",
    "target_id_contains",
    "source_name_contains",
    "target_name_contains",
    "backends",
    "attributions",
}
_ALLOWED_MATCH_KEYS = {*_LIST_MATCH_KEYS, "causal"}


@dataclass(frozen=True)
class RulePackRule:
    rule_id: str
    severity: str
    match: dict[str, Any]


@dataclass(frozen=True)
class RulePack:
    pack_id: str
    rules: tuple[RulePackRule, ...]

    def metadata(self) -> dict[str, Any]:
        return {
            "id": self.pack_id,
            "rule_count": len(self.rules),
            "schema_version": RULE_PACK_SCHEMA_VERSION,
        }


def _identifier(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    if len(value) > _MAX_ID_CHARS:
        raise ValueError(f"{label} exceeds {_MAX_ID_CHARS} characters")
    if any(character not in _ID_CHARS for character in value):
        raise ValueError(f"{label} may contain only letters, digits, '.', '_', and '-'")
    return value


def _validate_keys(payload: dict[str, Any], allowed: set[str], *, label: str) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ValueError(f"{label} contains unsupported keys: {', '.join(unknown)}")


def _match_values(value: object, *, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{label} must be a non-empty list of strings")
    if len(value) > _MAX_MATCH_VALUES:
        raise ValueError(f"{label} exceeds {_MAX_MATCH_VALUES} values")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item:
            raise ValueError(f"{label} must contain only non-empty strings")
        if len(item) > _MAX_MATCH_VALUE_CHARS:
            raise ValueError(
                f"{label} contains a value longer than {_MAX_MATCH_VALUE_CHARS} characters"
            )
        result.append(item)
    return tuple(result)


def _parse_rule(payload: object, *, pack_id: str, index: int) -> RulePackRule:
    if not isinstance(payload, dict):
        raise ValueError(f"rule {index} in {pack_id} must be an object")
    _validate_keys(payload, _ALLOWED_RULE_KEYS, label=f"rule {index} in {pack_id}")

    rule_id = _identifier(payload.get("id"), label=f"rule {index} id")
    severity = payload.get("severity")
    if severity not in _ALLOWED_SEVERITIES:
        raise ValueError(
            f"rule {pack_id}/{rule_id} severity must be one of: "
            + ", ".join(sorted(_ALLOWED_SEVERITIES))
        )

    raw_match = payload.get("match")
    if not isinstance(raw_match, dict) or not raw_match:
        raise ValueError(f"rule {pack_id}/{rule_id} match must be a non-empty object")
    _validate_keys(
        raw_match,
        _ALLOWED_MATCH_KEYS,
        label=f"rule {pack_id}/{rule_id} match",
    )

    match: dict[str, Any] = {}
    for key in sorted(_LIST_MATCH_KEYS):
        if key in raw_match:
            match[key] = _match_values(
                raw_match[key],
                label=f"rule {pack_id}/{rule_id} match.{key}",
            )
    if "causal" in raw_match:
        if not isinstance(raw_match["causal"], bool):
            raise ValueError(f"rule {pack_id}/{rule_id} match.causal must be boolean")
        match["causal"] = raw_match["causal"]
    return RulePackRule(rule_id=rule_id, severity=str(severity), match=match)


def load_rule_pack(path: Path) -> RulePack:
    source = Path(path).expanduser().resolve()
    try:
        size = source.stat().st_size
    except OSError as exc:
        raise ValueError(f"cannot read rule pack {source}: {exc}") from exc
    if size > _MAX_PACK_BYTES:
        raise ValueError(f"rule pack exceeds {_MAX_PACK_BYTES} bytes: {source}")
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid rule pack {source}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("rule pack root must be an object")
    _validate_keys(payload, _ALLOWED_TOP_KEYS, label="rule pack")

    schema_version = payload.get("rule_pack_schema_version")
    if schema_version != RULE_PACK_SCHEMA_VERSION:
        raise ValueError(
            "unsupported rule_pack_schema_version "
            f"{schema_version!r}; expected {RULE_PACK_SCHEMA_VERSION!r}"
        )
    pack_id = _identifier(payload.get("id"), label="rule pack id")
    raw_rules = payload.get("rules")
    if not isinstance(raw_rules, list) or not raw_rules:
        raise ValueError(f"rule pack {pack_id} rules must be a non-empty list")
    if len(raw_rules) > _MAX_RULES:
        raise ValueError(f"rule pack {pack_id} exceeds {_MAX_RULES} rules")

    rules = tuple(
        _parse_rule(rule, pack_id=pack_id, index=index)
        for index, rule in enumerate(raw_rules, start=1)
    )
    rule_ids = [rule.rule_id for rule in rules]
    if len(rule_ids) != len(set(rule_ids)):
        raise ValueError(f"rule pack {pack_id} contains duplicate rule ids")
    return RulePack(pack_id=pack_id, rules=rules)


def _node_map(graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        node["id"]: node
        for node in graph.get("nodes", [])
        if isinstance(node, dict) and isinstance(node.get("id"), str)
    }


def _edge_values(edge: dict[str, Any], key: str) -> set[str]:
    value = edge.get(key)
    if isinstance(value, str):
        return {value}
    if isinstance(value, list):
        return {item for item in value if isinstance(item, str)}
    return set()


def _matches_any_contains(text: str, values: Sequence[str]) -> bool:
    normalized = text.casefold()
    return any(value.casefold() in normalized for value in values)


def _rule_matches(
    rule: RulePackRule,
    *,
    edge: dict[str, Any],
    source: dict[str, Any] | None,
    target: dict[str, Any] | None,
) -> bool:
    match = rule.match
    relation = edge.get("relation")
    source_id = edge.get("source")
    target_id = edge.get("target")

    exact_checks = (
        ("relations", relation),
        ("source_types", source.get("type") if source else None),
        ("target_types", target.get("type") if target else None),
    )
    for key, value in exact_checks:
        allowed = match.get(key)
        if allowed is not None and value not in allowed:
            return False

    contains_checks = (
        ("source_id_contains", str(source_id or "")),
        ("target_id_contains", str(target_id or "")),
        ("source_name_contains", str(source.get("name") or "") if source else ""),
        ("target_name_contains", str(target.get("name") or "") if target else ""),
    )
    for key, text in contains_checks:
        values = match.get(key)
        if values is not None and not _matches_any_contains(text, values):
            return False

    for key in ("backends", "attributions"):
        required = match.get(key)
        if required is not None and not _edge_values(edge, key).intersection(required):
            return False

    if "causal" in match and edge.get("causal") is not match["causal"]:
        return False
    return True


def _event_ids(edge: dict[str, Any], limit: int = 24) -> list[str]:
    values = edge.get("event_ids") or []
    return [str(value) for value in values if isinstance(value, str)][:limit]


def _validate_pack_set(rule_packs: Sequence[RulePack]) -> None:
    pack_ids = [pack.pack_id for pack in rule_packs]
    if len(pack_ids) != len(set(pack_ids)):
        raise ValueError("rule pack ids must be unique within one analysis invocation")


def rule_pack_metadata(rule_packs: Sequence[RulePack]) -> list[dict[str, Any]]:
    _validate_pack_set(rule_packs)
    return [pack.metadata() for pack in rule_packs]


def evaluate_rule_packs(
    graph: dict[str, Any],
    rule_packs: Sequence[RulePack],
) -> list[dict[str, Any]]:
    _validate_pack_set(rule_packs)
    nodes = _node_map(graph)
    matches: list[dict[str, Any]] = []

    for edge in graph.get("edges", []):
        if not isinstance(edge, dict):
            continue
        edge_id = edge.get("id")
        source_id = edge.get("source")
        target_id = edge.get("target")
        relation = edge.get("relation")
        if not all(
            isinstance(value, str) and value
            for value in (edge_id, source_id, target_id, relation)
        ):
            continue
        source = nodes.get(source_id)
        target = nodes.get(target_id)

        for pack in rule_packs:
            for rule in pack.rules:
                if not _rule_matches(rule, edge=edge, source=source, target=target):
                    continue
                matches.append(
                    {
                        "rule_id": f"rule-pack:{pack.pack_id}:{rule.rule_id}",
                        "severity": rule.severity,
                        "title": "Rule-pack observation matched",
                        "summary": (
                            f"Rule pack {pack.pack_id}/{rule.rule_id} matched observed graph "
                            f"edge {edge_id}: {source_id} --{relation}--> {target_id}. "
                            "This records an observation match only; ExecWeave has not proven "
                            "byte-level data flow or exfiltration."
                        ),
                        "node_ids": [source_id, target_id],
                        "edge_ids": [edge_id],
                        "evidence_event_ids": _event_ids(edge),
                        "attributes": {
                            "rule_pack_schema_version": RULE_PACK_SCHEMA_VERSION,
                            "rule_pack_id": pack.pack_id,
                            "rule_pack_rule_id": rule.rule_id,
                            "relation": relation,
                            "causal": edge.get("causal"),
                            "observation_only": True,
                            "data_flow_proven": False,
                            "exfiltration_proven": False,
                        },
                    }
                )
    return matches


_SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2, "info": 3}


def analyze_graph_with_rule_packs(
    graph: dict[str, Any],
    rule_packs: Sequence[RulePack],
) -> dict[str, Any]:
    from .analysis import analyze_graph
    from .evidence_grade import EVIDENCE_GRADES, annotate_finding

    _validate_pack_set(rule_packs)
    report = analyze_graph(graph)
    edges_by_id = {
        edge_id: edge
        for edge in graph.get("edges", [])
        if isinstance(edge, dict)
        and isinstance((edge_id := edge.get("id")), str)
        and edge_id
    }
    custom_findings = [
        annotate_finding(finding, edges_by_id)
        for finding in evaluate_rule_packs(graph, rule_packs)
    ]
    findings = [*report.get("findings", []), *custom_findings]
    findings.sort(
        key=lambda finding: (
            _SEVERITY_ORDER.get(str(finding.get("severity") or ""), 99),
            str(finding.get("rule_id") or ""),
            list(finding.get("node_ids") or []),
        )
    )

    severity_counts = Counter(str(finding.get("severity") or "") for finding in findings)
    grade_counts = Counter(str(finding.get("evidence_grade") or "U") for finding in findings)
    limitations = list(report.get("limitations") or [])
    limitation = (
        "Rule-pack findings are single-edge observation matches; they do not prove "
        "byte-level data flow or exfiltration."
    )
    if limitation not in limitations:
        limitations.append(limitation)

    return {
        **report,
        "analysis_schema_version": "0.4",
        "rule_pack_schema_version": RULE_PACK_SCHEMA_VERSION,
        "rule_packs": rule_pack_metadata(rule_packs),
        "finding_count": len(findings),
        "severity_counts": {
            severity: severity_counts.get(severity, 0)
            for severity in ("high", "medium", "low", "info")
        },
        "evidence_grade_counts": {
            grade: grade_counts.get(grade, 0)
            for grade in EVIDENCE_GRADES
        },
        "limitations": limitations,
        "findings": findings,
    }
