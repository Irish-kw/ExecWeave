from __future__ import annotations

import copy
import os

import pytest

from execweave.viewer_external_endpoints import EXTERNAL_NODE_ID, LOCAL_NODE_ID
from execweave.viewer_projection import project_viewer_graph
from execweave.viewer_semantic_projection import (
    ORPHAN_FILES_NODE_ID,
    collapse_inference_requests,
)

ALL_PROVIDERS = (
    "claude", "codex", "antigravity", "cursor", "opencode", "ollama",
    "llamacpp", "vllm", "lmstudio", "anthropic", "openrouter", "litellm",
    "openai-compatible",
)
requested = os.environ.get("EXECWEAVE_PROVIDER_MATRIX", "").strip().lower()
PROVIDERS = (requested,) if requested in ALL_PROVIDERS else ALL_PROVIDERS


def _endpoint(address: str, *, when: str) -> dict[str, object]:
    return {
        "id": f"endpoint:{address}", "type": "network_endpoint", "name": address,
        "first_seen": when, "last_seen": when, "event_count": 1,
        "evidence_event_count": 1, "event_types": ["network.connection"], "attributes": {},
    }


def _graph(provider: str) -> dict[str, object]:
    root = {"id": f"agent:{provider}:root", "type": "agent", "name": "/root", "attributes": {"provider": provider, "agent_path": "/root", "agent_role": "root"}}
    process = {"id": f"process:{provider}", "type": "process", "name": provider, "attributes": {}}
    request = {"id": f"inference-request:{provider}:req-1", "type": "inference_request", "name": "req-1", "first_seen": "2026-09-07T00:00:01Z", "last_seen": "2026-09-07T00:00:02Z", "event_count": 2, "attributes": {"provider": provider}}
    model = {"id": f"model:{provider}:model-a", "type": "model", "name": "model-a", "attributes": {"provider": provider}}
    local = _endpoint("127.0.0.1:11434", when="2026-09-07T00:00:03Z")
    external = _endpoint("1.1.1.1:443", when="2026-09-07T00:00:04Z")
    orphan_file = {"id": f"file:/tmp/{provider}/result.txt", "type": "file", "name": "result.txt", "first_seen": "2026-09-07T00:00:05Z", "last_seen": "2026-09-07T00:00:05Z", "event_count": 1, "event_types": ["filesystem.created"], "attributes": {}}
    orphan_directory = {"id": f"directory:/tmp/{provider}/cache", "type": "directory", "name": "cache", "first_seen": "2026-09-07T00:00:06Z", "last_seen": "2026-09-07T00:00:06Z", "event_count": 1, "event_types": ["filesystem.created"], "attributes": {}}
    nodes = [root, process, request, model, local, external, orphan_file, orphan_directory]
    edges = [
        {"id": f"{request['id']}--USED_MODEL-->{model['id']}", "source": request["id"], "target": model["id"], "relation": "USED_MODEL", "count": 1, "first_seen": "2026-09-07T00:00:02Z", "last_seen": "2026-09-07T00:00:02Z", "first_sequence": 2, "last_sequence": 2},
        {"id": f"{process['id']}--CONNECTED_TO-->{local['id']}", "source": process["id"], "target": local["id"], "relation": "CONNECTED_TO", "count": 1, "first_seen": "2026-09-07T00:00:03Z", "last_seen": "2026-09-07T00:00:03Z", "first_sequence": 3, "last_sequence": 3, "event_ids": [f"{provider}-local"]},
        {"id": f"{process['id']}--CONNECTED_TO-->{external['id']}", "source": process["id"], "target": external["id"], "relation": "CONNECTED_TO", "count": 1, "first_seen": "2026-09-07T00:00:04Z", "last_seen": "2026-09-07T00:00:04Z", "first_sequence": 4, "last_sequence": 4, "event_ids": [f"{provider}-external"]},
    ]
    return {"graph_schema_version": "0.2", "session_id": f"provider-{provider}", "nodes": nodes, "edges": edges, "node_count": len(nodes), "edge_count": len(edges)}


@pytest.mark.parametrize("provider", PROVIDERS)
def test_provider_neutral_projection_has_no_request_or_endpoint_sprawl(provider: str) -> None:
    graph = _graph(provider)
    raw = copy.deepcopy(graph)
    projected = project_viewer_graph(graph)
    assert graph == raw
    node_by_id = {node["id"]: node for node in projected["nodes"]}
    assert not any(node.get("type") == "inference_request" for node in projected["nodes"])
    assert {LOCAL_NODE_ID, EXTERNAL_NODE_ID, ORPHAN_FILES_NODE_ID} <= set(node_by_id)
    local = node_by_id[LOCAL_NODE_ID]["attributes"]["endpoints"][0]
    assert (local["address"], local["first_seen"], local["first_sequence"]) == ("127.0.0.1:11434", "2026-09-07T00:00:03Z", 3)
    assert node_by_id[EXTERNAL_NODE_ID]["attributes"]["endpoints"][0]["address"] == "1.1.1.1:443"
    root_id, model_id = f"agent:{provider}:root", f"model:{provider}:model-a"
    inferred = [edge for edge in projected["edges"] if edge.get("relation") == "INFERRED" and edge.get("source") == root_id and edge.get("target") == model_id]
    assert len(inferred) == 1 and inferred[0]["count"] == 1
    assert inferred[0]["viewer_occurrences"][0]["request_ids"] == [f"inference-request:{provider}:req-1"]
    assert node_by_id[model_id]["attributes"]["viewer_inference_count"] == 1
    file_cluster = node_by_id[ORPHAN_FILES_NODE_ID]
    assert file_cluster["attributes"]["member_count"] == 2
    assert {item["type"] for item in file_cluster["attributes"]["entries"]} == {"file", "directory"}
    assert any(edge.get("source") == root_id and edge.get("target") == ORPHAN_FILES_NODE_ID and edge.get("relation") == "OBSERVED_FILES" for edge in projected["edges"])


@pytest.mark.parametrize("provider", PROVIDERS)
def test_model_switches_keep_chronological_inference_occurrences(provider: str) -> None:
    graph = _graph(provider)
    graph["nodes"] = [node for node in graph["nodes"] if node.get("type") not in {"inference_request", "model"}]
    graph["edges"] = [edge for edge in graph["edges"] if edge.get("relation") != "USED_MODEL"]
    root_id = f"agent:{provider}:root"
    for request_name, model_name, when, ordinal in (("req-1", "model-a", "2026-09-07T00:00:01Z", 1), ("req-2", "model-b", "2026-09-07T00:00:02Z", 2), ("req-3", "model-a", "2026-09-07T00:00:03Z", 3)):
        request_id, model_id = f"inference-request:{provider}:{request_name}", f"model:{provider}:{model_name}"
        if not any(node.get("id") == model_id for node in graph["nodes"]):
            graph["nodes"].append({"id": model_id, "type": "model", "name": model_name, "attributes": {"provider": provider}})
        graph["nodes"].append({"id": request_id, "type": "inference_request", "name": request_name, "first_seen": when, "last_seen": when, "attributes": {"provider": provider}})
        graph["edges"].append({"id": f"{request_id}--USED_MODEL-->{model_id}", "source": request_id, "target": model_id, "relation": "USED_MODEL", "count": 1, "first_seen": when, "last_seen": when, "first_sequence": ordinal, "last_sequence": ordinal})
    projected = project_viewer_graph(graph)
    inferred = {edge["target"]: edge for edge in projected["edges"] if edge.get("source") == root_id and edge.get("relation") == "INFERRED"}
    assert inferred[f"model:{provider}:model-a"]["count"] == 2
    assert inferred[f"model:{provider}:model-b"]["count"] == 1
    assert [item["request_ids"][0] for item in inferred[f"model:{provider}:model-a"]["viewer_occurrences"]] == [f"inference-request:{provider}:req-1", f"inference-request:{provider}:req-3"]


@pytest.mark.parametrize("provider", PROVIDERS)
def test_inferred_occurrence_keeps_root_prompt_answer_and_time(provider: str) -> None:
    """Every provider keeps conversation content on /root while request evidence stays hidden."""
    graph = _graph(provider)
    root_id = f"agent:{provider}:root"
    request_id = f"inference-request:{provider}:req-1"
    model_id = f"model:{provider}:model-a"
    entries = [
        {
            "provider": provider,
            "source_id": root_id,
            "evidence_source_id": request_id,
            "evidence_source_type": "inference_request",
            "conversation_preview": {
                "agent_path": "/root",
                "is_root": True,
                "messages": [
                    {
                        "timestamp": "2026-09-07T00:00:01Z",
                        "ordinal": 1,
                        "kind": "user_message",
                        "sender": "user",
                        "recipient": "/root",
                        "phase": None,
                        "text": f"{provider} prompt",
                    },
                    {
                        "timestamp": "2026-09-07T00:00:02Z",
                        "ordinal": 2,
                        "kind": "assistant_final_response",
                        "sender": "assistant",
                        "recipient": "user",
                        "phase": "final_answer",
                        "text": f"{provider} answer",
                    },
                ],
            },
        }
    ]
    nodes, edges, metadata = collapse_inference_requests(
        copy.deepcopy(graph["nodes"]), copy.deepcopy(graph["edges"]), entries
    )
    assert not any(node.get("type") == "inference_request" for node in nodes)
    inferred = next(
        edge
        for edge in edges
        if edge.get("source") == root_id
        and edge.get("target") == model_id
        and edge.get("relation") == "INFERRED"
    )
    occurrence = inferred["viewer_occurrences"][0]
    assert occurrence["first_seen"] == "2026-09-07T00:00:02Z"
    assert occurrence["first_sequence"] == 2
    assert occurrence["request_ids"] == [request_id]
    assert [message["text"] for message in occurrence["messages"]] == [
        f"{provider} prompt",
        f"{provider} answer",
    ]
    assert entries[0]["conversation_preview"]["agent_path"] == "/root"
    assert metadata["unresolved"] == []


def test_same_inference_request_gateway_runtime_pair_counts_once() -> None:
    graph = _graph("ollama")
    gateway = {"id": "inference-request:openrouter:shared", "type": "inference_request", "name": "shared", "attributes": {"provider": "openrouter"}}
    runtime_id = "inference-request:ollama:req-1"
    graph["nodes"].append(gateway)
    graph["edges"].append({"id": "same", "source": gateway["id"], "target": runtime_id, "relation": "SAME_INFERENCE_REQUEST", "count": 1})
    projected = project_viewer_graph(graph)
    inferred = [edge for edge in projected["edges"] if edge.get("relation") == "INFERRED"]
    assert len(inferred) == 1 and inferred[0]["count"] == 1
    assert set(inferred[0]["viewer_occurrences"][0]["request_ids"]) == {gateway["id"], runtime_id}


def test_unresolved_requests_are_hidden_but_reported() -> None:
    graph = _graph("ollama")
    graph["nodes"] = [node for node in graph["nodes"] if node.get("type") != "model"]
    graph["edges"] = [edge for edge in graph["edges"] if edge.get("relation") != "USED_MODEL"]
    projected = project_viewer_graph(graph)
    assert not any(node.get("type") == "inference_request" for node in projected["nodes"])
    unresolved = projected["viewer_projection"]["unresolved_inference_requests"]
    assert unresolved and unresolved[0]["reason"] == "missing_model"


def test_remaining_orphan_types_are_reported_in_projection_metadata() -> None:
    graph = _graph("ollama")
    graph["nodes"].append({"id": "mystery:1", "type": "mystery", "name": "mystery"})
    audit = project_viewer_graph(graph)["viewer_projection"]["orphan_audit"]
    mystery = next(item for item in audit["by_type"] if item["node_type"] == "mystery")
    assert mystery["count"] == 1 and mystery["examples"] == ["mystery:1"]


def test_shared_dashboard_surfaces_inference_and_file_clusters() -> None:
    from execweave.dashboard_shell import DASHBOARD_HTML

    assert "execweaveInferenceHistory" in DASHBOARD_HTML
    assert "kind==='model'" in DASHBOARD_HTML
    assert "kind==='file_cluster'" in DASHBOARD_HTML
    assert "Inference history" in DASHBOARD_HTML
