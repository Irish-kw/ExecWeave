from execweave.analysis import analyze_graph


def _base_graph() -> dict:
    process = "process:s1:100"
    sensitive = "file:/home/user/.ssh/id_ed25519"
    external = "network_endpoint:8.8.8.8:443"
    return {
        "session_id": "s1",
        "nodes": [
            {"id": process, "type": "process", "name": "python"},
            {"id": sensitive, "type": "file", "name": "id_ed25519"},
            {"id": external, "type": "network_endpoint", "name": "8.8.8.8:443"},
        ],
        "edges": [
            {
                "id": "file-edge",
                "source": process,
                "target": sensitive,
                "relation": "OPENED_READ",
                "causal": True,
                "first_sequence": 2,
                "last_sequence": 2,
                "event_ids": ["e-file"],
            },
            {
                "id": "net-edge",
                "source": process,
                "target": external,
                "relation": "CONNECTED_TO",
                "causal": True,
                "first_sequence": 3,
                "last_sequence": 3,
                "event_ids": ["e-net"],
            },
        ],
    }


def test_analysis_reports_sensitive_file_and_possible_network_path() -> None:
    result = analyze_graph(_base_graph())
    rule_ids = [finding["rule_id"] for finding in result["findings"]]

    assert "sensitive-file-access" in rule_ids
    assert "external-network-contact" in rule_ids
    assert "possible-sensitive-file-to-network-path" in rule_ids

    possible = next(
        finding
        for finding in result["findings"]
        if finding["rule_id"] == "possible-sensitive-file-to-network-path"
    )
    assert possible["severity"] == "high"
    assert possible["attributes"]["data_flow_proven"] is False
    assert possible["attributes"]["exfiltration_proven"] is False
    assert result["severity_counts"]["high"] == 1


def test_analysis_does_not_create_dataflow_finding_from_noncausal_file_observation() -> None:
    graph = _base_graph()
    graph["edges"][0]["causal"] = False
    result = analyze_graph(graph)
    assert not any(
        finding["rule_id"] == "possible-sensitive-file-to-network-path"
        for finding in result["findings"]
    )
    sensitive = next(
        finding for finding in result["findings"] if finding["rule_id"] == "sensitive-file-access"
    )
    assert sensitive["severity"] == "low"


def test_analysis_ignores_private_network_endpoint_for_external_rule() -> None:
    graph = _base_graph()
    graph["nodes"][2]["id"] = "network_endpoint:10.0.0.5:443"
    graph["nodes"][2]["name"] = "10.0.0.5:443"
    graph["edges"][1]["target"] = "network_endpoint:10.0.0.5:443"
    result = analyze_graph(graph)
    assert not any(
        finding["rule_id"] == "external-network-contact" for finding in result["findings"]
    )
    assert not any(
        finding["rule_id"] == "possible-sensitive-file-to-network-path"
        for finding in result["findings"]
    )
