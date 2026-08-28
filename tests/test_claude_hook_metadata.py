from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from execweave.claude_hook_cli import main as claude_hook_main


def _run_hook(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, payload: dict) -> list[dict]:
    sidecar = tmp_path / "semantic.jsonl"
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    assert claude_hook_main(["--sidecar", str(sidecar)]) == 0
    return [json.loads(line) for line in sidecar.read_text(encoding="utf-8").splitlines()]


@pytest.mark.parametrize(
    ("payload", "relation", "expected_event"),
    [
        (
            {
                "session_id": "session-1",
                "cwd": "/repo",
                "permission_mode": "default",
                "hook_event_name": "TaskCreated",
                "task_id": "task-1",
                "task_subject": "Inspect auth path",
                "task_description": "Trace the exact caller",
            },
            "HAS_TASK_SUBJECT",
            "TaskCreated",
        ),
        (
            {
                "session_id": "session-1",
                "cwd": "/repo",
                "permission_mode": "default",
                "hook_event_name": "PostCompact",
                "trigger": "auto",
                "compact_summary": "provider compact summary",
            },
            "OBSERVED_COMPACTION_SUMMARY",
            "PostCompact",
        ),
    ],
)
def test_persisted_official_content_keeps_exact_hook_event_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    payload: dict,
    relation: str,
    expected_event: str,
) -> None:
    records = _run_hook(tmp_path, monkeypatch, payload)

    record = next(item for item in records if item["relation"] == relation)
    assert record["attributes"]["attribution"] == "claude_official_hook_contract"
    assert record["attributes"]["claude_hook_event_name"] == expected_event
