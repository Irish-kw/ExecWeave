from __future__ import annotations

import json
from pathlib import Path

import pytest

from execweave.integrity import MANIFEST_FILENAME, seal_run_integrity, verify_run_integrity
from execweave.integrity_cli import main as integrity_main


def _run_dir(tmp_path: Path) -> Path:
    run_dir = tmp_path / "run"
    (run_dir / "content" / "sha256").mkdir(parents=True)
    (run_dir / "events.jsonl").write_text('{"event_type":"process_start"}\n', encoding="utf-8")
    (run_dir / "graph.json").write_text('{"nodes":[],"edges":[]}\n', encoding="utf-8")
    (run_dir / "content" / "sha256" / "demo.txt").write_text(
        "complete content\n", encoding="utf-8"
    )
    return run_dir


def test_seal_and_verify_inventory_is_deterministic(tmp_path: Path) -> None:
    run_dir = _run_dir(tmp_path)
    manifest = seal_run_integrity(run_dir)

    assert manifest["schema_version"] == "0.1"
    assert manifest["hash_algorithm"] == "sha256"
    assert manifest["sealed_file_count"] == 3
    assert manifest["trust_model"] == {
        "scope": "local_post_seal_corruption_detection",
        "malicious_writer_resistance": False,
        "external_trust_anchor": False,
    }
    assert [entry["path"] for entry in manifest["files"]] == [
        "content/sha256/demo.txt",
        "events.jsonl",
        "graph.json",
    ]
    assert len(manifest["manifest_body_sha256"]) == 64

    result = verify_run_integrity(run_dir)
    assert result.valid is True
    assert result.sealed_file_count == 3
    assert result.checked_file_count == 3
    assert result.errors == ()


def test_verify_detects_modified_missing_and_unsealed_files(tmp_path: Path) -> None:
    run_dir = _run_dir(tmp_path)
    seal_run_integrity(run_dir)

    (run_dir / "events.jsonl").write_text("modified\n", encoding="utf-8")
    (run_dir / "graph.json").unlink()
    (run_dir / "late.txt").write_text("created after seal\n", encoding="utf-8")

    result = verify_run_integrity(run_dir)
    assert result.valid is False
    assert any("mismatch for events.jsonl" in error for error in result.errors)
    assert "missing sealed file: graph.json" in result.errors
    assert "unsealed file present: late.txt" in result.errors


def test_verify_detects_manifest_tampering(tmp_path: Path) -> None:
    run_dir = _run_dir(tmp_path)
    seal_run_integrity(run_dir)
    manifest_path = run_dir / MANIFEST_FILENAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["sealed_file_count"] = 99
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    result = verify_run_integrity(run_dir)
    assert result.valid is False
    assert any("sealed_file_count" in error for error in result.errors)


def test_seal_refuses_existing_manifest(tmp_path: Path) -> None:
    run_dir = _run_dir(tmp_path)
    seal_run_integrity(run_dir)
    with pytest.raises(FileExistsError, match="already exists"):
        seal_run_integrity(run_dir)


def test_seal_rejects_symbolic_links(tmp_path: Path) -> None:
    run_dir = _run_dir(tmp_path)
    link = run_dir / "linked-events.jsonl"
    try:
        link.symlink_to(run_dir / "events.jsonl")
    except (NotImplementedError, OSError):
        pytest.skip("symbolic links are unavailable on this runner")

    with pytest.raises(ValueError, match="does not seal symbolic links"):
        seal_run_integrity(run_dir)


def test_cli_seal_and_verify_return_meaningful_status(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run_dir = _run_dir(tmp_path)
    assert integrity_main(["seal", str(run_dir)]) == 0
    sealed = json.loads(capsys.readouterr().out)
    assert sealed["status"] == "sealed"
    assert sealed["malicious_writer_resistance"] is False

    assert integrity_main(["verify", str(run_dir)]) == 0
    verified = json.loads(capsys.readouterr().out)
    assert verified["valid"] is True

    (run_dir / "events.jsonl").write_text("tampered\n", encoding="utf-8")
    assert integrity_main(["verify", str(run_dir)]) == 1
    failed = json.loads(capsys.readouterr().out)
    assert failed["valid"] is False


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
