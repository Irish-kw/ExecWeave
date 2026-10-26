"""Regression coverage for local-only ExecWeave integrity verification.

Historical tests/test_integrity.py is frozen; new status regressions live here.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from execweave.integrity import MANIFEST_FILENAME, seal_run_integrity
from execweave.integrity_cli import main as integrity_main


def _run_dir(tmp_path: Path) -> Path:
    root = tmp_path / "run"
    root.mkdir()
    (root / "events.jsonl").write_text('{"event_type":"process_start"}\n', encoding="utf-8")
    (root / "graph.json").write_text('{"nodes":[],"edges":[]}\n', encoding="utf-8")
    return root


@pytest.mark.parametrize("tamper", ["edit_event", "truncate", "delete_file"])
def test_local_checks_detect_changes_not_resealed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], tamper: str,
) -> None:
    root = _run_dir(tmp_path)
    seal_run_integrity(root)
    events = root / "events.jsonl"
    if tamper == "edit_event":
        events.write_text("rewritten\n", encoding="utf-8")
    elif tamper == "truncate":
        events.write_bytes(b"")
    else:
        events.unlink()

    assert integrity_main(["verify", str(root)]) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["valid"] is False
    assert result["local_integrity_valid"] is False
    assert result["status"] == "local_integrity_failed"
    assert result["malicious_writer_resistance"] is False
    assert result["errors"]
    assert "external_anchor_state" not in result
    assert "external_digest_match" not in result


def test_resealing_locally_can_hide_rewrite_and_cannot_prove_resistance(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    root = _run_dir(tmp_path)
    original = seal_run_integrity(root)["manifest_body_sha256"]
    (root / "events.jsonl").write_text("rewritten\n", encoding="utf-8")
    (root / MANIFEST_FILENAME).unlink()
    new_digest = seal_run_integrity(root)["manifest_body_sha256"]
    assert new_digest != original

    assert integrity_main(["verify", str(root)]) == 0
    checked = json.loads(capsys.readouterr().out)
    assert checked["valid"] is True
    assert checked["local_integrity_valid"] is True
    assert checked["status"] == "locally_valid"
    assert checked["malicious_writer_resistance"] is False
    assert "external_anchor_state" not in checked
    assert "external_digest_match" not in checked
    assert checked["reader"]["name"] == "execweave"


def test_seal_exposes_digest_without_publishing_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    root = _run_dir(tmp_path)
    assert integrity_main(["seal", str(root)]) == 0
    sealed = json.loads(capsys.readouterr().out)
    assert len(sealed["manifest_body_sha256"]) == 64
    assert sealed["status"] == "sealed"
    assert sealed["malicious_writer_resistance"] is False
    assert "external_anchor_state" not in sealed
    assert sealed["reader"]["name"] == "execweave"
