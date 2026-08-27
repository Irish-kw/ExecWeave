from __future__ import annotations

import json
from pathlib import Path

import pytest

from execweave.rule_pack import (
    RULE_PACK_SCHEMA_VERSION,
    analyze_graph_with_rule_packs,
    load_rule_pack,
)
from execweave.rule_pack_cli import main as rule_pack_main


def _write_pack(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _pack_payload() -> dict:
    return {
        "rule_pack_schema_version": RULE_PACK_SCHEMA_VERSION,
        "id": "local-policy",
        "rules": [
            {
                "id": "pem-read",
                "severity": "medium",
                "match": {
                    "relations": ["OPENED_READ"],
                    "source_types": ["process"],
                    "target_types": ["file"],
                    "target_name_contains": [".pem"],
                    "backends": ["strace"],
                    "causal": True,
                },
            }
        ],
    }


def _graph() -> dict:
    return {
        "session_id": "rule-pack-session",
        "nodes": [
            {"id": "process:s1:10", "type": "process", "name": "python"},
            {"id": "file:/workspace/key.pem", "type": "file", "name": "key.pem"},
        ],
        "edges": [
            {
                "id": "edge:pem-read",
                "source": "process:s1:10",
                "target": "file:/workspace/key.pem",
                "relation": "OPENED_READ",
                "causal": True,
                "backends": ["strace"],
                "attributions": ["syscall"],
                "inferred": False,
                "event_ids": ["event:pem-read"],
            }
        ],
    }


def test_rule_pack_matches_single_observed_edge_and_keeps_claims_conservative(
    tmp_path: Path,
) -> None:
    pack = load_rule_pack(_write_pack(tmp_path / "pack.json", _pack_payload()))
    report = analyze_graph_with_rule_packs(_graph(), [pack])

    assert report["analysis_schema_version"] == "0.4"
    assert report["rule_pack_schema_version"] == RULE_PACK_SCHEMA_VERSION
    assert report["rule_packs"] == [
        {"id": "local-policy", "rule_count": 1, "schema_version": RULE_PACK_SCHEMA_VERSION}
    ]
    finding = next(
        item
        for item in report["findings"]
        if item["rule_id"] == "rule-pack:local-policy:pem-read"
    )
    assert finding["severity"] == "medium"
    assert finding["evidence_grade"] == "A"
    assert finding["attributes"]["observation_only"] is True
    assert finding["attributes"]["data_flow_proven"] is False
    assert finding["attributes"]["exfiltration_proven"] is False
    assert "has not proven byte-level data flow or exfiltration" in finding["summary"]


def test_rule_pack_rejects_arbitrary_regex_matcher(tmp_path: Path) -> None:
    payload = _pack_payload()
    payload["rules"][0]["match"]["regex"] = [".*"]

    with pytest.raises(ValueError, match="unsupported keys: regex"):
        load_rule_pack(_write_pack(tmp_path / "regex.json", payload))


def test_rule_pack_rejects_custom_summary_or_attributes(tmp_path: Path) -> None:
    payload = _pack_payload()
    payload["rules"][0]["summary"] = "Exfiltration confirmed"

    with pytest.raises(ValueError, match="unsupported keys: summary"):
        load_rule_pack(_write_pack(tmp_path / "summary.json", payload))


def test_rule_pack_is_bounded_to_128_rules(tmp_path: Path) -> None:
    payload = _pack_payload()
    payload["rules"] = [
        {
            "id": f"rule-{index}",
            "severity": "low",
            "match": {"relations": ["OPENED_READ"]},
        }
        for index in range(129)
    ]

    with pytest.raises(ValueError, match="exceeds 128 rules"):
        load_rule_pack(_write_pack(tmp_path / "too-many.json", payload))


def test_multiple_rule_packs_must_have_unique_pack_ids(tmp_path: Path) -> None:
    first = load_rule_pack(_write_pack(tmp_path / "first.json", _pack_payload()))
    second = load_rule_pack(_write_pack(tmp_path / "second.json", _pack_payload()))

    with pytest.raises(ValueError, match="rule pack ids must be unique"):
        analyze_graph_with_rule_packs(_graph(), [first, second])


def test_rule_pack_cli_writes_report(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps(_graph()), encoding="utf-8")
    pack_path = _write_pack(tmp_path / "pack.json", _pack_payload())
    output = tmp_path / "report.json"

    assert (
        rule_pack_main(
            [
                str(graph_path),
                "--rule-pack",
                str(pack_path),
                "--output",
                str(output),
            ]
        )
        == 0
    )

    rendered = json.loads(capsys.readouterr().out)
    written = json.loads(output.read_text(encoding="utf-8"))
    assert rendered["rule_packs"][0]["id"] == "local-policy"
    assert written["findings"] == rendered["findings"]
