from pathlib import Path

import pytest

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
    assert "All node types" in html
    assert "All relations" in html
    assert "applyGraphFilters" in html


def test_viewer_contains_timeline_playback_and_partial_edge_semantics() -> None:
    html = render_graph_html(_graph())
    assert 'id="sequence-filter"' in html
    assert 'id="sequence-label"' in html
    assert 'id="timeline-play"' in html
    assert "Evidence sequence" in html
    assert "edgeExistsAt" in html
    assert "partial" in html
    assert "future counts are never shown early" in html


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
