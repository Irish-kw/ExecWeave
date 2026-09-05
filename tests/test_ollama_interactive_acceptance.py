from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ollama_interactive_acceptance as interactive  # noqa: E402
from acceptance.processes import CleanupReport, ProcessIdentity  # noqa: E402
from acceptance.reporting import Status, write_report  # noqa: E402


def test_relation_count_reads_only_matching_semantic_relations(tmp_path: Path) -> None:
    sidecar = tmp_path / "semantic.jsonl"
    sidecar.write_text(
        "\n".join(
            json.dumps({"relation": relation})
            for relation in (
                "OBSERVED_INFERENCE_REQUEST_MESSAGES",
                "OBSERVED_INFERENCE_RESPONSE",
                "OBSERVED_INFERENCE_RESPONSE",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    assert interactive._relation_count(sidecar, "OBSERVED_INFERENCE_RESPONSE") == 2
    assert interactive._relation_count(sidecar, "OBSERVED_INFERENCE_REQUEST_MESSAGES") == 1


def test_prompt_and_final_texts_keep_two_root_rounds() -> None:
    preview = {
        "messages": [
            {"sender": "user", "recipient": "/root", "text": "ROUND1"},
            {"sender": "/root", "recipient": None, "text": "ANSWER1"},
            {"sender": "user", "recipient": "/root", "text": "ROUND2"},
            {"sender": "/root", "recipient": "", "text": "ANSWER2"},
        ]
    }
    assert interactive._prompt_and_final_texts(preview) == (
        ["ROUND1", "ROUND2"],
        ["ANSWER1", "ANSWER2"],
    )


def test_unavailable_interactive_result_stays_skip_after_cleanup(tmp_path: Path) -> None:
    reason = "pywinpty/ConPTY is unavailable"
    result = interactive._skip_result(tmp_path, reason)
    interactive._record_cleanup(
        result,
        CleanupReport(terminated=(), killed=(), remaining=()),
        unavailable_reason=reason,
    )
    assert result.status == Status.SKIP_UNAVAILABLE
    assert result.checks["Cleanup"].status == Status.SKIP_UNAVAILABLE


def test_cleanup_failure_overrides_interactive_unavailable(tmp_path: Path) -> None:
    reason = "Headed Chromium unavailable"
    result = interactive._skip_result(tmp_path, reason)
    identity = ProcessIdentity(pid=424242, create_time=1.0)
    interactive._record_cleanup(
        result,
        CleanupReport(terminated=(), killed=(), remaining=(identity,)),
        unavailable_reason=reason,
    )
    assert result.status == Status.FAIL


def test_required_unavailable_interactive_provider_fails_overall(tmp_path: Path) -> None:
    result = interactive._skip_result(tmp_path, "ollama executable not found")
    summary = write_report(Path(result.artifacts), [result], {"ollama"})
    assert result.status == Status.SKIP_UNAVAILABLE
    assert summary["status"] == Status.FAIL.value


def test_main_reports_missing_prerequisites_as_skip(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.setattr(interactive.shutil, "which", lambda _name: None)
    monkeypatch.setattr(
        sys,
        "argv",
        ["ollama_interactive_acceptance.py", "--output-dir", str(tmp_path)],
    )
    assert interactive.main() == 0
    payload = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert payload["status"] == Status.SKIP_UNAVAILABLE.value


def test_main_required_missing_provider_returns_failure(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.setattr(interactive.shutil, "which", lambda _name: None)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ollama_interactive_acceptance.py",
            "--output-dir",
            str(tmp_path),
            "--require",
            "ollama",
        ],
    )
    assert interactive.main() == 1
    payload = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert payload["status"] == Status.FAIL.value


def test_terminal_backend_is_real_or_explicitly_unavailable(tmp_path: Path) -> None:
    if os.name == "nt":
        reason = interactive._terminal_backend_reason()
        if reason is not None:
            assert reason == "pywinpty/ConPTY is unavailable"
            return
        assert interactive._WinPtyTerminal.backend == "windows-conpty"
        return

    assert interactive._terminal_backend_reason() is None
    code = (
        "import os,sys\n"
        "print('TTY='+str(os.isatty(sys.stdin.fileno())), flush=True)\n"
        "line=input()\n"
        "print('ECHO='+line, flush=True)\n"
    )
    terminal = interactive._PosixTerminal(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env=dict(os.environ),
        artifact=tmp_path / "pty.txt",
    )
    try:
        terminal.write("HELLO\r")
        assert terminal.wait(5)
    finally:
        terminal.close()
    text = (tmp_path / "pty.txt").read_text(encoding="utf-8")
    assert "TTY=True" in text
    assert "ECHO=HELLO" in text
