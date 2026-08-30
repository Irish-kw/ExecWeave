from __future__ import annotations

from pathlib import Path

from execweave import live as live_module
from execweave import live_core
from execweave.codex_conversation import _agent_message_header, _agent_message_visible_text
from execweave.dashboard_shell import render_static_dashboard_html
from execweave.theme import inject_viewer_theme


def _empty_graph() -> dict[str, object]:
    return {
        "graph_schema_version": "0.2",
        "session_id": "review-regression",
        "event_count": 0,
        "node_count": 0,
        "edge_count": 0,
        "nodes": [],
        "edges": [],
    }


def test_plaintext_agent_message_may_quote_routing_like_lines() -> None:
    text = "The observed log contained:\nSender: worker-17\nTask name: backup\nMessage type: notice"
    header = _agent_message_header(text)

    assert header == {}
    assert _agent_message_visible_text(text, header) == text


def test_codex_routing_envelope_requires_a_payload_line() -> None:
    text = (
        "Message type: Agent Result\n"
        "Sender: /root/alpha\n"
        "Task name: /root\n"
        "Payload:\n"
        "actual answer"
    )
    header = _agent_message_header(text)

    assert header["message_type"] == "Agent Result"
    assert header["sender"] == "/root/alpha"
    assert header["task_name"] == "/root"
    assert _agent_message_visible_text(text, header) == "actual answer"


def test_live_html_contains_only_the_unified_agent_inspector() -> None:
    html = live_module._LIVE_HTML

    assert "window.__execweaveAgentPanel" in html
    assert 'id="conversation-records"' not in html
    assert 'id="execweave-conversation-panel"' not in html
    assert "execweave-conversation-tree" not in html
    assert "Open raw conversation evidence" not in html
    assert "Show all agents" not in html


def test_unified_snapshot_owns_theme_without_fake_sentinel() -> None:
    html = render_static_dashboard_html(_empty_graph(), conversation_entries=[])

    assert 'id="theme-toggle"' in html
    assert 'id="execweave-theme-toggle"' not in html
    assert "unified-dashboard-theme-owner" not in html
    assert inject_viewer_theme(html) == html


def test_final_rendering_does_not_hold_the_live_state_lock(
    monkeypatch, tmp_path: Path
) -> None:
    event_path = tmp_path / "events.jsonl"
    event_path.write_text("", encoding="utf-8")
    state = live_core._LiveState("review", event_path)
    observed = {"rendered": False}

    def fake_render(_graph: dict[str, object]) -> str:
        acquired = state._lock.acquire(blocking=False)
        assert acquired, "final rendering ran while the live polling lock was held"
        state._lock.release()
        observed["rendered"] = True
        return "<html><body>final</body></html>"

    monkeypatch.setattr(live_core, "render_graph_html", fake_render)
    state.finish(_empty_graph())

    assert observed["rendered"]
    assert state.final_html() == "<html><body>final</body></html>"


def test_prebuilt_viewer_snapshot_avoids_a_second_final_render(
    monkeypatch, tmp_path: Path
) -> None:
    event_path = tmp_path / "events.jsonl"
    event_path.write_text("", encoding="utf-8")
    state = live_core._LiveState("review", event_path)

    def fail_render(_graph: dict[str, object]) -> str:
        raise AssertionError("run_live must reuse the already-written viewer snapshot")

    monkeypatch.setattr(live_core, "render_graph_html", fail_render)
    state.finish(_empty_graph(), final_html="<html><body>snapshot</body></html>")

    assert state.final_html() == "<html><body>snapshot</body></html>"
