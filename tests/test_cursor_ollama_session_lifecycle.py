from __future__ import annotations

import json
import os
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

import pytest

import execweave.command as command_module
from execweave.auto_specialized import auto_specialized_launch
from execweave.command import resolve_launch_command


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.mark.skipif(os.name != "nt", reason="Windows Cursor shim regression")
def test_windows_cursor_path_shim_prefers_desktop_from_same_install(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    install = tmp_path / "custom-cursor"
    bin_dir = install / "resources" / "app" / "bin"
    bin_dir.mkdir(parents=True)
    shim = bin_dir / "cursor.cmd"
    shim.write_text("@echo off\r\n", encoding="utf-8")
    desktop = install / "Cursor.exe"
    desktop.write_bytes(b"MZ")

    monkeypatch.setattr(
        command_module.shutil,
        "which",
        lambda executable, path=None: str(shim) if executable == "cursor" else None,
    )
    monkeypatch.setattr(command_module, "_cursor_desktop_candidates", lambda: [])

    assert resolve_launch_command(["cursor"]) == [str(desktop.resolve())]


@pytest.mark.skipif(os.name != "nt", reason="Windows Cursor shim regression")
def test_explicit_cursor_launcher_path_is_not_rewritten(tmp_path: Path) -> None:
    install = tmp_path / "custom-cursor"
    bin_dir = install / "resources" / "app" / "bin"
    bin_dir.mkdir(parents=True)
    shim = bin_dir / "cursor.cmd"
    shim.write_text("@echo off\r\n", encoding="utf-8")
    desktop = install / "Cursor.exe"
    desktop.write_bytes(b"MZ")

    assert resolve_launch_command([str(shim), "--version"])[0] == str(shim.resolve())


class _IndependentOllamaHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return

    def do_POST(self) -> None:
        if self.path != "/api/chat":
            self.send_response(404)
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length", "0"))
        request = json.loads(self.rfile.read(length).decode("utf-8"))
        payload = {
            "model": request.get("model", "tiny"),
            "message": {"role": "assistant", "content": "serve relay answer"},
            "done": True,
        }
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def test_ollama_serve_relay_captures_client_outside_process_tree(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    public_port = _free_loopback_port()
    public_endpoint = f"http://127.0.0.1:{public_port}"
    sidecar = tmp_path / "events.semantic.jsonl"
    monkeypatch.setenv("EXECWEAVE_SEMANTIC_SIDECAR", str(sidecar))
    monkeypatch.setenv("OLLAMA_HOST", public_endpoint)

    upstream: ThreadingHTTPServer | None = None
    thread: threading.Thread | None = None
    try:
        with auto_specialized_launch(
            ["ollama", "serve"],
            server_relay=True,
        ) as environment:
            assert environment["OLLAMA_HOST"] != public_endpoint
            upstream_port = int(environment["OLLAMA_HOST"].rsplit(":", 1)[1])
            upstream = ThreadingHTTPServer(
                ("127.0.0.1", upstream_port),
                _IndependentOllamaHandler,
            )
            thread = threading.Thread(target=upstream.serve_forever, daemon=True)
            thread.start()

            # This request deliberately uses the original/public endpoint rather
            # than the child environment returned above. It models `ollama run`,
            # an SDK, or curl started from another terminal after `ollama serve`.
            request = Request(
                public_endpoint + "/api/chat",
                data=json.dumps(
                    {
                        "model": "tiny",
                        "messages": [{"role": "user", "content": "outside client"}],
                    }
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(request, timeout=5) as response:
                result = json.loads(response.read().decode("utf-8"))
            assert result["message"]["content"] == "serve relay answer"

        rows = [
            json.loads(line)
            for line in sidecar.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        kinds = {
            (row.get("target", {}).get("attributes") or {}).get("content_kind")
            for row in rows
            if isinstance(row, dict)
        }
        assert "model_runtime.ollama.request_messages" in kinds
        assert "model_runtime.ollama.assistant_messages" in kinds
        assert any(
            row.get("attributes", {}).get("transport_relay_observed") is True
            for row in rows
            if isinstance(row, dict)
        )
    finally:
        if upstream is not None:
            upstream.shutdown()
            upstream.server_close()
        if thread is not None:
            thread.join(timeout=2)


def test_ollama_serve_relay_does_not_change_remote_bind(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("EXECWEAVE_SEMANTIC_SIDECAR", str(tmp_path / "semantic.jsonl"))
    monkeypatch.setenv("OLLAMA_HOST", "http://192.0.2.10:11434")

    with auto_specialized_launch(
        ["ollama", "serve"],
        server_relay=True,
    ) as environment:
        assert environment["OLLAMA_HOST"] == "http://192.0.2.10:11434"
