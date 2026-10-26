from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.error import URLError

import execweave.auto_specialized as auto_module
import execweave.collector as collector_module
from execweave.live import run_live


def test_lmstudio_post_probe_requires_explicit_local_port(monkeypatch) -> None:
    monkeypatch.delenv("LMS_SERVER_HOST", raising=False)

    spec = auto_module._lmstudio_post_probe_spec(
        [r"C:\\Tools\\lms.exe", "server", "start", "--port", "12345"]
    )
    assert spec is not None
    assert spec.runtime == "lmstudio"
    assert spec.endpoint == "http://127.0.0.1:12345"
    assert spec.path == "/v1/models"

    bound = auto_module._lmstudio_post_probe_spec(
        ["lms", "server", "start", "--port=12346", "--bind", "localhost"]
    )
    assert bound is not None
    assert bound.endpoint == "http://localhost:12346"

    assert auto_module._lmstudio_post_probe_spec(["lms", "server", "start"]) is None
    assert auto_module._lmstudio_post_probe_spec(
        ["lms", "server", "start", "--port", "not-a-port"]
    ) is None

    monkeypatch.setenv("LMS_SERVER_HOST", "example.com")
    assert auto_module._lmstudio_post_probe_spec(
        ["lms", "server", "start", "--port", "12347"]
    ) is None


def test_lmstudio_prepare_does_not_claim_preexisting_server(monkeypatch) -> None:
    monkeypatch.delenv("LMS_SERVER_HOST", raising=False)
    monkeypatch.setattr(
        auto_module,
        "_get_json",
        lambda url, timeout: {"data": [{"id": "already-there"}]},
    )

    prepared = auto_module.prepare_post_command_specialized_probe(
        ["lms", "server", "start", "--port", "12345"]
    )
    assert prepared is None


def test_run_live_materializes_lmstudio_catalog_only_after_successful_start(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("LMS_SERVER_HOST", raising=False)
    calls = 0

    def fake_get_json(url: str, *, timeout: float) -> dict[str, object]:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise URLError("not running before launch")
        return {
            "data": [
                {"id": "lmstudio/catalog-model", "owned_by": "lmstudio"},
            ]
        }

    monkeypatch.setattr(auto_module, "_get_json", fake_get_json)
    monkeypatch.setattr(
        collector_module,
        "resolve_launch_command",
        lambda command: [sys.executable, "-c", "pass"],
    )

    result = run_live(
        ["lms", "server", "start", "--port", "12345"],
        watch_root=tmp_path,
        output_dir=tmp_path / "lmstudio-live",
        poll_interval=0.02,
        collect_filesystem=False,
        collect_network=False,
        port=0,
        open_browser=False,
        linger_seconds=0,
    )

    assert result.return_code == 0
    assert calls >= 2
    assert result.semantic_sidecar.exists()
    records = [
        json.loads(line)
        for line in result.semantic_sidecar.read_text(encoding="utf-8").splitlines()
    ]
    assert records
    assert all(record["relation"] == "ADVERTISES_MODEL" for record in records)
    assert all(record["attributes"]["provider"] == "lmstudio" for record in records)

    graph = json.loads(result.graph.read_text(encoding="utf-8"))
    assert graph["source_path"].endswith("events.semantic.jsonl")
    assert any(edge["relation"] == "ADVERTISES_MODEL" for edge in graph["edges"])
    assert all(edge["relation"] != "LOADED_MODEL" for edge in graph["edges"])
    assert any(
        node.get("type") == "model" and node.get("name") == "lmstudio/catalog-model"
        for node in graph["nodes"]
    )


def test_failed_lmstudio_start_does_not_materialize_catalog(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("LMS_SERVER_HOST", raising=False)
    calls = 0

    def unavailable_before_launch(url: str, *, timeout: float) -> dict[str, object]:
        nonlocal calls
        calls += 1
        raise URLError("not running")

    monkeypatch.setattr(auto_module, "_get_json", unavailable_before_launch)
    monkeypatch.setattr(
        collector_module,
        "resolve_launch_command",
        lambda command: [sys.executable, "-c", "raise SystemExit(2)"],
    )

    result = run_live(
        ["lms", "server", "start", "--port", "12345"],
        watch_root=tmp_path,
        output_dir=tmp_path / "lmstudio-failed",
        poll_interval=0.02,
        collect_filesystem=False,
        collect_network=False,
        port=0,
        open_browser=False,
        linger_seconds=0,
    )

    assert result.return_code == 2
    assert calls == 1
    assert result.materialized_event_stream == result.event_stream
    assert not result.semantic_sidecar.exists() or result.semantic_sidecar.stat().st_size == 0
    graph = json.loads(result.graph.read_text(encoding="utf-8"))
    assert all(edge["relation"] != "ADVERTISES_MODEL" for edge in graph["edges"])
