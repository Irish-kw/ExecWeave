from __future__ import annotations

import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import execweave.auto_specialized as auto_module
import execweave.collector as collector_module
from execweave.live import run_live


class _OllamaHandler(BaseHTTPRequestHandler):
    payload: dict[str, object] = {"models": []}

    def log_message(self, format: str, *args: object) -> None:
        return

    def do_GET(self) -> None:
        if self.path != "/api/ps":
            self.send_response(404)
            self.end_headers()
            return
        body = json.dumps(type(self).payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class _ModelsHandler(BaseHTTPRequestHandler):
    payload: dict[str, object] = {"data": []}

    def log_message(self, format: str, *args: object) -> None:
        return

    def do_GET(self) -> None:
        if self.path != "/v1/models":
            self.send_response(404)
            self.end_headers()
            return
        body = json.dumps(type(self).payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _wait_until(predicate, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("condition did not become true before timeout")


def _line_count(path: Path) -> int:
    if not path.exists():
        return 0
    return len(path.read_text(encoding="utf-8").splitlines())


def _start_server(
    handler: type[BaseHTTPRequestHandler],
) -> tuple[ThreadingHTTPServer, threading.Thread]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _start_ollama_server(
    payload: dict[str, object],
) -> tuple[ThreadingHTTPServer, threading.Thread]:
    _OllamaHandler.payload = payload
    return _start_server(_OllamaHandler)


def _start_models_server(
    payload: dict[str, object],
) -> tuple[ThreadingHTTPServer, threading.Thread]:
    _ModelsHandler.payload = payload
    return _start_server(_ModelsHandler)


def _stop_server(server: ThreadingHTTPServer, thread: threading.Thread) -> None:
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def test_ollama_serve_detection_is_cross_platform() -> None:
    assert auto_module._is_ollama_serve(["ollama", "serve"])
    assert auto_module._is_ollama_serve([r"C:\\Tools\\ollama.exe", "SERVE"])
    assert auto_module._is_ollama_serve(["/usr/local/bin/ollama", "serve"])
    assert not auto_module._is_ollama_serve(["ollama", "run", "model"])
    assert not auto_module._is_ollama_serve(["python", "server.py"])


def test_model_server_detection_covers_llamacpp_and_vllm() -> None:
    llama = auto_module._probe_spec(
        ["llama-server", "--host", "0.0.0.0", "--port", "18080"]
    )
    assert llama is not None
    assert llama.runtime == "llamacpp"
    assert llama.endpoint == "http://127.0.0.1:18080"

    vllm = auto_module._probe_spec(
        ["vllm", "serve", "model-a", "--host=localhost", "--port=18000"]
    )
    assert vllm is not None
    assert vllm.runtime == "vllm"
    assert vllm.endpoint == "http://localhost:18000"

    module = auto_module._probe_spec(
        [
            sys.executable,
            "-m",
            "vllm.entrypoints.openai.api_server",
            "--port",
            "18001",
        ]
    )
    assert module is not None
    assert module.runtime == "vllm"
    assert module.endpoint == "http://127.0.0.1:18001"

    assert auto_module._probe_spec(
        ["llama-server", "--host", "192.0.2.10", "--port", "18080"]
    ) is None
    assert auto_module._probe_spec(
        ["vllm", "serve", "model-a", "--host", "example.com"]
    ) is None


def test_ollama_auto_probe_endpoint_is_loopback_only(monkeypatch) -> None:
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    assert auto_module._ollama_endpoint_from_environment() == "http://127.0.0.1:11434"

    monkeypatch.setenv("OLLAMA_HOST", "localhost")
    assert auto_module._ollama_endpoint_from_environment() == "http://localhost:11434"

    monkeypatch.setenv("OLLAMA_HOST", "127.0.0.1:12000")
    assert auto_module._ollama_endpoint_from_environment() == "http://127.0.0.1:12000"

    monkeypatch.setenv("OLLAMA_HOST", "http://0.0.0.0:13000")
    assert auto_module._ollama_endpoint_from_environment() == "http://127.0.0.1:13000"

    for value in (
        "http://example.com:11434",
        "https://127.0.0.1:11434",
        "http://user@127.0.0.1:11434",
        "http://127.0.0.1:11434/api",
    ):
        monkeypatch.setenv("OLLAMA_HOST", value)
        assert auto_module._ollama_endpoint_from_environment() is None


def test_ollama_live_probe_appends_only_new_or_changed_model_evidence(
    monkeypatch,
    tmp_path: Path,
) -> None:
    server, thread = _start_ollama_server(
        {
            "models": [
                {
                    "name": "model-a:latest",
                    "size": 100,
                    "size_vram": 80,
                    "details": {"parameter_size": "7B", "quantization_level": "Q4_K_M"},
                }
            ]
        }
    )
    port = server.server_address[1]

    sidecar = tmp_path / "semantic.jsonl"
    monkeypatch.setenv("EXECWEAVE_SEMANTIC_SIDECAR", str(sidecar))
    monkeypatch.setenv("OLLAMA_HOST", f"127.0.0.1:{port}")
    monkeypatch.setattr(auto_module, "_PROBE_STARTUP_GRACE_SECONDS", 0.01)
    monkeypatch.setattr(auto_module, "_PROBE_INTERVAL_SECONDS", 0.02)
    monkeypatch.setattr(auto_module, "_PROBE_TIMEOUT_SECONDS", 0.20)

    try:
        with auto_module.auto_specialized_probe(["ollama", "serve"]):
            _wait_until(lambda: _line_count(sidecar) == 1)
            time.sleep(0.08)
            assert _line_count(sidecar) == 1

            _OllamaHandler.payload = {
                "models": [
                    {
                        "name": "model-a:latest",
                        "size": 100,
                        "size_vram": 80,
                        "details": {
                            "parameter_size": "7B",
                            "quantization_level": "Q4_K_M",
                        },
                    },
                    {
                        "name": "model-b:latest",
                        "size": 200,
                        "size_vram": 160,
                        "details": {"parameter_size": "14B"},
                    },
                ]
            }
            _wait_until(lambda: _line_count(sidecar) == 2)

        records = [json.loads(line) for line in sidecar.read_text(encoding="utf-8").splitlines()]
        assert [record["relation"] for record in records] == ["LOADED_MODEL", "LOADED_MODEL"]
        assert {record["target"]["name"] for record in records} == {
            "model-a:latest",
            "model-b:latest",
        }
        assert all(record["attributes"]["provider"] == "ollama" for record in records)
    finally:
        _stop_server(server, thread)


def test_run_live_automatically_materializes_ollama_loaded_model(
    monkeypatch,
    tmp_path: Path,
) -> None:
    server, thread = _start_ollama_server(
        {
            "models": [
                {
                    "name": "live-model:latest",
                    "size": 123,
                    "size_vram": 100,
                    "details": {"parameter_size": "8B"},
                }
            ]
        }
    )
    port = server.server_address[1]
    monkeypatch.setenv("OLLAMA_HOST", f"127.0.0.1:{port}")
    monkeypatch.setattr(auto_module, "_PROBE_STARTUP_GRACE_SECONDS", 0.01)
    monkeypatch.setattr(auto_module, "_PROBE_INTERVAL_SECONDS", 0.02)
    monkeypatch.setattr(auto_module, "_PROBE_TIMEOUT_SECONDS", 0.20)
    monkeypatch.setattr(
        collector_module,
        "resolve_launch_command",
        lambda command: [sys.executable, "-c", "import time; time.sleep(0.25)"],
    )

    try:
        result = run_live(
            ["ollama", "serve"],
            watch_root=tmp_path,
            output_dir=tmp_path / "ollama-live",
            poll_interval=0.03,
            collect_filesystem=False,
            collect_network=False,
            port=0,
            open_browser=False,
            linger_seconds=0,
        )
        assert result.return_code == 0
        assert result.semantic_sidecar.exists()
        graph = json.loads(result.graph.read_text(encoding="utf-8"))
        assert graph["source_path"].endswith("events.semantic.jsonl")
        assert any(edge["relation"] == "LOADED_MODEL" for edge in graph["edges"])
        assert any(
            node.get("type") == "model" and node.get("name") == "live-model:latest"
            for node in graph["nodes"]
        )
    finally:
        _stop_server(server, thread)


def test_run_live_auto_probes_llamacpp_and_vllm_catalogs(
    monkeypatch,
    tmp_path: Path,
) -> None:
    server, thread = _start_models_server({"data": [{"id": "catalog-model", "owned_by": "local"}]})
    port = server.server_address[1]
    monkeypatch.setattr(auto_module, "_PROBE_STARTUP_GRACE_SECONDS", 0.01)
    monkeypatch.setattr(auto_module, "_PROBE_INTERVAL_SECONDS", 0.02)
    monkeypatch.setattr(auto_module, "_PROBE_TIMEOUT_SECONDS", 0.20)
    monkeypatch.setattr(
        collector_module,
        "resolve_launch_command",
        lambda command: [sys.executable, "-c", "import time; time.sleep(0.25)"],
    )

    cases = (
        (
            "llamacpp",
            ["llama-server", "--host", "127.0.0.1", "--port", str(port)],
        ),
        (
            "vllm",
            ["vllm", "serve", "model-a", "--host", "0.0.0.0", "--port", str(port)],
        ),
    )
    try:
        for runtime, command in cases:
            result = run_live(
                command,
                watch_root=tmp_path,
                output_dir=tmp_path / f"{runtime}-live",
                poll_interval=0.03,
                collect_filesystem=False,
                collect_network=False,
                port=0,
                open_browser=False,
                linger_seconds=0,
            )
            assert result.return_code == 0
            graph = json.loads(result.graph.read_text(encoding="utf-8"))
            assert graph["source_path"].endswith("events.semantic.jsonl")
            assert any(edge["relation"] == "SERVES_MODEL" for edge in graph["edges"])
            assert any(
                node.get("type") == "model" and node.get("name") == "catalog-model"
                for node in graph["nodes"]
            )
            records = [
                json.loads(line)
                for line in result.semantic_sidecar.read_text(encoding="utf-8").splitlines()
            ]
            assert records
            assert all(record["attributes"]["provider"] == runtime for record in records)
    finally:
        _stop_server(server, thread)


def test_startup_grace_does_not_claim_preexisting_ollama_server(
    monkeypatch,
    tmp_path: Path,
) -> None:
    server, thread = _start_ollama_server({"models": [{"name": "preexisting:latest"}]})
    port = server.server_address[1]
    monkeypatch.setenv("OLLAMA_HOST", f"127.0.0.1:{port}")
    monkeypatch.setattr(auto_module, "_PROBE_STARTUP_GRACE_SECONDS", 0.30)
    monkeypatch.setattr(auto_module, "_PROBE_INTERVAL_SECONDS", 0.02)
    monkeypatch.setattr(auto_module, "_PROBE_TIMEOUT_SECONDS", 0.20)
    monkeypatch.setattr(
        collector_module,
        "resolve_launch_command",
        lambda command: [sys.executable, "-c", "raise SystemExit(2)"],
    )

    try:
        result = run_live(
            ["ollama", "serve"],
            watch_root=tmp_path,
            output_dir=tmp_path / "failed-ollama-live",
            poll_interval=0.03,
            collect_filesystem=False,
            collect_network=False,
            port=0,
            open_browser=False,
            linger_seconds=0,
        )
        assert result.return_code == 2
        assert result.materialized_event_stream == result.event_stream
        assert not result.semantic_sidecar.exists() or result.semantic_sidecar.stat().st_size == 0
        graph = json.loads(result.graph.read_text(encoding="utf-8"))
        assert all(edge["relation"] != "LOADED_MODEL" for edge in graph["edges"])
    finally:
        _stop_server(server, thread)


def test_auto_probe_is_inactive_without_live_sidecar(monkeypatch) -> None:
    monkeypatch.delenv("EXECWEAVE_SEMANTIC_SIDECAR", raising=False)

    def fail_probe(**kwargs) -> None:
        raise AssertionError("probe must not start without a run-specific sidecar")

    monkeypatch.setattr(auto_module, "_run_model_probe", fail_probe)
    with auto_module.auto_specialized_probe(["ollama", "serve"]):
        pass
