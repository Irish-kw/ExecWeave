"""Selecting an agent answers one question first: what did this agent say?

Clicking an agent opened with a raw node dump, then capability prose, then a
communications list and an activity list that repeat the same seventeen content
chips per entry. The turns came last, and the first of them was a
four-thousand-character plugin preamble the provider prepends to every subagent,
so three different agents opened with an identical wall of text.

The panel now leads with the agent's own turns. Nothing is removed: the node
JSON and the trace panel are still there, folded, and the injected preamble is
still readable behind a disclosure.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

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
    # The pre is reparented into a disclosure, so the seam still appends `p`.
    assert "let p=document.createElement('pre')" in source
    assert "fold.append(label,p);p=fold;" in source


def test_the_trace_panel_yields_to_the_conversation() -> None:
    source = INSPECTOR.read_text(encoding="utf-8")
    assert "panel.open=!document.querySelector('.execweave-said')" in source, (
        "the trace panel must not open over the turns the reader came for"
    )


def test_the_injected_preamble_is_folded_not_dropped() -> None:
    source = VIEWER.read_text(encoding="utf-8")
    assert "execweaveInjectedContext" in source
    assert "<recommended_plugins>" in source and "<environment_context>" in source
    assert "injected task context" in source, "the preamble stays readable behind a summary"


# ── execute the shipped panel ────────────────────────────────────────────────


def _graph() -> dict[str, Any]:
    return {
        "nodes": [
            {
                "id": "agent:OpenAI Codex",
                "type": "agent",
                "name": "OpenAI Codex",
                "attributes": {"provider": "codex", "agent_role": "root", "root_agent_path": "/root"},
            },
            {
                "id": "agent:codex:S:subagent:one",
                "type": "agent",
                "name": "default",
                "attributes": {
                    "provider": "codex",
                    "agent_role": "subagent",
                    "child_agent_path": "/root/alpha",
                    "parent_agent_path": "/root",
                },
            },
        ],
        "edges": [],
    }


_PREAMBLE = "<recommended_plugins>\n" + ("- Some Plugin (some@remote)\n" * 200)


def _entries() -> list[dict[str, Any]]:
    messages = [
        {"sender": "/root", "recipient": "/root/alpha", "kind": "task", "text": _PREAMBLE},
        {
            "sender": "/root",
            "recipient": "/root/alpha",
            "kind": "task",
            "text": "",
            "content_state": "provider_encrypted",
        },
        {"sender": "/root/alpha", "recipient": "/root", "kind": "message", "text": "ALPHA ANSWER"},
    ]
    return [
        {
            "provider": "codex",
            "source_id": "agent:codex:S:subagent:one",
            "source_name": "/root/alpha",
            "conversation_preview": {
                "agent_path": "/root/alpha",
                "thread_id": "T1",
                "is_root": False,
                "messages": messages,
            },
        }
    ]


def _panel_script(tmp_path: Path, path: str = "/root/alpha"):
    """Render the shipped showDetails for an agent and report what it drew."""
    from execweave.viewer_projection import write_graph_html

    html_path = tmp_path / "viewer.html"
    write_graph_html(_graph(), html_path)
    html = html_path.read_text(encoding="utf-8")

    start = html.index("function execweaveInjectedContext")
    end = html.index("function showDetails(kind,value){")
    helpers = html[start:end]

    script = tmp_path / "panel.js"
    script.write_text(
        """
const rows=[];
const el=(tag)=>({tagName:tag.toUpperCase(),className:'',children:[],textContent:'',
  classList:{add(c){this.self.className=(this.self.className+' '+c).trim()}},
  append(...kids){for(const k of kids)this.children.push(k)},
  appendChild(k){this.children.push(k);return k}});
const document={createElement(tag){const node=el(tag);node.classList.self=node;
  Object.defineProperty(node,'classList',{value:{add:c=>{node.className=(node.className+' '+c).trim()}}});
  return node}};
"""
        + helpers
        + """
const record={path:process.env.EW_PATH||'/root/alpha'};
const messages=JSON.parse(process.argv[2]);
const box=document.createElement('div');
for(const group of execweaveGroupSaidTurns(messages))
  execweaveAppendSaidGroup(box,group,record.path);
const flat=box.children.map(row=>{
  const who=row.children[0],body=row.children[1];
  const inner=body.children.length?body.children[0]:null;
  const summary=inner&&inner.children.length?inner.children[0]:null;
  return {who:who.textContent,
          body:summary?summary.textContent:body.textContent,
          folded:Boolean(summary),
          quiet:body.className.includes('quiet')};
});
console.log(JSON.stringify(flat));
""",
        encoding="utf-8",
    )
    return script


def _render(messages: list[dict[str, Any]], path: str, tmp_path: Path) -> list[dict[str, Any]]:
    script = _panel_script(tmp_path, path)
    env = {**os.environ, "EW_PATH": path}
    result = subprocess.run(
        [shutil.which("node"), str(script), json.dumps(messages)],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


@pytest.mark.skipif(shutil.which("node") is None, reason="node is unavailable")
def test_turns_read_as_who_said_what(tmp_path: Path) -> None:
    turns = _render(_entries()[0]["conversation_preview"]["messages"], "/root/alpha", tmp_path)
    # An inbound turn names its sender; only an outbound turn carries the arrow.
    assert [turn["who"] for turn in turns] == ["/root", "/root", "this agent →"]

    preamble, encrypted, answer = turns
    assert preamble["folded"], "the injected preamble must not lead the panel in full"
    assert "injected task context" in preamble["body"]
    assert str(len(_PREAMBLE)) in preamble["body"], "say how much was folded away"

    assert encrypted["quiet"], "an unexposed turn is one quiet line, not a paragraph"
    assert "provider-encrypted" in encrypted["body"]

    assert answer["body"] == "ALPHA ANSWER"
    assert not answer["folded"] and not answer["quiet"]


@pytest.mark.skipif(shutil.which("node") is None, reason="node is unavailable")
def test_a_run_of_unexposed_turns_collapses_but_still_names_its_recipients(
    tmp_path: Path,
) -> None:
    """Root dispatched three children behind encryption; one line, three names."""
    messages = [
        {"sender": "/root", "recipient": "/root/a", "text": "", "content_state": "provider_encrypted"},
        {"sender": "/root", "recipient": "/root/b", "text": "", "content_state": "provider_encrypted"},
        {"sender": "/root", "recipient": "/root/c", "text": "", "content_state": "provider_encrypted"},
        {"sender": "/root", "recipient": None, "text": "three are working on it"},
    ]
    turns = _render(messages, "/root", tmp_path)
    assert len(turns) == 2, [turn["body"] for turn in turns]

    collapsed = turns[0]
    assert collapsed["quiet"]
    assert collapsed["body"].startswith("3 turns the provider did not expose")
    for child in ("/root/a", "/root/b", "/root/c"):
        assert child in collapsed["body"], "a fold must not hide who was dispatched"
    assert turns[1]["body"] == "three are working on it"


@pytest.mark.skipif(shutil.which("node") is None, reason="node is unavailable")
def test_a_lone_unexposed_turn_is_not_reworded_as_a_run(tmp_path: Path) -> None:
    turns = _render(
        [{"sender": "/root", "recipient": "/root/a", "text": "", "content_state": "provider_encrypted"}],
        "/root",
        tmp_path,
    )
    assert len(turns) == 1
    assert turns[0]["body"].startswith("provider-encrypted")


@pytest.mark.skipif(shutil.which("node") is None, reason="node is unavailable")
def test_unexposed_turns_from_different_senders_do_not_merge(tmp_path: Path) -> None:
    """Merging across senders would claim one party said what two parties said."""
    turns = _render(
        [
            {"sender": "/root", "recipient": "/root/a", "text": "", "content_state": "provider_encrypted"},
            {"sender": "/root/a", "recipient": "/root", "text": "", "content_state": "provider_encrypted"},
        ],
        "/root/a",
        tmp_path,
    )
    assert len(turns) == 2, "two senders must stay two rows"
    assert [turn["who"] for turn in turns] == ["/root", "this agent \u2192"]
