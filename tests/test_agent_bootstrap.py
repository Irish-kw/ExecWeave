from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

from execweave.agent_bootstrap import (
    AgentBootstrapResult,
    bootstrap_supported_agent,
    supported_agent,
)
from execweave.claude_hook_cli import main as claude_hook_main
from execweave.codex_hook_cli import main as codex_hook_main
from execweave.cursor_hook_cli import main as cursor_hook_main
from execweave.entry import _live_command
from execweave.opencode_hook_cli import main as opencode_hook_main
from execweave.opencode_plugin_cli import plugin_text


@pytest.mark.parametrize(
    ("command", "provider"),
    [
        (["claude"], "claude"),
        (["C:\\Tools\\codex.exe"], "codex"),
        (["/opt/cursor"], "cursor"),
        (["opencode.bat"], "opencode"),
        (["python", "agent.py"], None),
    ],
)
def test_supported_agent_normalizes_platform_launchers(
    command: list[str],
    provider: str | None,
) -> None:
    assert supported_agent(command) == provider


@pytest.mark.parametrize(
    ("provider", "expected_relative", "marker"),
    [
        ("claude", Path(".claude/settings.json"), "execweave-claude-hook --auto"),
        ("codex", Path(".codex/hooks.json"), "execweave-codex-hook --auto"),
        ("cursor", Path(".cursor/hooks.json"), "execweave-cursor-hook --auto"),
    ],
)
def test_json_bootstrap_is_idempotent_and_preserves_existing_configuration(
    tmp_path: Path,
    provider: str,
    expected_relative: Path,
    marker: str,
) -> None:
    target = tmp_path / expected_relative
    target.parent.mkdir(parents=True)
    original = {
        "unrelated": {"keep": True},
        "hooks": {"UserDefinedEvent": [{"command": "user-hook"}]},
    }
    target.write_text(json.dumps(original), encoding="utf-8")

    first = bootstrap_supported_agent([provider], home=tmp_path, environment={})
    second = bootstrap_supported_agent([provider], home=tmp_path, environment={})

    assert first == AgentBootstrapResult(
        provider=provider,
        status="active",
        path=str(target),
        changed=True,
        detail="specialized hook/plugin bootstrap is configured",
    )
    assert second.status == "active"
    assert second.changed is False
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["unrelated"] == {"keep": True}
    assert payload["hooks"]["UserDefinedEvent"] == [{"command": "user-hook"}]
    serialized = json.dumps(payload, sort_keys=True)
    assert marker in serialized
    assert serialized.count(marker) >= 1


def test_provider_environment_overrides_are_honored(tmp_path: Path) -> None:
    claude_root = tmp_path / "claude-config"
    codex_root = tmp_path / "codex-home"
    environment = {
        "CLAUDE_CONFIG_DIR": str(claude_root),
        "CODEX_HOME": str(codex_root),
    }

    claude = bootstrap_supported_agent(["claude"], home=tmp_path, environment=environment)
    codex = bootstrap_supported_agent(["codex"], home=tmp_path, environment=environment)

    assert claude.path == str(claude_root / "settings.json")
    assert codex.path == str(codex_root / "hooks.json")


def test_invalid_existing_json_fails_open_without_overwrite(tmp_path: Path) -> None:
    target = tmp_path / ".claude" / "settings.json"
    target.parent.mkdir(parents=True)
    original = b"{ definitely-not-json"
    target.write_bytes(original)

    result = bootstrap_supported_agent(["claude"], home=tmp_path, environment={})

    assert result.status == "bootstrap_failed"
    assert result.changed is False
    assert target.read_bytes() == original
    assert result.detail is not None
    assert len(result.detail) <= 240


def test_claude_disable_all_hooks_is_reported_as_unavailable(tmp_path: Path) -> None:
    target = tmp_path / ".claude" / "settings.json"
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps({"disableAllHooks": True}), encoding="utf-8")

    result = bootstrap_supported_agent(["claude"], home=tmp_path, environment={})

    assert result.status == "unavailable"
    assert result.provider == "claude"
    assert result.detail == "Claude hooks are disabled by disableAllHooks"


def test_unknown_command_does_not_modify_any_provider_configuration(tmp_path: Path) -> None:
    result = bootstrap_supported_agent(
        ["python", "my_agent.py"],
        home=tmp_path,
        environment={},
    )

    assert result.status == "unavailable"
    assert result.provider is None
    assert list(tmp_path.iterdir()) == []


def test_opencode_bootstrap_uses_global_plugin_and_is_idempotent(tmp_path: Path) -> None:
    result = bootstrap_supported_agent(["opencode"], home=tmp_path, environment={})
    second = bootstrap_supported_agent(["opencode"], home=tmp_path, environment={})
    target = tmp_path / ".config" / "opencode" / "plugins" / "execweave.ts"

    assert result.status == "active"
    assert result.changed is True
    assert second.changed is False
    assert result.path == str(target)
    text = target.read_text(encoding="utf-8")
    assert 'Bun.spawn(["execweave-opencode-hook", "--auto"], {' in text
    assert plugin_text(("execweave-opencode-hook", "--auto")) == text
    assert not (tmp_path / ".opencode").exists()


@pytest.mark.parametrize(
    ("main", "expected_stdout"),
    [
        (claude_hook_main, ""),
        (codex_hook_main, ""),
        (cursor_hook_main, "{}\n"),
        (opencode_hook_main, "{}\n"),
    ],
)
def test_auto_installed_hooks_are_inert_without_execweave_sidecar(
    monkeypatch,
    tmp_path: Path,
    capsys,
    main,
    expected_stdout: str,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("EXECWEAVE_SEMANTIC_SIDECAR", raising=False)
    monkeypatch.setattr(sys, "stdin", io.StringIO("not-json-and-must-not-be-read"))

    assert main(["--auto"]) == 0
    captured = capsys.readouterr()
    assert captured.out == expected_stdout
    assert captured.err == ""
    assert not (tmp_path / ".execweave").exists()


def _invoke_auto_hook(monkeypatch, main, payload: dict[str, object]) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    assert main(["--auto"]) == 0


def test_auto_hooks_still_emit_when_live_sidecar_is_present(monkeypatch, tmp_path: Path) -> None:
    sidecar = tmp_path / "semantic.jsonl"
    monkeypatch.setenv("EXECWEAVE_SEMANTIC_SIDECAR", str(sidecar))

    _invoke_auto_hook(
        monkeypatch,
        claude_hook_main,
        {
            "session_id": "claude-session",
            "cwd": str(tmp_path),
            "hook_event_name": "SessionStart",
            "model": "claude-test",
        },
    )
    _invoke_auto_hook(
        monkeypatch,
        codex_hook_main,
        {
            "session_id": "codex-session",
            "cwd": str(tmp_path),
            "hook_event_name": "SessionStart",
            "model": "gpt-test",
            "source": "startup",
        },
    )
    _invoke_auto_hook(
        monkeypatch,
        cursor_hook_main,
        {
            "conversation_id": "cursor-conversation",
            "generation_id": "cursor-generation",
            "session_id": "cursor-session",
            "hook_event_name": "sessionStart",
            "cwd": str(tmp_path),
            "workspace_roots": [str(tmp_path)],
            "model": "claude-test",
            "model_id": "claude-test-id",
        },
    )
    _invoke_auto_hook(
        monkeypatch,
        opencode_hook_main,
        {
            "hook_event_name": "chat.message",
            "sessionID": "opencode-session",
            "messageID": "message-1",
            "agent": "build",
            "model": {"providerID": "openrouter", "modelID": "gpt-test"},
            "cwd": str(tmp_path),
        },
    )

    records = [
        json.loads(line) for line in sidecar.read_text(encoding="utf-8").splitlines()
    ]
    providers = {
        record.get("attributes", {}).get("provider")
        for record in records
        if isinstance(record.get("attributes"), dict)
    }
    assert {"claude", "codex", "cursor", "opencode"}.issubset(providers)


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (["live", "--open", "--", "claude"], ["claude"]),
        (["live", "--port", "0", "codex"], ["codex"]),
        (["record", "--", "claude"], []),
        (["live", "--unknown", "claude"], []),
    ],
)
def test_live_command_extracts_only_live_launch_command(
    argv: list[str],
    expected: list[str],
) -> None:
    assert _live_command(argv) == expected
