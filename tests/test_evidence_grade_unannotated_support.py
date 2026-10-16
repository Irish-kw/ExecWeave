from execweave.evidence_grade import grade_edge


def _edge(
    edge_id: str,
    *,
    causal: bool | None = True,
    inferred: bool | None = False,
    attributions: list[str] | None = None,
    inference_methods: list[str] | None = None,
) -> dict:
    return {
        "id": edge_id,
        "causal": causal,
        "inferred": inferred,
        "attributions": attributions or [],
        "backends": ["test"],
        "inference_methods": inference_methods or [],
    }


def test_unannotated_support_observation_blocks_direct_grades() -> None:
    edge = _edge("mixed", attributions=["syscall"])
    edge["causal_unannotated_count"] = 1
    result = grade_edge(edge)
    assert result.grade == "U"
    assert result.reason == (
        "some supporting observations lack an explicit causal flag or attribution"
    )
    assert result.causal_unannotated_count == 1

    edge = _edge("sampled", attributions=["process_polling"])
    edge["attribution_unannotated_count"] = 2
    assert grade_edge(edge).grade == "U"

    edge = _edge("session", causal=None, attributions=["session_observation"])
    edge["causal_unannotated_count"] = 1
    assert grade_edge(edge).grade == "U"


def test_unannotated_support_keeps_inferred_and_noncausal_precedence() -> None:
    inferred = _edge("d", inferred=True, attributions=["syscall"], inference_methods=["m"])
    inferred["causal_unannotated_count"] = 1
    noncausal = _edge("c", causal=False, attributions=["syscall"])
    noncausal["causal_unannotated_count"] = 1
    assert grade_edge(inferred).grade == "D"
    assert grade_edge(noncausal).grade == "C"


def test_edges_without_unannotated_counters_keep_their_grade() -> None:
    result = grade_edge(_edge("legacy", attributions=["syscall"]))
    assert result.grade == "A"
    assert result.causal_unannotated_count == 0
    assert result.attribution_unannotated_count == 0


def test_folded_edge_records_unannotated_observations(tmp_path) -> None:
    from execweave.graph import GraphAccumulator

    def event(index: int, attributes: dict) -> dict:
        return {
            "schema_version": "0.1",
            "event_id": f"e{index}",
            "session_id": "s",
            "timestamp": f"2026-01-01T00:00:0{index}Z",
            "event_type": "file.opened",
            "relation": "OPENED_READ",
            "source": {"type": "process", "id": "process:1", "name": "python"},
            "target": {"type": "file", "id": "file:/tmp/a", "name": "/tmp/a"},
            "sequence": index,
            "attributes": attributes,
        }

    syscall = {"backend": "strace", "attribution": "syscall", "causal": True}
    graph = GraphAccumulator(session_id="s", source_path=tmp_path / "events.jsonl")
    graph.apply(event(1, syscall))
    graph.apply(event(2, dict(syscall)))
    [edge] = graph.to_dict()["edges"]
    assert edge["causal"] is True
    assert edge["causal_unannotated_count"] == 0
    assert edge["attribution_unannotated_count"] == 0
    assert grade_edge(edge).grade == "A"

    graph = GraphAccumulator(session_id="s", source_path=tmp_path / "events.jsonl")
    graph.apply(event(1, syscall))
    graph.apply(event(2, {"backend": "strace"}))
    [edge] = graph.to_dict()["edges"]
    # The aggregate flag still ignores the omitted value; the grade must not.
    assert edge["causal"] is True
    assert edge["attributions"] == ["syscall"]
    assert edge["causal_unannotated_count"] == 1
    assert edge["attribution_unannotated_count"] == 1
    assert grade_edge(edge).grade == "U"
