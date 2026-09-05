from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ollama_visible_acceptance as visible  # noqa: E402
from acceptance.processes import CleanupReport, ProcessIdentity  # noqa: E402
from acceptance.reporting import Status, write_report  # noqa: E402


def test_clean_output_removes_ansi_and_carriage_returns() -> None:
    assert visible._clean_output("\x1b[31mhello\x1b[0m\r\nworld  \r\n") == "hello\nworld"


def test_local_model_present_requires_exact_model_identity() -> None:
    tags = {
        "models": [
            {"name": "deepseek-r1:1.5b", "model": "deepseek-r1:1.5b"},
            {"name": "qwen3:latest"},
        ]
    }
    assert visible._local_model_present(tags, "deepseek-r1:1.5b")
    assert visible._local_model_present(tags, "qwen3")
    assert not visible._local_model_present(tags, "deepseek-r1")
    assert not visible._local_model_present(tags, "qwen")


def test_network_evidence_uses_native_network_endpoint_type() -> None:
    assert visible._has_network_evidence({"nodes": [{"type": "network_endpoint"}]})
    assert not visible._has_network_evidence({"nodes": [{"type": "endpoint"}]})
    assert not visible._has_network_evidence({"nodes": []})


def test_final_must_be_grounded_in_independent_client_output() -> None:
    assert visible._final_matches_client_output("The answer is 4.", "Thinking...\nThe answer is 4.\n")
    assert not visible._final_matches_client_output("placeholder", "The answer is 4.")
    assert not visible._final_matches_client_output("", "The answer is 4.")


def test_windows_finalize_stops_only_owned_ollama_serve_descendant(monkeypatch) -> None:
    class FakeChild:
        def __init__(self, command: list[str]) -> None:
            self.command = command
            self.terminated = False

        def cmdline(self) -> list[str]:
            return self.command

        def terminate(self) -> None:
            self.terminated = True

    owned_server = FakeChild([r"C:\\Program Files\\Ollama\\ollama.exe", "serve"])
    unrelated_child = FakeChild([r"C:\\Windows\\System32\\python.exe", "worker.py"])

    class FakeParent:
        def children(self, recursive: bool = False):
            assert recursive is True
            return [unrelated_child, owned_server]

    class FakePopen:
        pid = 4242

        def poll(self):
            return None

    monkeypatch.setattr(visible.os, "name", "nt")
    monkeypatch.setattr(visible.psutil, "Process", lambda _pid: FakeParent())

    assert visible._interrupt(FakePopen())
    assert owned_server.terminated
    assert not unrelated_child.terminated


def test_windows_finalize_fails_closed_when_owned_server_is_ambiguous(monkeypatch) -> None:
    class FakeChild:
        def __init__(self) -> None:
            self.terminated = False

        def cmdline(self) -> list[str]:
            return ["ollama.exe", "serve"]

        def terminate(self) -> None:
            self.terminated = True

    children = [FakeChild(), FakeChild()]

    class FakeParent:
        def children(self, recursive: bool = False):
            assert recursive is True
            return children

    class FakePopen:
        pid = 4343

        def poll(self):
            return None

    monkeypatch.setattr(visible.os, "name", "nt")
    monkeypatch.setattr(visible.psutil, "Process", lambda _pid: FakeParent())

    assert not visible._interrupt(FakePopen())
    assert not any(child.terminated for child in children)


def test_unavailable_result_stays_skip_after_successful_cleanup(tmp_path: Path) -> None:
    reason = "Local Ollama model is unavailable: fixture"
    result = visible._skip_result(tmp_path, reason)
    assert result.status == Status.SKIP_UNAVAILABLE

    visible._record_cleanup(
        result,
        CleanupReport(terminated=(), killed=(), remaining=()),
        unavailable_reason=reason,
    )

    assert result.status == Status.SKIP_UNAVAILABLE
    assert result.checks["Cleanup"].status == Status.SKIP_UNAVAILABLE
    summary = write_report(Path(result.artifacts), [result], set())
    assert summary["status"] == Status.SKIP_UNAVAILABLE.value


def test_required_unavailable_provider_fails_overall(tmp_path: Path) -> None:
    result = visible._skip_result(tmp_path, "ollama executable not found")
    summary = write_report(Path(result.artifacts), [result], {"ollama"})
    assert result.status == Status.SKIP_UNAVAILABLE
    assert summary["status"] == Status.FAIL.value


def test_cleanup_failure_overrides_unavailable_skip(tmp_path: Path) -> None:
    reason = "Headed Chromium unavailable"
    result = visible._skip_result(tmp_path, reason)
    remaining = ProcessIdentity(pid=424242, create_time=1.0)

    visible._record_cleanup(
        result,
        CleanupReport(terminated=(), killed=(), remaining=(remaining,)),
        unavailable_reason=reason,
    )

    assert result.status == Status.FAIL
    assert result.checks["Cleanup"].status == Status.FAIL


def test_live_url_pattern_requires_loopback_tokenized_url() -> None:
    line = "ExecWeave live: http://127.0.0.1:43123/?t=secret-token"
    match = visible._LIVE_URL_RE.search(line)
    assert match is not None
    assert match.group(1) == "http://127.0.0.1:43123/?t=secret-token"
    assert visible._LIVE_URL_RE.search("ExecWeave live: http://0.0.0.0:43123/?t=x") is None


def test_main_reports_missing_prerequisites_as_skip(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.setattr(visible.shutil, "which", lambda _name: None)
    monkeypatch.setattr(
        sys,
        "argv",
        ["ollama_visible_acceptance.py", "--output-dir", str(tmp_path)],
    )

    assert visible.main() == 0
    payload = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert payload["status"] == Status.SKIP_UNAVAILABLE.value


def test_main_required_missing_provider_returns_failure(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.setattr(visible.shutil, "which", lambda _name: None)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ollama_visible_acceptance.py",
            "--output-dir",
            str(tmp_path),
            "--require",
            "ollama",
        ],
    )

    assert visible.main() == 1
    payload = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert payload["status"] == Status.FAIL.value
