from __future__ import annotations

import http.client
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from execweave.auto_specialized import _record_ollama_inference_exchange
from execweave.http_proxy import ExecWeaveHTTPProxyServer, ProxyConfig
from execweave.viewer_semantic_projection import collapse_inference_requests


class _OllamaUpstream(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def log_message(self, format: str, *args: object) -> None:
        return

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        if length:
            self.rfile.read(length)
        payload = json.dumps(
            {
                "model": "demo",
                "message": {"role": "assistant", "content": "ok"},
                "done": True,
            },
            separators=(",", ":"),
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def _start(server: ThreadingHTTPServer) -> threading.Thread:
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread


def _post(port: int, path: str, body: dict[str, object]) -> bytes:
    payload = json.dumps(body, separators=(",", ":")).encode()
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request(
            "POST",
            path,
            body=payload,
            headers={"Content-Type": "application/json", "Content-Length": str(len(payload))},
        )
        response = connection.getresponse()
        data = response.read()
        assert response.status == 200
        return data
    finally:
        connection.close()


def _events(path: Path) -> list[dict[str, object]]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_managed_ollama_filter_uses_request_phase_before_response(tmp_path: Path) -> None:
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), _OllamaUpstream)
    upstream_thread = _start(upstream)
    sidecar = tmp_path / "semantic.jsonl"
    proxy = ExecWeaveHTTPProxyServer(
        ("127.0.0.1", 0),
        ProxyConfig(
            upstream=f"http://127.0.0.1:{upstream.server_port}",
            sidecar=sidecar,
            mode="ollama",
        ),
        recorder=_record_ollama_inference_exchange,
    )
    proxy_thread = _start(proxy)
    try:
        data = _post(
            proxy.server_port,
            "/api/chat",
            {
                "model": "demo",
                "messages": [{"role": "user", "content": "ping"}],
                "stream": False,
            },
        )
        assert json.loads(data)["message"]["content"] == "ok"
    finally:
        proxy.shutdown()
        proxy.server_close()
        proxy_thread.join(timeout=5)
        upstream.shutdown()
        upstream.server_close()
        upstream_thread.join(timeout=5)

    events = _events(sidecar)
    relations = [event.get("relation") for event in events]
    assert relations.count("REQUESTED_MODEL") == 1
    requested = next(event for event in events if event.get("relation") == "REQUESTED_MODEL")
    assert requested["source"]["type"] == "inference_request"
    assert requested["target"]["type"] == "model"
    assert requested["target"]["name"] == "demo"
    assert requested["attributes"]["capture_phase"] == "request"
    assert requested["attributes"]["response_observed"] is False
    assert requested["attributes"]["inferred"] is False
    response_index = relations.index("OBSERVED_INFERENCE_RESPONSE")
    assert relations.index("REQUESTED_MODEL") < response_index
    assert relations.index("OBSERVED_INFERENCE_REQUEST_RAW") < response_index
    phases_before_response = [
        event["attributes"]["capture_phase"]
        for event in events[:response_index]
        if isinstance(event.get("attributes"), dict)
        and "capture_phase" in event["attributes"]
    ]
    assert phases_before_response
    assert set(phases_before_response) == {"request"}


def test_managed_ollama_filter_does_not_capture_non_inference_route(tmp_path: Path) -> None:
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), _OllamaUpstream)
    upstream_thread = _start(upstream)
    sidecar = tmp_path / "semantic.jsonl"
    proxy = ExecWeaveHTTPProxyServer(
        ("127.0.0.1", 0),
        ProxyConfig(
            upstream=f"http://127.0.0.1:{upstream.server_port}",
            sidecar=sidecar,
            mode="ollama",
        ),
        recorder=_record_ollama_inference_exchange,
    )
    proxy_thread = _start(proxy)
    try:
        _post(
            proxy.server_port,
            "/api/show",
            {
                "model": "demo",
                # Deliberately include a request-like field: route filtering, not
                # payload shape, must decide whether this managed relay captures it.
                "messages": [{"role": "user", "content": "do not capture"}],
            },
        )
    finally:
        proxy.shutdown()
        proxy.server_close()
        proxy_thread.join(timeout=5)
        upstream.shutdown()
        upstream.server_close()
        upstream_thread.join(timeout=5)

    assert _events(sidecar) == []


def test_requested_model_resolves_projection_and_hides_request_content() -> None:
    root_id = "agent:ollama:root"
    request_id = "inference-request:ollama:req-1"
    model_id = "model:ollama:demo"
    content_id = "observed-content:request"
    nodes = [
        {
            "id": root_id,
            "type": "agent",
            "name": "/root",
            "attributes": {"provider": "ollama", "agent_path": "/root", "agent_role": "root"},
        },
        {
            "id": request_id,
            "type": "inference_request",
            "name": "req-1",
            "first_seen": "2026-09-07T00:00:01Z",
            "last_seen": "2026-09-07T00:00:02Z",
            "attributes": {"provider": "ollama"},
        },
        {
            "id": model_id,
            "type": "model",
            "name": "demo",
            "attributes": {"provider": "ollama"},
        },
        {
            "id": content_id,
            "type": "observed_content",
            "name": "request",
            "attributes": {"content_kind": "model_runtime.ollama.request"},
        },
    ]
    edges = [
        {
            "id": "requested-model",
            "source": request_id,
            "target": model_id,
            "relation": "REQUESTED_MODEL",
            "first_seen": "2026-09-07T00:00:01Z",
            "last_seen": "2026-09-07T00:00:01Z",
            "first_sequence": 1,
            "last_sequence": 1,
        },
        {
            "id": "request-content",
            "source": request_id,
            "target": content_id,
            "relation": "OBSERVED_INFERENCE_REQUEST",
            "first_seen": "2026-09-07T00:00:01Z",
            "last_seen": "2026-09-07T00:00:01Z",
            "first_sequence": 2,
            "last_sequence": 2,
        },
    ]

    projected_nodes, projected_edges, metadata = collapse_inference_requests(nodes, edges, [])

    assert metadata["unresolved"] == []
    assert metadata["logical_inference_count"] == 1
    assert not any(node.get("type") == "inference_request" for node in projected_nodes)
    assert not any(node.get("id") == content_id for node in projected_nodes)
    inferred = next(edge for edge in projected_edges if edge.get("relation") == "INFERRED")
    assert inferred["source"] == root_id
    assert inferred["target"] == model_id
    assert inferred["count"] == 1
    occurrence = inferred["viewer_occurrences"][0]
    assert occurrence["request_ids"] == [request_id]
    assert occurrence["model_id"] == model_id
    assert occurrence["content_references"][0]["id"] == content_id
