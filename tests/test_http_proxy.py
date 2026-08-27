from __future__ import annotations

import http.client
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from execweave.http_proxy import ProxyConfig, create_proxy_server, sanitize_upstream


class UpstreamHandler(BaseHTTPRequestHandler):
    seen_authorization = None

    def log_message(self, format: str, *args: object) -> None:
        return

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        request = json.loads(body)
        type(self).seen_authorization = self.headers.get("Authorization")
        if self.path == "/api/chat":
            chunks = [
                {"model": "qwen3", "message": {"role": "assistant", "content": "hi"}},
                {
                    "model": "qwen3",
                    "message": {
                        "role": "assistant",
                        "tool_calls": [
                            {"function": {"name": "weather", "arguments": {"city": "Taipei"}}}
                        ],
                    },
                    "done": True,
                },
            ]
            payload = b"".join(
                json.dumps(item, separators=(",", ":")).encode() + b"\n" for item in chunks
            )
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        payload = json.dumps(
            {
                "id": "chatcmpl-1",
                "model": request.get("model", "demo"),
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "ok",
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "type": "function",
                                    "function": {"name": "echo", "arguments": "{}"},
                                }
                            ],
                        }
                    }
                ],
            },
            separators=(",", ":"),
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def _start(server):
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread


def _content_for(sidecar: Path, relation: str):
    events = [json.loads(line) for line in sidecar.read_text().splitlines() if line.strip()]
    event = next(item for item in events if item["relation"] == relation)
    path = sidecar.parent / event["attributes"]["content_path"]
    return event, path.read_bytes()


def test_ollama_stream_capture_is_full_fidelity_and_credentials_are_not_recorded(tmp_path: Path):
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), UpstreamHandler)
    upstream_thread = _start(upstream)
    upstream_url = f"http://127.0.0.1:{upstream.server_port}"
    sidecar = tmp_path / "events.jsonl"
    proxy = create_proxy_server(
        listen_host="127.0.0.1",
        listen_port=0,
        config=ProxyConfig(upstream=upstream_url, sidecar=sidecar, mode="ollama"),
    )
    proxy_thread = _start(proxy)
    try:
        request = {
            "model": "qwen3",
            "stream": True,
            "messages": [{"role": "user", "content": "hello"}],
            "tools": [{"type": "function", "function": {"name": "weather"}}],
            "options": {"temperature": 0.25, "seed": 7},
        }
        body = json.dumps(request, separators=(",", ":")).encode()
        connection = http.client.HTTPConnection("127.0.0.1", proxy.server_port, timeout=5)
        connection.request(
            "POST",
            "/api/chat",
            body=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer transport-secret",
            },
        )
        response = connection.getresponse()
        response_body = response.read()
        assert response.status == 200
        assert response_body.count(b"\n") == 2
        assert UpstreamHandler.seen_authorization == "Bearer transport-secret"
        _, stored_request = _content_for(sidecar, "OBSERVED_INFERENCE_REQUEST")
        assert json.loads(stored_request) == request
        _, raw_request = _content_for(sidecar, "OBSERVED_INFERENCE_REQUEST_RAW")
        assert raw_request == body
        _, messages = _content_for(sidecar, "OBSERVED_INFERENCE_REQUEST_MESSAGES")
        assert json.loads(messages) == request["messages"]
        _, tools = _content_for(sidecar, "OBSERVED_TOOL_DEFINITIONS")
        assert json.loads(tools) == request["tools"]
        _, options = _content_for(sidecar, "OBSERVED_INFERENCE_REQUEST_CONFIG")
        assert json.loads(options)["options"] == request["options"]
        _, chunks = _content_for(sidecar, "OBSERVED_INFERENCE_STREAM_CHUNKS")
        assert len(json.loads(chunks)) == 2
        _, calls = _content_for(sidecar, "OBSERVED_ASSISTANT_TOOL_CALLS")
        assert json.loads(calls)[0]["function"]["name"] == "weather"
        all_stored = sidecar.read_bytes() + b"".join(
            path.read_bytes() for path in (tmp_path / "content").rglob("*") if path.is_file()
        )
        assert b"transport-secret" not in all_stored
    finally:
        proxy.shutdown()
        upstream.shutdown()
        proxy.server_close()
        upstream.server_close()
        proxy_thread.join(2)
        upstream_thread.join(2)


def test_openai_compatible_nonstream_response_and_tool_call_are_preserved(tmp_path: Path):
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), UpstreamHandler)
    upstream_thread = _start(upstream)
    sidecar = tmp_path / "events.jsonl"
    proxy = create_proxy_server(
        listen_host="127.0.0.1",
        listen_port=0,
        config=ProxyConfig(
            upstream=f"http://127.0.0.1:{upstream.server_port}/v1",
            sidecar=sidecar,
            provider_name="local-openai",
        ),
    )
    proxy_thread = _start(proxy)
    try:
        body = b'{"model":"demo","messages":[{"role":"user","content":"ping"}]}'
        connection = http.client.HTTPConnection("127.0.0.1", proxy.server_port, timeout=5)
        connection.request(
            "POST",
            "/chat/completions",
            body=body,
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        payload = response.read()
        assert response.status == 200
        assert json.loads(payload)["choices"][0]["message"]["content"] == "ok"
        _, stored = _content_for(sidecar, "OBSERVED_INFERENCE_RESPONSE")
        assert json.loads(stored) == json.loads(payload)
        _, raw_response = _content_for(sidecar, "OBSERVED_INFERENCE_RESPONSE_RAW")
        assert raw_response == payload
        _, calls = _content_for(sidecar, "OBSERVED_ASSISTANT_TOOL_CALLS")
        assert json.loads(calls)[0]["id"] == "call-1"
    finally:
        proxy.shutdown()
        upstream.shutdown()
        proxy.server_close()
        upstream.server_close()
        proxy_thread.join(2)
        upstream_thread.join(2)


def test_capture_exception_is_fail_open_for_transport(tmp_path: Path):
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), UpstreamHandler)
    upstream_thread = _start(upstream)

    def broken_recorder(*args, **kwargs):
        raise RuntimeError("disk unavailable")

    proxy = create_proxy_server(
        listen_host="127.0.0.1",
        listen_port=0,
        config=ProxyConfig(
            upstream=f"http://127.0.0.1:{upstream.server_port}",
            sidecar=tmp_path / "events.jsonl",
        ),
        recorder=broken_recorder,
    )
    proxy_thread = _start(proxy)
    try:
        connection = http.client.HTTPConnection("127.0.0.1", proxy.server_port, timeout=5)
        connection.request(
            "POST",
            "/v1/chat/completions",
            body=b'{"model":"demo"}',
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        payload = response.read()
        assert response.status == 200
        assert json.loads(payload)["id"] == "chatcmpl-1"
    finally:
        proxy.shutdown()
        upstream.shutdown()
        proxy.server_close()
        upstream.server_close()
        proxy_thread.join(2)
        upstream_thread.join(2)


def test_proxy_rejects_connect_absolute_targets_https_upstream_and_nonloopback(tmp_path: Path):
    with pytest.raises(ValueError, match="http://"):
        sanitize_upstream("https://example.com/v1")
    with pytest.raises(ValueError, match="loopback"):
        create_proxy_server(
            listen_host="0.0.0.0",
            listen_port=0,
            config=ProxyConfig(upstream="http://127.0.0.1:9", sidecar=tmp_path / "x.jsonl"),
        )
    proxy = create_proxy_server(
        listen_host="127.0.0.1",
        listen_port=0,
        config=ProxyConfig(upstream="http://127.0.0.1:9", sidecar=tmp_path / "x.jsonl"),
    )
    thread = _start(proxy)
    try:
        connection = http.client.HTTPConnection("127.0.0.1", proxy.server_port, timeout=5)
        connection.request("CONNECT", "example.com:443")
        response = connection.getresponse()
        response.read()
        assert response.status == 405
        connection = http.client.HTTPConnection("127.0.0.1", proxy.server_port, timeout=5)
        connection.request("GET", "http://example.com/v1/models")
        response = connection.getresponse()
        response.read()
        assert response.status == 400
    finally:
        proxy.shutdown()
        proxy.server_close()
        thread.join(2)
