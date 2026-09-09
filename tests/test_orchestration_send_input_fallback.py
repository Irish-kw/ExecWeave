from __future__ import annotations

from pathlib import Path

import execweave.viewer_orchestration_projection as flow
from test_orchestration_flow_projection import A1, A2, _graph


def test_send_input_without_tool_input_uses_bounded_provider_recipient_correlation(
    tmp_path: Path, monkeypatch,
) -> None:
    graph = _graph(tmp_path)
    graph["edges"] = [
        edge
        for edge in graph["edges"]
        if edge["id"] not in {"input-send1", "input-send2"}
    ]
    for node in graph["nodes"]:
        if node["id"] == "call:send-a1":
            node["first_seen"] = "2026-09-09T00:00:25.000000Z"
            node["last_seen"] = "2026-09-09T00:00:25.250000Z"
        elif node["id"] == "call:send-a2":
            node["first_seen"] = "2026-09-09T00:00:28.000000Z"
            node["last_seen"] = "2026-09-09T00:00:28.250000Z"

    monkeypatch.setattr(
        flow,
        "conversation_record_entries",
        lambda _graph, _root: [
            {
                "conversation_preview": {
                    "messages": [
                        {
                            "timestamp": "2026-09-09T00:00:25.600000Z",
                            "recipient": "Singer",
                            "kind": "user",
                            "text": "message intentionally not copied into the flow edge",
                        },
                        {
                            "timestamp": "2026-09-09T00:00:28.550000Z",
                            "recipient": "Rawls",
                            "kind": "user",
                            "text": "another private message body",
                        },
                    ]
                }
            }
        ],
    )

    projected = flow.project_model_orchestration_viewer_graph(graph)
    send_edges = [
        edge
        for edge in projected["edges"]
        if edge.get("viewer_only") is True and edge.get("relation") == "SENT_INPUT_TO"
    ]
    assert {(edge["target"], edge["count"]) for edge in send_edges} == {(A1, 1), (A2, 1)}
    assert all(edge.get("inferred") is True for edge in send_edges)
    assert all(
        edge.get("source_semantics") == ["provider_conversation_temporal_correlation"]
        for edge in send_edges
    )
    serialized = repr(send_edges)
    assert "message intentionally not copied" not in serialized
    assert "another private message body" not in serialized
