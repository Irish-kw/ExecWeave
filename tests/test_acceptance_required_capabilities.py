from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from acceptance import reporting  # noqa: E402
from acceptance.reporting import FEATURES, Result, Status, write_report  # noqa: E402


def _pass_required(result: Result) -> None:
    for feature in result.required_features:
        result.check(feature, True, "required check passed")


def test_required_capability_skip_cannot_hide_behind_other_passes() -> None:
    result = Result("ollama", "interactive-visible", "EW-X", "windows")
    result.check("Launch", True, "client launched")
    result.skip("Network", "native network evidence unavailable")
    assert result.status == Status.FAIL


def test_scenario_scope_skip_remains_optional_when_required_features_pass() -> None:
    result = Result("ollama", "visible-live", "EW-X", "windows")
    _pass_required(result)
    result.skip("Tool call", "plain ollama run has no tool in this scenario")
    result.skip("Fold state", "single round")
    assert result.status == Status.PASS


def test_python_semantic_absence_is_labeled_as_negative_invariant() -> None:
    result = Result("python", "native-os-only", "EW-X", "linux")
    result.check("Prompt", True, "no provider prompt semantics were observed")
    result.check("Final", True, "no provider final semantics were observed")
    result.check("Tool call", True, "no provider tool semantics were observed")
    assert result.checks["Prompt"].evidence_kind == "negative_absence"
    assert result.checks["Final"].evidence_kind == "negative_absence"
    assert result.checks["Tool call"].evidence_kind == "negative_absence"


def test_report_records_source_state_and_required_feature_contract(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        reporting,
        "_source_state",
        lambda: {"sha": "abc123", "dirty": False, "ref": "test/live-dashboard-acceptance"},
    )
    result = Result("offline-ollama-fixture", "offline", "EW-X", "linux")
    _pass_required(result)
    for feature in FEATURES:
        if feature not in result.checks:
            result.skip(feature, "outside this scenario")

    summary = write_report(tmp_path, [result], {"offline-ollama-fixture"})
    persisted = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert summary["status"] == "PASS"
    assert persisted["source"] == {
        "sha": "abc123",
        "dirty": False,
        "ref": "test/live-dashboard-acceptance",
    }
    assert "Network" not in persisted["results"][0]["required_features"]
