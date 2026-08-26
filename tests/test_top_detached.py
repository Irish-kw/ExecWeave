from __future__ import annotations

import io
import threading
from pathlib import Path
from types import SimpleNamespace
from urllib.request import Request

import pytest

import execweave.top as top_module
import execweave.top_cli as top_cli_module


def test_run_top_launches_dashboard_in_separate_terminal(monkeypatch, tmp_path) -> None:
    observed: dict[str, object] = {}

    def fake_launch(
        live_url: str,
        *,
        token_file: Path,
        command: list[str],
        refresh_seconds: float,
    ) -> bool:
        observed["live_url"] = live_url
        observed["token_file"] = token_file
        observed["token"] = token_file.read_text(encoding="utf-8")
        observed["command"] = command
        observed["refresh_seconds"] = refresh_seconds
        return True

    def fake_run_live(command, **kwargs):
        observed["run_command"] = list(command)
        kwargs["announce"]("http://127.0.0.1:43210/?t=secret-token")
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
    assert observed["token"] == "secret-token"
    assert observed["command"] == ["codex"]
    assert observed["refresh_seconds"] == 0.25
    assert not observed["token_file"].exists()


def test_dashboard_attach_command_keeps_token_out_of_argv(tmp_path) -> None:
    token_file = tmp_path / "execweave-top-test.token"
    argv = top_module._dashboard_attach_argv(
        "http://127.0.0.1:12345/",
        token_file=token_file,
        command=["codex", "--model", "gpt-test"],
        refresh_seconds=0.5,
    )
    assert argv[1:4] == ["-m", "execweave", "top"]
    assert "--attach" in argv
    assert "http://127.0.0.1:12345/" in argv
    assert "--attach-token-file" in argv
    assert str(token_file) in argv
    assert "secret-token" not in argv
    assert "--attach-command-json" in argv


def test_top_attach_mode_consumes_token_file_and_does_not_launch_agent(monkeypatch) -> None:
    observed: dict[str, object] = {}
    token_file = top_module._create_attach_token_file("secret-token")

    def fake_attached(
        live_url: str,
        *,
        token: str,
        command: list[str],
        refresh_seconds: float,
    ) -> None:
        observed["live_url"] = live_url
        observed["token"] = token
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
            "--attach-token-file",
            str(token_file),
            "--attach-command-json",
            '["codex"]',
            "--refresh",
            "0.2",
        ]
    )

    assert result == 0
    assert observed == {
        "live_url": "http://127.0.0.1:8765/",
        "token": "secret-token",
        "command": ["codex"],
        "refresh_seconds": 0.2,
    }
    assert not token_file.exists()


def test_terminal_top_client_sends_token_as_header(monkeypatch) -> None:
    observed: dict[str, object] = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return b'{"kind":"noop","sequence":0,"live_finished":false}'

    def fake_urlopen(request, timeout):
        assert isinstance(request, Request)
        observed["url"] = request.full_url
        observed["token"] = request.get_header("X-execweave-token")
        observed["timeout"] = timeout
        return Response()

    monkeypatch.setattr(top_module, "urlopen", fake_urlopen)
    client = top_module.TerminalTopClient(
        live_url="http://127.0.0.1:8765/",
        token="secret-token",
        command=["codex"],
        refresh_seconds=0.25,
        stream=io.StringIO(),
        stop_event=threading.Event(),
    )

    payload = client._fetch()
    assert payload["kind"] == "noop"
    assert observed["url"] == "http://127.0.0.1:8765/live.json?after=-1"
    assert observed["token"] == "secret-token"


def test_consume_attach_token_file_rejects_arbitrary_path(tmp_path) -> None:
    path = tmp_path / "not-an-execweave-token.txt"
    path.write_text("secret-token", encoding="utf-8")
    with pytest.raises(ValueError):
        top_module._consume_attach_token_file(path)
    assert path.exists()


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1:8765/",
        "http://example.com:8765/",
        "http://127.0.0.1/",
        "http://127.0.0.1:8765/live.json",
        "http://user@127.0.0.1:8765/",
        "http://127.0.0.1:8765/?t=secret-token",
    ],
)
def test_top_attach_rejects_nonlocal_or_nonbase_urls(url: str) -> None:
    with pytest.raises(ValueError):
        top_cli_module._validate_attach_url(url)


def test_top_attach_accepts_loopback_forms() -> None:
    assert top_cli_module._validate_attach_url("http://127.0.0.1:8765/")
    assert top_cli_module._validate_attach_url("http://localhost:8765/")
    assert top_cli_module._validate_attach_url("http://[::1]:8765/")
