from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from acceptance.contracts import ConversationSnapshot, same_conversation, verify_conversation  # noqa: E402
from acceptance.reporting import FEATURES, Result, Status, overall_status, redact, write_report  # noqa: E402


def test_prompt_containing_done_never_passes_assistant_completion():
    snapshot = ConversationSnapshot(
        "/root", "EW-TEST-ABC. Reply exactly EW-DONE-ABC", "unrelated email"
    )
    checked = verify_conversation(snapshot, marker="EW-TEST-ABC", done="EW-DONE-ABC")
    assert checked["Prompt"] and checked["/root"]
    assert not checked["Final"]


def test_foreign_marker_and_wrong_owner_fail_even_when_answer_matches():
    snapshot = ConversationSnapshot("/root/child", "EW-TEST-ABC FOREIGN", "EW-DONE-ABC")
    checked = verify_conversation(
        snapshot, marker="EW-TEST-ABC", done="EW-DONE-ABC", foreign_markers=("FOREIGN",)
    )
    assert checked["Final"] and not checked["/root"] and not checked["Isolation"]
    assert not same_conversation(
        snapshot, ConversationSnapshot("/root", snapshot.prompt, snapshot.final)
    )


def test_unavailable_provider_is_not_pass_and_require_fails():
    result = Result("codex", "live", "EW-X", "windows")
    for feature in FEATURES:
        result.skip(feature, "Command unavailable")
    assert result.status == Status.SKIP_UNAVAILABLE
    assert overall_status([result], {"codex"}) == Status.FAIL
    assert overall_status([result], set()) == Status.SKIP_UNAVAILABLE


def test_unexecuted_assertions_fail_and_failure_cannot_be_overwritten(tmp_path):
    result = Result("python", "offline", "EW-X", "windows")
    result.check("Launch", False, "Launch failed")
    result.check("Launch", True, "retry")
    summary = write_report(tmp_path, [result], set())
    assert summary["status"] == "FAIL"
    assert all(check.status == Status.FAIL for check in result.checks.values())
    assert json.loads((tmp_path / "summary.json").read_text()) == summary


def test_report_escapes_untrusted_text_and_redacts_loopback_tokens(tmp_path):
    result = Result("<script>alert(1)</script>", "offline", "EW-X", "windows")
    for feature in FEATURES:
        result.check(feature, True, "http://localhost/?t=secret <img src=x onerror=alert(1)>")
    write_report(tmp_path, [result], set())
    document = (tmp_path / "report.html").read_text(encoding="utf-8")
    assert "<script>" not in document and "<img " not in document
    assert "secret" not in document
    assert "secret" not in (tmp_path / "summary.json").read_text()
    assert redact("Authorization: Bearer secret") == "Authorization: [REDACTED] [REDACTED]"
