from __future__ import annotations

import json
import socket
import sys
import threading
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

import psutil
import pytest

import execweave
import execweave.collector as collector_module
from execweave.auto_specialized import auto_specialized_launch
from execweave.collector import RuntimeCollector
from execweave.live_core import run_live
from execweave.sink import JsonlSink


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_json(url: str, timeout: float = 8.0) -> dict[str, object]:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=0.5) as response:
                value = json.loads(response.read().decode("utf-8"))
            if isinstance(value, dict):
                return value
        except (URLError, OSError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
        time.sleep(0.05)
    raise AssertionError(f"endpoint did not become ready: {url}: {last_error}")


def _wait_for_child_ready(
    ready_path: Path,
    *,
    started_path: Path,
    thread: threading.Thread,
    errors: list[BaseException],
    result: dict[str, object],
    event_path: Path,
    timeout: float = 8.0,
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if ready_path.exists():
            return
        if errors or not thread.is_alive():
            events = event_path.read_text(encoding="utf-8") if event_path.exists() else ""
            raise AssertionError(
                "collector stopped before fake Ollama became ready: "
                f"started={started_path.exists()} errors={errors!r} "
                f"result={result!r} events={events}"
            )
        time.sleep(0.02)
    events = event_path.read_text(encoding="utf-8") if event_path.exists() else ""
    raise AssertionError(
        "fake Ollama did not become ready: "
        f"started={started_path.exists()} thread_alive={thread.is_alive()} "
        f"errors={errors!r} result={result!r} events={events}"
    )


def _write_fake_ollama_server(path: Path) -> None:
    path.write_text(
        r'''from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

Path(os.environ["FAKE_OLLAMA_STARTED"]).write_text("started", encoding="utf-8")
endpoint = urlsplit(os.environ["OLLAMA_HOST"])

class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def send_json(self, payload, status=200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/ps":
            self.send_json({"models": []})
            return
        self.send_json({"error": "not found"}, 404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        request = json.loads(self.rfile.read(length).decode("utf-8"))
        if self.path != "/api/chat":
            self.send_json({"error": "not found"}, 404)
            return
        self.send_json({
            "model": request.get("model", "tiny"),
            "message": {"role": "assistant", "content": "collector relay answer"},
            "done": True,
        })
        self.server.done = True

server = HTTPServer((endpoint.hostname, endpoint.port), Handler)
server.timeout = 0.2
server.done = False
Path(os.environ["FAKE_OLLAMA_READY"]).write_text("ready", encoding="utf-8")
while not server.done:
    server.handle_request()
server.server_close()
''',
        encoding="utf-8",
    )


def test_runtime_collector_ollama_serve_captures_independent_client(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    public_port = _free_loopback_port()
    public_endpoint = f"http://127.0.0.1:{public_port}"
    sidecar = tmp_path / "semantic.jsonl"
    event_path = tmp_path / "events.jsonl"
    started_path = tmp_path / "fake-ollama.started"
    ready_path = tmp_path / "fake-ollama.ready"
    fake_server = tmp_path / "fake_ollama_server.py"
    _write_fake_ollama_server(fake_server)

    monkeypatch.setenv("EXECWEAVE_SEMANTIC_SIDECAR", str(sidecar))
    monkeypatch.setenv("OLLAMA_HOST", public_endpoint)
    monkeypatch.setenv("FAKE_OLLAMA_STARTED", str(started_path))
    monkeypatch.setenv("FAKE_OLLAMA_READY", str(ready_path))
    monkeypatch.setattr(
        collector_module,
        "resolve_launch_command",
        lambda command: [sys.executable, str(fake_server)],
    )

    collector = RuntimeCollector(
        session_id="serve-integration",
        sink=JsonlSink(event_path),
        watch_root=tmp_path,
        poll_interval=0.02,
        collect_filesystem=False,
        collect_network=False,
    )
    result: dict[str, object] = {}
    errors: list[BaseException] = []

    def run_collector() -> None:
        try:
            result["return_code"] = collector.run(["ollama", "serve"])
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=run_collector, daemon=True)
    thread.start()

    _wait_for_child_ready(
        ready_path,
        started_path=started_path,
        thread=thread,
        errors=errors,
        result=result,
        event_path=event_path,
    )
    assert _wait_for_json(public_endpoint + "/api/ps") == {"models": []}

    request = Request(
        public_endpoint + "/api/chat",
        data=json.dumps(
            {
                "model": "tiny",
                "messages": [{"role": "user", "content": "outside process tree"}],
            }
        ).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=5) as response:
        response_payload = json.loads(response.read().decode("utf-8"))
    assert response_payload["message"]["content"] == "collector relay answer"

    thread.join(timeout=10)
    assert not thread.is_alive()
    assert errors == []
    assert result["return_code"] == 0

    semantic_rows = [
        json.loads(line)
        for line in sidecar.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    kinds = {
        (row.get("target", {}).get("attributes") or {}).get("content_kind")
        for row in semantic_rows
        if isinstance(row, dict)
    }
    assert "model_runtime.ollama.request_messages" in kinds
    assert "model_runtime.ollama.assistant_messages" in kinds
    assert any(
        row.get("attributes", {}).get("transport_relay_observed") is True
        for row in semantic_rows
        if isinstance(row, dict)
    )

    runtime_rows = [
        json.loads(line)
        for line in event_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    started = next(row for row in runtime_rows if row["event_type"] == "session.started")
    assert started["attributes"]["execweave_version"] == execweave.__version__


def test_ollama_serve_relay_bind_failure_is_not_silent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # A raw TCP listener is intentionally not an Ollama server: the /api/ps
    # preflight must not classify arbitrary port occupancy as a server to preserve.
    holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    holder.bind(("127.0.0.1", 0))
    holder.listen()
    port = int(holder.getsockname()[1])
    monkeypatch.setenv("EXECWEAVE_SEMANTIC_SIDECAR", str(tmp_path / "semantic.jsonl"))
    monkeypatch.setenv("OLLAMA_HOST", f"http://127.0.0.1:{port}")
    try:
        with pytest.raises(RuntimeError, match="could not reserve the Ollama endpoint"):
            with auto_specialized_launch(
                ["ollama", "serve"],
                server_relay=True,
            ):
                raise AssertionError("relay must not silently fall back")
    finally:
        holder.close()


def test_ctrl_c_still_materializes_live_artifacts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def interrupt_poll(self: RuntimeCollector, root: psutil.Process) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(RuntimeCollector, "_sample_process_tree", interrupt_poll)
    result = run_live(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        watch_root=tmp_path,
        output_dir=tmp_path / "run",
        collect_filesystem=False,
        collect_network=False,
        open_browser=False,
        linger_seconds=0,
    )

    assert result.return_code == 130
    assert result.graph.exists()
    assert result.viewer.exists()
    assert result.materialized_event_stream.exists()

    rows = [
        json.loads(line)
        for line in result.event_stream.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    finished = next(row for row in rows if row["event_type"] == "session.finished")
    assert finished["attributes"]["return_code"] == 130
    assert finished["attributes"]["interrupted"] is True
    assert finished["attributes"]["execweave_version"] == execweave.__version__

    launched = next(row for row in rows if row["event_type"] == "process.started")
    pid = int(launched["target"]["attributes"]["pid"])
    assert not psutil.pid_exists(pid)
