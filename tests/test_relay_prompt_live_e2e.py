"""Slow native HTTP -> sidecar -> live DOM -> merged graph -> finished DOM.

The upstream is an offline fixture, not a claimed live provider acceptance.
"""

from __future__ import annotations

import http.client
import json
import os
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from uuid import uuid4

import pytest

from execweave import live
from execweave.graph import build_execution_graph, write_execution_graph
from execweave.http_proxy import ProxyConfig, create_proxy_server
from execweave.semantic import merge_semantic_sidecar
from execweave.viewer_projection import write_graph_html
from test_semantic import _runtime_events, _write_jsonl
from test_viewer_agent_isolation_e2e import _browser

pytestmark = pytest.mark.viewer_e2e


def test_prompt_is_visible_before_response_and_not_duplicated_when_finished(tmp_path):
    marker = "EW-PROMPT-" + uuid4().hex[:8]
    done = marker + "-DONE"
    prompt = f"{marker} Reply exactly {done}"
    release = threading.Event()
    received = threading.Event()
    completed = threading.Event()
    errors = []

    class SlowModel(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            assert body["messages"][-1]["content"] == prompt
            received.set()
            if not release.wait(40):
                return
            payload = json.dumps(
                {
                    "model": "fixture",
                    "message": {"role": "assistant", "content": done},
                    "done": True,
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    runtime = tmp_path / "events.jsonl"
    sidecar = tmp_path / "semantic.jsonl"
    records = _runtime_events()
    records[0]["source"].update(id="agent:Ollama", name="Ollama")
    for record in records[:2]:
        record["timestamp"] = datetime.now(timezone.utc).isoformat()
    _write_jsonl(runtime, records[:2])
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), SlowModel)
    proxy = create_proxy_server(
        listen_host="127.0.0.1",
        listen_port=0,
        config=ProxyConfig(
            upstream=f"http://127.0.0.1:{upstream.server_port}", sidecar=sidecar, mode="ollama"
        ),
    )
    state = live._LiveState("s1", runtime, sidecar)
    server = live._LocalThreadingHTTPServer(
        ("127.0.0.1", 0), live._handler_factory(state, "test-token")
    )
    threads = []
    for service in (upstream, proxy, server):
        thread = threading.Thread(target=service.serve_forever, daemon=True)
        thread.start()
        threads.append(thread)

    def request():
        connection = http.client.HTTPConnection("127.0.0.1", proxy.server_port, timeout=45)
        try:
            connection.request(
                "POST",
                "/api/chat",
                body=json.dumps(
                    {
                        "model": "fixture",
                        "stream": True,
                        "messages": [{"role": "user", "content": prompt}],
                    }
                ),
                headers={"Content-Type": "application/json"},
            )
            assert done in connection.getresponse().read().decode()
        except Exception as error:
            errors.append(str(error))
        finally:
            connection.close()
            completed.set()

    client = threading.Thread(target=request, daemon=True)
    client.start()
    manager, executable = _browser()
    try:
        assert received.wait(5)
        with manager as pw:
            browser = pw.chromium.launch(
                headless=os.environ.get("EXECWEAVE_ACCEPTANCE_HEADED") != "1",
                **({"executable_path": executable} if executable else {}),
            )
            try:
                page = browser.new_page(viewport={"width": 1440, "height": 1000})
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(f"http://127.0.0.1:{server.server_port}/?t=test-token")
                page.locator('.node[data-id="agent:Ollama"]').click(timeout=10000)
                page.wait_for_function(
                    "marker=>document.querySelector('#details').innerText.includes(marker)",
                    arg=marker,
                    timeout=10000,
                )
                early = page.locator("#details").inner_text()
                assert prompt in early
                assert early.partition("FINAL RESPONSE\n")[2].strip() != done
                assert not completed.is_set() and not release.is_set()
                emitted = [
                    json.loads(line) for line in sidecar.read_text(encoding="utf-8").splitlines()
                ]
                assert not any(
                    event["relation"] == "OBSERVED_INFERENCE_RESPONSE" for event in emitted
                )
                page.screenshot(path=str(tmp_path / "01-prompt-before-response.png"))
                release.set()
                assert completed.wait(5)
                page.wait_for_function(
                    "done=>document.querySelector('#details').innerText.split('FINAL RESPONSE\\n')[1]?.trim()===done",
                    arg=done,
                    timeout=10000,
                )
                live_text = page.locator("#details").inner_text()
                assert live_text.count(prompt) == 1
                page.screenshot(path=str(tmp_path / "02-live-final.png"))
                records[-1]["timestamp"] = datetime.now(timezone.utc).isoformat()
                _write_jsonl(runtime, records)
                merged = tmp_path / "events.semantic.jsonl"
                merge_semantic_sidecar(runtime, sidecar, merged)
                graph = build_execution_graph(merged)
                write_execution_graph(graph, tmp_path / "graph.json")
                write_graph_html(graph.to_dict(), tmp_path / "viewer.html")
                page.goto((tmp_path / "viewer.html").as_uri())
                page.locator('.node[data-id="agent:Ollama"]').click(timeout=10000)
                assert page.locator("#details").inner_text() == live_text
                page.screenshot(path=str(tmp_path / "03-finished.png"))
                emitted = [
                    json.loads(line) for line in sidecar.read_text(encoding="utf-8").splitlines()
                ]
                for relation in (
                    "OBSERVED_INFERENCE_REQUEST_MESSAGES",
                    "OBSERVED_INFERENCE_RESPONSE",
                ):
                    assert sum(event["relation"] == relation for event in emitted) == 1
                assert len({event["source"]["id"] for event in emitted}) == 1
                assert not errors
            finally:
                browser.close()
    finally:
        release.set()
        client.join(5)
        for service in (server, proxy, upstream):
            service.shutdown()
            service.server_close()
        for thread in threads:
            thread.join(5)
