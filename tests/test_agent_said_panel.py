"""Compact agent-inspector source contracts.

The v0.7.9 dashboard no longer renders a generic who-said-what transcript. Root
shows Prompt + Final response; a child shows Task + Thinking + Response. These
checks keep the original regression node IDs while pinning the privacy and
attribution rules used by that compact inspector.
"""

from __future__ import annotations

from pathlib import Path

from execweave.viewer_agent_panel import _AGENT_PANEL_JS

SRC = Path(__file__).resolve().parents[1] / "src" / "execweave"
VIEWER = SRC / "viewer.py"
INSPECTOR = SRC / "viewer_content_inspector.py"


# ── the seam other injectors depend on must survive ──────────────────────────


def test_the_detail_seam_is_untouched() -> None:
    """inject_standalone_content_inspector splices on this exact text."""
    assert "  details.append(p);\n}" in VIEWER.read_text(encoding="utf-8"), (
        "changing the seam silently drops the content, agent, message and "
        "delegation inspectors from every standalone viewer"
    )


def test_the_raw_dump_is_folded_without_moving_the_seam() -> None:
    source = VIEWER.read_text(encoding="utf-8")
    assert "let p=document.createElement('pre')" in source
    assert "fold.append(label,p);p=fold;" in source


def test_the_trace_panel_yields_to_the_conversation() -> None:
    source = INSPECTOR.read_text(encoding="utf-8")
    assert "panel.open=!document.querySelector('.execweave-said')" in source


def test_the_injected_preamble_is_folded_not_dropped() -> None:
    source = VIEWER.read_text(encoding="utf-8")
    assert "execweaveInjectedContext" in source
    assert "<recommended_plugins>" in source and "<environment_context>" in source
    assert "injected task context" in source


# ── v0.7.9 compact inspector contracts ───────────────────────────────────────


def test_turns_read_as_who_said_what(tmp_path: Path) -> None:
    del tmp_path
    source = _AGENT_PANEL_JS
    assert "card('Task',fields.task)" in source
    assert "card('Thinking',fields.thinking)" in source
    assert "card('Response',fields.response)" in source
    assert "const own=(message,path)=>!message?.sender||String(message.sender)===path;" in source
    assert "String(message?.recipient||'')===path" in source
    assert "recordFor(node)" in source


def test_a_run_of_unexposed_turns_collapses_but_still_names_its_recipients(
    tmp_path: Path,
) -> None:
    del tmp_path
    source = _AGENT_PANEL_JS
    assert "const ENCRYPTED_NOTICE='Observed — plaintext not exposed by provider.';" in source
    assert "const isEncrypted=" in source
    assert "const isObserved=" in source
    assert "displayText(message)" in source
    assert "card('Task',fields.task)" in source
    assert "isPlain(message)" not in source


def test_a_lone_unexposed_turn_is_not_reworded_as_a_run(tmp_path: Path) -> None:
    del tmp_path
    source = _AGENT_PANEL_JS
    assert "content_state||''" in source
    assert "provider_encrypted" in source
    assert "Observed — plaintext not exposed by provider." in source
    assert "turns the provider did not expose" not in source
    assert "Not observed." in source


def test_unexposed_turns_from_different_senders_do_not_merge(tmp_path: Path) -> None:
    del tmp_path
    source = _AGENT_PANEL_JS
    assert "const parent=path.includes('/')" in source
    assert "sender===parent" in source
    assert "sender===path" not in source
    assert "own(message,path)" in source
