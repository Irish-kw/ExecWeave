from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from typing import Any

import pytest

import execweave.codex_hook_cli as codex_hook_cli


def _write_child_rollout(
    codex_home: Path,
    *,
    parent_thread: str,
    child_thread: str,
    agent_path: str,
) -> Path:
    sessions = codex_home / "sessions" / "2026" / "08" / "29"
    sessions.mkdir(parents=True, exist_ok=True)
    rollout = sessions / f"rollout-2026-08-29T00-00-00-{child_thread}.jsonl"
    records = [
        {
            "timestamp": "2026-08-29T00:00:00Z",
            "type": "session_meta",
            "payload": {
                "id": child_thread,
                "parent_thread_id": parent_thread,
                "agent_path": agent_path,
                "agent_nickname": agent_path.rsplit("/", 1)[-1],
                "source": {
                    "subagent": {
                        "thread_spawn": {
                            "parent_thread_id": parent_thread,
                            "agent_path": agent_path,
                            "agent_nickname": agent_path.rsplit("/", 1)[-1],
                        }
                    }
                },
            },
        },
        {
            "timestamp": "2026-08-29T00:00:01Z",
            "ordinal": 1,
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "phase": "commentary",
                "content": [
                    {
                        "type": "output_text",
                        "text": f"private work for {agent_path}",
                    }
                ],
            },
        },
        {
            "timestamp": "2026-08-29T00:00:02Z",
            "ordinal": 2,
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "phase": "final_answer",
                "content": [
                    {
                        "type": "output_text",
                        "text": f"final response from {agent_path}",
                    }
                ],
            },
        },
    ]
    rollout.write_text(
        "".join(json.dumps(record, separators=(",", ":")) + "\n" for record in records),
        encoding="utf-8",
    )
    return rollout


def _payload(
    *,
    parent_thread: str,
    child_thread: str,
    rollout: Path,
    cwd: Path,
) -> dict[str, Any]:
    return {
        "hook_event_name": "SubagentStop",
        "session_id": parent_thread,
        "turn_id": "turn-1",
        "agent_id": child_thread,
        "agent_type": "default",
        "cwd": str(cwd),
        "model": "gpt-test",
        "permission_mode": "default",
        "stop_hook_active": False,
        "transcript_path": str(
            rollout.with_name(f"rollout-2026-08-29T00-00-00-{parent_thread}.jsonl")
        ),
        "agent_transcript_path": str(rollout),
        "last_assistant_message": f"final response from {child_thread}",
    }


def _run_hook(
    monkeypatch: pytest.MonkeyPatch,
    payload: dict[str, Any],
    sidecar: Path,
    *,
    strict: bool = False,
) -> int:
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    args = ["--sidecar", str(sidecar)]
    if strict:
        args.append("--strict")
    return codex_hook_cli.main(args)


def _records(sidecar: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in sidecar.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _content_kind(record: dict[str, Any]) -> str | None:
    target = record.get("target")
    if not isinstance(target, dict):
        return None
    attributes = target.get("attributes")
    if not isinstance(attributes, dict):
        return None
    value = attributes.get("content_kind")
    return value if isinstance(value, str) else None


@pytest.mark.parametrize(("strict", "expected_code"), [(False, 0), (True, 1)])
def test_codex_content_failure_does_not_block_child_transcript_archive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    strict: bool,
    expected_code: int,
) -> None:
    codex_home = tmp_path / "codex-home"
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    parent_thread = "parent-thread"
    child_thread = "child-thread"
    rollout = _write_child_rollout(
        codex_home,
        parent_thread=parent_thread,
        child_thread=child_thread,
        agent_path="/root/child",
    )
    payload = _payload(
        parent_thread=parent_thread,
        child_thread=child_thread,
        rollout=rollout,
        cwd=tmp_path,
    )
    sidecar = tmp_path / "run" / "semantic.jsonl"

    def fail_content(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        raise RuntimeError("synthetic optional content failure")

    monkeypatch.setattr(codex_hook_cli, "codex_hook_to_content_events", fail_content)

    assert _run_hook(monkeypatch, payload, sidecar, strict=strict) == expected_code

    records = _records(sidecar)
    assert any(
        record.get("event_type") == "semantic.codex.subagent.stopped"
        for record in records
    )
    assert any(_content_kind(record) == "codex.provider_hook_metadata" for record in records)
    archives = [
        record
        for record in records
        if record.get("event_type") == "semantic.codex.conversation.transcript.archived"
    ]
    assert len(archives) == 1
    assert archives[0]["source"]["id"] == (
        f"agent:codex:{parent_thread}:subagent:{child_thread}"
    )
    assert archives[0]["attributes"]["transcript_scope"] == "subagent"
    assert archives[0]["attributes"]["codex_hook_event_name"] == "SubagentStop"


def test_codex_five_child_stops_archive_even_when_three_content_captures_fail(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    codex_home = tmp_path / "codex-home"
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    parent_thread = "parent-thread"
    sidecar = tmp_path / "run" / "semantic.jsonl"
    child_ids = [f"child-{index}" for index in range(5)]
    failing = set(child_ids[:3])
    original = codex_hook_cli.codex_hook_to_content_events

    def flaky_content(
        payload: dict[str, Any],
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        if payload.get("agent_id") in failing:
            raise RuntimeError("synthetic content failure")
        return original(payload, **kwargs)

    monkeypatch.setattr(codex_hook_cli, "codex_hook_to_content_events", flaky_content)

    for index, child_thread in enumerate(child_ids):
        rollout = _write_child_rollout(
            codex_home,
            parent_thread=parent_thread,
            child_thread=child_thread,
            agent_path=f"/root/child_{index}",
        )
        payload = _payload(
            parent_thread=parent_thread,
            child_thread=child_thread,
            rollout=rollout,
            cwd=tmp_path,
        )
        assert _run_hook(monkeypatch, payload, sidecar) == 0

    records = _records(sidecar)
    metadata = [
        record
        for record in records
        if _content_kind(record) == "codex.provider_hook_metadata"
    ]
    archives = [
        record
        for record in records
        if record.get("event_type") == "semantic.codex.conversation.transcript.archived"
    ]

    assert len(metadata) == 5
    assert len(archives) == 5
    assert {
        record["source"]["attributes"]["agent_id"]
        for record in archives
    } == set(child_ids)
    assert all(record["attributes"]["transcript_scope"] == "subagent" for record in archives)
