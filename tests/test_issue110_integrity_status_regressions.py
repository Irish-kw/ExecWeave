"""Issue #110: end-to-end external digest status must not hide local corruption.

New tests are kept separate from the frozen historical integrity test file.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from execweave.integrity import MANIFEST_FILENAME, seal_run_integrity
from execweave.integrity_cli import main as integrity_main


def _run_dir(tmp_path: Path) -> Path:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "events.jsonl").write_text(
        '{"event_type":"process_start"}\\n', encoding="utf-8"
    )
    (run_dir / "graph.json").write_text(
        '{"nodes":[],"edges":[]}\\n', encoding="utf-8"
    )
    return run_dir


@pytest.mark.parametrize("tamper", ["edit_event", "truncate", "delete_file"])
def test_cli_never_reports_digest_match_as_local_integrity_success(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], tamper: str
) -> None:
    """The expected manifest hash may match while sealed files are corrupted."""
    run_dir = _run_dir(tmp_path)
    expected = seal_run_integrity(run_dir)["manifest_body_sha256"]
    events = run_dir / "events.jsonl"
    if tamper == "edit_event":
        events.write_text("changed event and content\\n", encoding="utf-8")
    elif tamper == "truncate":
        events.write_bytes(b"")
    else:
        events.unlink()

    assert integrity_main([
        "verify", str(run_dir), "--expected-manifest-body-sha256", expected,
    ]) == 1
    outcome = json.loads(capsys.readouterr().out)
    assert outcome["valid"] is False
    # External digest matches the intact original manifest, not the local files.
    assert outcome["external_anchor_match"] is True
    assert outcome["external_anchor_state"] == (
        "external_digest_match_local_integrity_failed"
    )
    assert outcome["errors"]


def test_cli_keeps_success_and_resealed_mismatch_states_distinct(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run_dir = _run_dir(tmp_path)
    original_digest = seal_run_integrity(run_dir)["manifest_body_sha256"]
    verify = ["verify", str(run_dir), "--expected-manifest-body-sha256", original_digest]

    assert integrity_main(verify) == 0
    clean = json.loads(capsys.readouterr().out)
    assert clean["valid"] is True
    assert clean["external_anchor_state"] == "external_digest_match"

    # A local writer with access to the run can replace the manifest as well.
    (run_dir / "events.jsonl").write_text("rewritten\\n", encoding="utf-8")
    (run_dir / MANIFEST_FILENAME).unlink()
    new_digest = seal_run_integrity(run_dir)["manifest_body_sha256"]
    assert new_digest != original_digest

    assert integrity_main(verify) == 1
    changed = json.loads(capsys.readouterr().out)
    assert changed["valid"] is False
    assert changed["external_anchor_match"] is False
    assert changed["external_anchor_state"] == "external_digest_mismatch_or_invalid"
    assert "external anchor digest mismatch" in changed["errors"]

    # Without any external expected digest, do not imply remote trust.
    assert integrity_main(["verify", str(run_dir)]) == 0
    unanchored = json.loads(capsys.readouterr().out)
    assert unanchored["external_anchor_state"] == "unanchored"
