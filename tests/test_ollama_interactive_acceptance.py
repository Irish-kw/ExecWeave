from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ollama_interactive_acceptance as interactive  # noqa: E402
from acceptance.processes import CleanupReport, ProcessIdentity  # noqa: E402
from acceptance.reporting import Status, write_report  # noqa: E402


def _content_ref(root: Path, name: str, value: object) -> str:
    path = root / "content" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")
    return path.relative_to(root).as_posix()


def _semantic_row(
    relation: str,
    source_id: str,
    *,
    content_path: str | None = None,
) -> dict[str, object]:
    attributes: dict[str, object] = {}
    if content_path is not None:
        attributes["content_path"] = content_path
    return {
        "relation": relation,
        "source": {"type": "inference_request", "id": source_id},
        "attributes": attributes,
    }


def _write_sidecar(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )


def test_marker_exchange_ignores_unrelated_responses(tmp_path: Path) -> None:
    sidecar = tmp_path / "semantic.jsonl"
    marker = "EW-INTERACTIVE-ABCDEF1234-ROUND1"
    target = "inference-request:ollama:target-round-1"
    request_ref = _content_ref(
        tmp_path,
        "round1.json",
        [{"role": "user", "content": marker + " What is 2+3?"}],
    )
    rows = [
        _semantic_row("OBSERVED_INFERENCE_RESPONSE", "inference-request:ollama:probe-1"),
        _semantic_row("OBSERVED_INFERENCE_RESPONSE", "inference-request:ollama:probe-2"),
        _semantic_row(
            "OBSERVED_INFERENCE_REQUEST_MESSAGES",
            target,
            content_path=request_ref,
        ),
    ]
    _write_sidecar(sidecar, rows)

    # The old count gate would already see two responses and could falsely pass both
    # rounds. The marker-bound gate must stay incomplete until this request's response.
    assert interactive._marker_exchange_state(sidecar, tmp_path, marker) == (target, False)

    rows.append(_semantic_row("OBSERVED_INFERENCE_RESPONSE", target))
    _write_sidecar(sidecar, rows)
    assert interactive._marker_exchange_state(sidecar, tmp_path, marker) == (target, True)


def test_two_markers_require_two_distinct_matching_sources(tmp_path: Path) -> None:
    sidecar = tmp_path / "semantic.jsonl"
    marker_one = "EW-INTERACTIVE-ABCDEF1234-ROUND1"
    marker_two = "EW-INTERACTIVE-ABCDEF1234-ROUND2"
    source_one = "inference-request:ollama:round-1"
    source_two = "inference-request:ollama:round-2"
    rows = [
        _semantic_row(
            "OBSERVED_INFERENCE_REQUEST_MESSAGES",
            source_one,
            content_path=_content_ref(tmp_path, "round1.json", [{"content": marker_one}]),
        ),
        _semantic_row(
            "OBSERVED_INFERENCE_REQUEST_MESSAGES",
            source_two,
            content_path=_content_ref(tmp_path, "round2.json", [{"content": marker_two}]),
        ),
        _semantic_row("OBSERVED_INFERENCE_RESPONSE", source_one),
    ]
    _write_sidecar(sidecar, rows)

    assert interactive._marker_exchange_state(sidecar, tmp_path, marker_one) == (
        source_one,
        True,
    )
    assert interactive._marker_exchange_state(sidecar, tmp_path, marker_two) == (
        source_two,
        False,
    )


def test_marker_request_identity_must_be_unambiguous(tmp_path: Path) -> None:
    sidecar = tmp_path / "semantic.jsonl"
    marker = "EW-INTERACTIVE-ABCDEF1234-ROUND1"
    rows = [
        _semantic_row(
            "OBSERVED_INFERENCE_REQUEST_MESSAGES",
            "inference-request:ollama:a",
            content_path=_content_ref(tmp_path, "a.json", [{"content": marker}]),
        ),
        _semantic_row(
            "OBSERVED_INFERENCE_REQUEST_MESSAGES",
            "inference-request:ollama:b",
            content_path=_content_ref(tmp_path, "b.json", [{"content": marker}]),
        ),
    ]
    _write_sidecar(sidecar, rows)

    with pytest.raises(AssertionError, match="multiple inference-request identities"):
        interactive._marker_exchange_state(sidecar, tmp_path, marker)


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


@pytest.mark.viewer_e2e
def test_required_e2e_terminal_backend_round_trip(tmp_path: Path, capsys) -> None:
    assert interactive._terminal_backend_reason() is None
    code = (
        "import os,sys\n"
        "print('TTY='+str(os.isatty(sys.stdin.fileno())), flush=True)\n"
        "print('READY', flush=True)\n"
        "line=input()\n"
        "print('ECHO='+line, flush=True)\n"
    )
    artifact = tmp_path / "terminal-e2e.txt"
    terminal = interactive._spawn_terminal(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env=dict(os.environ),
        artifact=artifact,
    )
    try:
        expected_backend = "windows-conpty" if os.name == "nt" else "posix-pty"
        assert terminal.backend == expected_backend
        terminal.write("HELLO\r")
        assert terminal.wait(10)
    finally:
        terminal.close()
    text = artifact.read_text(encoding="utf-8")
    assert "READY" in text
    assert "ECHO=HELLO" in text
    assert "TTY=True" in text
    displayed = capsys.readouterr().out
    assert "[OLLAMA]" in displayed
    assert "ECHO=HELLO" in displayed
