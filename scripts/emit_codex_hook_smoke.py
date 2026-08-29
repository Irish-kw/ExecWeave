"""Drive the Codex hook surface in CI using the record shapes a real run produces.

The v0.7.2 conversation regression shipped because no CI check ever fed ExecWeave a
Codex ``SubagentStop``. Codex puts the child rollout on ``agent_transcript_path`` and
leaves ``transcript_path`` pointing at the parent session rollout; selecting the
parent silently dropped every child conversation while CI stayed green.

This emitter writes a real parent rollout and a real child rollout into a temporary
``CODEX_HOME``, then sends the lifecycle hooks that reference them, so the record
pipeline has to make that choice for real.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

SESSION_ID = "01a04cea-0a14-71e0-8c32-4aeafda0f039"
CHILD_ID = "01a04cea-67b2-7683-9f6b-cd644497b862"
CHILD_PATH = "/root/explorer"
TURN_ID = "01a04cea-4023-7990-b890-ce7cb0d87c5a"
CHILD_TURN_ID = "01a04cea-683d-7a81-a7c6-c554a4b78881"

ROOT_PROMPT = "CI ROOT PROMPT"
ROOT_COMMENTARY = "CI ROOT COMMENTARY"
ROOT_FINAL = "CI ROOT FINAL ANSWER"
CHILD_TASK = "CI CHILD TASK"
CHILD_PRIVATE = "CI CHILD PRIVATE REASONING"
CHILD_FINAL = "CI CHILD FINAL RESPONSE"


def _record(ordinal: int, record_type: str, payload: dict) -> dict:
    return {
        "timestamp": f"2026-08-29T09:{ordinal // 60:02d}:{ordinal % 60:02d}.000Z",
        "ordinal": ordinal,
        "type": record_type,
        "payload": payload,
    }


def _message(ordinal: int, role: str, text: str, *, phase=None, user_text=False) -> dict:
    payload: dict = {
        "type": "message",
        "role": role,
        "content": [
            {"type": "input_text" if role == "user" else "output_text", "text": text}
        ],
    }
    if phase is not None:
        payload["phase"] = phase
    if user_text:
        payload["internal_chat_message_metadata_passthrough"] = {
            "content_item_kinds": ["user.text"]
        }
    return _record(ordinal, "response_item", payload)


def _parent_rollout() -> list[dict]:
    """The parent rollout: root's own turns plus the routing records it observed."""
    return [
        _record(0, "session_meta", {"id": SESSION_ID, "session_id": SESSION_ID,
                                    "originator": "codex-tui", "source": "cli"}),
        _message(1, "user", ROOT_PROMPT, user_text=True),
        _message(2, "assistant", ROOT_COMMENTARY, phase="commentary"),
        _record(3, "response_item", {
            "type": "function_call",
            "name": "spawn_agent",
            "namespace": "collaboration",
            "call_id": "call_ci_spawn_1",
            "arguments": json.dumps({"task_name": "explorer", "fork_turns": "all",
                                     "message": "gAAAAAci-encrypted-task-payload"}),
        }),
        _record(4, "event_msg", {
            "type": "item_completed",
            "thread_id": SESSION_ID,
            "turn_id": TURN_ID,
            "item": {"type": "SubAgentActivity", "id": "call_ci_spawn_1",
                     "kind": "started", "agent_thread_id": CHILD_ID,
                     "agent_path": CHILD_PATH},
        }),
        _record(5, "response_item", {
            "type": "function_call_output",
            "call_id": "call_ci_spawn_1",
            "output": json.dumps({"task_name": CHILD_PATH}),
        }),
        _record(6, "inter_agent_communication_metadata", {"trigger_turn": False}),
        _record(7, "response_item", {
            "type": "agent_message",
            "id": "amsg_ci_1",
            "author": CHILD_PATH,
            "recipient": "/root",
            "content": [{
                "type": "input_text",
                "text": (f"Message Type: FINAL_ANSWER\nTask name: /root\n"
                         f"Sender: {CHILD_PATH}\nPayload:\n{CHILD_FINAL}"),
            }],
        }),
        _message(8, "assistant", ROOT_FINAL, phase="final_answer"),
    ]


def _child_rollout() -> list[dict]:
    """The child rollout: inherited parent context, then the child's own turns."""
    return [
        _record(0, "session_meta", {
            "id": CHILD_ID,
            "session_id": CHILD_ID,
            "originator": "codex-tui",
            "source": {"subagent": {"thread_spawn": {
                "agent_path": CHILD_PATH,
                "agent_nickname": "explorer",
                "parent_thread_id": SESSION_ID,
            }}},
            # Everything before this ordinal is replayed parent history, not the
            # child's own conversation.
            "subagent_history_start_ordinal": 3,
        }),
        _message(1, "user", ROOT_PROMPT, user_text=True),
        _message(2, "assistant", ROOT_COMMENTARY, phase="commentary"),
        _message(3, "user", CHILD_TASK),
        _message(4, "assistant", CHILD_PRIVATE, phase="commentary"),
        _message(5, "assistant", CHILD_FINAL, phase="final_answer"),
    ]


def _write_rollout(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )


def _hook(payload: dict) -> None:
    subprocess.run(
        ["execweave-codex-hook"], input=json.dumps(payload), text=True, check=True
    )


def _child_command() -> tuple[list[str], str]:
    if os.name == "nt":
        return ["ping", "-n", "4", "127.0.0.1"], "ping -n 4 127.0.0.1"
    return ["sleep", "3"], "sleep 3"


def main() -> int:
    if not os.environ.get("EXECWEAVE_SEMANTIC_SIDECAR"):
        raise SystemExit("run-bound semantic sidecar environment was not inherited")

    codex_home = Path(tempfile.mkdtemp(prefix="execweave-codex-smoke-"))
    os.environ["CODEX_HOME"] = str(codex_home)
    sessions = codex_home / "sessions" / "2026" / "08" / "29"
    parent_path = sessions / f"rollout-2026-08-29T17-46-41-{SESSION_ID}.jsonl"
    child_path = sessions / f"rollout-2026-08-29T17-47-10-{CHILD_ID}.jsonl"
    _write_rollout(parent_path, _parent_rollout())
    _write_rollout(child_path, _child_rollout())

    child_argv, declared_command = _child_command()
    base = {
        "cwd": str(Path.cwd()),
        "model": "gpt-5.6-terra",
        "permission_mode": "default",
        "session_id": SESSION_ID,
    }

    _hook({**base, "hook_event_name": "SessionStart", "source": "startup",
           "transcript_path": str(parent_path)})
    _hook({**base, "hook_event_name": "UserPromptSubmit", "prompt": ROOT_PROMPT,
           "turn_id": TURN_ID, "transcript_path": str(parent_path)})
    _hook({**base, "hook_event_name": "PreToolUse", "turn_id": TURN_ID,
           "tool_name": "Bash", "tool_use_id": "ci-codex-tool-use",
           "tool_input": {"command": declared_command},
           "transcript_path": str(parent_path)})
    _hook({**base, "hook_event_name": "SubagentStart", "agent_id": CHILD_ID,
           "agent_type": "default", "turn_id": CHILD_TURN_ID,
           "transcript_path": str(child_path)})
    # The record that matters: transcript_path is the PARENT, agent_transcript_path
    # is the CHILD. Archiving the parent here is the v0.7.2 regression.
    _hook({**base, "hook_event_name": "SubagentStop", "agent_id": CHILD_ID,
           "agent_type": "default", "turn_id": CHILD_TURN_ID,
           "stop_hook_active": False,
           "last_assistant_message": CHILD_FINAL,
           "transcript_path": str(parent_path),
           "agent_transcript_path": str(child_path)})
    _hook({**base, "hook_event_name": "Stop", "turn_id": TURN_ID,
           "stop_hook_active": False, "last_assistant_message": ROOT_FINAL,
           "transcript_path": str(parent_path)})
    _hook({**base, "hook_event_name": "SessionEnd", "reason": "other",
           "transcript_path": str(parent_path)})

    process = subprocess.Popen(child_argv)
    time.sleep(0.5)
    return int(process.wait())


if __name__ == "__main__":
    raise SystemExit(main())
