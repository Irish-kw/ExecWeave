from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import python_native_acceptance as native  # noqa: E402
from acceptance.processes import CleanupReport, ProcessIdentity  # noqa: E402
from acceptance.reporting import Status, write_report  # noqa: E402


def test_semantic_relations_only_reports_semantic_vocabulary(tmp_path: Path) -> None:
    sidecar = tmp_path / "semantic.jsonl"
    sidecar.write_text(
        "\n".join(
            json.dumps({"relation": relation})
            for relation in (
                "CONNECTED_TO",
                "OBSERVED_INFERENCE_RESPONSE",
                "DECLARED_AGENT_SPAWNED",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    assert native._semantic_relations(sidecar) == {
        "OBSERVED_INFERENCE_RESPONSE",
        "DECLARED_AGENT_SPAWNED",
    }


def test_nodes_of_type_is_exact() -> None:
    graph = {"nodes": [{"type": "process", "id": "p1"}, {"type": "file", "id": "f1"}]}
    assert native._nodes_of_type(graph, "process") == [{"type": "process", "id": "p1"}]
    assert native._nodes_of_type(graph, "network_endpoint") == []


def test_child_program_contains_real_file_process_and_loopback_actions() -> None:
    program = native._child_program("MARKER-123")
    assert "acceptance.txt" in program
    assert "subprocess.Popen" in program
    assert "127.0.0.1" in program
    assert "MARKER-123" in program


def test_unavailable_native_result_stays_skip_after_cleanup(tmp_path: Path) -> None:
    reason = "Headed Chromium unavailable"
    result = native._skip_result(tmp_path, reason)
    native._record_cleanup(
        result,
        CleanupReport(terminated=(), killed=(), remaining=()),
        unavailable_reason=reason,
    )
    assert result.status == Status.SKIP_UNAVAILABLE
    assert result.checks["Cleanup"].status == Status.SKIP_UNAVAILABLE


def test_cleanup_failure_overrides_native_unavailable(tmp_path: Path) -> None:
    reason = "Headed Chromium unavailable"
    result = native._skip_result(tmp_path, reason)
    identity = ProcessIdentity(pid=424242, create_time=1.0)
    native._record_cleanup(
        result,
        CleanupReport(terminated=(), killed=(), remaining=(identity,)),
        unavailable_reason=reason,
    )
    assert result.status == Status.FAIL


def test_required_unavailable_native_python_fails_overall(tmp_path: Path) -> None:
    result = native._skip_result(tmp_path, "execweave executable not found")
    summary = write_report(Path(result.artifacts), [result], {"python"})
    assert result.status == Status.SKIP_UNAVAILABLE
    assert summary["status"] == Status.FAIL.value


def test_main_missing_execweave_reports_skip(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(native.shutil, "which", lambda _name: None)
    monkeypatch.setattr(
        sys,
        "argv",
        ["python_native_acceptance.py", "--output-dir", str(tmp_path)],
    )
    assert native.main() == 0
    payload = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert payload["status"] == Status.SKIP_UNAVAILABLE.value


def test_main_required_missing_execweave_returns_failure(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.setattr(native.shutil, "which", lambda _name: None)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "python_native_acceptance.py",
            "--output-dir",
            str(tmp_path),
            "--require",
            "python",
        ],
    )
    assert native.main() == 1
    payload = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert payload["status"] == Status.FAIL.value
