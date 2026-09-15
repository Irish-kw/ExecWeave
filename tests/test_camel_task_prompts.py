from __future__ import annotations

import json
from pathlib import Path

from execweave.framework_adapters import (
    AdapterContext,
    CAMELAdapter,
    ContentCapturePolicy,
)


def _records(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_camel_task_prompt_is_persisted_and_bound_to_task(tmp_path: Path) -> None:
    prompt = "Write one concise factual sentence about the observed endpoint."
    context = AdapterContext(
        framework="camel",
        run_id="run-task-prompt",
        sidecar=tmp_path / "semantic.jsonl",
        content_root=tmp_path,
        capture_policy=ContentCapturePolicy("prompt_and_response"),
    )
    adapter = CAMELAdapter(context)
    task = adapter.task_created("task-1", name=prompt, content=prompt)

    records = _records(tmp_path / "semantic.jsonl")
    created = next(record for record in records if record["event_type"] == "TASK_CREATED")
    assert created["target"]["id"] == task.id
    assert created["target"]["name"] == prompt
    assert created["target"]["attributes"]["task_prompt"] == prompt
    content = next(record for record in records if record["event_type"] == "TASK_CONTENT_RECORDED")
    assert content["relation"] == "HAS_TASK_CONTENT"
    assert content["source"]["id"] == task.id
    assert content["target"]["type"] == "observed_content"
    reference = content["attributes"]["content_ref"]
    assert (tmp_path / reference).read_text(encoding="utf-8") == prompt


def test_camel_seeded_task_is_not_replaced_by_callback_without_prompt(tmp_path: Path) -> None:
    prompt = "Use the local Ollama endpoint and report completion."
    context = AdapterContext(
        framework="camel",
        run_id="run-task-prompt-callback",
        sidecar=tmp_path / "semantic.jsonl",
        content_root=tmp_path,
        capture_policy=ContentCapturePolicy("prompt_and_response"),
    )
    adapter = CAMELAdapter(context)
    seeded = adapter.task_created("task-1", name=prompt, content=prompt)
    callback_task = adapter._callback_event(
        "log_task_created",
        (),
        {"task": {"task_id": "task-1"}},
    )

    assert callback_task.id == seeded.id
    assert callback_task.name == prompt
    records = _records(tmp_path / "semantic.jsonl")
    assert sum(record["event_type"] == "TASK_CONTENT_RECORDED" for record in records) == 1
