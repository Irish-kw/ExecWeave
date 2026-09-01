from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

import pytest

from execweave.auto_specialized import auto_specialized_launch
from execweave.content_evidence import content_observation_event
from execweave.content_store import FullFidelityContentStore
from execweave.conversation_records import conversation_record_entries
from execweave.graph import GraphAccumulator
from execweave.model_runtime import sanitize_endpoint
from execweave.model_runtime_full_fidelity import runtime_exchange_to_content_events
from execweave.viewer_projection import write_graph_html


def _agent(conversation_id: str) -> dict[str, object]:
    return {
        "type": "agent",
        "id": f"agent:antigravity:conversation:{conversation_id}",
        "name": "Antigravity conversation",
        "attributes": {"provider": "antigravity", "conversation_id": conversation_id},
    }


def _agy_records(rounds: int) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    step = 0
    for index in range(rounds):
        rows.append({
            "step_index": step,
            "source": "USER_EXPLICIT",
            "type": "USER_INPUT",
            "status": "DONE",
            "created_at": f"2026-09-01T01:{index:02d}:00Z",
            "content": f"<USER_REQUEST>\nquestion {index}\n</USER_REQUEST>\n<ADDITIONAL_METADATA>hidden {index}</ADDITIONAL_METADATA>",
        })
        step += 1
        rows.append({
            "step_index": step,
            "source": "MODEL",
            "type": "PLANNER_RESPONSE",
            "status": "DONE",
            "created_at": f"2026-09-01T01:{index:02d}:01Z",
            "content": f"answer {index}",
        })
        step += 1
        rows.append({
            "step_index": step,
            "source": "MODEL",
            "type": "GENERIC",
            "status": "DONE",
            "created_at": f"2026-09-01T01:{index:02d}:02Z",
            "content": f"TOOL RESULT MUST NOT BE FINAL {index}",
        })
        step += 1
    return rows


def _agy_graph(tmp_path: Path, rounds: int) -> tuple[dict[str, object], Path]:
    run_root = tmp_path / "run"
    store = FullFidelityContentStore(run_root)
    transcript = tmp_path / "transcript_full.jsonl"
    transcript.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in _agy_records(rounds)),
        encoding="utf-8",
    )
    reference = store.put_file(
        transcript,
        content_kind="antigravity.conversation_transcript",
        media_type="text/plain; charset=utf-8",
        representation="provider_transcript_jsonl_snapshot",
    )
    event = content_observation_event(
        timestamp="2026-09-01T02:00:00Z",
        provider="antigravity",
        source=_agent("main-real-wire"),
        reference=reference,
        relation="HAS_CONVERSATION_TRANSCRIPT",
        observed_field="transcriptPath",
        evidence_source="provider_transcript",
        attribution="antigravity_hook",
    )
    graph = GraphAccumulator(session_id="agy-real-wire", source_path=run_root / "events.jsonl")
    graph.apply(event)
    materialized = graph.to_dict()
    materialized["nodes"].append({
        "id": "agent:Antigravity",
        "type": "agent",
        "name": "Antigravity",
        "attributes": {"provider": "antigravity"},
    })
    return materialized, run_root


def _preview(entries: list[dict[str, object]], provider: str) -> dict[str, object]:
    previews = [
        entry["conversation_preview"]
        for entry in entries
        if entry.get("provider") == provider and isinstance(entry.get("conversation_preview"), dict)
    ]
    assert len(previews) == 1
    return previews[0]


def test_antigravity_real_wire_uses_user_explicit_and_rejects_generic_tool_results(tmp_path: Path) -> None:
    graph, run_root = _agy_graph(tmp_path, 3)
    preview = _preview(conversation_record_entries(graph, run_root), "antigravity")
    messages = preview["messages"]
    assert [message["text"] for message in messages] == [
        "question 0", "answer 0", "question 1", "answer 1", "question 2", "answer 2"
    ]
    assert [message["ordinal"] for message in messages] == [0, 1, 3, 4, 6, 7]
    assert all("ADDITIONAL_METADATA" not in str(message["text"]) for message in messages)
    assert all("TOOL RESULT MUST NOT BE FINAL" not in str(message["text"]) for message in messages)


def test_antigravity_middle_rounds_survive_more_than_eighty_visible_messages(tmp_path: Path) -> None:
    graph, run_root = _agy_graph(tmp_path, 50)
    preview = _preview(conversation_record_entries(graph, run_root), "antigravity")
    texts = [message["text"] for message in preview["messages"]]
    assert len(texts) == 100
    assert "question 25" in texts and "answer 25" in texts
    assert preview["messages_truncated"] is False


def test_loopback_ollama_endpoint_evidence_is_preserved() -> None:
    assert sanitize_endpoint("http://localhost:11434") == "http://localhost:11434"
    assert sanitize_endpoint("http://127.0.0.1:11434") == "http://127.0.0.1:11434"
    assert sanitize_endpoint("http://[::1]:11434") == "http://[::1]:11434"


def _ollama_graph(tmp_path: Path, rounds: int = 3) -> tuple[dict[str, object], Path]:
    run_root = tmp_path / "ollama-run"
    store = FullFidelityContentStore(run_root)
    graph = GraphAccumulator(session_id="ollama-history", source_path=run_root / "events.jsonl")
    history: list[dict[str, str]] = []
    for index in range(rounds):
        history.append({"role": "user", "content": f"ollama question {index}"})
        request_history = [dict(message) for message in history]
        response = {"model": "tiny", "message": {"role": "assistant", "content": f"ollama answer {index}"}, "done": True}
        for event in runtime_exchange_to_content_events(
            {"request": {"model": "tiny", "messages": request_history}, "response": response},
            store=store,
            runtime="ollama",
            endpoint="http://localhost:11434",
            request_id=f"turn-{index}",
            timestamp=f"2026-09-01T03:0{index}:00Z",
        ):
            graph.apply(event)
        history.append({"role": "assistant", "content": f"ollama answer {index}"})
    materialized = graph.to_dict()
    materialized["nodes"].extend([
        {"id": "agent:Ollama", "type": "agent", "name": "Ollama", "attributes": {"provider": "ollama"}},
        {"id": "model-runtime:ollama:viewer-duplicate", "type": "model_runtime", "name": "ollama", "attributes": {"provider": "ollama", "endpoint": "http://127.0.0.1:11434"}},
        {"id": "model:ollama:tiny", "type": "model", "name": "tiny", "attributes": {"provider": "ollama"}},
    ])
    materialized["edges"].append({
        "id": "runtime-model",
        "source": "model-runtime:ollama:viewer-duplicate",
        "target": "model:ollama:tiny",
        "relation": "LOADED_MODEL",
        "count": 1,
    })
    return materialized, run_root


def test_ollama_cumulative_chat_requests_publish_one_new_round_each(tmp_path: Path) -> None:
    graph, run_root = _ollama_graph(tmp_path)
    entries = conversation_record_entries(graph, run_root)
    preview = _preview(entries, "ollama")
    texts = [message["text"] for message in preview["messages"]]
    assert texts == [
        "ollama question 0", "ollama answer 0",
        "ollama question 1", "ollama answer 1",
        "ollama question 2", "ollama answer 2",
    ]
    owner = next(entry for entry in entries if isinstance(entry.get("conversation_preview"), dict))
    assert owner["source_id"] == "agent:Ollama"


def test_ollama_generate_response_becomes_assistant_message(tmp_path: Path) -> None:
    run_root = tmp_path / "generate"
    store = FullFidelityContentStore(run_root)
    graph = GraphAccumulator(session_id="ollama-generate", source_path=run_root / "events.jsonl")
    for event in runtime_exchange_to_content_events(
        {"request": {"model": "tiny", "prompt": "generate prompt"}, "response": {"model": "tiny", "response": "generate answer", "done": True}},
        store=store,
        runtime="ollama",
        endpoint="http://localhost:11434",
        request_id="generate-1",
        timestamp="2026-09-01T04:00:00Z",
    ):
        graph.apply(event)
    materialized = graph.to_dict()
    materialized["nodes"].append({"id": "agent:Ollama", "type": "agent", "name": "Ollama", "attributes": {"provider": "ollama"}})
    preview = _preview(conversation_record_entries(materialized, run_root), "ollama")
    assert [message["text"] for message in preview["messages"]] == ["generate prompt", "generate answer"]


class _OllamaHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length).decode("utf-8"))
        payload = {
            "model": body.get("model", "tiny"),
            "message": {"role": "assistant", "content": "relay answer"},
            "done": True,
        }
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def test_ollama_run_launch_uses_loopback_relay_and_records_exchange(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), _OllamaHandler)
    thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    thread.start()
    sidecar = tmp_path / "events.semantic.jsonl"
    monkeypatch.setenv("EXECWEAVE_SEMANTIC_SIDECAR", str(sidecar))
    monkeypatch.setenv("OLLAMA_HOST", f"http://127.0.0.1:{upstream.server_port}")
    try:
        with auto_specialized_launch(["ollama", "run", "tiny"]) as environment:
            assert environment["OLLAMA_HOST"] != os.environ["OLLAMA_HOST"]
            request = Request(
                environment["OLLAMA_HOST"] + "/api/chat",
                data=json.dumps({"model": "tiny", "messages": [{"role": "user", "content": "relay prompt"}]}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(request, timeout=5) as response:
                assert json.loads(response.read().decode("utf-8"))["message"]["content"] == "relay answer"
        rows = [json.loads(line) for line in sidecar.read_text(encoding="utf-8").splitlines() if line.strip()]
        kinds = {
            (row.get("target", {}).get("attributes") or {}).get("content_kind")
            for row in rows
            if isinstance(row, dict)
        }
        assert "model_runtime.ollama.request_messages" in kinds
        assert "model_runtime.ollama.assistant_messages" in kinds
    finally:
        upstream.shutdown()
        upstream.server_close()
        thread.join(timeout=2)


def test_ollama_serve_and_remote_hosts_are_not_relayed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXECWEAVE_SEMANTIC_SIDECAR", str(tmp_path / "semantic.jsonl"))
    original = dict(os.environ)
    with auto_specialized_launch(["ollama", "serve"]) as environment:
        assert environment.get("OLLAMA_HOST") == original.get("OLLAMA_HOST")
    monkeypatch.setenv("OLLAMA_HOST", "http://192.0.2.10:11434")
    with auto_specialized_launch(["ollama", "run", "tiny"]) as environment:
        assert environment["OLLAMA_HOST"] == "http://192.0.2.10:11434"


def _required_browser(playwright: object):
    try:
        return playwright.chromium.launch()
    except Exception as error:  # noqa: BLE001
        if os.environ.get("EXECWEAVE_E2E_REQUIRED", "").lower() not in {"", "0", "false"}:
            pytest.fail(f"Chromium required for conversation-integrity gate: {error}")
        pytest.skip(f"Chromium unavailable: {error}")


@pytest.mark.viewer_e2e
def test_antigravity_real_wire_dashboard_has_one_main_node_and_folded_history(tmp_path: Path) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    graph, run_root = _agy_graph(tmp_path, 3)
    viewer = run_root / "viewer.html"
    write_graph_html(graph, viewer)
    with sync_api.sync_playwright() as playwright:
        browser = _required_browser(playwright)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.goto(viewer.as_uri())
            page.wait_for_selector(".node")
            visible_ids = page.eval_on_selector_all(".node", "nodes=>nodes.map(node=>node.dataset.id)")
            assert "agent:Antigravity" not in visible_ids
            assert "agent:antigravity:conversation:main-real-wire" in visible_ids
            page.eval_on_selector(
                '.node[data-id="agent:antigravity:conversation:main-real-wire"]',
                "node=>node.dispatchEvent(new MouseEvent('click',{bubbles:true}))",
            )
            page.wait_for_function("()=>(document.getElementById('details')?.innerText||'').includes('question 2')")
            details = page.locator("#details")
            assert details.locator(".execweave-agent-older").count() == 2
            text = details.inner_text()
            assert "answer 2" in text
            assert "TOOL RESULT MUST NOT BE FINAL" not in text
            first = details.locator(".execweave-agent-older").first
            first.locator("summary").click()
            assert first.evaluate("node=>node.open")
            page.evaluate("entries=>window.__execweaveAgentPanel.setEntries(entries)", conversation_record_entries(graph, run_root))
            assert details.locator(".execweave-agent-older").first.evaluate("node=>node.open")
        finally:
            browser.close()


@pytest.mark.viewer_e2e
def test_ollama_dashboard_has_one_owner_node_and_folded_history(tmp_path: Path) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    graph, run_root = _ollama_graph(tmp_path)
    viewer = run_root / "viewer.html"
    write_graph_html(graph, viewer)
    with sync_api.sync_playwright() as playwright:
        browser = _required_browser(playwright)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.goto(viewer.as_uri())
            page.wait_for_selector(".node")
            visible_ids = page.eval_on_selector_all(".node", "nodes=>nodes.map(node=>node.dataset.id)")
            assert "model-runtime:ollama:viewer-duplicate" not in visible_ids
            assert "agent:Ollama" in visible_ids
            page.eval_on_selector(
                '.node[data-id="agent:Ollama"]',
                "node=>node.dispatchEvent(new MouseEvent('click',{bubbles:true}))",
            )
            page.wait_for_function("()=>(document.getElementById('details')?.innerText||'').includes('ollama question 2')")
            details = page.locator("#details")
            assert details.locator(".execweave-agent-older").count() == 2
            assert "ollama answer 2" in details.inner_text()
        finally:
            browser.close()
