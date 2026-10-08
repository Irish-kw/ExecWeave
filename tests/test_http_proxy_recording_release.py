from __future__ import annotations

import http.client
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from execweave import _http_proxy_bounded as bounded
from execweave.http_proxy import ProxyConfig, create_proxy_server

_DONE = "RELEASE-DONE"


class _StreamingModel(BaseHTTPRequestHandler):
    def log_message(self, *args: object) -> None:
        pass

    def do_POST(self) -> None:
        self.rfile.read(int(self.headers.get("Content-Length", "0")))
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.end_headers()
        for content, done in (("RELEASE-", False), ("DONE", True)):
            frame = {
                "model": "fixture",
                "message": {"role": "assistant", "content": content},
                "done": done,
            }
            self.wfile.write(json.dumps(frame).encode("utf-8") + b"\n")
            self.wfile.flush()


def _relations(sidecar: Path) -> list[str]:
    if not sidecar.exists():
        return []
    return [
        json.loads(line)["relation"]
        for line in sidecar.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _serve(tmp_path: Path):
    sidecar = tmp_path / "semantic.jsonl"
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), _StreamingModel)
    proxy = create_proxy_server(
        listen_host="127.0.0.1",
        listen_port=0,
        config=ProxyConfig(
            upstream=f"http://127.0.0.1:{upstream.server_port}",
            sidecar=sidecar,
            mode="ollama",
        ),
    )
    for service in (upstream, proxy):
        threading.Thread(target=service.serve_forever, daemon=True).start()
    return sidecar, upstream, proxy


def _chat(proxy) -> str:
    client = http.client.HTTPConnection("127.0.0.1", proxy.server_port, timeout=20)
    try:
        client.request(
            "POST",
            "/api/chat",
            body=json.dumps(
                {
                    "model": "fixture",
                    "stream": True,
                    "messages": [{"role": "user", "content": "hello"}],
                }
            ),
            headers={"Content-Type": "application/json"},
        )
        return client.getresponse().read().decode("utf-8")
    finally:
        client.close()


def test_recording_is_on_disk_before_the_client_sees_the_end(tmp_path: Path) -> None:
    sidecar, upstream, proxy = _serve(tmp_path)
    try:
        body = _chat(proxy)
        relations = _relations(sidecar)
    finally:
        for service in (proxy, upstream):
            service.shutdown()
            service.server_close()

    assert body.count("\n") == 2 and '"done": true' in body
    assert relations.count("OBSERVED_INFERENCE_REQUEST_MESSAGES") == 1
    assert relations.count("OBSERVED_INFERENCE_RESPONSE") == 1


def test_slow_recording_releases_the_client_and_closing_waits_for_it(
    tmp_path: Path, monkeypatch
) -> None:
    unblock = threading.Event()
    recording = threading.Event()
    record_capture = bounded._record_capture

    def slow_record_capture(*args, **kwargs):
        recording.set()
        assert unblock.wait(30)
        return record_capture(*args, **kwargs)

    monkeypatch.setattr(bounded, "_CLIENT_RELEASE_SECONDS", 0.2)
    monkeypatch.setattr(bounded, "_record_capture", slow_record_capture)
    sidecar, upstream, proxy = _serve(tmp_path)
    closer = threading.Thread(target=lambda: (proxy.shutdown(), proxy.server_close()))
    try:
        started = time.monotonic()
        body = _chat(proxy)
        elapsed = time.monotonic() - started

        # The client got the whole stream while its response was still being recorded.
        assert body.count("\n") == 2 and '"done": true' in body
        assert elapsed < 10
        assert recording.is_set() and not unblock.is_set()
        assert "OBSERVED_INFERENCE_RESPONSE" not in _relations(sidecar)

        # Closing the proxy does not drop the recording still in flight.
        closer.start()
        closer.join(0.5)
        assert closer.is_alive()
        unblock.set()
        closer.join(20)
        assert not closer.is_alive()
        relations = _relations(sidecar)
    finally:
        unblock.set()
        if not closer.is_alive() and closer.ident is None:
            proxy.shutdown()
            proxy.server_close()
        upstream.shutdown()
        upstream.server_close()

    assert relations.count("OBSERVED_INFERENCE_REQUEST_MESSAGES") == 1
    assert relations.count("OBSERVED_INFERENCE_RESPONSE") == 1
    response = next(
        json.loads(line)
        for line in sidecar.read_text(encoding="utf-8").splitlines()
        if json.loads(line)["relation"] == "OBSERVED_INFERENCE_RESPONSE"
    )
    stored = tmp_path / response["attributes"]["content_path"]
    assert _DONE in stored.read_text(encoding="utf-8")
