"""Antigravity child Task/Thinking/Response uses Agy kinds, not Codex user_message."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from execweave.viewer_agent_panel import _AGENT_PANEL_JS
from execweave.viewer_agent_panel_antigravity import ANTIGRAVITY_CHILD_ROUNDS_JS
from execweave.viewer_agent_panel_codex import CODEX_CHILD_ROUNDS_JS
from execweave.viewer_agent_panel_default import DEFAULT_CHILD_ROUNDS_JS

ROOT = Path(__file__).resolve().parents[1]


def test_agy_does_not_copy_codex_user_message_task_rule() -> None:
    assert "kind==='user_message'" not in ANTIGRAVITY_CHILD_ROUNDS_JS
    assert "kind==='user_message'" in CODEX_CHILD_ROUNDS_JS
    assert "antigravity_addressed_task" in ANTIGRAVITY_CHILD_ROUNDS_JS
    assert "planner_response" in ANTIGRAVITY_CHILD_ROUNDS_JS
    assert "antigravity_addressed_task" not in DEFAULT_CHILD_ROUNDS_JS
    assert "execweaveAntigravityChildRounds" in _AGENT_PANEL_JS


def _eval_agy_rounds(messages: list[dict[str, object]], path: str) -> list[dict[str, object]]:
    harness = r"""
const isObserved=message=>!!message&&!!String(message?.text||'').trim();
const isInjected=message=>String(message?.content_role||'')==='shared_injected_context';
const own=(message,path)=>!message?.sender||String(message.sender)===path;
const messageText=message=>typeof message?.text==='string'?message.text.trim():'';
const displayText=message=>messageText(message);
const uniqueTexts=messages=>{const seen=new Set(),out=[];for(const message of messages){const text=displayText(message);if(!text||seen.has(text))continue;seen.add(text);out.push(text)}return out};
function messageKey(message){return JSON.stringify([message?.timestamp??null,message?.ordinal??null,message?.sender??null,message?.recipient??null,message?.kind??null])}
function stampOf(message){return String(message?.timestamp||'')}
function windows(messages,openers){
  if(!openers.length)return[{opener:null,messages}];
  const out=[];
  for(let index=0;index<openers.length;index++){
    const from=messages.indexOf(openers[index]);
    const next=index+1<openers.length?messages.indexOf(openers[index+1]):messages.length;
    out.push({opener:openers[index],messages:messages.slice(from<0?0:from,next<0?messages.length:next)});
  }
  return out;
}
"""
    script = (
        harness
        + "\n"
        + ANTIGRAVITY_CHILD_ROUNDS_JS
        + "\nconst messages="
        + json.dumps(messages)
        + ";\nconst rounds=execweaveAntigravityChildRounds(messages,"
        + json.dumps(path)
        + ");\nprocess.stdout.write(JSON.stringify(rounds));\n"
    )
    completed = subprocess.run(
        ["node", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)
    assert isinstance(payload, list)
    return payload


def test_agy_child_task_comes_from_addressed_assignment_not_root_prompt() -> None:
    path = "/root/child-1"
    messages = [
        {
            "kind": "user_message",
            "sender": "user",
            "recipient": "/root",
            "text": "ROOT PROMPT ONE",
            "timestamp": "2026-09-01T10:00:00Z",
            "ordinal": 1,
        },
        {
            "kind": "task",
            "phase": "assignment",
            "sender": "/root",
            "recipient": path,
            "text": "TASK UNIQUE 1",
            "content_role": "antigravity_addressed_task",
            "timestamp": "2026-09-01T10:10:00Z",
            "ordinal": 2,
        },
        {
            "kind": "assistant_message",
            "sender": path,
            "phase": "planner_response",
            "text": "child planner reply",
            "timestamp": "2026-09-01T10:11:00Z",
            "ordinal": 3,
        },
    ]
    rounds = _eval_agy_rounds(messages, path)
    assert len(rounds) == 1
    cards = dict(rounds[0]["cards"])
    assert cards["Task"] == "TASK UNIQUE 1"
    assert cards["Thinking"] == ""
    assert cards["Response"] == "child planner reply"
    assert "ROOT PROMPT ONE" not in json.dumps(rounds)


def test_agy_two_assignments_are_foldable_and_do_not_wash_siblings() -> None:
    path = "/root/child-1"
    messages = [
        {
            "kind": "subagent_task",
            "phase": "assignment",
            "sender": "/root",
            "recipient": path,
            "text": "child A first task",
            "timestamp": "2026-09-01T01:00:00Z",
            "ordinal": 1,
        },
        {
            "kind": "assistant_message",
            "sender": path,
            "phase": "planner_response",
            "text": "child A first response",
            "timestamp": "2026-09-01T01:00:05Z",
            "ordinal": 2,
        },
        {
            "kind": "task",
            "phase": "assignment",
            "sender": "/root",
            "recipient": path,
            "text": "child A second task",
            "content_role": "antigravity_addressed_task",
            "timestamp": "2026-09-01T01:01:00Z",
            "ordinal": 3,
        },
        {
            "kind": "assistant_message",
            "sender": path,
            "phase": "planner_response",
            "text": "child A second response",
            "timestamp": "2026-09-01T01:01:05Z",
            "ordinal": 4,
        },
        {
            "kind": "task",
            "phase": "assignment",
            "sender": "/root",
            "recipient": "/root/child-2",
            "text": "child B first task",
            "timestamp": "2026-09-01T01:00:01Z",
            "ordinal": 5,
        },
    ]
    rounds = _eval_agy_rounds(messages, path)
    assert len(rounds) == 2
    assert dict(rounds[0]["cards"])["Task"] == "child A first task"
    assert dict(rounds[1]["cards"])["Task"] == "child A second task"
    assert dict(rounds[1]["cards"])["Response"] == "child A second response"
    dumped = json.dumps(rounds)
    assert "child B first task" not in dumped
    assert "execweave-agent-older" in _AGENT_PANEL_JS
