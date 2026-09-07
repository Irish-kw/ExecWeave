from __future__ import annotations

import io
import json
import sys
import tomllib
from pathlib import Path

import pytest

from execweave import codex_hook_entry


_CODEX_LIFECYCLE_EVENTS = (
    "Interrupt",  # stale ExecWeave installs may still contain this retired event
    "PermissionRequest",
    "PostCompact",
    "PostToolUse",
    "PreCompact",
    "PreToolUse",
    "SessionEnd",
    "SessionStart",
    "Stop",
    "SubagentStart",
    "SubagentStop",
    "UserPromptSubmit",
)


@pytest.mark.parametrize("event_name", _CODEX_LIFECYCLE_EVENTS)
def test_global_auto_hook_is_inert_when_execweave_is_not_running(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    event_name: str,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("EXECWEAVE_SEMANTIC_SIDECAR", raising=False)
    monkeypatch.setattr(
        sys,
        "stdin",
        io.StringIO(
            json.dumps(
                {
                    "hook_event_name": event_name,
                    "session_id": "direct-codex-session",
                    "cwd": str(tmp_path),
                }
            )
        ),
    )

    def must_not_load_capture_stack():
        raise AssertionError("inactive --auto hook loaded the capture implementation")

    monkeypatch.setattr(codex_hook_entry, "_load_capture_main", must_not_load_capture_stack)

    assert codex_hook_entry.main(["--auto"]) == 0
    assert not (tmp_path / ".execweave").exists()


def test_global_auto_hook_normalizes_capture_nonzero_to_success(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("EXECWEAVE_SEMANTIC_SIDECAR", str(tmp_path / "semantic.jsonl"))
    monkeypatch.setattr(codex_hook_entry, "_load_capture_main", lambda: lambda _argv: 1)

    assert codex_hook_entry.main(["--auto"]) == 0


def test_global_auto_hook_normalizes_unexpected_capture_exception_to_success(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("EXECWEAVE_SEMANTIC_SIDECAR", str(tmp_path / "semantic.jsonl"))

    def broken_capture(_argv: list[str]) -> int:
        raise KeyError("unexpected capture defect")

    monkeypatch.setattr(codex_hook_entry, "_load_capture_main", lambda: broken_capture)

    assert codex_hook_entry.main(["--auto"]) == 0


def test_explicit_strict_auto_preserves_nonzero_diagnostic_status(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("EXECWEAVE_SEMANTIC_SIDECAR", str(tmp_path / "semantic.jsonl"))
    monkeypatch.setattr(codex_hook_entry, "_load_capture_main", lambda: lambda _argv: 7)

    assert codex_hook_entry.main(["--auto", "--strict"]) == 7


def test_codex_console_script_uses_fail_open_global_entry() -> None:
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    scripts = project["project"]["scripts"]

    assert scripts["execweave-codex-hook"] == "execweave.codex_hook_entry:main"
