from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from acceptance.interrupt_guard import run_guarded_main  # noqa: E402


def test_keyboard_interrupt_persists_fail_report_in_created_run(tmp_path: Path) -> None:
    run_root = tmp_path / "scenario-run"

    def interrupted() -> int:
        run_root.mkdir()
        raise KeyboardInterrupt

    def args() -> SimpleNamespace:
        return SimpleNamespace(output_dir=tmp_path)

    assert (
        run_guarded_main(
            main_fn=interrupted,
            parse_args=args,
            provider="fixture",
            mode="interrupt-test",
            required_from_args=lambda _args: {"fixture"},
            artifact_prefix="fixture",
        )
        == 1
    )

    summary = json.loads((run_root / "summary.json").read_text(encoding="utf-8"))
    assert summary["status"] == "FAIL"
    assert summary["required"] == ["fixture"]
    assert summary["results"][0]["checks"]["Launch"]["status"] == "FAIL"
    assert summary["results"][0]["checks"]["Cleanup"]["status"] == "FAIL"
    assert (run_root / "report.html").is_file()
    assert "must not be used as PASS evidence" in (run_root / "INTERRUPTED.txt").read_text(
        encoding="utf-8"
    )


def test_normal_main_status_is_unchanged(tmp_path: Path) -> None:
    calls = 0

    def normal() -> int:
        nonlocal calls
        calls += 1
        return 7

    assert (
        run_guarded_main(
            main_fn=normal,
            parse_args=lambda: SimpleNamespace(output_dir=tmp_path),
            provider="fixture",
            mode="normal-test",
            required_from_args=lambda _args: set(),
            artifact_prefix="fixture",
        )
        == 7
    )
    assert calls == 1
    assert not list(tmp_path.iterdir())
