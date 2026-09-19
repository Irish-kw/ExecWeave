"""Keep ordinary conversation reads lightweight and explicit exports self-contained."""
from __future__ import annotations

import copy
import json

import pytest

from execweave import investigation_index
from execweave.conversation_records import conversation_index_payload, write_conversation_records
from execweave.viewer_projection import render_graph_html, write_graph_html
from test_investigation_workspace import scenario


def test_default_projection_has_no_event_inspection(tmp_path, monkeypatch):
    graph, *_ = scenario(tmp_path)
    before = copy.deepcopy(graph)

    def forbidden(*args, **kwargs):
        raise AssertionError("ordinary conversation reads must not inspect event streams")

    monkeypatch.setattr(investigation_index, "build_investigation_index", forbidden)
    payload = conversation_index_payload(graph, tmp_path)
    assert "investigation" not in payload
    assert payload["entries"]
    assert graph == before


def test_extension_does_not_change_the_historical_projection(tmp_path):
    graph, *_ = scenario(tmp_path)
    ordinary = conversation_index_payload(graph, tmp_path)
    extended = conversation_index_payload(graph, tmp_path, include_investigation=True)
    assert extended.pop("investigation")["messages"]
    assert ordinary == extended


@pytest.mark.parametrize("exporter", ["records", "render", "write"])
def test_offline_exporters_explicitly_inspect_events(tmp_path, monkeypatch, exporter):
    graph, *_ = scenario(tmp_path)
    calls = []
    original = investigation_index.build_investigation_index

    def observed(*args, **kwargs):
        calls.append(True)
        return original(*args, **kwargs)

    monkeypatch.setattr(investigation_index, "build_investigation_index", observed)
    if exporter == "records":
        path, _ = write_conversation_records(graph, tmp_path)
        assert json.loads(path.read_text())["investigation"]["messages"]
    elif exporter == "render":
        html = render_graph_html(graph)
        assert "window.__execweaveStaticInvestigation=" in html
    else:
        write_graph_html(graph, tmp_path / "viewer.html")
        assert json.loads((tmp_path / "conversations.json").read_text())["investigation"]["messages"]
    assert calls == [True]
