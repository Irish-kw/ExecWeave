"""Exercise the JavaScript used by both live and finished dashboards."""
from __future__ import annotations

import pytest

from test_execution_flow_integrity import _agent, _edge, _model, _project
from test_provider_dashboard_contract import ALL_PROVIDERS


def _graph(provider):
    nodes = [
        _agent("root", "/root", provider=provider, agent_role="root"),
        _agent("child", "worker", provider=provider),
        {"id": "session:run", "type": "session", "name": "run"},
        _model("m1", "model-one", provider=provider),
        _model("m2", "model-two", provider=provider),
        _model("mc", "child-model", provider=provider),
        {"id": "tool1", "type": "tool", "name": "read", "attributes": {}},
        {"id": "tool2", "type": "tool", "name": "write", "attributes": {}},
    ]
    edges = [
        _edge("start", "root", "session:run", "STARTED_SESSION", 1),
        _edge("model1", "root", "m1", "INVOKES_MODEL", 2),
        _edge("read", "root", "tool1", "CALLED_TOOL", 3),
        _edge("spawn", "root", "child", "SPAWNED_AGENT", 4),
        _edge("child-model", "child", "mc", "INVOKES_MODEL", 5),
        _edge("switch", "root", "m2", "SWITCHED_MODEL", 6),
        _edge("write", "root", "tool2", "CALLED_TOOL", 7),
        _edge("reply", "child", "root", "SENT_AGENT_MESSAGE", 8),
    ]
    return {"session_id": "run", "nodes": nodes, "edges": edges}


@pytest.mark.parametrize("provider", ALL_PROVIDERS)
def test_root_session_model_switch_tools_and_return(provider):
    result = _project(_graph(provider))
    edges = result["edges"]
    contexts = {n["attributes"]["model_resource_id"]: n["id"] for n in result["nodes"]
                if n.get("attributes", {}).get("viewer_model_context")
                and n["attributes"].get("owner_agent_id") == "root"}
    assert set(contexts) == {"m1", "m2"}  # Never assign the child's model to root.
    assert any(e["source"] == "root" and e["target"] == "session:run" for e in edges)
    for model, tool in (("m1", "tool1"), ("m2", "tool2")):
        assert any(e["source"] == "session:run" and e["target"] == contexts[model] for e in edges)
        assert any(e["source"] == contexts[model] and e["target"] == tool for e in edges)
    reply = next(n for n in result["nodes"] if n.get("attributes", {}).get("viewer_return_message"))
    assert any(e["source"] == "child" and e["target"] == reply["id"] for e in edges)
    assert any(e["source"] == reply["id"] and e["target"] == "root" for e in edges)
    assert len({n["id"] for n in result["nodes"]}) == len(result["nodes"])
    known = {n["id"] for n in result["nodes"]}
    assert all(e["source"] in known and e["target"] in known for e in edges)


def test_recording_membership_reconnects_root_without_inventing_launch():
    graph = _graph("antigravity")
    graph["nodes"].append(_agent("launcher", "agy"))
    graph["edges"][0]["source"] = "launcher"
    result = _project(graph)
    membership = next(e for e in result["edges"] if e["source"] == "root" and e["target"] == "session:run")
    assert membership["relation"] == "RECORDED_IN_SESSION"
    assert membership["causal"] is False
    assert membership["attributes"]["recording_session_id"] == "run"


def test_multiple_sessions_without_exact_membership_are_not_cross_joined():
    graph = _graph("codex")
    graph["edges"] = graph["edges"][1:]
    graph["nodes"].append({"id": "session:other", "type": "session"})
    result = _project(graph)
    assert not any(e["source"] == "root" and e["target"].startswith("session:") for e in result["edges"])


def test_model_switch_return_to_same_model_reuses_context():
    graph = _graph("antigravity")
    graph["edges"].append(_edge("switch-back", "root", "m1", "INVOKES_MODEL", 9))
    result = _project(graph)
    contexts = [n for n in result["nodes"] if n.get("attributes", {}).get("viewer_model_context")
                and n["attributes"].get("owner_agent_id") == "root"]
    assert len(contexts) == 2


def test_tool_aggregate_is_partitioned_by_model_without_losing_calls():
    graph = _graph("codex")
    calls = [
        {"invocation_id": "first", "owner_id": "root", "call_ids": [], "first_sequence": 3},
        {"invocation_id": "second", "owner_id": "root", "call_ids": [], "first_sequence": 7},
    ]
    edge = next(e for e in graph["edges"] if e["id"] == "read")
    edge.update(count=2, viewer_tool_call_occurrences=calls)
    result = _project(graph)
    model_contexts = {n["id"]: n["attributes"]["model_resource_id"] for n in result["nodes"] if n.get("attributes", {}).get("viewer_model_context")}
    edges = [e for e in result["edges"] if e["target"] == "tool1"]
    assert {model_contexts[e["source"]] for e in edges} == {"m1", "m2"}
    assert sorted(row["invocation_id"] for e in edges for row in e["viewer_tool_call_occurrences"]) == ["first", "second"]
    assert all(e["count"] == 1 for e in edges)


def test_aggregate_model_return_is_used_but_unknown_middle_switch_is_not_guessed():
    graph = _graph("codex")
    first = next(e for e in graph["edges"] if e["id"] == "model1")
    first.update(last_sequence=9, count=2)
    graph["edges"].append(_edge("late-read", "root", "tool1", "CALLED_TOOL", 10))
    result = _project(graph)
    context = next(n["id"] for n in result["nodes"] if n.get("attributes", {}).get("viewer_model_context") and n["attributes"]["model_resource_id"] == "m1")
    assert any(e.get("viewer_original_edge_id") == "late-read" and e["source"] == context for e in result["edges"])
    first["count"] = 3
    result = _project(graph)
    assert any(e["source"] == "root" and e["target"] == "tool2" and e["attributes"].get("model_attribution") == "not_observed" for e in result["edges"])


@pytest.mark.viewer_e2e
@pytest.mark.parametrize("provider", ALL_PROVIDERS)
def test_browser_session_flow_and_collapsed_incoming_history(provider, tmp_path):
    from execweave.dashboard_shell import render_static_dashboard_html
    from test_viewer_agent_isolation_e2e import _browser, _launch, _click_id

    graph = _graph(provider)
    messages = [
        {"kind": "agent_message", "sender": "/worker-a", "recipient": "/root", "text": "A delivered result", "ordinal": 1},
        {"kind": "agent_message", "sender": "/worker-b", "recipient": "/root", "text": "B delivered result", "ordinal": 2},
    ]
    entries = [{"source_id": "root", "provider": provider, "conversation_preview": {
        "is_root": True, "agent_path": "/root", "messages": messages,
    }}]
    manager, executable = _browser()
    with manager as playwright:
        browser = _launch(playwright, executable)
        try:
            page = browser.new_page(viewport={"width": 1800, "height": 1000})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.set_content(render_static_dashboard_html(graph, conversation_entries=entries))
            page.wait_for_selector(".node")
            display = page.evaluate("window.__execweaveCore.getDisplayGraph()")
            assert any(e["source"] == "root" and e["target"] == "session:run" for e in display["edges"])
            assert len([e for e in display["edges"] if e["source"] == "session:run" and e["relation"] == "MODEL_CONTEXT"]) == 2
            root_box = page.locator('.node[data-id="root"]').bounding_box()
            session_box = page.locator('.node[data-id="session:run"]').bounding_box()
            assert root_box["x"] < session_box["x"]
            for context in [n for n in display["nodes"] if n.get("attributes", {}).get("owner_agent_id") == "root" and n.get("attributes", {}).get("viewer_model_context")]:
                box = page.locator(f'.node[data-id="{context["id"]}"]').bounding_box()
                assert session_box["x"] < box["x"]
            _click_id(page, "root")
            folds = page.locator(".execweave-message-history")
            assert folds.count() == 2
            assert folds.evaluate_all("xs=>xs.every(x=>!x.open)")
            folds.first.locator("summary").click()
            assert "B delivered result" in folds.first.inner_text()
            _click_id(page, "child")
            assert page.locator(".execweave-message-history").count() == 0
            _click_id(page, "root")
            assert page.locator(".execweave-message-history").first.get_attribute("open") is not None
            assert not errors
            page.screenshot(path=str(tmp_path / f"{provider}-session-history.png"), full_page=True)
        finally:
            browser.close()
