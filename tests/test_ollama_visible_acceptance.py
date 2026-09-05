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
