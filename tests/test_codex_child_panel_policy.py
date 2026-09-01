"""Codex child Task/Thinking/Response policy stays out of the shared default."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from execweave.codex_conversation import codex_rollout_previews
from execweave.conversation_records_codex import drop_root_user_prompts_from_codex_children
from execweave.viewer_agent_panel import _AGENT_PANEL_JS
from execweave.viewer_agent_panel_codex import CODEX_CHILD_ROUNDS_JS
from execweave.viewer_agent_panel_default import DEFAULT_CHILD_ROUNDS_JS

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures" / "codex_multi_agent"
MENDEL_TASK = (
    "Investigate the Mendel inheritance notes and return only the child's own answer."
)


def test_codex_task_rule_is_not_in_default_or_other_providers() -> None:
    assert "kind==='user_message'" in CODEX_CHILD_ROUNDS_JS
    assert "kind==='user_message'" not in DEFAULT_CHILD_ROUNDS_JS
    src = ROOT / "src" / "execweave"
    for name in (
        "viewer_agent_panel_default.py",
        "viewer_agent_panel_antigravity.py",
        "viewer_agent_panel_claude.py",
    ):
        text = (src / name).read_text(encoding="utf-8")
        assert "kind==='user_message'" not in text
    assert "execweaveCodexChildRounds" in _AGENT_PANEL_JS
    assert "function execweaveDefaultChildRounds" in _AGENT_PANEL_JS


def _eval_codex_rounds(messages: list[dict[str, object]], path: str) -> list[dict[str, object]]:
    harness = r"""
const ENCRYPTED_NOTICE='Observed — plaintext not exposed by provider.';
const isEncrypted=message=>String(message?.content_state||'')==='provider_encrypted';
const messageText=message=>typeof message?.text==='string'?message.text.trim():'';
const isObserved=message=>!!message&&(isEncrypted(message)||!!messageText(message));
const isInjected=message=>String(message?.content_role||'')==='shared_injected_context';
const own=(message,path)=>!message?.sender||String(message.sender)===path;
const displayText=message=>isEncrypted(message)?ENCRYPTED_NOTICE:messageText(message);
const summarise=text=>{const line=String(text||'').split('\n').map(part=>part.trim()).find(Boolean)||'';return line.length>52?line.slice(0,52)+'…':line};
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
        + CODEX_CHILD_ROUNDS_JS
        + "\nconst messages="
        + json.dumps(messages)
        + ";\nconst rounds=execweaveCodexChildRounds(messages,"
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


def test_codex_child_user_message_from_parent_is_that_childs_task() -> None:
    path = "/root/Mendel"
    messages = [
        {
            "kind": "user_message",
            "sender": "/root",
            "recipient": "/root/Mendel",
            "text": MENDEL_TASK,
            "timestamp": "2026-09-01T10:00:00Z",
            "ordinal": 1,
        },
        {
            "kind": "assistant_message",
            "sender": "/root/Mendel",
            "phase": "commentary",
            "text": "Mendel PRIVATE REASONING",
            "timestamp": "2026-09-01T10:00:01Z",
            "ordinal": 2,
        },
        {
            "kind": "subagent_final_response",
            "sender": "/root/Mendel",
            "recipient": "/root",
            "phase": "final_answer",
            "text": "Mendel FINAL RESPONSE",
            "timestamp": "2026-09-01T10:00:02Z",
            "ordinal": 3,
        },
        {
            "kind": "user_message",
            "sender": "/root",
            "recipient": "/root/other",
            "text": "OTHER CHILD PROMPT",
            "timestamp": "2026-09-01T10:00:03Z",
            "ordinal": 4,
        },
    ]
    rounds = _eval_codex_rounds(messages, path)
    assert len(rounds) == 1
    cards = dict(rounds[0]["cards"])
    assert cards["Task"] == MENDEL_TASK
    assert cards["Thinking"] == "Mendel PRIVATE REASONING"
    assert cards["Response"] == "Mendel FINAL RESPONSE"
    assert "OTHER CHILD PROMPT" not in json.dumps(rounds)


def test_codex_child_without_reasoning_evidence_is_not_observed() -> None:
    path = "/root/Mendel"
    messages = [
        {
            "kind": "user_message",
            "sender": "/root",
            "recipient": path,
            "text": MENDEL_TASK,
            "timestamp": "2026-09-01T10:00:00Z",
            "ordinal": 1,
        },
        {
            "kind": "subagent_final_response",
            "sender": path,
            "recipient": "/root",
            "phase": "final_answer",
            "text": "done",
            "timestamp": "2026-09-01T10:00:02Z",
            "ordinal": 2,
        },
    ]
    cards = dict(_eval_codex_rounds(messages, path)[0]["cards"])
    assert cards["Task"] == MENDEL_TASK
    assert cards["Thinking"] == ""
    assert cards["Response"] == "done"


def test_codex_child_multiple_user_messages_are_separate_foldable_rounds() -> None:
    path = "/root/Mendel"
    messages = [
        {
            "kind": "user_message",
            "sender": "/root",
            "recipient": path,
            "text": "first assignment",
            "timestamp": "2026-09-01T10:00:00Z",
            "ordinal": 1,
        },
        {
            "kind": "subagent_final_response",
            "sender": path,
            "phase": "final_answer",
            "text": "first answer",
            "timestamp": "2026-09-01T10:01:00Z",
            "ordinal": 2,
        },
        {
            "kind": "user_message",
            "sender": "/root",
            "recipient": path,
            "text": "second assignment",
            "timestamp": "2026-09-01T11:00:00Z",
            "ordinal": 3,
        },
        {
            "kind": "subagent_final_response",
            "sender": path,
            "phase": "final_answer",
            "text": "second answer",
            "timestamp": "2026-09-01T11:01:00Z",
            "ordinal": 4,
        },
    ]
    rounds = _eval_codex_rounds(messages, path)
    assert len(rounds) == 2
    assert dict(rounds[0]["cards"])["Task"] == "first assignment"
    assert dict(rounds[1]["cards"])["Task"] == "second assignment"
    assert "execweave-agent-older" in _AGENT_PANEL_JS
    assert "foldStateFor(node)" in _AGENT_PANEL_JS
    assert "ordered.slice(1)" in _AGENT_PANEL_JS


def test_codex_root_prompt_shape_is_unchanged_in_root_renderer() -> None:
    assert "function rootRounds(messages,path)" in _AGENT_PANEL_JS
    assert (
        "(String(message?.kind||'')==='user_message'||String(message?.sender||'')==='user')"
        in _AGENT_PANEL_JS
    )
    previews = codex_rollout_previews(FIXTURES / "rollout-main.jsonl")
    root = next(preview for preview in previews if preview.get("agent_path") == "/root")
    prompts = [
        message.get("text")
        for message in root.get("messages") or []
        if message.get("kind") == "user_message" and message.get("recipient") == "/root"
    ]
    assert "USER TASK: run five agents" in prompts


def test_fixture_child_task_is_addressed_only_to_that_child() -> None:
    previews = codex_rollout_previews(FIXTURES / "rollout-main.jsonl")
    child = next(
        preview
        for preview in previews
        if preview.get("agent_path") == "/root/rain_forecast"
    )
    path = "/root/rain_forecast"
    messages = list(child.get("messages") or [])
    messages[0] = {
        **messages[0],
        "kind": "user_message",
        "sender": "/root",
        "recipient": path,
        "text": "TASK FOR rain_forecast",
    }
    rounds = _eval_codex_rounds(messages, path)
    assert len(rounds) >= 1
    assert dict(rounds[0]["cards"])["Task"].startswith("TASK FOR rain_forecast")
    assert dict(rounds[0]["cards"])["Response"] == "rain_forecast FINAL RESPONSE"
    other = next(
        preview
        for preview in previews
        if preview.get("agent_path") == "/root/hydrology"
    )
    hydrology = _eval_codex_rounds(list(other.get("messages") or []), "/root/hydrology")
    assert "rain_forecast" not in json.dumps(hydrology)


def test_codex_child_fold_does_not_reuse_root_user_prompt() -> None:
    path = "/root/charisma_judge"
    root_prompt = "開三個agent討論 1.我帥嗎"
    messages = [
        {
            "kind": "user_message",
            "sender": "user",
            "recipient": "/root",
            "text": root_prompt,
            "timestamp": "2026-09-01T00:29:00Z",
            "ordinal": 1,
        },
        {
            "kind": "task",
            "phase": "assignment",
            "sender": "/root",
            "recipient": path,
            "text": None,
            "content_state": "provider_encrypted",
            "timestamp": "2026-09-01T00:29:05Z",
            "ordinal": 2,
        },
        {
            "kind": "subagent_final_response",
            "sender": path,
            "recipient": "/root",
            "phase": "final_answer",
            "text": "帥不帥得看臉，不能只看自我感覺。",
            "timestamp": "2026-09-01T00:30:00Z",
            "ordinal": 3,
        },
        {
            "kind": "new_task",
            "phase": "assignment",
            "sender": "/root",
            "recipient": path,
            "text": None,
            "content_state": "provider_encrypted",
            "timestamp": "2026-09-01T00:31:00Z",
            "ordinal": 4,
        },
        {
            "kind": "subagent_final_response",
            "sender": path,
            "recipient": "/root",
            "phase": "final_answer",
            "text": "第二輪仍只看該 child 自己的回覆。",
            "timestamp": "2026-09-01T00:32:00Z",
            "ordinal": 5,
        },
    ]
    preview = {"is_root": False, "agent_path": path, "messages": list(messages)}
    drop_root_user_prompts_from_codex_children(
        [{"provider": "codex", "conversation_preview": preview}]
    )
    assert all(
        not (
            str(message.get("sender") or "") == "user"
            and str(message.get("recipient") or "") == "/root"
        )
        for message in preview["messages"]
    )
    rounds = _eval_codex_rounds(messages, path)
    dumped = json.dumps(rounds, ensure_ascii=False)
    assert root_prompt not in dumped
    assert "開三個agent討論" not in dumped
    assert len(rounds) == 2
    first = dict(rounds[0]["cards"])
    second = dict(rounds[1]["cards"])
    assert first["Task"] == "Observed — plaintext not exposed by provider."
    assert first["Thinking"] == ""
    assert "帥不帥得看臉" in first["Response"]
    assert second["Task"] == "Observed — plaintext not exposed by provider."
    assert "第二輪仍只看該 child 自己的回覆" in second["Response"]
    assert rounds[0]["label"] == "Observed — plaintext not exposed by provider."
    assert "round.label?round:" in _AGENT_PANEL_JS
