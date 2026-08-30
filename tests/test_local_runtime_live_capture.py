"""The assembled stream, not a single frame, must reach the materialized record.

Before this stage the relay archived every streamed frame but published
``chunks[-1]`` as the canonical response. The last frame of an OpenAI-style stream
carries an empty delta, so a live streaming run produced a record whose assistant
message was empty and whose tool calls were fragments — one per frame, each holding
a slice of the JSON arguments.

These tests drive the real proxy against a real upstream and read what landed on
disk, so they fail if the assembler is bypassed anywhere in the capture path.
"""

from __future__ import annotations

import http.client
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from execweave.evidence_availability import AVAILABLE, CAPTURE_INTERRUPTED
from execweave.http_proxy import ProxyConfig, create_proxy_server

_SSE_FRAMES: list[dict[str, Any]] = [
    {"id": "chatcmpl-9", "model": "local", "choices": [
        {"index": 0, "delta": {"role": "assistant", "content": "Reading "}, "finish_reason": None}]},
    {"choices": [{"index": 0, "delta": {"reasoning_content": "pick the file"}, "finish_reason": None}]},
    {"choices": [{"index": 0, "delta": {"content": "路徑 \U0001f600"}, "finish_reason": None}]},
    {"choices": [{"index": 0, "delta": {"tool_calls": [
        {"index": 0, "id": "call_a", "type": "function",
         "function": {"name": "read_", "arguments": '{"pa'}}]}, "finish_reason": None}]},
    {"choices": [{"index": 0, "delta": {"tool_calls": [
        {"index": 0, "function": {"name": "file", "arguments": 'th":"foo"}'}}]}, "finish_reason": None}]},
    {"choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]},
    {"choices": [], "usage": {"prompt_tokens": 11, "completion_tokens": 5, "total_tokens": 16}},
]


class _StreamingUpstream(BaseHTTPRequestHandler):
    truncate = False

    def log_message(self, format: str, *args: object) -> None:
        return

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        self.rfile.read(length)
        frames = _SSE_FRAMES[:3] if type(self).truncate else _SSE_FRAMES
        body = "".join(
            f"data: {json.dumps(frame, separators=(',', ':'), ensure_ascii=False)}\n\n"
            for frame in frames
        )
        if not type(self).truncate:
            body += "data: [DONE]\n\n"
        payload = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def _start(server: ThreadingHTTPServer) -> threading.Thread:
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread


def _events(sidecar: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in sidecar.read_text().splitlines() if line.strip()]


def _content_for(sidecar: Path, relation: str) -> tuple[dict[str, Any], bytes]:
    event = next(item for item in _events(sidecar) if item["relation"] == relation)
    return event, (sidecar.parent / event["attributes"]["content_path"]).read_bytes()


def _run_stream(tmp_path: Path, *, truncate: bool) -> Path:
    _StreamingUpstream.truncate = truncate
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), _StreamingUpstream)
    upstream_thread = _start(upstream)
    sidecar = tmp_path / "events.jsonl"
    proxy = create_proxy_server(
        listen_host="127.0.0.1",
        listen_port=0,
        config=ProxyConfig(
            upstream=f"http://127.0.0.1:{upstream.server_port}",
            sidecar=sidecar,
            mode="openai-compatible",
            provider_name="local-runtime",
        ),
    )
    proxy_thread = _start(proxy)
    try:
        body = json.dumps(
            {"model": "local", "stream": True, "messages": [{"role": "user", "content": "go"}]},
            separators=(",", ":"),
        ).encode()
        connection = http.client.HTTPConnection("127.0.0.1", proxy.server_port, timeout=5)
        connection.request(
            "POST",
            "/v1/chat/completions",
            body=body,
            headers={"Content-Type": "application/json", "Authorization": "Bearer secret-token"},
        )
        response = connection.getresponse()
        assert response.status == 200
        response.read()
    finally:
        proxy.shutdown()
        upstream.shutdown()
        proxy.server_close()
        upstream.server_close()
        proxy_thread.join(2)
        upstream_thread.join(2)
    return sidecar


def test_streamed_run_materializes_the_assembled_response(tmp_path: Path) -> None:
    sidecar = _run_stream(tmp_path, truncate=False)
    event, stored = _content_for(sidecar, "OBSERVED_INFERENCE_RESPONSE")
    response = json.loads(stored)

    message = response["choices"][0]["message"]
    assert message["content"] == "Reading 路徑 \U0001f600", "streamed text must reach the record"
    assert message["reasoning_content"] == "pick the file"
    assert response["choices"][0]["finish_reason"] == "tool_calls"
    assert response["usage"]["total_tokens"] == 16

    attributes = event["attributes"]
    assert attributes["stream_assembled"] is True
    assert attributes["stream_wire_format"] == "openai_chat_delta"
    assert attributes["stream_terminated"] is True
    assert attributes["stream_malformed_chunks"] == 0
    assert attributes["response_availability"] == AVAILABLE
    assert attributes["stream_tool_arguments_parse_cleanly"] is True


def test_tool_call_evidence_is_whole_not_one_fragment_per_frame(tmp_path: Path) -> None:
    sidecar = _run_stream(tmp_path, truncate=False)
    _, stored = _content_for(sidecar, "OBSERVED_ASSISTANT_TOOL_CALLS")
    calls = json.loads(stored)
    assert len(calls) == 1, f"a call split across frames became {len(calls)} records"
    assert calls[0]["function"]["name"] == "read_file"
    assert json.loads(calls[0]["function"]["arguments"]) == {"path": "foo"}


def test_raw_frames_are_still_archived_alongside_the_canonical_response(tmp_path: Path) -> None:
    sidecar = _run_stream(tmp_path, truncate=False)
    _, frames = _content_for(sidecar, "OBSERVED_INFERENCE_STREAM_CHUNKS")
    assert len(json.loads(frames)) == len(_SSE_FRAMES)
    _, raw = _content_for(sidecar, "OBSERVED_INFERENCE_RESPONSE_RAW")
    assert raw.startswith(b"data: ")


def test_interrupted_stream_is_recorded_as_interrupted(tmp_path: Path) -> None:
    sidecar = _run_stream(tmp_path, truncate=True)
    event, stored = _content_for(sidecar, "OBSERVED_INFERENCE_RESPONSE")
    response = json.loads(stored)
    assert response["choices"][0]["message"]["content"] == "Reading 路徑 \U0001f600"
    assert response["choices"][0]["finish_reason"] is None
    attributes = event["attributes"]
    assert attributes["stream_terminated"] is False
    assert attributes["response_availability"] == CAPTURE_INTERRUPTED
    assert "without a terminating frame" in attributes["stream_assembly_notes"]


def test_transport_credentials_never_reach_the_stored_stream(tmp_path: Path) -> None:
    sidecar = _run_stream(tmp_path, truncate=False)
    stored = sidecar.read_bytes() + b"".join(
        path.read_bytes() for path in (tmp_path / "content").rglob("*") if path.is_file()
    )
    assert b"secret-token" not in stored


def test_assembling_the_stream_does_not_double_publish_evidence(tmp_path: Path) -> None:
    """Once tool calls live in the assembled response, the emitter downstream
    publishes them; the relay must supplement rather than duplicate."""
    from collections import Counter

    sidecar = _run_stream(tmp_path, truncate=False)
    counts = Counter(event["relation"] for event in _events(sidecar))
    duplicated = sorted(relation for relation, count in counts.items() if count > 1)
    assert not duplicated, f"relations published more than once: {duplicated}"
