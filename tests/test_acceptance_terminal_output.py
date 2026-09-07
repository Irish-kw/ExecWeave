from __future__ import annotations

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from acceptance.terminal_output import TerminalTranscript  # noqa: E402


def test_transcript_tees_redacted_complete_lines_and_preserves_utf8(capsys) -> None:
    artifact = io.StringIO()
    transcript = TerminalTranscript(artifact)
    payload = "你好\nAuthorization: Bearer secret-value\nurl?t=private-token\n".encode()
    for byte in payload:
        transcript.feed(bytes([byte]))
    transcript.close()
    logged = artifact.getvalue()
    visible = capsys.readouterr().out
    assert "你好" in logged and "你好" in visible
    assert "[OLLAMA]" in visible
    for text in (logged, visible):
        assert "secret-value" not in text
        assert "private-token" not in text
        assert "[REDACTED]" in text


def test_transcript_buffers_partial_secret_and_flushes_eof(capsys) -> None:
    artifact = io.StringIO()
    transcript = TerminalTranscript(artifact)
    transcript.feed("api_ke")
    assert not capsys.readouterr().out
    assert not artifact.getvalue()
    transcript.feed("y=secret")
    transcript.close()
    assert artifact.getvalue() == "api_key=[REDACTED]\n"
    assert "secret" not in capsys.readouterr().out


def test_transcript_does_not_replay_terminal_controls(capsys) -> None:
    artifact = io.StringIO()
    transcript = TerminalTranscript(artifact)
    transcript.feed("\x1b[31mhello\x1b[0m\x1b]0;title\x07\x00\r\n")
    transcript.close()
    assert artifact.getvalue() == "hello\n"
    assert capsys.readouterr().out == "[OLLAMA] hello\n"


def test_oversized_line_streams_complete_redacted_content(capsys) -> None:
    artifact = io.StringIO()
    transcript = TerminalTranscript(artifact)
    left = "x" * 70000
    right = "y" * 70000
    transcript.feed("start-" + left + "?to")
    transcript.feed("ken=private-token&Bearer se")
    transcript.feed("cret-value " + right + "-done\nnormal\n")
    transcript.close()

    logged = artifact.getvalue()
    visible = capsys.readouterr().out
    for text in (logged, visible):
        assert "omitted" not in text
        assert "private-token" not in text
        assert "secret-value" not in text
        assert "?token=[REDACTED]&Bearer [REDACTED] " in text
        assert left in text
        assert right in text
        assert "normal" in text


def test_ansi_sequence_split_across_reads_is_removed(capsys) -> None:
    artifact = io.StringIO()
    transcript = TerminalTranscript(artifact)
    transcript.feed("before\x1b[")
    transcript.feed("31mred\x1b]0;ti")
    transcript.feed("tle\x07after\n")
    transcript.close()
    assert artifact.getvalue() == "beforeredafter\n"
    assert capsys.readouterr().out == "[OLLAMA] beforeredafter\n"
