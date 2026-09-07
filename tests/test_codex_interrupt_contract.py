from __future__ import annotations

import io
import json
import sys
import time
from pathlib import Path

import pytest

from execweave import codex_hook_entry
from execweave.codex_hook_cli import codex_hook_config


def _payload(tmp_path: Path) -> dict[str, object]:
    return {
        "hook_event_name": "Interrupt",
        "session_id": "codex-interrupt-session",
        "turn_id": "turn-1",
        "cwd": str(tmp_path),
        "model": "gpt-test",
        "permission_mode": "default",
    }


def test_generated_interrupt_hook_is_async_and_bounded() -> None:
    config = codex_hook_config("execweave-codex-hook --auto")
    group = config["hooks"]["Interrupt"][0]
    assert "matcher" not in group
    handler = group["hooks"][0]
    assert handler["command"] == "execweave-codex-hook --auto"
    assert handler["timeout"] == 3
    assert handler["async"] is True

    session_end = config["hooks"]["SessionEnd"][0]["hooks"][0]
    assert session_end["timeout"] == 3


def test_active_auto_interrupt_uses_fast_path_without_loading_capture_stack(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    sidecar = tmp_path / "semantic.jsonl"
    monkeypatch.setenv("EXECWEAVE_SEMANTIC_SIDECAR", str(sidecar))
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(_payload(tmp_path))))

    def must_not_load_capture_stack():
        raise AssertionError("Interrupt loaded the normal capture stack")

    monkeypatch.setattr(codex_hook_entry, "_load_capture_main", must_not_load_capture_stack)

    assert codex_hook_entry.main(["--auto"]) == 0
    records = [json.loads(line) for line in sidecar.read_text(encoding="utf-8").splitlines()]
    assert [record["relation"] for record in records] == ["OBSERVED_TURN_INTERRUPT"]
    assert records[0]["attributes"]["codex_turn_id"] == "turn-1"


def test_active_auto_interrupt_does_not_wait_for_normal_five_second_sidecar_lock(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    sidecar = tmp_path / "semantic.jsonl"
    lock_dir = sidecar.with_name(sidecar.name + ".lock")
    lock_dir.mkdir()
    monkeypatch.setenv("EXECWEAVE_SEMANTIC_SIDECAR", str(sidecar))
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(_payload(tmp_path))))

    started = time.monotonic()
    assert codex_hook_entry.main(["--auto"]) == 0
    elapsed = time.monotonic() - started

    assert elapsed < 0.75
    assert not sidecar.exists()
