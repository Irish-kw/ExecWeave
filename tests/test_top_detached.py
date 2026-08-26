from __future__ import annotations

from types import SimpleNamespace

import execweave.top as top_module
import execweave.top_cli as top_cli_module


def test_run_top_launches_dashboard_in_separate_terminal(monkeypatch, tmp_path) -> None:
    observed: dict[str, object] = {}

    def fake_launch(live_url: str, *, command: list[str], refresh_seconds: float) -> bool:
        observed["live_url"] = live_url
        observed["command"] = command
        observed["refresh_seconds"] = refresh_seconds
        return True

    def fake_run_live(command, **kwargs):
        observed["run_command"] = list(command)
        kwargs["announce"]("http://127.0.0.1:43210/")
        return SimpleNamespace(return_code=0)

    monkeypatch.setattr(top_module, "launch_dashboard_terminal", fake_launch)
    monkeypatch.setattr(top_module, "run_live", fake_run_live)

    result = top_module.run_top(
        ["codex"],
        watch_root=tmp_path,
        refresh_seconds=0.25,
    )

    assert result.return_code == 0
    assert observed["run_command"] == ["codex"]
    assert observed["live_url"] == "http://127.0.0.1:43210/"
    assert observed["command"] == ["codex"]
    assert observed["refresh_seconds"] == 0.25


def test_dashboard_attach_command_reenters_top_as_client() -> None:
    argv = top_module._dashboard_attach_argv(
        "http://127.0.0.1:12345/",
        command=["codex", "--model", "gpt-test"],
        refresh_seconds=0.5,
    )
    assert argv[1:4] == ["-m", "execweave", "top"]
    assert "--attach" in argv
    assert "http://127.0.0.1:12345/" in argv
    assert "--attach-command-json" in argv


def test_top_attach_mode_does_not_launch_agent(monkeypatch) -> None:
    observed: dict[str, object] = {}

    def fake_attached(live_url: str, *, command: list[str], refresh_seconds: float) -> None:
        observed["live_url"] = live_url
        observed["command"] = command
        observed["refresh_seconds"] = refresh_seconds

    def fail_run_top(*args, **kwargs):
        raise AssertionError("attach client must not launch the Agent again")

    monkeypatch.setattr(top_cli_module, "run_attached_top", fake_attached)
    monkeypatch.setattr(top_cli_module, "run_top", fail_run_top)

    result = top_cli_module.main(
        [
            "--attach",
            "http://127.0.0.1:8765/",
            "--attach-command-json",
            '["codex"]',
            "--refresh",
            "0.2",
        ]
    )

    assert result == 0
    assert observed == {
        "live_url": "http://127.0.0.1:8765/",
        "command": ["codex"],
        "refresh_seconds": 0.2,
    }
