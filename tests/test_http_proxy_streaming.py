from __future__ import annotations

import http.client
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from execweave.http_proxy import ProxyConfig, create_proxy_server


def _start(server):
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread


def test_unicode_upstream_error_returns_502_instead_of_eof(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Localized Windows socket errors must not crash the HTTP status writer."""
    original_request = http.client.HTTPConnection.request

    def fail_upstream_request(connection, *args, **kwargs):
        if connection.host == "127.0.0.1" and connection.port == 9:
            raise OSError("無法連線，因為目標電腦拒絕連線")
        return original_request(connection, *args, **kwargs)

    monkeypatch.setattr(http.client.HTTPConnection, "request", fail_upstream_request)
    proxy = create_proxy_server(
        listen_host="127.0.0.1",
        listen_port=0,
        config=ProxyConfig(
            upstream="http://127.0.0.1:9",
            sidecar=tmp_path / "semantic.jsonl",
            mode="ollama",
        ),
    )
    thread = _start(proxy)
    client = http.client.HTTPConnection("127.0.0.1", proxy.server_port, timeout=3)
    try:
        client.request("HEAD", "/")
        response = client.getresponse()
        assert response.status == 502
        assert response.reason.startswith("upstream HTTP relay failed:")
        response.reason.encode("latin-1")
    finally:
        client.close()
        proxy.shutdown()
        proxy.server_close()
        thread.join(3)


@pytest.mark.parametrize("chunked", [False, True])
def test_relay_delivers_first_bytes_before_upstream_finishes(tmp_path: Path, chunked: bool):
    """NEW-005: native socket ordering, not post-completion content equality."""
    release_final = threading.Event()
    recorded = threading.Event()
    captures = []

    class SlowUpstream(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.send_header(
                "Transfer-Encoding" if chunked else "Content-Length", "chunked" if chunked else "9"
            )
            self.end_headers()
            self.wfile.write(b"5\r\nfirst\r\n" if chunked else b"first")
            self.wfile.flush()
            if not release_final.wait(10):
                return
            self.wfile.write(b"4\r\nlast\r\n0\r\n\r\n" if chunked else b"last")
            self.wfile.flush()

    def capture(config, **exchange):
        captures.append(exchange)
        recorded.set()

    upstream = ThreadingHTTPServer(("127.0.0.1", 0), SlowUpstream)
    proxy = create_proxy_server(
        listen_host="127.0.0.1",
        listen_port=0,
        config=ProxyConfig(
            upstream=f"http://127.0.0.1:{upstream.server_port}",
            sidecar=tmp_path / "semantic.jsonl",
            mode="ollama",
        ),
        recorder=capture,
    )
    threads = [_start(upstream), _start(proxy)]
    client = http.client.HTTPConnection("127.0.0.1", proxy.server_port, timeout=3)
    try:
        client.request("GET", "/api/chat")
        response = client.getresponse()
        assert response.read(5) == b"first", "relay withheld bytes until upstream completion"
        assert not release_final.is_set()
        assert not recorded.is_set(), "this test does not invent partial semantic events"
        release_final.set()
        assert response.read() == b"last"
        assert recorded.wait(3)
        assert len(captures) == 1
        assert captures[0]["response_body"] == b"firstlast"
    finally:
        release_final.set()
        client.close()
        proxy.shutdown()
        upstream.shutdown()
        proxy.server_close()
        upstream.server_close()
        for thread in threads:
            thread.join(3)
