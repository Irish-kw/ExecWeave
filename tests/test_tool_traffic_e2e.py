"""Tool calls have a visible surface without being drawn into the graph.

``tool_call`` and ``observed_content`` are in ``hiddenTypes`` because a run makes one
tool_call per invocation and drawing them buries everything else. That is a reason to
keep them out of the graph, not a reason to keep them from the reader: until now the
tool a run invoked, the command it declared and the input recorded for it had no
surface anywhere.

The shape here mirrors a real Claude run: agent -REQUESTED_TOOL_CALL-> tool_call,
which -DECLARED_COMMAND-> command, -HAS_TOOL_INPUT-> observed_content, and
-USES_TOOL-> tool.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from test_graph_node_sizing_e2e import _browser, _launch, _render

DIGEST = "cf4186dcf3dae08b9057e6263cefba644ffd5c4ce334505a3bcc8f82faf81608"


def _run_graph() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "nodes": [
            {"id": "agent:Claude Code", "type": "agent", "name": "/root",
             "attributes": {"agent_role": "root", "agent_path": "/root"}},
            {"id": "agent:quiet", "type": "agent", "name": "quiet",
             "attributes": {"agent_role": "child", "agent_path": "/root/quiet"}},
            {"id": "tool:claude:Bash", "type": "tool", "name": "Bash",
             "attributes": {"provider": "claude", "native_name": "Bash"}},
            {"id": "tool-call:claude:s:u1", "type": "tool_call", "name": "Bash",
             "first_seen": "2026-08-31T07:31:00Z",
             "attributes": {"provider": "claude", "tool_name": "Bash",
                            "tool_use_id": "u1", "input_keys": ["command"]}},
            {"id": "command:sha256:f43a", "type": "command", "name": "sleep 3",
             "attributes": {"command": "sleep 3", "truncated": False}},
            {"id": f"observed-content:claude.tool_input:sha256:{DIGEST}",
             "type": "observed_content", "name": "claude.tool_input",
             "attributes": {"content_kind": "claude.tool_input", "sha256": DIGEST,
                            "size_bytes": 21, "complete_from_source": True,
                            "path": f"content/sha256/{DIGEST}.json"}},
        ],
        "edges": [
            {"id": "e1", "source": "agent:Claude Code", "target": "tool-call:claude:s:u1",
             "relation": "REQUESTED_TOOL_CALL", "attributes": {}},
            {"id": "e2", "source": "tool-call:claude:s:u1", "target": "command:sha256:f43a",
             "relation": "DECLARED_COMMAND", "attributes": {}},
            {"id": "e3", "source": "tool-call:claude:s:u1",
             "target": f"observed-content:claude.tool_input:sha256:{DIGEST}",
             "relation": "HAS_TOOL_INPUT", "attributes": {}},
            {"id": "e4", "source": "tool-call:claude:s:u1", "target": "tool:claude:Bash",
             "relation": "USES_TOOL", "attributes": {}},
            {"id": "e5", "source": "agent:Claude Code", "target": "agent:quiet",
             "relation": "SPAWNED_AGENT", "attributes": {}},
        ],
    }


def _cards_after_clicking(tmp_path: Path, node_id: str) -> dict[str, str]:
    viewer = _render(tmp_path, _run_graph())
    manager, executable = _browser()
    with manager as playwright:
        browser = _launch(playwright, executable)
        try:
            page = browser.new_page(viewport={"width": 1600, "height": 1000})
            page.goto(viewer.as_uri())
            page.wait_for_selector(".node", timeout=15000)
            page.eval_on_selector(
                f'.node[data-id="{node_id}"]',
                "el => el.dispatchEvent(new MouseEvent('click', {bubbles: true}))",
            )
            page.wait_for_timeout(250)
            pairs = page.evaluate(
                """() => [...document.querySelectorAll('.execweave-agent-card')].map(c => [
                    c.querySelector('.execweave-agent-label')?.textContent,
                    c.querySelector('.execweave-agent-body')?.textContent])"""
            )
            return {label: body for label, body in pairs if label}
        finally:
            browser.close()


def test_the_agent_that_asked_shows_what_it_invoked(tmp_path: Path) -> None:
    cards = _cards_after_clicking(tmp_path, "agent:Claude Code")
    assert "Tools" in cards, f"the agent's tool traffic has no surface: {sorted(cards)}"
    tools = cards["Tools"]
    assert "Bash" in tools, tools
    assert "sleep 3" in tools, f"the declared command is not shown: {tools!r}"


def test_a_recorded_input_is_described_not_claimed_as_read(tmp_path: Path) -> None:
    """The page cannot read the content store, so it must not imply that it has."""
    tools = _cards_after_clicking(tmp_path, "agent:Claude Code")["Tools"]
    assert "21 bytes" in tools and "complete" in tools, tools
    assert DIGEST[:12] in tools, f"the digest identifying the record is missing: {tools!r}"


def test_an_agent_that_invoked_nothing_shows_no_tool_card(tmp_path: Path) -> None:
    cards = _cards_after_clicking(tmp_path, "agent:quiet")
    assert "Tools" not in cards, (
        f"an agent that requested no tool call must not grow an empty card: {sorted(cards)}"
    )


def test_the_tool_reports_its_traffic(tmp_path: Path) -> None:
    cards = _cards_after_clicking(tmp_path, "tool:claude:Bash")
    assert cards.get("Calls") == "1", cards
    # The caller is named the way the graph names it, by agent path.
    assert cards.get("Requested by") == "/root", cards


def test_tool_calls_are_still_kept_out_of_the_graph(tmp_path: Path) -> None:
    """Surfacing the traffic must not undo the reason it was hidden.

    One tool_call per invocation drawn as a node is what buried the graph; the fix is
    a panel, not a flood.
    """
    viewer = _render(tmp_path, _run_graph())
    manager, executable = _browser()
    with manager as playwright:
        browser = _launch(playwright, executable)
        try:
            page = browser.new_page(viewport={"width": 1600, "height": 1000})
            page.goto(viewer.as_uri())
            page.wait_for_selector(".node", timeout=15000)
            drawn = page.eval_on_selector_all(".node", "n => n.map(e => e.dataset.id)")
        finally:
            browser.close()
    assert not [node for node in drawn if str(node).startswith("tool-call:")], drawn
    assert not [node for node in drawn if str(node).startswith("observed-content:")], drawn
    assert "tool:claude:Bash" in drawn, "the tool itself must still be on the graph"
