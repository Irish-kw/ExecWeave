"""The gateway, API or runtime that served an inferred model stays linked to it in the viewer.

Collapsing inference requests removes the request node that carried SERVED_INFERENCE and
ROUTED_TO_PROVIDER. Without a replacement edge the gateway/API/runtime node would float with
no path from the run's root, so the served model links to it with a viewer-only edge whose
evidence names the hidden requests or the runtime catalog edges it stands for.
"""
from __future__ import annotations

import copy
from collections import deque

from execweave.viewer_projection import project_viewer_graph
from execweave.viewer_semantic_projection import (
    ORPHAN_FILES_NODE_ID,
    _roots,
    collapse_inference_requests,
    link_inference_infrastructure,
)

SCOPE = "52791ec32ba4e0efb8dc241a"
ROOT = "agent:python:root"


def _node(node_id: str, kind: str, name: str, **attributes: object) -> dict[str, object]:
    return {"id": node_id, "type": kind, "name": name, "first_seen": "2026-10-07T00:00:01Z", "last_seen": "2026-10-07T00:00:01Z", "event_count": 1, "attributes": dict(attributes)}


def _edge(source: str, relation: str, target: str, sequence: int) -> dict[str, object]:
    when = f"2026-10-07T00:00:{sequence:02d}Z"
    return {"id": f"{source}--{relation}-->{target}", "source": source, "target": target, "relation": relation, "count": 1, "first_seen": when, "last_seen": when, "first_sequence": sequence, "last_sequence": sequence}


def _graph(nodes: list[dict[str, object]], edges: list[dict[str, object]]) -> dict[str, object]:
    root = _node(ROOT, "agent", "/root", provider="python", agent_path="/root", agent_role="root")
    process = _node("process:python", "process", "python")
    nodes = [root, process, *nodes]
    edges = [_edge(ROOT, "LAUNCHED", "process:python", 1), *edges]
    return {"graph_schema_version": "0.2", "session_id": "infra", "nodes": nodes, "edges": edges, "node_count": len(nodes), "edge_count": len(edges)}


def _gateway_graph() -> dict[str, object]:
    gateway = f"inference-gateway:litellm:{SCOPE}"
    provider = "inference-provider:7d3194f79e645c42e4396dda"
    request = f"inference-request:litellm:{SCOPE}:gw-1"
    served = f"model:gateway:litellm:{SCOPE}:openai/gpt-4.1"
    alias = f"model:gateway:litellm:{SCOPE}:smart"
    nodes = [
        _node(gateway, "inference_gateway", "litellm", endpoint_scope=SCOPE, provider="litellm"),
        _node(provider, "inference_provider", "openai"),
        _node(request, "inference_request", "gw-1", endpoint_scope=SCOPE, provider="litellm"),
        _node(served, "model", "openai/gpt-4.1", catalog_id="openai/gpt-4.1", endpoint_scope=SCOPE, provider="litellm"),
        _node(alias, "model", "smart", catalog_id="smart", endpoint_scope=SCOPE, provider="litellm"),
    ]
    edges = [
        _edge(gateway, "SERVED_INFERENCE", request, 2),
        _edge(request, "REQUESTED_MODEL", alias, 3),
        _edge(request, "ROUTED_TO_MODEL", served, 4),
        _edge(request, "ROUTED_TO_PROVIDER", provider, 5),
    ]
    return _graph(nodes, edges)


def _runtime_graph(*, extra_catalog_edge: bool = False) -> dict[str, object]:
    runtime = f"model-runtime:vllm:{SCOPE}"
    request = f"inference-request:openai-compatible:{SCOPE}:ex-0"
    served = f"model:openai-compatible:{SCOPE}:Qwen/Qwen3-8B"
    catalog = "model:vllm:Qwen/Qwen3-8B"
    unrelated = "model:vllm:meta-llama/Llama-3.2-3B"
    nodes = [
        _node(runtime, "model_runtime", "vllm", endpoint_scope=SCOPE, provider="vllm"),
        _node(request, "inference_request", "ex-0", endpoint_scope=SCOPE, provider="openai-compatible"),
        _node(served, "model", "Qwen/Qwen3-8B", catalog_id="Qwen/Qwen3-8B", endpoint_scope=SCOPE, provider="openai-compatible"),
        _node(catalog, "model", "Qwen/Qwen3-8B", provider="vllm"),
        _node(unrelated, "model", "meta-llama/Llama-3.2-3B", provider="vllm"),
    ]
    edges = [
        _edge(request, "REQUESTED_MODEL", served, 2),
        _edge(runtime, "SERVES_MODEL", catalog, 3),
        _edge(runtime, "SERVES_MODEL", unrelated, 4),
    ]
    if extra_catalog_edge:
        edges.append(_edge("process:python", "OPENED_MODEL", catalog, 5))
    return _graph(nodes, edges)


def _by_id(projected: dict[str, object]) -> tuple[dict[str, dict], list[dict]]:
    return {node["id"]: node for node in projected["nodes"]}, list(projected["edges"])


def _reachable_from_root(projected: dict[str, object]) -> set[str]:
    adjacency: dict[str, set[str]] = {}
    for edge in projected["edges"]:
        adjacency.setdefault(edge["source"], set()).add(edge["target"])
    seen, queue = {ROOT}, deque([ROOT])
    while queue:
        for nxt in adjacency.get(queue.popleft(), ()):
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return seen


def test_gateway_serving_and_provider_routing_survive_request_collapse() -> None:
    graph = _gateway_graph()
    raw = copy.deepcopy(graph)
    projected = project_viewer_graph(graph)
    assert graph == raw
    nodes, edges = _by_id(projected)
    gateway, provider = f"inference-gateway:litellm:{SCOPE}", "inference-provider:7d3194f79e645c42e4396dda"
    served, alias = f"model:gateway:litellm:{SCOPE}:openai/gpt-4.1", f"model:gateway:litellm:{SCOPE}:smart"
    request = f"inference-request:litellm:{SCOPE}:gw-1"

    # The routed model is what answered; the alias the caller asked for is kept on the occurrence.
    inferred = [edge for edge in edges if edge["relation"] == "INFERRED"]
    assert [(edge["source"], edge["target"]) for edge in inferred] == [(ROOT, served)]
    occurrence = inferred[0]["viewer_occurrences"][0]
    assert occurrence["requested_model_ids"] == [alias]
    assert occurrence["requested_model_names"] == ["smart"]
    assert occurrence["served_by_ids"] == [gateway]
    assert occurrence["routed_provider_ids"] == [provider]
    assert alias not in nodes and request not in nodes

    by_relation = {edge["relation"]: edge for edge in edges if edge["source"] == served}
    assert by_relation["SERVED_BY"]["target"] == gateway
    assert by_relation["ROUTED_TO_PROVIDER"]["target"] == provider
    for edge in (by_relation["SERVED_BY"], by_relation["ROUTED_TO_PROVIDER"]):
        assert edge["causal"] is False and edge["viewer_only"] is True and edge["inferred"] is False
        assert edge["viewer_request_ids"] == [request]
        assert edge["attributions"] == ["viewer_inference_infrastructure_projection"]
    assert by_relation["SERVED_BY"]["viewer_link_basis"] == ["served_inference"]
    assert projected["viewer_projection"]["inference_infrastructure_edge_count"] == 2
    assert {gateway, provider, served} <= _reachable_from_root(projected)


def test_runtime_catalog_model_folds_into_the_served_model_by_endpoint_scope() -> None:
    graph = _runtime_graph()
    raw = copy.deepcopy(graph)
    projected = project_viewer_graph(graph)
    assert graph == raw
    nodes, edges = _by_id(projected)
    runtime = f"model-runtime:vllm:{SCOPE}"
    served = f"model:openai-compatible:{SCOPE}:Qwen/Qwen3-8B"
    catalog, unrelated = "model:vllm:Qwen/Qwen3-8B", "model:vllm:meta-llama/Llama-3.2-3B"

    # One Qwen node, served by the runtime; the runtime's other catalog entry stays as observed.
    assert catalog not in nodes
    assert [item["id"] for item in nodes[served]["attributes"]["viewer_runtime_models"]] == [catalog]
    served_by = [edge for edge in edges if edge["relation"] == "SERVED_BY"]
    assert [(edge["source"], edge["target"]) for edge in served_by] == [(served, runtime)]
    assert served_by[0]["viewer_link_basis"] == ["endpoint_scope"]
    assert served_by[0]["inferred"] is True and served_by[0]["causal"] is False
    assert served_by[0]["evidence_edge_ids"] == [f"{runtime}--SERVES_MODEL-->{catalog}"]
    assert served_by[0]["viewer_runtime_relations"] == ["SERVES_MODEL"]
    assert any(edge["source"] == runtime and edge["target"] == unrelated and edge["relation"] == "SERVES_MODEL" for edge in edges)
    assert projected["viewer_projection"]["folded_runtime_model_count"] == 1
    assert {runtime, served, unrelated} <= _reachable_from_root(projected)


def test_catalog_model_with_its_own_evidence_is_not_folded() -> None:
    projected = project_viewer_graph(_runtime_graph(extra_catalog_edge=True))
    nodes, edges = _by_id(projected)
    runtime, catalog = f"model-runtime:vllm:{SCOPE}", "model:vllm:Qwen/Qwen3-8B"
    served = f"model:openai-compatible:{SCOPE}:Qwen/Qwen3-8B"
    assert catalog in nodes
    assert "viewer_runtime_models" not in nodes[served]["attributes"]
    assert any(edge["source"] == runtime and edge["target"] == catalog and edge["relation"] == "SERVES_MODEL" for edge in edges)
    assert any(edge["source"] == served and edge["target"] == runtime and edge["relation"] == "SERVED_BY" for edge in edges)
    assert projected["viewer_projection"]["folded_runtime_model_count"] == 0


def test_runtime_reporting_the_served_model_itself_is_linked_directly() -> None:
    runtime = "model-runtime:ollama:7866d63830422cd421667c95"
    request = "inference-request:ollama:req-1"
    model = "model:ollama:llama3.2"
    graph = _graph(
        [
            _node(runtime, "model_runtime", "ollama", provider="ollama"),
            _node(request, "inference_request", "req-1", provider="ollama"),
            _node(model, "model", "llama3.2", provider="ollama"),
        ],
        [_edge(request, "USED_MODEL", model, 2), _edge(runtime, "LOADED_MODEL", model, 3)],
    )
    projected = project_viewer_graph(graph)
    nodes, edges = _by_id(projected)
    served_by = [edge for edge in edges if edge["relation"] == "SERVED_BY"]
    assert [(edge["source"], edge["target"], edge["viewer_link_basis"], edge["inferred"]) for edge in served_by] == [(model, runtime, ["runtime_model"], False)]
    assert not any(edge["relation"] == "LOADED_MODEL" for edge in edges)
    assert served_by[0]["evidence_edge_ids"] == [f"{runtime}--LOADED_MODEL-->{model}"]
    assert {runtime, model} <= _reachable_from_root(projected)


def test_alias_with_evidence_outside_the_request_stays_visible() -> None:
    graph = _gateway_graph()
    alias = f"model:gateway:litellm:{SCOPE}:smart"
    graph["edges"].append(_edge(f"inference-gateway:litellm:{SCOPE}", "ADVERTISES_MODEL", alias, 6))
    nodes, edges = _by_id(project_viewer_graph(graph))
    assert alias in nodes
    assert any(edge["target"] == alias and edge["relation"] == "ADVERTISES_MODEL" for edge in edges)


def test_link_inference_infrastructure_does_not_mutate_its_input() -> None:
    graph = _runtime_graph()
    nodes, edges, _ = collapse_inference_requests(copy.deepcopy(graph["nodes"]), copy.deepcopy(graph["edges"]), [])
    before = (copy.deepcopy(nodes), copy.deepcopy(edges))
    out_nodes, out_edges, summary = link_inference_infrastructure(nodes, edges)
    assert (nodes, edges) == before
    assert summary == {"infrastructure_edge_count": 1, "folded_runtime_model_count": 1}
    assert len(out_nodes) == len(nodes) - 1


def test_no_inference_means_no_infrastructure_edges() -> None:
    graph = _graph([_node("model-runtime:ollama:x", "model_runtime", "ollama")], [])
    nodes, edges, summary = link_inference_infrastructure(graph["nodes"], graph["edges"])
    assert (nodes, edges) == (graph["nodes"], graph["edges"])
    assert summary == {"infrastructure_edge_count": 0, "folded_runtime_model_count": 0}


LAUNCHER = "agent:python"


def _framework_run(*, extra_launcher: bool = False, framework_launcher: bool = False) -> dict[str, object]:
    # A user's own script running a framework: no agent is marked /root, the program that
    # started the recording made the wire call, and the framework agent ran inside it.
    request = "inference-request:openai-compatible:run:ex-0"
    model = "model:openai-compatible:run:gpt-4.1"
    nodes = [
        _node(LAUNCHER, "agent", "python", provider="python"),
        _node("agent:autogen:run:assistant", "agent", "assistant", provider="autogen", conversation_scope="framework_agent"),
        _node("session:run", "session", "run"),
        _node(request, "inference_request", "ex-0", provider="openai-compatible"),
        _node(model, "model", "gpt-4.1", provider="openai-compatible"),
        _node("file:/work/notes.txt", "file", "notes.txt", path="/work/notes.txt"),
    ]
    starter = "agent:autogen:run:assistant" if framework_launcher else LAUNCHER
    edges = [_edge(starter, "STARTED_SESSION", "session:run", 1), _edge(request, "REQUESTED_MODEL", model, 2)]
    if extra_launcher:
        nodes.append(_node("agent:node", "agent", "node", provider="node"))
        edges.append(_edge("agent:node", "STARTED_SESSION", "session:run", 1))
    return {"graph_schema_version": "0.2", "session_id": "run", "nodes": nodes, "edges": edges, "node_count": len(nodes), "edge_count": len(edges)}


def test_single_program_launcher_is_the_root_of_a_framework_run() -> None:
    graph = _framework_run()
    assert _roots(graph["nodes"], [], graph["edges"]) == ([LAUNCHER], {"python": [LAUNCHER]})
    # Without the session evidence there is no basis to choose among the agents.
    assert _roots(graph["nodes"], []) == ([], {})
    nodes, edges = _by_id(project_viewer_graph(graph))
    model = "model:openai-compatible:run:gpt-4.1"
    assert [(e["source"], e["target"]) for e in edges if e["relation"] == "INFERRED"] == [(LAUNCHER, model)]
    # The file nothing else touched is still reached from the program, not left floating.
    assert ORPHAN_FILES_NODE_ID in nodes
    assert [(e["source"], e["relation"]) for e in edges if e["target"] == ORPHAN_FILES_NODE_ID] == [(LAUNCHER, "OBSERVED_FILES")]


def test_ambiguous_or_framework_only_launchers_are_not_promoted_to_root() -> None:
    for graph in (_framework_run(extra_launcher=True), _framework_run(framework_launcher=True)):
        assert _roots(graph["nodes"], [], graph["edges"]) == ([], {})
        projected = project_viewer_graph(graph)
        _, edges = _by_id(projected)
        assert not any(e["relation"] == "INFERRED" for e in edges)
        assert projected["viewer_projection"]["unresolved_inference_requests"] == [
            {"request_ids": ["inference-request:openai-compatible:run:ex-0"], "reason": "missing_owner"}]
        assert not any(e["target"] == ORPHAN_FILES_NODE_ID for e in edges)
