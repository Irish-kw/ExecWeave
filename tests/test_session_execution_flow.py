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
    # Root -> model -> session: the session is entered through the model the root
    # used, and a model switch adds a second context that returns to the same session.
    assert not any(e["source"] == "root" and e["target"] == "session:run" for e in edges)
    ranks = {n["id"]: n["attributes"]["viewer_flow_rank"] for n in result["nodes"]}
    for model, tool in (("m1", "tool1"), ("m2", "tool2")):
        assert any(e["source"] == "root" and e["target"] == contexts[model] and e["relation"] == "MODEL_CONTEXT" for e in edges)
        assert any(e["source"] == contexts[model] and e["target"] == "session:run" and e["relation"] == "USED_IN_SESSION" for e in edges)
        assert any(e["source"] == contexts[model] and e["target"] == tool for e in edges)
        assert ranks["root"] < ranks[contexts[model]] < ranks["session:run"]
    reply = next(n for n in result["nodes"] if n.get("attributes", {}).get("viewer_return_message"))
    assert any(e["source"] == "child" and e["target"] == reply["id"] for e in edges)
    assert any(e["source"] == reply["id"] and e["target"] == "root" for e in edges)
    assert len({n["id"] for n in result["nodes"]}) == len(result["nodes"])
    known = {n["id"] for n in result["nodes"]}
    assert all(e["source"] in known and e["target"] in known for e in edges)
    reached, queue = {"root"}, ["root"]
    while queue:
        current = queue.pop()
        for e in edges:
            if e["source"] == current and e["target"] not in reached:
                reached.add(e["target"])
                queue.append(e["target"])
    assert reached == known  # Nothing floats away from the root.


def test_recording_membership_reconnects_root_without_inventing_launch():
    graph = _graph("antigravity")
    graph["nodes"].append(_agent("launcher", "agy"))
    graph["edges"][0]["source"] = "launcher"
    result = _project(graph)
    # The same product's launcher is the root actor: folded into it, never a second
    # floating actor, and its launch is kept as evidence rather than drawn as causal.
    assert not any(n["id"] == "launcher" for n in result["nodes"])
    root = next(n for n in result["nodes"] if n["id"] == "root")
    assert "launcher" in root["attributes"]["viewer_merged_agent_ids"]
    session = next(n for n in result["nodes"] if n["id"] == "session:run")
    assert "start" in session["attributes"]["viewer_start_edge_ids"]
    assert not any(e["target"] == "session:run" and e.get("causal") is not False for e in result["edges"])
    assert not any(e["source"] == "root" and e["target"] == "session:run" for e in result["edges"])
    memberships = [e for e in result["edges"] if e["target"] == "session:run"]
    assert {e["relation"] for e in memberships} == {"USED_IN_SESSION"}
    assert all(e["attributes"]["recording_session_id"] == "run" for e in memberships)


def test_session_without_an_observed_model_is_recorded_from_the_root():
    graph = _graph("antigravity")
    graph["nodes"].append(_agent("launcher", "agy"))
    graph["edges"] = [e for e in graph["edges"] if e["relation"] not in {"INVOKES_MODEL", "SWITCHED_MODEL"}]
    graph["edges"][0]["source"] = "launcher"
    result = _project(graph)
    # The folded launcher's own launch evidence, still attributed to the launcher.
    launch = next(e for e in result["edges"] if e["source"] == "root" and e["target"] == "session:run")
    assert (launch["relation"], launch["causal"], launch["viewer_original_source"]) == ("STARTED_SESSION", False, "launcher")

    graph["edges"] = graph["edges"][1:]
    result = _project(graph)
    membership = next(e for e in result["edges"] if e["source"] == "root" and e["target"] == "session:run")
    assert membership["relation"] == "RECORDED_IN_SESSION"
    assert membership["causal"] is False
    assert membership["attributes"]["recording_session_id"] == "run"
    assert membership["attributes"]["model_attribution"] == "not_observed"


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


def _reachable(result, start):
    reached, queue = {start}, [start]
    while queue:
        current = queue.pop()
        for e in result["edges"]:
            if e["source"] == current and e["target"] not in reached:
                reached.add(e["target"])
                queue.append(e["target"])
    return reached


def _framework_graph(framework, wire, hosted=True):
    # A user's own script: the program that started the recording issues the wire
    # calls, and the framework agents it runs report their own view of the same model.
    nodes = [
        _agent("launcher", "python", provider="python"),
        {"id": "session:run", "type": "session", "name": "run"},
        {"id": "proc", "type": "process", "name": "python app.py", "attributes": {}},
        _agent("planner", "planner", provider=framework, conversation_scope="framework_agent"),
        _agent("coder", "coder", provider=framework, conversation_scope="framework_agent"),
        _model("m1", "model-one", provider=wire),
        _model("fw:m1", "model-one", provider=framework),
        {"id": "tool:search", "type": "tool", "name": "search", "attributes": {}},
    ]
    edges = [
        _edge("start", "launcher", "session:run", "STARTED_SESSION", 1),
        _edge("launch", "session:run", "proc", "LAUNCHED", 1),
        _edge("parent", "planner", "coder", "PARENT_AGENT", 2),
        _edge("ask1", "planner", "fw:m1", "REQUESTS_MODEL_CALL", 3),
        _edge("ok1", "planner", "fw:m1", "MODEL_CALL_RESPONDS", 4),
        _edge("ask2", "planner", "fw:m1", "REQUESTS_MODEL_CALL", 5),
        _edge("fail2", "planner", "fw:m1", "MODEL_CALL_FAILED", 6),
        _edge("wire", "launcher", "m1", "INVOKES_MODEL", 7),
        _edge("call1", "coder", "tool:search", "REQUESTS_TOOL_CALL", 8),
        _edge("ret1", "coder", "tool:search", "TOOL_CALL_RETURNS", 9),
        _edge("call2", "coder", "tool:search", "REQUESTS_TOOL_CALL", 10),
        _edge("err2", "coder", "tool:search", "TOOL_CALL_FAILED", 11),
    ]
    if hosted:
        edges += [
            _edge("host-planner", "planner", "proc", "CORRELATED_WITH_PROCESS", 2),
            _edge("host-coder", "coder", "proc", "CORRELATED_WITH_PROCESS", 2),
        ]
    return {"session_id": "run", "nodes": nodes, "edges": edges}


FRAMEWORKS = (("autogen", "openai"), ("camel", "ollama"), ("metagpt", "anthropic"))


@pytest.mark.parametrize(("framework", "wire"), FRAMEWORKS)
def test_framework_agents_hosted_by_the_recorded_program_use_its_wire_model(framework, wire):
    result = _project(_framework_graph(framework, wire))
    edges = result["edges"]
    nodes = {n["id"]: n for n in result["nodes"]}
    context = "viewer:model-context:launcher:m1"
    # The framework's own report of the model is the same model the program called on
    # the wire: one model node, entered from the program, then used by the agent.
    assert "fw:m1" not in nodes
    assert nodes[context]["attributes"]["viewer_framework_model_ids"] == ["fw:m1"]
    used = [e for e in edges if e["relation"] == "USED_BY_AGENT"]
    assert [(e["source"], e["target"]) for e in used] == [(context, "planner")]
    assert used[0]["count"] == 2
    assert {k: used[0]["attributes"][k] for k in ("request_count", "response_count", "failure_count")} == {
        "request_count": 2, "response_count": 1, "failure_count": 1}
    # The program hosts the top agent; the child is reached through its parent only.
    hosts = [(e["source"], e["target"]) for e in edges if e["relation"] == "HOSTS_AGENT"]
    assert hosts == [("proc", "planner")]
    assert any(e["source"] == "planner" and e["target"] == "coder" and e["relation"] == "PARENT_AGENT" for e in edges)
    # Request, result and failure of the same call are one edge with ×N counts.
    tool = [e for e in edges if e["target"] == "tool:search"]
    assert [(e["source"], e["relation"]) for e in tool] == [("coder", "CALLED_TOOL")]
    assert {k: tool[0]["attributes"][k] for k in ("request_count", "result_count", "failure_count")} == {
        "request_count": 2, "result_count": 1, "failure_count": 1}
    rank = {i: n["attributes"]["viewer_flow_rank"] for i, n in nodes.items()}
    order = ["launcher", context, "session:run", "proc", "planner", "coder", "tool:search"]
    assert [rank[i] for i in order] == sorted(rank[i] for i in order)
    assert len({rank[i] for i in order}) == len(order)
    assert _reachable(result, "launcher") == set(nodes)


@pytest.mark.parametrize(("framework", "wire"), FRAMEWORKS)
def test_framework_agents_outside_the_program_keep_their_own_model(framework, wire):
    graph = _framework_graph(framework, wire, hosted=False)
    graph["nodes"].append(_agent("helper", "helper", provider="other"))
    result = _project(graph)
    edges = result["edges"]
    # Without evidence that the program hosts them, the framework's model report is
    # not merged into the program's wire call.
    called = [e for e in edges if e["relation"] == "CALLED_MODEL"]
    assert [(e["source"], e["target"]) for e in called] == [("planner", "fw:m1")]
    assert {k: called[0]["attributes"][k] for k in ("request_count", "response_count", "failure_count")} == {
        "request_count": 2, "response_count": 1, "failure_count": 1}
    assert not any(e["relation"] in {"USED_BY_AGENT", "HOSTS_AGENT"} for e in edges)
    attached = {e["target"] for e in edges if e["source"] == "session:run" and e["relation"] == "SESSION_AGENT"}
    assert attached == {"planner", "helper"}
    assert _reachable(result, "launcher") == {n["id"] for n in result["nodes"]}


def test_structural_edges_win_rank_order_and_traffic_closes_the_cycle():
    graph = _framework_graph("autogen", "openai")
    graph["edges"] = [e for e in graph["edges"] if e["id"] not in {"ask1", "ok1", "ask2", "fail2"}]
    graph["edges"] += [
        _edge("child-ask", "coder", "fw:m1", "REQUESTS_MODEL_CALL", 3),
        _edge("child-reply", "coder", "planner", "SENT_AGENT_MESSAGE", 4),
        _edge("parent-ask", "planner", "fw:m1", "REQUESTS_MODEL_CALL", 5),
    ]
    result = _project(graph)
    rank = {n["id"]: n["attributes"]["viewer_flow_rank"] for n in result["nodes"]}
    # The child's earlier activity must not rank it before its parent: the parent edge
    # is structure, and the child's message back to the parent is the feedback edge.
    assert rank["planner"] < rank["coder"]
    parent = next(e for e in result["edges"] if e["relation"] == "PARENT_AGENT")
    assert not parent.get("viewer_flow_feedback")
    back = [e for e in result["edges"] if e["target"] == "planner" and e["relation"] == "SENT_AGENT_MESSAGE"]
    assert len(back) == 1 and back[0]["viewer_flow_feedback"] is True


def test_launcher_model_contexts_are_promoted_to_the_root_once_per_model():
    graph = _graph("antigravity")
    graph["nodes"].append(_agent("launcher", "agy"))
    for e in graph["edges"]:
        if e["id"] in {"start", "model1"}:
            e["source"] = "launcher"
    result = _project(graph)
    contexts = [n for n in result["nodes"] if n.get("attributes", {}).get("viewer_model_context")]
    owned = sorted((n["attributes"]["owner_agent_id"], n["attributes"]["model_resource_id"]) for n in contexts)
    # The launcher's model use belongs to the root it is folded into: one context per
    # model, each entered from the root and returning to the same session.
    assert owned == [("child", "mc"), ("root", "m1"), ("root", "m2")]
    for context in contexts:
        if context["attributes"]["owner_agent_id"] != "root":
            continue
        assert any(e["source"] == "root" and e["target"] == context["id"] and e["relation"] == "MODEL_CONTEXT" for e in result["edges"])
        assert any(e["source"] == context["id"] and e["target"] == "session:run" and e["relation"] == "USED_IN_SESSION" for e in result["edges"])
    assert _reachable(result, "root") == {n["id"] for n in result["nodes"]}


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
            assert not any(e["source"] == "root" and e["target"] == "session:run" for e in display["edges"])
            assert len([e for e in display["edges"] if e["source"] == "root" and e["relation"] == "MODEL_CONTEXT"]) == 2
            assert len([e for e in display["edges"] if e["target"] == "session:run" and e["relation"] == "USED_IN_SESSION"]) == 2
            root_box = page.locator('.node[data-id="root"]').bounding_box()
            session_box = page.locator('.node[data-id="session:run"]').bounding_box()
            contexts = [n for n in display["nodes"] if n.get("attributes", {}).get("owner_agent_id") == "root" and n.get("attributes", {}).get("viewer_model_context")]
            assert len(contexts) == 2
            for context in contexts:
                box = page.locator(f'.node[data-id="{context["id"]}"]').bounding_box()
                assert root_box["x"] < box["x"] < session_box["x"]
            _click_id(page, "root")
            folds = page.locator(".execweave-message-history")
            assert page.locator('.execweave-agent-communication').get_attribute('data-agent-id') == 'root'
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
