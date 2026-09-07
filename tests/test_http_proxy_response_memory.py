from __future__ import annotations

import gc
import http.client
import json
import threading
import time
import tracemalloc
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from execweave.http_proxy import ProxyConfig, create_proxy_server

_FRAME_COUNT = 256
_PADDING_CHARS = 64 * 1024
_MAX_TRACED_PEAK_BYTES = 12 * 1024 * 1024


def _start(server: ThreadingHTTPServer) -> threading.Thread:
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread


def _events(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _wait_for_relation(path: Path, relation: str, timeout: float = 5.0) -> list[dict[str, object]]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            events = _events(path)
            if any(event.get("relation") == relation for event in events):
                return events
        time.sleep(0.02)
    return _events(path) if path.exists() else []


def test_default_relay_large_stream_has_bounded_transport_capture_memory(tmp_path: Path) -> None:
    """NEW-005: full raw fidelity must not require one in-memory wire-response copy."""

    padding = "x" * _PADDING_CHARS

    class LargeStreamUpstream(BaseHTTPRequestHandler):
        def log_message(self, *args: object) -> None:
            pass

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            self.rfile.read(length)
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.end_headers()
            for _ in range(_FRAME_COUNT):
                frame = {
                    "model": "fixture",
                    "message": {"role": "assistant", "content": ""},
                    "padding": padding,
                    "done": False,
                }
                self.wfile.write(
                    json.dumps(frame, separators=(",", ":")).encode("utf-8") + b"\n"
                )
            final = {
                "model": "fixture",
                "message": {"role": "assistant", "content": "DONE"},
                "done": True,
            }
            self.wfile.write(
                json.dumps(final, separators=(",", ":")).encode("utf-8") + b"\n"
            )
            self.wfile.flush()

    sidecar = tmp_path / "semantic.jsonl"
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), LargeStreamUpstream)
    proxy = create_proxy_server(
        listen_host="127.0.0.1",
        listen_port=0,
        config=ProxyConfig(
            upstream=f"http://127.0.0.1:{upstream.server_port}",
            sidecar=sidecar,
            mode="ollama",
        ),
    )
    threads = [_start(upstream), _start(proxy)]
    request_body = json.dumps(
        {
            "model": "fixture",
            "messages": [{"role": "user", "content": "hello"}],
            "stream": True,
        },
        separators=(",", ":"),
    ).encode("utf-8")
    client = http.client.HTTPConnection("127.0.0.1", proxy.server_port, timeout=20)
    observed_bytes = 0
    peak_bytes = 0
    try:
        gc.collect()
        tracemalloc.start()
        tracemalloc.reset_peak()
        client.request(
            "POST",
            "/api/chat",
            body=request_body,
            headers={"Content-Type": "application/json"},
        )
        response = client.getresponse()
        while chunk := response.read(64 * 1024):
            observed_bytes += len(chunk)
        _, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        events = _wait_for_relation(sidecar, "OBSERVED_INFERENCE_RESPONSE_RAW")
        raw = next(
            event
            for event in events
            if event.get("relation") == "OBSERVED_INFERENCE_RESPONSE_RAW"
        )
        raw_attrs = raw["attributes"]
        assert isinstance(raw_attrs, dict)
        assert raw_attrs["content_size_bytes"] == observed_bytes
        raw_path = tmp_path / str(raw_attrs["content_path"])
        assert raw_path.stat().st_size == observed_bytes
        assert observed_bytes > 16 * 1024 * 1024

        response_event = next(
            event
            for event in events
            if event.get("relation") == "OBSERVED_INFERENCE_RESPONSE"
        )
        response_attrs = response_event["attributes"]
        assert isinstance(response_attrs, dict)
        semantic_path = tmp_path / str(response_attrs["content_path"])
        assert "DONE" in semantic_path.read_text(encoding="utf-8")

        assert peak_bytes <= _MAX_TRACED_PEAK_BYTES, (
            "default relay capture memory scaled with the full wire response: "
            f"wire={observed_bytes} peak={peak_bytes} limit={_MAX_TRACED_PEAK_BYTES}"
        )
    finally:
        if tracemalloc.is_tracing():
            tracemalloc.stop()
        client.close()
        proxy.shutdown()
        upstream.shutdown()
        proxy.server_close()
        upstream.server_close()
        for thread in threads:
            thread.join(3)
