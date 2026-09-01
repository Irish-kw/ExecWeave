"""Ollama panel shows current-turn prompt/response and does not invent Task folds."""

from __future__ import annotations

import json
import subprocess

from execweave.conversation_records_ollama import _ollama_current_turn
from execweave.viewer_agent_panel_codex import CODEX_CHILD_ROUNDS_JS
from execweave.viewer_agent_panel_ollama import OLLAMA_CHILD_ROUNDS_JS


def test_ollama_does_not_copy_codex_or_invent_task_cards() -> None:
    assert "['Task'" not in OLLAMA_CHILD_ROUNDS_JS
    assert "['Thinking'" not in OLLAMA_CHILD_ROUNDS_JS
    assert "['Prompt'" in OLLAMA_CHILD_ROUNDS_JS
    assert "['Final response'" in OLLAMA_CHILD_ROUNDS_JS
    assert "kind==='user_message'" in CODEX_CHILD_ROUNDS_JS
    assert "isTask" not in OLLAMA_CHILD_ROUNDS_JS


def test_ollama_current_turn_keeps_last_user_and_assistant_only() -> None:
    preview = {
        "messages": [
            {"sender": "user", "kind": "user_message", "content_role": "ollama_request_surface", "text": "old"},
            {"sender": "assistant", "kind": "assistant_message", "content_role": "ollama_response_surface", "text": "old-a"},
            {"sender": "user", "kind": "user_message", "content_role": "ollama_request_surface", "text": "now"},
            {"sender": "assistant", "kind": "assistant_message", "content_role": "ollama_response_surface", "text": "now-a"},
        ]
    }
    _ollama_current_turn(preview)
    assert [message["text"] for message in preview["messages"]] == ["now", "now-a"]


def _eval(messages: list[dict[str, object]], path: str) -> list[dict[str, object]]:
    harness = r"""
const isObserved=message=>!!message&&!!String(message?.text||'').trim();
const isInjected=message=>String(message?.content_role||'')==='shared_injected_context';
const own=(message,path)=>!message?.sender||String(message.sender)===path||String(message.sender)==='assistant';
const messageText=message=>typeof message?.text==='string'?message.text.trim():'';
const displayText=message=>messageText(message);
function messageKey(message){return JSON.stringify([message?.timestamp??null,message?.text??null])}
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
    script = harness + "\n" + OLLAMA_CHILD_ROUNDS_JS + f"\nprocess.stdout.write(JSON.stringify(execweaveOllamaChildRounds({json.dumps(messages)},{json.dumps(path)})));\n"
    completed = subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True)
    return json.loads(completed.stdout)


def test_ollama_single_turn_has_no_task_fold() -> None:
    rounds = _eval(
        [
            {"kind": "user_message", "sender": "user", "recipient": "/root", "text": "hello", "content_role": "ollama_request_surface"},
            {"kind": "assistant_message", "sender": "/root", "text": "hi", "content_role": "ollama_response_surface"},
        ],
        "/root",
    )
    assert len(rounds) == 1
    assert dict(rounds[0]["cards"]) == {"Prompt": "hello", "Final response": "hi"}


def test_ollama_multiple_user_turns_are_separate_rounds() -> None:
    rounds = _eval(
        [
            {"kind": "user_message", "sender": "user", "recipient": "/root", "text": "one", "timestamp": "t1"},
            {"kind": "assistant_message", "sender": "/root", "text": "a1", "timestamp": "t2"},
            {"kind": "user_message", "sender": "user", "recipient": "/root", "text": "two", "timestamp": "t3"},
            {"kind": "assistant_message", "sender": "/root", "text": "a2", "timestamp": "t4"},
        ],
        "/root",
    )
    assert len(rounds) == 2
    assert dict(rounds[1]["cards"])["Prompt"] == "two"
