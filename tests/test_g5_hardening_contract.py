from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ollama_interactive_acceptance as interactive  # noqa: E402
from acceptance.reporting import Status, write_report  # noqa: E402


def test_public_g5_entry_uses_hardened_formal_journey() -> None:
    assert interactive._run_interactive.__module__ == "acceptance.g5_runner"
    assert interactive._impl._run_interactive is interactive._run_interactive


def test_keyboard_interrupt_becomes_persistable_failure(
    monkeypatch, tmp_path: Path
) -> None:
    def interrupted() -> str | None:
        raise KeyboardInterrupt()

    monkeypatch.setattr(interactive._impl, "_terminal_backend_reason", interrupted)

    result = interactive._run_interactive(
        output_root=tmp_path,
        model="local-model",
        execweave_bin="execweave",
        ollama_bin="ollama",
        timeout=10,
    )
    assert result.status == Status.FAIL
    assert result.checks["Launch"].status == Status.FAIL
    assert "KeyboardInterrupt" in result.checks["Launch"].reason
    assert result.checks["Cleanup"].status == Status.PASS

    summary = write_report(Path(result.artifacts), [result], {"ollama"})
    assert summary["status"] == Status.FAIL.value
    assert (Path(result.artifacts) / "summary.json").is_file()
    assert (Path(result.artifacts) / "report.html").is_file()
