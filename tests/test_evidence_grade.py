from execweave.evidence_grade import annotate_finding, grade_edge, weakest_grade


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


def test_grade_a_requires_direct_causal_syscall_attribution() -> None:
    result = grade_edge(_edge("a", attributions=["syscall"]))
    assert result.grade == "A"
    assert result.reason == "direct causal syscall attribution"


def test_grade_b_marks_sampled_process_attribution() -> None:
    result = grade_edge(_edge("b", attributions=["process_polling"]))
    assert result.grade == "B"


def test_grade_c_marks_noncausal_or_session_correlated_evidence() -> None:
    noncausal = grade_edge(_edge("c1", causal=False, attributions=["syscall"]))
    session = grade_edge(_edge("c2", causal=None, attributions=["session_observation"]))
    assert noncausal.grade == "C"
    assert session.grade == "C"


def test_grade_d_cannot_be_upgraded_by_causal_flag() -> None:
    result = grade_edge(
        _edge(
            "d",
            causal=True,
            inferred=True,
            attributions=["syscall"],
            inference_methods=["temporal_correlation"],
        )
    )
    assert result.grade == "D"


def test_finding_uses_weakest_support_and_unknown_stays_unknown() -> None:
    finding = {"rule_id": "r", "severity": "high", "edge_ids": ["strong", "sampled"]}
    annotated = annotate_finding(
        finding,
        {
            "strong": _edge("strong", attributions=["syscall"]),
            "sampled": _edge("sampled", attributions=["polling"]),
        },
    )
    assert annotated["severity"] == "high"
    assert annotated["evidence_grade"] == "B"
    assert [item["grade"] for item in annotated["evidence_basis"]] == ["A", "B"]

    unknown = annotate_finding(
        {"rule_id": "missing", "severity": "low", "edge_ids": ["absent"]},
        {},
    )
    assert unknown["evidence_grade"] == "U"
    assert unknown["severity"] == "low"
    assert weakest_grade(["A", "future-grade"]) == "U"
