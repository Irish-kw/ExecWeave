"""Native adapter/HTTP boundaries and bounded investigation publication."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from execweave import live, live_core
from execweave.content_store import FullFidelityContentStore
from execweave.graph import GraphAccumulator
from execweave.investigation_index import InvestigationCache, build_investigation_index
from execweave.model_runtime_full_fidelity import runtime_exchange_to_content_events
from test_investigation_workspace import browser_page, overwrite, scenario, show

# Reuse a real browser fixture; every browser case runs or fails, never skips.
__all__ = ["browser_page"]


@pytest.mark.parametrize("runtime", ["ollama", "llamacpp", "vllm", "lmstudio"])
def test_real_runtime_normalizer_keeps_request_response_without_inventing_owner(tmp_path, runtime):
    events = runtime_exchange_to_content_events(
        {"request": {"model": "example", "messages": [{"role": "user", "content": "request"}]},
         "response": {"model": "example", "message": {"role": "assistant", "content": "answer"}, "done": True}},
        store=FullFidelityContentStore(tmp_path), runtime=runtime,
        endpoint="http://127.0.0.1:11434", request_id="native-one",
    )
    accumulator = GraphAccumulator(session_id="runtime-run", source_path=tmp_path / "events.jsonl")
    for i, event in enumerate(events):
        accumulator.apply({**event, "session_id": "runtime-run", "sequence": i})
    graph = accumulator.to_dict()
    graph["nodes"].append({"id": "unrelated-root", "type": "agent", "name": "only root"})
    row = build_investigation_index(graph, tmp_path)["calls"][0]
    assert row["owner_id"] is None and row["identity_bound"] is False
    assert {"request", "response"} <= set(row["phases"])
    assert row["observation_basis"] == "explicit_graph_call"
    assert all(r["state"] == "registered_not_read" for r in row["references"])
    assert {r["relation"] for r in row["references"]} >= {"OBSERVED_INFERENCE_REQUEST", "OBSERVED_INFERENCE_RESPONSE"}


@pytest.mark.parametrize("ambiguous", [False, True])
def test_native_tool_owner_requires_one_explicit_owner(tmp_path, ambiguous):
    reference = FullFidelityContentStore(tmp_path).put_text("tool answer", content_kind="test.tool_result").to_dict()
    graph = {"session_id": "one", "nodes": [
        {"id": "a", "type": "agent"}, {"id": "b", "type": "agent"},
        {"id": "tool", "type": "tool"}, {"id": "call", "type": "tool_call"},
        {"id": "body", "type": "observed_content", "attributes": reference}],
        "edges": [{"source": "a", "target": "call", "relation": "REQUESTED_TOOL_CALL"},
                  {"source": "call", "target": "tool", "relation": "USES_TOOL"},
                  {"source": "call", "target": "body", "relation": "HAS_TOOL_OUTPUT"}]}
    if ambiguous:
        graph["edges"].append({"source": "b", "target": "call", "relation": "REQUESTED_TOOL_CALL"})
    row = build_investigation_index(graph, tmp_path)["calls"][0]
    assert row["owner_id"] == (None if ambiguous else "a")
    assert row["identity_bound"] is (not ambiguous)
    assert row["phases"] == ["response"]


@pytest.mark.parametrize("mutation", ["wrong_type", "viewer_only", "inferred"])
def test_invalid_owner_edges_cannot_attribute_native_calls(tmp_path, mutation):
    graph = {"session_id": "one", "nodes": [{"id": "a", "type": "agent"}, {"id": "call", "type": "tool_call"}],
             "edges": [{"source": "a", "target": "call", "relation": "REQUESTED_TOOL_CALL"}]}
    if mutation == "wrong_type":
        graph["nodes"][0]["type"] = "model"
    else:
        graph["edges"][0][mutation] = True
    row = build_investigation_index(graph, tmp_path)["calls"][0]
    assert row["owner_id"] is None and row["identity_bound"] is False


@pytest.mark.parametrize("bad", [[], {}, True, 5])
def test_malformed_reference_fields_do_not_crash(tmp_path, bad):
    graph, events, *_ = scenario(tmp_path)
    for e in events:
        if e["event_type"] == "MESSAGE_SENT":
            e["attributes"]["content_ref"] = bad
    overwrite(tmp_path, events)
    index = build_investigation_index(graph, tmp_path)
    assert any(r["state"] == "invalid_reference" for m in index["messages"] for r in m["references"])


def test_missing_participant_does_not_pair_unrelated_occurrences(tmp_path):
    graph, events, *_ = scenario(tmp_path)
    for e in events:
        if e["event_type"] in {"MESSAGE_SENT", "MESSAGE_RECEIVED"}:
            e["source"] = None
            e["attributes"]["sender_agent_id"] = None
    overwrite(tmp_path, events)
    rows = build_investigation_index(graph, tmp_path)["messages"]
    assert len(rows) == 3
    assert all(not r["identity_bound"] and len(r["phases"]) == 1 for r in rows)


def test_graph_output_budget_is_visible(tmp_path):
    graph = {"session_id": "one", "nodes": [{"id": f"a{i}", "type": "agent"} for i in range(10010)], "edges": []}
    index = build_investigation_index(graph, tmp_path)
    assert len(index["agents"]) == 10000
    assert index["inspection"]["agent_rows_omitted"] == 10
    assert index["inspection"]["graph_inventory_partial"] is True


def test_unchanged_stream_uses_bounded_cache(tmp_path, monkeypatch):
    from execweave import investigation_index as implementation
    graph, _, *_ = scenario(tmp_path)
    cache = InvestigationCache()
    first = build_investigation_index(graph, tmp_path, cache=cache)
    def unexpected(*args, **kwargs):
        raise AssertionError("unchanged stream was rescanned")
    monkeypatch.setattr(implementation, "_scan", unexpected)
    assert build_investigation_index(graph, tmp_path, cache=cache) == first


@pytest.fixture
def server(tmp_path):
    graph, _, *_ = scenario(tmp_path)
    events = tmp_path / "events.jsonl"
    events.write_text("", encoding="utf-8")
    state = live._LiveState("one", events)
    state.finish(graph)
    instance = live_core._LocalThreadingHTTPServer(("127.0.0.1", 0), live._handler_factory(state, "integration-token"))
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{instance.server_address[1]}", state
    finally:
        instance.shutdown()
        instance.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


@pytest.mark.parametrize("token", [None, "bad-token"])
def test_on_demand_index_preserves_authentication(server, token):
    base, _ = server
    headers = {"X-ExecWeave-Token": token} if token else {}
    with pytest.raises(HTTPError) as failure:
        urlopen(Request(base + "/conversations.json?investigation=1", headers=headers), timeout=5)
    assert failure.value.code == 401
    failure.value.close()


def test_normal_history_does_not_scan_stream_and_explicit_request_does(server, monkeypatch):
    from execweave import investigation_index as implementation
    base, _ = server
    original, calls = implementation._scan, []
    def record(*args, **kwargs):
        calls.append(True)
        return original(*args, **kwargs)
    monkeypatch.setattr(implementation, "_scan", record)
    def get(suffix):
        with urlopen(Request(base + suffix, headers={"X-ExecWeave-Token": "integration-token"}), timeout=5) as response:
            assert response.headers["Cache-Control"] == "no-store"
            return json.load(response)
    payload = get("/conversations.json")
    assert "investigation" not in payload and calls == []
    detailed = get("/conversations.json?investigation=1")
    assert len(detailed["investigation"]["messages"]) == 2 and len(calls) == 1
    assert detailed["entries"] == payload["entries"]
    assert get("/conversations.json?investigation=1")["investigation"] == detailed["investigation"]
    assert len(calls) == 1


def test_real_workload_exports_inspectable_handoff_without_task_success(tmp_path, monkeypatch):
    # Real process and recorder. The workload uses deterministic framework SDK
    # observations, not a paid model or a claim that upstream CAMEL was started.
    from execweave.live import run_live
    import execweave
    monkeypatch.setenv("PYTHONPATH", str(Path(execweave.__file__).resolve().parent.parent))
    code = '''from execweave.framework_adapters import AdapterContext, CAMELAdapter
ctx=AdapterContext.from_environment("camel",capture_mode="prompt_and_response")
a=CAMELAdapter(ctx)
p=a.agent_created("producer",name="Producer")
r=a.agent_created("reviewer",name="Reviewer")
a.message("exchange",p,r,content="recorded output")
a.message("exchange",p,r,content="recorded output",received=True)
raise SystemExit(3)
'''
    result = run_live([sys.executable, "-c", code], watch_root=tmp_path, output_dir=tmp_path / "run",
                      collect_filesystem=False, collect_network=False, port=0, open_browser=False, linger_seconds=0)
    assert result.return_code == 3
    payload = json.loads((tmp_path / "run" / "conversations.json").read_text())
    rows = payload["investigation"]["messages"]
    assert len(rows) == 1 and rows[0]["phases"] == ["sent", "received"]
    assert all(r["state"] == "registered_not_read" for r in rows[0]["references"])
    assert "__execweaveStaticInvestigation=" in (tmp_path / "run" / "viewer.html").read_text()
    raw = json.loads((tmp_path / "run" / "graph.json").read_text())
    assert "investigation" not in raw
    assert raw["session_outcome"]["state"] == "failed"
    assert json.loads((tmp_path / "run" / "finalization.json").read_text())["state"] == "complete"


@pytest.mark.viewer_e2e
def test_shared_host_uses_exactly_one_agent_panel_instance(tmp_path, browser_page):
    graph, _, *_ = scenario(tmp_path)
    show(browser_page, graph, build_investigation_index(graph, tmp_path))
    assert browser_page.evaluate("window.__execweaveDashboard.agentPanel===window.__execweaveAgentPanel")
    browser_page.get_by_role("button", name="Close exploration", exact=True).click()
    assert browser_page.locator("#execweave-explore-run").evaluate("n=>n===document.activeElement")


@pytest.mark.viewer_e2e
def test_partial_response_and_foreign_session_do_not_synchronize(tmp_path, browser_page):
    from execweave.dashboard_shell import render_static_dashboard_html
    graph, _, *_ = scenario(tmp_path)
    page = browser_page
    page.set_content(render_static_dashboard_html(graph))
    for status, session in [(206, "one"), (200, "foreign")]:
        page.evaluate("([status,session])=>{window.__execweaveStaticMode=false;window.fetch=async()=>({ok:true,status,json:async()=>({session_id:session,entries:[]})})}", [status, session])
        assert page.evaluate("()=>window.__execweaveAgentPanel.finishConversationPolling()") is False
        assert page.evaluate("()=>window.__execweaveAgentPanel.isFinishedSynchronized()") is False
    page.evaluate("scope=>{window.fetch=async()=>({ok:true,status:200,json:async()=>({session_id:'one',source_path:scope,entries:[]})})}", graph["source_path"])
    assert page.evaluate("()=>window.__execweaveAgentPanel.finishConversationPolling()") is True


@pytest.mark.viewer_e2e
def test_index_publication_failure_is_not_a_successful_sync(tmp_path, browser_page):
    from execweave.dashboard_shell import render_static_dashboard_html
    graph, _, *_ = scenario(tmp_path)
    page = browser_page
    page.set_content(render_static_dashboard_html(graph))
    page.evaluate("""()=>{
        window.__execweaveStaticMode=false;
        window.fetch=async()=>({ok:true,status:200,json:async()=>({entries:[],investigation:{}})});
        window.__execweaveInvestigation.setIndex=()=>{throw new Error('publication failure')};
    }""")
    assert page.evaluate("()=>window.__execweaveAgentPanel.finishConversationPolling()") is False
    assert page.evaluate("()=>window.__execweaveAgentPanel.isFinishedSynchronized()") is False


@pytest.mark.viewer_e2e
def test_run_change_clears_old_explorer_even_with_late_index(tmp_path, browser_page):
    graph, _, *_ = scenario(tmp_path)
    index = build_investigation_index(graph, tmp_path)
    page = browser_page
    show(page, graph, index)
    page.evaluate("()=>{window.__execweaveCore.getGraph().session_id='new-run';window.__execweaveDashboard.onPayload({})}")
    assert not page.locator("#execweave-investigation-dialog").is_visible()
    page.evaluate("x=>window.__execweaveInvestigation.setIndex(x)", index)
    page.get_by_role("button", name="Explore run", exact=True).click()
    page.get_by_role("button", name="Handoffs", exact=True).click()
    assert page.locator(".investigation-row").count() == 0


def test_medium_inventory_timing_is_recorded_not_a_universal_benchmark(tmp_path, record_testsuite_property):
    graph, _, *_ = scenario(tmp_path, total=1000)
    start = time.monotonic()
    index = build_investigation_index(graph, tmp_path)
    elapsed = time.monotonic() - start
    record_testsuite_property("index_seconds", elapsed)
    record_testsuite_property("index_bytes", len(json.dumps(index).encode()))
    assert len(index["messages"]) == 1001
    assert index["inspection"]["limit_reached"] is False
    # A gross liveness boundary, not the planned product p95 latency gate.
    assert elapsed < 10


def test_arbitrary_related_payload_is_not_a_file_snapshot(tmp_path):
    graph, _, *_ = scenario(tmp_path)
    body = next(n for n in graph["nodes"] if n["type"] == "observed_content")
    graph["nodes"].append({"id": "f", "type": "file", "name": "DESIGN.md"})
    graph["edges"].append({"source": "f", "target": body["id"], "relation": "ASSOCIATED_WITH"})
    row = build_investigation_index(graph, tmp_path)["artifacts"][0]
    assert row["snapshot_count"] == 0 and row["related_content_count"] == 1
    assert row["related_content"][0]["reference"] is not None


@pytest.mark.viewer_e2e
def test_record_disclosure_survives_pagination(tmp_path, browser_page):
    graph, _, *_ = scenario(tmp_path, total=30)
    page = browser_page
    show(page, graph, build_investigation_index(graph, tmp_path))
    page.get_by_role("button", name="Handoffs", exact=True).click()
    chosen = page.locator(".investigation-row").first
    record = chosen.get_attribute("data-record-id")
    chosen.locator("summary").click()
    chosen.get_by_text("Native occurrence:", exact=False).wait_for()
    page.get_by_role("button", name="Next page", exact=True).click()
    page.get_by_role("button", name="Previous page", exact=True).click()
    assert page.locator(".investigation-row[open]").get_attribute("data-record-id") == record


@pytest.mark.viewer_e2e
def test_missing_index_identity_is_not_accepted(tmp_path, browser_page):
    graph, _, *_ = scenario(tmp_path)
    index = build_investigation_index(graph, tmp_path)
    page = browser_page
    show(page, graph, index)
    page.evaluate("x=>window.__execweaveInvestigation.setIndex(x)", {**index, "session_id": None})
    assert "not accepted" in page.locator("#execweave-investigation-updates").inner_text()
    page.get_by_role("button", name="Refresh index", exact=True).click()
    assert page.locator(".investigation-row").count() == 3


@pytest.mark.viewer_e2e
def test_explicit_index_request_waits_for_normal_request_without_new_poll_loop(tmp_path, browser_page):
    from execweave.dashboard_shell import render_static_dashboard_html
    graph, _, *_ = scenario(tmp_path)
    page = browser_page
    page.set_content(render_static_dashboard_html(graph))
    page.evaluate("""()=>{
      window.__execweaveStaticMode=false;window.requests=[];window.completeFirst=null;
      window.fetch=async url=>{window.requests.push(url);if(window.requests.length===1)await new Promise(r=>window.completeFirst=r);return {ok:true,status:200,json:async()=>({entries:[]})}};
      window.first=window.__execweaveAgentPanel.refresh();
      window.second=window.__execweaveAgentPanel.refresh({includeInvestigation:true});
    }""")
    assert page.evaluate("window.requests") == ["/conversations.json"]
    page.evaluate("window.completeFirst()")
    assert page.evaluate("()=>window.second") is True
    assert page.evaluate("window.requests") == ["/conversations.json", "/conversations.json?investigation=1"]
