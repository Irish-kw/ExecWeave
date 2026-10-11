"""#122 release-blocker contracts: local integrity, reader provenance, handoff warnings."""
from __future__ import annotations

import json
from importlib.metadata import version
from pathlib import Path

import pytest

from execweave.integrity_cli import main as integrity_main
from execweave.session_summary import SessionSummary
from execweave.validate import validate_event_stream
from execweave.viewer_run_assessment import RUN_ASSESSMENT_JS, RUN_ASSESSMENT_CSS
from test_issue110_observation_diagnostics import _finish, _handoff, _stream


@pytest.mark.parametrize("schemas", [
    ["0.3", "0.3"], ["0.2", "0.3"], ["0.3", "0.2"],
])
def test_issue122_future_schema_has_named_error(
    tmp_path: Path, schemas: list[str],
) -> None:
    path = tmp_path / "events.jsonl"
    _stream(path, schemas)
    result = validate_event_stream(path)
    assert result.valid is False
    assert result.to_dict()["reader"]["version"] == version("execweave")
    assert any("unsupported_schema_version" in error
               and "0.3" in error and "0.2" in error for error in result.errors)


def test_issue122_missing_schema_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    _stream(path, ["0.2", "0.2"])
    lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    del lines[0]["schema_version"]
    path.write_text("".join(json.dumps(line) + "\n" for line in lines), encoding="utf-8")
    result = validate_event_stream(path)
    assert result.valid is False
    assert any("unsupported_schema_version" in err for err in result.errors)


def test_issue122_reader_metadata_exists_even_when_invalid(tmp_path: Path) -> None:
    invalid = validate_event_stream(tmp_path / "missing.jsonl")
    assert invalid.to_dict()["reader"] == {"name": "execweave", "version": version("execweave")}


def test_issue122_handoff_diagnostic_is_uncertainty_not_delivery_failure() -> None:
    summary = SessionSummary()
    summary.observe(_handoff("id-1", "MESSAGE_SENT"))
    summary.observe(_handoff("id-1", "MESSAGE_RECEIVED"))
    summary.observe(_handoff("id-2", "MESSAGE_SENT"))
    summary.observe(_finish())
    delivery = summary.observation["message_delivery"]
    assert delivery["diagnostics"] == [{
        "kind": "message_receive_not_observed",
        "message_id": "id-2",
        "sender_id": "agent:engineer",
        "recipient_id": "agent:reviewer",
        "delivery_status": "receive_not_observed",
        "delivery_failure_proven": False,
    }]
    assert summary.observation["state"] == "observation_incomplete"
    assert delivery["delivery_failure_proven"] is False


def test_issue122_top_level_handoff_marker_and_click_contract() -> None:
    assert "execweave-handoff-alerts" in RUN_ASSESSMENT_JS
    assert "receive not observed" in RUN_ASSESSMENT_JS
    assert "line.onclick=" in RUN_ASSESSMENT_JS
    assert "api.selectNode(recipient.id)" in RUN_ASSESSMENT_JS
    assert "data-warning" in RUN_ASSESSMENT_CSS
    assert ".edge.handoff-unconfirmed" in RUN_ASSESSMENT_CSS


def test_issue122_local_verification_reader_and_no_anchor(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / "run"
    root.mkdir()
    (root / "graph.json").write_text('{"nodes":[],"edges":[]}', encoding="utf-8")
    assert integrity_main(["seal", str(root)]) == 0
    sealed = json.loads(capsys.readouterr().out)
    assert sealed["malicious_writer_resistance"] is False
    assert "external_anchor_state" not in sealed

    assert integrity_main(["verify", str(root)]) == 0
    verified = json.loads(capsys.readouterr().out)
    assert verified["valid"] is True
    assert verified["local_integrity_valid"] is True
    assert verified["malicious_writer_resistance"] is False
    assert verified["reader"] == {"name": "execweave", "version": version("execweave")}

    (root / "graph.json").write_text("changed", encoding="utf-8")
    assert integrity_main(["verify", str(root)]) == 1
    tampered = json.loads(capsys.readouterr().out)
    assert tampered["valid"] is False


@pytest.mark.parametrize("suffix", [
    "md", "zh-TW.md", "zh-CN.md", "de.md", "fr.md", "ja.md", "ko.md", "ru.md",
])
def test_issue122_local_only_docs_and_downgrade_parity(suffix: str) -> None:
    path = Path(__file__).resolve().parents[1] / "docs" / (
        "run-integrity." + suffix)
    body = path.read_text(encoding="utf-8")
    for marker in (
        "<!-- ew:trust:local-only -->",
        "<!-- ew:trust:privileged -->",
        "<!-- ew:compat:no-downgrade -->",
    ):
        assert marker in body
        tail = body.split(marker, 1)[1].split("\n", 3)[0:3]
        assert any(part.strip() for part in tail)
    assert "v0.8.34" in body
    assert "v0.8.35" in body
    for removed in ("--anchor-github", "--expected-manifest-body-sha256",
                    "EXECWEAVE_INTEGRITY_GITHUB_TOKEN"):
        assert removed not in body
