from __future__ import annotations

import io
import json
import os
import sys
from pathlib import Path

import execweave.command as command_module
from execweave.agent_bootstrap import bootstrap_supported_agent, supported_agent
from execweave.antigravity_hook_cli import antigravity_hook_config, main as antigravity_hook_main
from execweave.collector import infer_agent_name
from execweave.command import resolve_launch_command


def _executable(path: Path) -> Path:
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    if os.name != "nt":
        path.chmod(0o755)
    return path


def test_antigravity_names_are_recognized_as_current_agent() -> None:
    assert supported_agent(["agy"]) == "antigravity"
    assert supported_agent(["antigravity"]) == "antigravity"
    assert infer_agent_name(["agy"]) == "Antigravity"
    assert infer_agent_name(["antigravity"]) == "Antigravity"


def test_antigravity_friendly_alias_resolves_to_agy(monkeypatch, tmp_path: Path) -> None:
    agy = _executable(tmp_path / ("agy.exe" if os.name == "nt" else "agy"))

    def fake_which(executable: str, path: str | None = None) -> str | None:
        del path
        if executable == "agy":
            return str(agy)
        return None

    monkeypatch.setattr(command_module.shutil, "which", fake_which)

    assert resolve_launch_command(["antigravity", "--version"]) == [
        str(agy.resolve()),
        "--version",
    ]


def test_cursor_falls_back_to_desktop_binary_when_no_path_launcher(
    monkeypatch,
    tmp_path: Path,
) -> None:
    cursor = _executable(tmp_path / ("Cursor.exe" if os.name == "nt" else "Cursor"))
    monkeypatch.setattr(command_module.shutil, "which", lambda executable, path=None: None)
    monkeypatch.setattr(command_module, "_cursor_desktop_candidates", lambda: [cursor])

    assert resolve_launch_command(["cursor", "--reuse-window"]) == [
        str(cursor.resolve()),
        "--reuse-window",
    ]


def test_antigravity_bootstrap_uses_named_passive_hook_schema(tmp_path: Path) -> None:
    target = tmp_path / ".gemini" / "config" / "hooks.json"
    target.parent.mkdir(parents=True)
    target.write_text(
        json.dumps({"user-hook": {"PostInvocation": [{"command": "user-command"}]}}),
        encoding="utf-8",
    )

    first = bootstrap_supported_agent(["agy"], home=tmp_path, environment={})
    second = bootstrap_supported_agent(["agy"], home=tmp_path, environment={})

    assert first.provider == "antigravity"
    assert first.status == "active"
    assert first.changed is True
    assert first.path == str(target)
    assert second.status == "active"
    assert second.changed is False

    payload = json.loads(target.read_text(encoding="utf-8"))
    assert "user-hook" in payload
    hook = payload["execweave-observability"]
    assert "PostToolUse" in hook
    assert "PreInvocation" in hook
    assert "PostInvocation" in hook
    assert "PreToolUse" not in hook
    assert "execweave-antigravity-hook" in json.dumps(hook)


def test_antigravity_config_does_not_auto_approve_tool_permissions() -> None:
    hook = antigravity_hook_config()["execweave-observability"]
    assert "PreToolUse" not in hook
    assert hook["PostToolUse"][0]["matcher"] == "*"


def test_antigravity_auto_hook_is_inert_without_live_sidecar(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("EXECWEAVE_SEMANTIC_SIDECAR", raising=False)
    monkeypatch.setattr(sys, "stdin", io.StringIO("must-not-be-read"))

    assert antigravity_hook_main(["--auto", "--event", "PostToolUse"]) == 0
    captured = capsys.readouterr()
    assert captured.out == "{}\n"
    assert captured.err == ""
    assert not (tmp_path / ".execweave").exists()


def test_antigravity_post_tool_hook_emits_provider_evidence(
    monkeypatch,
    tmp_path: Path,
) -> None:
    sidecar = tmp_path / "semantic.jsonl"
    monkeypatch.setenv("EXECWEAVE_SEMANTIC_SIDECAR", str(sidecar))
    payload = {
        "conversationId": "conversation-1",
        "workspacePaths": [str(tmp_path)],
        "transcriptPath": str(tmp_path / "transcript.jsonl"),
        "artifactDirectoryPath": str(tmp_path / "artifacts"),
        "modelName": "gemini-test",
        "stepIdx": 5,
        "toolCall": {
            "name": "run_command",
            "args": {"CommandLine": "echo hello", "Cwd": str(tmp_path)},
        },
        "error": "",
    }
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))

    assert antigravity_hook_main(["--auto", "--event", "PostToolUse"]) == 0

    records = [json.loads(line) for line in sidecar.read_text(encoding="utf-8").splitlines()]
    assert records
    assert any(
        isinstance(record.get("attributes"), dict)
        and record["attributes"].get("provider") == "antigravity"
        for record in records
    )
    assert any(record.get("relation") == "USES_TOOL" for record in records)
    assert any(record.get("relation") == "DECLARED_COMMAND" for record in records)
