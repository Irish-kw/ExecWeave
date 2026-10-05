"""Reproduce the 0.8.34 observation failure without a paid/privileged provider.

No test here executes sudo or writes a system hook. Native workloads and synthetic
provider/configuration tests are kept distinct; neither stands in for real agy.
"""
from __future__ import annotations

import json
import os
import shlex
import stat
import sys
from pathlib import Path

import pytest

from execweave import entry
from execweave.agent_bootstrap import bootstrap_supported_agent, inspect_supported_agent
from execweave.collector import RuntimeCollector
from execweave.filesystem import FileWatcher
from execweave.graph import GraphAccumulator
from execweave.hook_command import hook_argv, hook_command
from execweave.hook_delivery import sidecar_delivery
from execweave.live import run_live
from execweave.run_assessment import build_run_assessment
from execweave.schema import Entity, RuntimeEvent
from execweave.sink import JsonlSink

PRIMES = "2 3 5 7 11 13 17 19 23 29"
WORKLOAD = '''from pathlib import Path
import subprocess, sys
Path('primes.py').write_text("print('2 3 5 7 11 13 17 19 23 29')\\n", encoding='utf-8')
p = subprocess.run([sys.executable, 'primes.py'], capture_output=True, text=True, check=True)
Path('output.txt').write_text(p.stdout, encoding='utf-8')
'''


def records(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


@pytest.fixture(params=["equal", "nested", "external"])
def native_run(tmp_path, request):
    work = tmp_path / "work"
    work.mkdir()
    out = {"equal": work, "nested": work / "run", "external": tmp_path / "run"}[request.param]
    result = run_live([sys.executable, "-c", WORKLOAD], watch_root=work, output_dir=out,
                      open_browser=False, linger_seconds=0, collect_network=False,
                      poll_interval=0.10)
    return work, result


def test_native_files_survive_all_output_watch_layouts(native_run):
    work, result = native_run
    assert result.return_code == 0
    # Independent task assertion. This does not grant graph observation completeness.
    assert (work / "output.txt").read_text().strip() == PRIMES
    graph = json.loads(result.graph.read_text())
    files = {node["name"]: node for node in graph["nodes"] if node["type"] == "file"}
    for name in ("primes.py", "output.txt"):
        assert name in files
        assert files[name]["attributes"]["writer_identity"] == "unknown"
        assert files[name]["attributes"]["snapshot_state"] == "not_captured"
    assert "events.jsonl" not in files and "semantic.jsonl" not in files
    assert graph["event_count"] < 300  # no recorder-created filesystem feedback loop
    observation = graph["observation_assessment"]
    assert observation["state"] == "observation_incomplete"
    assert observation["unknown_owner_files"] >= 2
    assert {"zero_specialized_evidence", "unknown_file_writer", "short_lived_process_loss_possible",
            "file_snapshot_not_captured"}.issubset(observation["reasons"])
    assert observation["missed_process_lower_bound"] is None  # no fabricated missing-child count
    assert graph["session_outcome"]["state"] == "observation_incomplete"
    assert graph["session_outcome"]["execution_state"] == "succeeded"
    assessment = build_run_assessment(graph)
    assert assessment["execution"]["state"] == "succeeded"
    assert assessment["task_validation"]["state"] == "unverified"
    final = json.loads((result.output_dir / "finalization.json").read_text())
    assert final["observation_assessment"] == observation
    assert final["session_status"] == "observation_incomplete"
    assert final["session_outcome"] == graph["session_outcome"]
    html = result.viewer.read_text(encoding="utf-8")
    assert "OBSERVATION INCOMPLETE" in html
    assert "Observation completeness" in html
    assert "unknown_file_writer" in html
    summary = result.to_dict()
    assert summary["semantic_sidecar"] is None
    assert summary["semantic_sidecar_status"] == "not_produced"
    assert summary["artifacts"]["semantic_sidecar"] == {"status": "not_produced", "path": None}


def test_summary_does_not_advertise_deleted_artifact(native_run):
    _work, result = native_run
    result.viewer.unlink()
    summary = result.to_dict()
    assert summary["viewer"] is None
    assert summary["artifacts"]["viewer"]["status"] == "not_produced"


def test_final_metadata_reconciliation_catches_changes_without_notifications(tmp_path, monkeypatch):
    sink = JsonlSink(tmp_path / "events.jsonl")
    session = Entity(type="session", id="session:test")
    existing = tmp_path / "existing.txt"
    existing.write_text("before")
    removed = tmp_path / "removed.txt"
    removed.write_text("delete me")
    watcher = FileWatcher(root=tmp_path, session_id="test", session_entity=session, sink=sink,
                          excluded_roots=[sink.path])
    monkeypatch.setattr(watcher, "_schedule_and_start", lambda: None)
    monkeypatch.setattr(watcher, "_shutdown_observer", lambda timeout: None)
    watcher.start()
    (tmp_path / "primes.py").write_text("print(2)")
    existing.write_text("after")
    removed.unlink()
    watcher.stop()
    seen = {(r["event_type"], r["target"]["name"]) for r in records(sink.path)}
    assert ("filesystem.created", "primes.py") in seen
    assert ("filesystem.modified", "existing.txt") in seen
    assert ("filesystem.deleted", "removed.txt") in seen
    before = sink.path.read_bytes()
    watcher.stop()
    assert sink.path.read_bytes() == before
    assert all(r["attributes"]["causal"] is False for r in records(sink.path))


def test_incomplete_inventory_is_not_silently_complete(tmp_path, monkeypatch):
    sink = JsonlSink(tmp_path / "events.jsonl")
    watcher = FileWatcher(root=tmp_path, session_id="test",
                          session_entity=Entity(type="session", id="session:test"),
                          sink=sink, excluded_roots=[sink.path])
    monkeypatch.setattr(watcher, "_schedule_and_start", lambda: None)
    monkeypatch.setattr(watcher, "_shutdown_observer", lambda timeout: None)
    watcher.start()
    watcher._inventory_limited = True
    watcher.stop()
    assert any(r["attributes"].get("reason") == "filesystem_inventory_incomplete"
               for r in records(sink.path))


def test_zero_specialized_recomputed_after_late_semantic_events(tmp_path):
    acc = GraphAccumulator(session_id="test", source_path=tmp_path / "events.jsonl")
    acc.apply({"event_type": "session.finished", "attributes": {"return_code": 0}})
    assert "zero_specialized_evidence" in acc.to_dict()["observation_assessment"]["reasons"]
    acc.apply({"event_type": "semantic.task.completed", "attributes": {"backend": "semantic"}})
    assert "zero_specialized_evidence" not in acc.to_dict()["observation_assessment"]["reasons"]
    assert acc.to_dict()["observation_assessment"]["state"] != "complete"


def test_read_only_file_notification_is_not_unknown_writer(tmp_path):
    acc = GraphAccumulator(session_id="test", source_path=tmp_path / "events.jsonl")
    acc.apply({"event_type": "filesystem.opened", "target": {"type": "file", "id": "file:x"},
               "attributes": {"causal": False}})
    assert acc.to_dict()["observation_assessment"]["unknown_owner_files"] == 0


@pytest.mark.parametrize("body,state", [(None, "not_produced"), ("", "no_records"),
                                         ("\n\n", "no_records"), ("{}", "invalid_record"),
                                         ("not json", "unreadable_or_invalid")])
def test_missing_empty_and_bogus_hook_delivery(tmp_path, body, state):
    path = tmp_path / "semantic.jsonl"
    if body is not None:
        path.write_text(body)
    assert sidecar_delivery(str(path))["state"] == state


def test_configured_silent_hook_creates_durable_warning(tmp_path, monkeypatch):
    # Synthetic configuration, not a real agy claim.
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    result = bootstrap_supported_agent(["agy"], home=home, environment={})
    assert result.status == "configured_unverified"
    sidecar = tmp_path / "semantic.jsonl"
    monkeypatch.setenv("EXECWEAVE_SEMANTIC_SIDECAR", str(sidecar))
    sink = JsonlSink(tmp_path / "events.jsonl")
    collector = RuntimeCollector(session_id="test", sink=sink, watch_root=tmp_path)
    collector._record_observation_warnings(["agy"], Entity(type="session", id="session:test"))
    warnings = [r for r in records(sink.path) if r["attributes"].get("reason") == "hook_no_evidence"]
    assert len(warnings) == 1
    assert warnings[0]["attributes"]["hook_configuration_state"] == "configured_unverified"
    assert warnings[0]["attributes"]["delivery"]["state"] == "not_produced"
    assert warnings[0]["target"]["type"] == "observation_warning"


def test_live_entry_never_installs_hook(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(entry.cli, "main", lambda args: 0)
    def forbidden(*args, **kwargs):
        raise AssertionError("live must not install or repair agent hooks")
    monkeypatch.setattr(entry, "bootstrap_supported_agent", forbidden)
    assert entry.main(["live", "--", "agy", "--print", "hello"]) == 0
    assert list(tmp_path.iterdir()) == []


def test_explicit_installer_and_status_are_distinct(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    if hasattr(os, "geteuid"):
        monkeypatch.setattr(os, "geteuid", lambda: 1000)
    assert entry.main(["hooks", "status", "antigravity"]) == 0
    assert list(tmp_path.iterdir()) == []
    assert entry.main(["hooks", "install", "antigravity"]) == 0
    assert (tmp_path / ".gemini/config/hooks.json").is_file()
    assert "configured_unverified" in capsys.readouterr().out


@pytest.mark.skipif(not hasattr(os, "geteuid"), reason="POSIX effective UID check")
def test_explicit_installer_refuses_root(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    assert entry.main(["hooks", "install", "antigravity"]) == 2
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("provider,module", [("claude", "execweave.claude_hook_cli"),
    ("codex", "execweave.codex_hook_entry"), ("antigravity", "execweave.antigravity_hook_cli"),
    ("cursor", "execweave.cursor_hook_cli"), ("opencode", "execweave.opencode_hook_cli")])
def test_hook_uses_absolute_interpreter_not_path(provider, module, tmp_path, monkeypatch):
    executable = tmp_path / "venv with spaces" / "bin" / "python"
    monkeypatch.setattr(sys, "executable", str(executable))
    assert hook_argv(provider) == [str(executable), "-I", "-m", module, "--auto"]
    if os.name != "nt":
        assert shlex.split(hook_command(provider)) == hook_argv(provider)


def test_explicit_install_upgrades_old_bare_antigravity_hook(tmp_path):
    path = tmp_path / ".gemini/config/hooks.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"execweave-observability": {
        "enabled": True, "Stop": [{"command": "execweave-antigravity-hook --auto --event Stop"}]},
        "user-hook": {"command": "leave-me-alone"}}))
    result = bootstrap_supported_agent(["agy"], home=tmp_path, environment={})
    assert result.changed is True
    data = json.loads(path.read_text())
    assert data["execweave-observability"]["Stop"][0]["command"] == hook_command("antigravity") + " --event Stop"
    assert data["user-hook"]["command"] == "leave-me-alone"
    assert inspect_supported_agent(["agy"], home=tmp_path, environment={}).status == "configured_unverified"
    assert bootstrap_supported_agent(["agy"], home=tmp_path, environment={}).changed is False


@pytest.mark.skipif(os.name == "nt", reason="POSIX file modes; Windows ACLs require separate verification")
def test_events_created_owner_only_and_no_symlink_or_hardlink(tmp_path):
    event = RuntimeEvent.create(session_id="test", event_type="test", relation="TEST")
    path = tmp_path / "events.jsonl"
    JsonlSink(path).emit(event)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    link = tmp_path / "link"
    link.symlink_to(path)
    with pytest.raises(ValueError, match="symlink"):
        JsonlSink(link)
    original = tmp_path / "original"
    original.touch()
    hardlink = tmp_path / "hardlink"
    os.link(original, hardlink)
    with pytest.raises(ValueError, match="private regular"):
        JsonlSink(hardlink).emit(event)
    assert original.read_bytes() == b""


def test_static_browser_shows_execution_and_observation_separately(tmp_path):
    from playwright.sync_api import sync_playwright
    from execweave.viewer_projection import write_graph_html
    acc = GraphAccumulator(session_id="test", source_path=tmp_path / "events.jsonl")
    acc.apply(RuntimeEvent.create(session_id="test", event_type="session.finished",
              relation="FINISHED_SESSION", attributes={"return_code": 0,
              "short_lived_process_loss_possible": True}).to_dict())
    target = tmp_path / "viewer.html"
    write_graph_html(acc.to_dict(), target)
    with sync_playwright() as pw:
        executable = os.environ.get("EXECWEAVE_E2E_CHROMIUM")
        browser = pw.chromium.launch(**({"executable_path": executable} if executable else {}))
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.set_content(target.read_text(encoding="utf-8"))
        assert page.locator('[data-axis="execution"]').get_attribute("data-state") == "succeeded"
        assert "OBSERVATION INCOMPLETE" in page.locator('[data-axis="observation"]').inner_text()
        assert page.locator('[data-axis="task"]').get_attribute("data-state") == "unverified"
        assert errors == []
        browser.close()


def test_parent_directory_noise_never_hides_user_file_events(tmp_path):
    from watchdog.events import DirModifiedEvent, FileCreatedEvent, DirCreatedEvent
    from execweave.filesystem import SessionFileEventHandler
    sink = JsonlSink(tmp_path / "run" / "events.jsonl")
    handler = SessionFileEventHandler(session_id="test", sink=sink,
        session_entity=Entity(type="session", id="session:test"), excluded_roots=[sink.path])
    handler._emit(DirModifiedEvent(str(sink.path.parent)))
    handler._emit(DirModifiedEvent(str(tmp_path)))
    assert not sink.path.exists()
    handler._emit(FileCreatedEvent(str(tmp_path / "primes.py")))
    handler._emit(DirCreatedEvent(str(tmp_path / "work")))
    handler._emit(DirModifiedEvent(str(tmp_path / "work")))
    seen = records(sink.path)
    assert [r["event_type"] for r in seen] == [
        "filesystem.created", "filesystem.created", "filesystem.modified"]
    assert seen[0]["target"]["name"] == "primes.py"


def test_negative_example_verifies_task_without_approving_observation(tmp_path):
    from execweave.observation_demo import run_example
    report = run_example(tmp_path / "example")
    assert report["example_reproduced"] is True
    assert report["execution"]["state"] == "succeeded"
    assert report["independent_example_task_verification"]["state"] == "passed"
    assert report["observation_acceptance"] == "FAIL"
    assert report["uses_real_provider"] is False
    with pytest.raises(FileExistsError):
        run_example(tmp_path / "example")


def test_unknown_writer_does_not_invent_a_missing_snapshot(tmp_path):
    acc = GraphAccumulator(session_id="test", source_path=tmp_path / "events.jsonl")
    acc.apply(RuntimeEvent.create(session_id="test", event_type="filesystem.modified",
        relation="OBSERVED_FILE_CHANGE", target=Entity(type="file", id="file:example"),
        attributes={"causal": False, "snapshot_state": "captured"}).to_dict())
    assessment = acc.to_dict()["observation_assessment"]
    assert "unknown_file_writer" in assessment["reasons"]
    assert "file_snapshot_not_captured" not in assessment["reasons"]
    assert assessment["files_with_uncaptured_snapshots"] == 0


def test_malformed_snapshot_state_cannot_crash_event_consumption(tmp_path):
    acc = GraphAccumulator(session_id="test", source_path=tmp_path / "events.jsonl")
    acc.apply(RuntimeEvent.create(session_id="test", event_type="filesystem.modified",
        relation="OBSERVED_FILE_CHANGE", target=Entity(type="file", id="file:example"),
        attributes={"snapshot_state": ["not_captured"]}).to_dict())
    assert acc.to_dict()["observation_assessment"]["state"] == "observation_incomplete"


def test_invalid_observation_metadata_is_not_promoted_at_finalization(tmp_path):
    from execweave.finalization import record_finalization
    (tmp_path / "graph.json").write_text(json.dumps({"nodes": [], "edges": [],
        "observation_assessment": {"schema_version": "0.1", "state": []}}))
    (tmp_path / "conversations.json").write_text(json.dumps({"entries": []}))
    (tmp_path / "viewer.html").write_text("<html></html>")
    report = record_finalization(tmp_path, state="complete")
    assert report["session_status"] == "observation_incomplete"
    assert report["observation_assessment"]["reasons"] == ["graph_assessment_unreadable"]
