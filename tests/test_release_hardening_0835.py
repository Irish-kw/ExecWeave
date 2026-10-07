from __future__ import annotations

import json
import os
import stat
import threading
from http.client import HTTPConnection
from pathlib import Path

import pytest

from execweave.agent_bootstrap import AgentBootstrapResult
from execweave.collector import ProcessSnapshot, RuntimeCollector
from execweave.finalization import record_finalization
from execweave.filesystem import SessionFileEventHandler
from execweave.graph_ops import load_graph, validate_graph_payload
from execweave.live import _LiveState, _LocalThreadingHTTPServer, _PairingGate, _handler_factory
from execweave.private_io import (
    private_file_security_state,
    write_private_json,
    write_private_text,
)
from execweave.run_assessment import build_run_assessment
from execweave.schema import Entity
from execweave.sink import JsonlSink
from watchdog.events import FileModifiedEvent


def _records(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_private_artifact_writer_is_owner_only_and_rejects_link_targets(tmp_path: Path) -> None:
    target = tmp_path / "graph.json"
    write_private_json(target, {"secret": "value"})
    assert private_file_security_state(target) == "owner_only"
    if os.name != "nt":
        assert stat.S_IMODE(target.stat().st_mode) == 0o600
        link = tmp_path / "linked.json"
        link.symlink_to(target)
        with pytest.raises(ValueError, match="unsafe artifact destination"):
            write_private_text(link, "replacement", replace=True)
    original = tmp_path / "original.json"
    original.write_text("old", encoding="utf-8")
    hardlink = tmp_path / "hardlink.json"
    os.link(original, hardlink)
    with pytest.raises(ValueError, match="multiply-linked"):
        write_private_text(hardlink, "replacement", replace=True)
    assert original.read_text(encoding="utf-8") == "old"


def test_finalization_persists_assessment_bound_to_graph(tmp_path: Path) -> None:
    graph = {
        "graph_schema_version": "0.2",
        "session_id": "s1",
        "source_path": str(tmp_path / "events.jsonl"),
        "session_outcome": {
            "recorder_finished": True,
            "event_id": "finish-1",
            "timestamp": "2026-10-07T00:00:00Z",
            "return_code": 0,
            "collector_failed": False,
            "interrupted": False,
            "execution_state": "succeeded",
        },
        "observation_assessment": {
            "schema_version": "0.1",
            "state": "not_verified",
            "reasons": ["fixture"],
        },
        "nodes": [],
        "edges": [],
    }
    write_private_json(tmp_path / "graph.json", graph)
    write_private_json(
        tmp_path / "conversations.json",
        {"schema_version": "0.3", "entries": []},
    )
    write_private_text(tmp_path / "viewer.html", "<!doctype html><title>fixture</title>")
    result = record_finalization(tmp_path, state="complete")
    assert result["run_assessment"] == build_run_assessment(graph)
    assert result["run_assessment_binding"]["graph"] == result["artifacts"]["graph.json"]
    assert result["run_assessment_binding"]["assessment_schema_version"] == "0.1"
    saved = json.loads((tmp_path / "finalization.json").read_text(encoding="utf-8"))
    assert saved["run_assessment"] == result["run_assessment"]
    assert saved["run_assessment_binding"] == result["run_assessment_binding"]
    assert private_file_security_state(tmp_path / "finalization.json") == "owner_only"


def test_graph_reader_supports_known_versions_and_rejects_future_format(tmp_path: Path) -> None:
    for version in ("0.1", "0.2"):
        payload = {"graph_schema_version": version, "nodes": [], "edges": []}
        path = tmp_path / f"graph-{version}.json"
        write_private_json(path, payload)
        assert load_graph(path)["graph_schema_version"] == version
    with pytest.raises(ValueError, match="unsupported graph schema version: 9.0"):
        validate_graph_payload({"graph_schema_version": "9.0", "nodes": [], "edges": []})
    with pytest.raises(ValueError, match="unsupported graph schema version: missing"):
        validate_graph_payload({"nodes": [], "edges": []})


@pytest.mark.parametrize(
    ("state", "code", "collector_failed", "interrupted", "domain"),
    [
        ("failed", 7, False, False, "task"),
        ("collector_failed", 1, True, False, "environment"),
        ("interrupted", 130, False, True, "operator"),
        ("succeeded", 0, False, False, None),
    ],
)
def test_execution_failure_domain_is_explicit(
    state: str, code: int, collector_failed: bool, interrupted: bool, domain: str | None
) -> None:
    graph = {
        "graph_schema_version": "0.2",
        "nodes": [],
        "edges": [],
        "session_outcome": {
            "recorder_finished": True,
            "event_id": "finish",
            "return_code": code,
            "collector_failed": collector_failed,
            "interrupted": interrupted,
            "execution_state": state,
        },
    }
    execution = build_run_assessment(graph)["execution"]
    assert execution["state"] == state
    assert execution["failure_domain"] == domain


def test_privilege_process_creates_visible_non_enforcement_risk_record(tmp_path: Path) -> None:
    sink = JsonlSink(tmp_path / "events.jsonl")
    collector = RuntimeCollector(session_id="s", sink=sink, watch_root=tmp_path)
    collector._record_privilege_risk(
        ProcessSnapshot(
            pid=123,
            ppid=1,
            name="sudo",
            cmdline=["sudo", "example"],
            exe="/usr/bin/sudo",
            create_time=1.0,
        )
    )
    [event] = _records(sink.path)
    assert event["event_type"] == "risk.privilege_process"
    assert event["target"]["type"] == "risk_record"
    assert event["attributes"]["default_decision"] == "deny"
    assert event["attributes"]["enforced"] is False
    assert event["attributes"]["control_state"] == "observation_only"


def test_system_path_change_creates_risk_without_writing_system_path(tmp_path: Path) -> None:
    sink = JsonlSink(tmp_path / "events.jsonl")
    session = Entity(type="session", id="session:s")
    handler = SessionFileEventHandler(
        session_id="s", session_entity=session, sink=sink, excluded_roots=[sink.path]
    )
    handler._emit(FileModifiedEvent("/etc/execweave-never-created"))
    rows = _records(sink.path)
    assert [row["event_type"] for row in rows] == [
        "filesystem.modified",
        "risk.system_path_change",
    ]
    risk = rows[-1]
    assert risk["attributes"]["trigger"] == "system_configuration"
    assert risk["attributes"]["default_decision"] == "deny"
    assert risk["attributes"]["enforced"] is False
    assert not Path("/etc/execweave-never-created").exists()


def test_hook_configuration_is_time_qualified_at_start_and_end(tmp_path: Path, monkeypatch) -> None:
    import execweave.agent_bootstrap as bootstrap

    monkeypatch.setattr(bootstrap, "supported_agent", lambda command: "antigravity")
    states = iter(
        [
            AgentBootstrapResult(
                provider="antigravity", status="configured_unverified",
                path="/fixture/hooks.json", changed=False, detail="fixture"
            ),
            AgentBootstrapResult(
                provider="antigravity", status="not_configured",
                path="/fixture/hooks.json", changed=False, detail="fixture"
            ),
        ]
    )
    monkeypatch.setattr(bootstrap, "inspect_supported_agent", lambda command: next(states))
    sink = JsonlSink(tmp_path / "events.jsonl")
    collector = RuntimeCollector(session_id="s", sink=sink, watch_root=tmp_path)
    session = Entity(type="session", id="session:s")
    collector._record_hook_state(["agy"], session, phase="session_start")
    collector._record_hook_state(["agy"], session, phase="session_end")
    rows = _records(sink.path)
    assert [row["attributes"]["phase"] for row in rows] == ["session_start", "session_end"]
    assert [row["attributes"]["status"] for row in rows] == [
        "configured_unverified", "not_configured"
    ]
    assert all(row["timestamp"] for row in rows)
    assert all(row["attributes"]["delivery_proven"] is False for row in rows)


def test_browser_pairing_exchanges_post_body_for_http_only_cookie(tmp_path: Path) -> None:
    state = _LiveState("s", tmp_path / "events.jsonl")
    token = "api-secret"
    gate = _PairingGate("pair-secret")
    server = _LocalThreadingHTTPServer(("127.0.0.1", 0), _handler_factory(state, token, gate))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    try:
        connection = HTTPConnection(host, port, timeout=2)
        body = "code=pair-secret"
        connection.request(
            "POST", "/pair", body=body,
            headers={"Content-Type": "application/x-www-form-urlencoded",
                     "Content-Length": str(len(body))},
        )
        response = connection.getresponse()
        assert response.status == 303
        cookie = response.getheader("Set-Cookie")
        assert cookie is not None
        assert "HttpOnly" in cookie and "SameSite=Strict" in cookie
        assert token in cookie
        assert "pair-secret" not in cookie
        response.read()
        connection.close()

        connection = HTTPConnection(host, port, timeout=2)
        connection.request("GET", "/graph.json", headers={"Cookie": cookie.split(";", 1)[0]})
        response = connection.getresponse()
        assert response.status == 200
        response.read()
        connection.close()

        # The pairing secret is one-time and the API token is not accepted in a URL.
        connection = HTTPConnection(host, port, timeout=2)
        connection.request("POST", "/pair", body=body,
                           headers={"Content-Length": str(len(body))})
        response = connection.getresponse()
        assert response.status == 403
        response.read()
        connection.close()
        connection = HTTPConnection(host, port, timeout=2)
        connection.request("GET", "/graph.json?t=api-secret")
        response = connection.getresponse()
        assert response.status == 401
        response.read()
        connection.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_automatic_capture_policy_fails_closed_without_breaking_explicit_sdk_capture(
    tmp_path: Path, monkeypatch
) -> None:
    from execweave._http_proxy_base import ProxyConfig, record_exchange_fail_open
    from execweave.content_store import FullFidelityContentStore
    from execweave.privacy import (
        CONTENT_CAPTURE_ENV,
        content_capture_policy,
        full_content_capture_enabled,
    )

    # The environment policy controls automatic recorders, not explicit SDK calls.
    # Otherwise observability could change the workload's own program semantics.
    explicit = tmp_path / "explicit-sdk"
    monkeypatch.setenv(CONTENT_CAPTURE_ENV, "metadata_only")
    assert content_capture_policy().mode == "metadata_only"
    assert full_content_capture_enabled() is False
    reference = FullFidelityContentStore(explicit).put_text(
        "explicit-sdk-secret", content_kind="framework.explicit"
    )
    assert (explicit / reference.path).read_text(encoding="utf-8") == "explicit-sdk-secret"
    assert private_file_security_state(explicit / reference.path) == "owner_only"

    # Automatic localhost-proxy capture must fail closed without persisting plaintext.
    automatic = tmp_path / "automatic"
    config = ProxyConfig(upstream="http://127.0.0.1:8000", sidecar=automatic / "semantic.jsonl")
    assert record_exchange_fail_open(
        config, exchange_id="x", request_body=b'{"messages":[{"content":"SECRET"}]}',
        request_content_type="application/json", response_body=b'{"choices":[]}',
        response_content_type="application/json", method="POST", request_path="/v1/chat",
        status=200,
    ) is False
    assert not (automatic / "content").exists()
    assert not config.sidecar.exists()

    # Mistyped policy values also fail closed at automatic boundaries.
    monkeypatch.setenv(CONTENT_CAPTURE_ENV, "typo-full-ish")
    assert content_capture_policy().state == "invalid_fail_closed"
    assert full_content_capture_enabled() is False
    assert record_exchange_fail_open(
        config, exchange_id="y", request_body=b'{"messages":[]}',
        request_content_type="application/json", response_body=b'{"choices":[]}',
        response_content_type="application/json", method="POST", request_path="/v1/chat",
        status=200,
    ) is False
    assert not (automatic / "content").exists()

    monkeypatch.setenv(CONTENT_CAPTURE_ENV, "full")
    assert full_content_capture_enabled() is True


def test_live_defaults_metadata_only_and_requires_explicit_full_opt_in(tmp_path: Path) -> None:
    import sys

    from execweave.live import run_live

    for name, requested in (("default", "metadata_only"), ("full", "full")):
        root = tmp_path / name
        work = root / "work"
        work.mkdir(parents=True)
        kwargs = {} if requested == "metadata_only" else {"content_capture": "full"}
        result = run_live(
            [sys.executable, "-c", "pass"],
            watch_root=work,
            output_dir=root / "out",
            collect_filesystem=False,
            collect_network=False,
            open_browser=False,
            linger_seconds=0,
            **kwargs,
        )
        started = next(
            row for row in _records(result.event_stream) if row["event_type"] == "session.started"
        )
        assert started["attributes"]["content_capture_mode"] == requested
        session = started["target"]
        assert session["attributes"]["content_capture_mode"] == requested
        if requested == "metadata_only":
            assert started["attributes"]["content_capture_policy_state"] == "explicit_metadata_only"
        else:
            assert started["attributes"]["content_capture_policy_state"] == "explicit_full"


def test_real_runs_separate_task_failure_from_environment_failure(tmp_path: Path) -> None:
    import sys

    from execweave.live import run_live

    task_work = tmp_path / "task-work"
    task_work.mkdir()
    task = run_live(
        [sys.executable, "-c", "raise SystemExit(7)"],
        watch_root=task_work,
        output_dir=tmp_path / "task-out",
        collect_filesystem=False,
        collect_network=False,
        open_browser=False,
        linger_seconds=0,
    )
    assert task.return_code == 7
    task_final = json.loads((task.output_dir / "finalization.json").read_text(encoding="utf-8"))
    assert task_final["run_assessment"]["execution"]["state"] == "failed"
    assert task_final["run_assessment"]["execution"]["failure_domain"] == "task"

    env_work = tmp_path / "env-work"
    env_work.mkdir()
    env_out = tmp_path / "env-out"
    with pytest.raises(FileNotFoundError):
        run_live(
            ["definitely-no-execweave-command-0835"],
            watch_root=env_work,
            output_dir=env_out,
            collect_filesystem=False,
            collect_network=False,
            open_browser=False,
            linger_seconds=0,
        )
    # Launch failure is still a finalized, readable run rather than a missing graph.
    assert {"events.jsonl", "graph.json", "viewer.html", "conversations.json", "finalization.json"}.issubset(
        {path.name for path in env_out.iterdir()}
    )
    env_final = json.loads((env_out / "finalization.json").read_text(encoding="utf-8"))
    assert env_final["run_assessment"]["execution"]["state"] == "collector_failed"
    assert env_final["run_assessment"]["execution"]["failure_domain"] == "environment"
    assert env_final["run_assessment_binding"]["graph"] == env_final["artifacts"]["graph.json"]


def test_file_only_reader_upgrade_and_rollback_contract(tmp_path: Path) -> None:
    import sys

    from execweave.live import run_live
    from execweave.viewer import build_viewer_from_graph

    work = tmp_path / "work"
    work.mkdir()
    result = run_live(
        [sys.executable, "-c", "pass"],
        watch_root=work,
        output_dir=tmp_path / "run",
        collect_filesystem=False,
        collect_network=False,
        open_browser=False,
        linger_seconds=0,
    )
    graph = load_graph(result.graph)
    assert graph["graph_schema_version"] == "0.2"
    reopened = build_viewer_from_graph(result.graph, tmp_path / "reopened.html", open_browser=False)
    assert reopened.is_file()
    assert private_file_security_state(reopened) == "owner_only"

    # Current reader is an upgrade path for the prior 0.1 format.
    validate_graph_payload({"graph_schema_version": "0.1", "nodes": [], "edges": []})
    # A simulated rolled-back 0.1-only reader must reject 0.2 instead of misreading it.
    with pytest.raises(ValueError, match="unsupported graph schema version: 0.2"):
        validate_graph_payload(
            {"graph_schema_version": "0.2", "nodes": [], "edges": []},
            supported_versions=frozenset({"0.1"}),
        )


def test_event_and_semantic_streams_use_private_append_policy(tmp_path: Path) -> None:
    from execweave.codex_adapter import append_semantic_records
    from execweave.schema import RuntimeEvent

    events = tmp_path / "events.jsonl"
    JsonlSink(events).emit(RuntimeEvent.create(session_id="s", event_type="test", relation="TEST"))
    assert private_file_security_state(events) == "owner_only"

    sidecar = tmp_path / "semantic.jsonl"
    append_semantic_records(
        sidecar,
        [{
            "timestamp": "2026-10-07T00:00:00Z",
            "event_type": "semantic.test",
            "relation": "OBSERVED",
            "source": None,
            "target": None,
            "attributes": {},
        }],
    )
    assert private_file_security_state(sidecar) == "owner_only"


def test_external_integrity_anchor_must_match_out_of_band_digest(tmp_path: Path) -> None:
    from execweave.integrity import seal_run_integrity, verify_run_integrity

    run = tmp_path / "sealed-run"
    run.mkdir()
    write_private_text(run / "evidence.txt", "evidence")
    manifest = seal_run_integrity(run)
    digest = manifest["manifest_body_sha256"]

    anchored = verify_run_integrity(run, expected_manifest_body_sha256=digest)
    assert anchored.valid is True
    assert anchored.external_anchor_checked is True
    assert anchored.external_anchor_match is True

    # The external value is not stored inside the writable run tree. A different
    # externally supplied digest therefore makes verification fail even if the local
    # manifest is internally self-consistent.
    wrong = "0" * 64 if digest != "0" * 64 else "1" * 64
    mismatch = verify_run_integrity(run, expected_manifest_body_sha256=wrong)
    assert mismatch.valid is False
    assert mismatch.external_anchor_checked is True
    assert mismatch.external_anchor_match is False
    assert "external anchor digest mismatch" in mismatch.errors
