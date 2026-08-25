from pathlib import Path

import pytest

from execweave.graph_ops import condense_graph
from execweave.viewer import render_graph_html, write_graph_html


def _graph(*, with_sequence: bool = True) -> dict:
    edge = {
        "id": "e1",
        "source": "process:p1",
        "target": "file:/tmp/x",
        "relation": "OPENED_READ",
        "count": 3,
        "causal": True,
        "backends": ["strace"],
    }
    if with_sequence:
        edge["first_sequence"] = 2
        edge["last_sequence"] = 7
    return {
        "graph_schema_version": "0.1",
        "session_id": "s1",
        "event_count": 7,
        "node_count": 2,
        "edge_count": 1,
        "nodes": [
            {"id": "process:p1", "type": "process", "name": "python"},
            {
                "id": "file:/tmp/x",
                "type": "file",
                "name": "</script><script>alert(1)</script>",
            },
        ],
        "edges": [edge],
    }


def _inferred_graph() -> dict:
    return {
        "graph_schema_version": "0.1",
        "session_id": "s1",
        "event_count": 3,
        "node_count": 2,
        "edge_count": 1,
        "nodes": [
            {"id": "tool-call:1", "type": "tool_call", "name": "Bash"},
            {"id": "process:p1", "type": "process", "name": "python"},
        ],
        "edges": [
            {
                "id": "correlation:1",
                "source": "tool-call:1",
                "target": "process:p1",
                "relation": "CORRELATED_WITH_PROCESS",
                "count": 1,
                "causal": False,
                "inferred": True,
                "inference_methods": ["unique_process_argv_tail_match"],
                "confidence_min": 0.8,
                "confidence_max": 0.8,
                "supporting_event_ids": ["event-1", "event-2"],
            }
        ],
    }


def _expandable_graph() -> dict:
    process_id = "process:p1"
    nodes = [{"id": process_id, "type": "process", "name": "python"}]
    edges = []
    for index in range(4):
        node_id = f"file:/repo/src/file_{index}.py"
        nodes.append({"id": node_id, "type": "file", "name": f"file_{index}.py"})
        edges.append(
            {
                "id": f"edge-{index}",
                "source": process_id,
                "target": node_id,
                "relation": "OPENED_READ",
                "count": 1,
                "causal": True,
                "first_sequence": index + 1,
                "last_sequence": index + 1,
            }
        )
    graph = {
        "graph_schema_version": "0.1",
        "session_id": "s1",
        "event_count": 4,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "nodes": nodes,
        "edges": edges,
    }
    return condense_graph(graph, threshold=4, include_expansion=True)


def test_viewer_is_standalone_and_escapes_embedded_graph_data() -> None:
    html = render_graph_html(_graph())
    assert "ExecWeave" in html
    assert "<svg" in html
    assert 'src="http' not in html
    assert "https://" not in html
    assert "</script><script>alert(1)</script>" not in html
    assert "\\u003c/script\\u003e" in html


def test_viewer_contains_focus_filters() -> None:
    html = render_graph_html(_graph())
    assert 'id="type-filter"' in html
    assert 'id="relation-filter"' in html
    assert 'id="causal-filter"' in html
    assert 'id="observed-only-filter"' in html
    assert "All node types" in html
    assert "All relations" in html
    assert "applyGraphFilters" in html


def test_viewer_contains_focused_neighborhood_controls() -> None:
    html = render_graph_html(_graph())
    assert 'id="clear-focus"' in html
    assert "Focus 1 hop" in html
    assert "Focus 2 hops" in html
    assert "focusNeighborhood" in html
    assert "setFocus" in html
    assert "never creates inferred edges" in html


def test_viewer_contains_saved_view_presets() -> None:
    html = render_graph_html(_graph())
    assert 'id="preset-select"' in html
    assert 'id="save-preset"' in html
    assert 'id="delete-preset"' in html
    assert "snapshotView" in html
    assert "observed_only:observedOnlyFilter.checked" in html
    assert "state.observed_only===true" in html
    assert "loadPresets" in html
    assert "localStorage" in html
    assert "Graph evidence is never copied into preset storage" in html
    assert "page session only" in html


def test_viewer_contains_timeline_playback_and_partial_edge_semantics() -> None:
    html = render_graph_html(_graph())
    assert 'id="sequence-filter"' in html
    assert 'id="sequence-label"' in html
    assert 'id="timeline-play"' in html
    assert "Evidence sequence" in html
    assert "edgeExistsAt" in html
    assert "partial" in html
    assert "future counts are never shown early" in html


def test_viewer_distinguishes_inferred_edges_from_observed_edges() -> None:
    html = render_graph_html(_inferred_graph())
    assert "Inferred correlation" in html
    assert "They are not observed or causal evidence" in html
    assert ".edge.inferred" in html
    assert "edge.inferred===true" in html
    assert "· inferred" in html
    assert '"inferred":true' in html
    assert '"causal":false' in html


def test_viewer_observed_only_filter_removes_inferred_before_focus() -> None:
    html = render_graph_html(_inferred_graph())
    assert "observed only" in html
    assert "observedOnlyFilter.checked" in html
    assert "(!observedOnly||e.inferred!==true)" in html
    assert "const eligible=evidenceEdges(currentNodes,currentEdges)" in html
    assert "removes derived inferred relationships before focus traversal" in html


def test_viewer_contains_progressive_cluster_expansion() -> None:
    graph = _expandable_graph()
    html = render_graph_html(graph)
    cluster_id = next(iter(graph["expansion"]["clusters"]))

    assert cluster_id in html
    assert 'id="collapse-clusters"' in html
    assert "Expand cluster" in html
    assert "materializedGraph" in html
    assert "expandedClusters" in html
    assert "graph-condense --keep-expansion" in html


def test_viewer_safely_handles_graphs_without_sequence_metadata() -> None:
    html = render_graph_html(_graph(with_sequence=False))
    assert "const maxSequence=Math.max(0" in html
    assert "timeline.style.display='none'" in html


def test_write_graph_html_refuses_existing_nonempty_output(tmp_path: Path) -> None:
    output = tmp_path / "viewer.html"
    written = write_graph_html(_graph(), output)
    assert written == output.resolve()
    assert output.read_text(encoding="utf-8").startswith("<!doctype html>")

    with pytest.raises(FileExistsError):
        write_graph_html(_graph(), output)
