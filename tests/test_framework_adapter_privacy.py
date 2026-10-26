from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from execweave.framework_adapters import AdapterContext, AutoGenAdapter, ContentCapturePolicy


class ThoughtEvent(SimpleNamespace):
    pass


def test_autogen_thought_event_never_persists_private_reasoning(tmp_path: Path) -> None:
    context = AdapterContext(
        framework="autogen",
        run_id="privacy-run",
        sidecar=tmp_path / "semantic.jsonl",
        content_root=tmp_path,
        capture_policy=ContentCapturePolicy("prompt_and_response"),
    )
    adapter = AutoGenAdapter(context)
    adapter.observe_agentchat_event(
        ThoughtEvent(
            id="thought-1",
            source="planner",
            content="PRIVATE_CHAIN_OF_THOUGHT_SHOULD_NOT_BE_CAPTURED",
            metadata={"reasoning": "PRIVATE_CHAIN_OF_THOUGHT_SHOULD_NOT_BE_CAPTURED"},
        )
    )

    payload = (tmp_path / "semantic.jsonl").read_text(encoding="utf-8")
    assert "PRIVATE_CHAIN_OF_THOUGHT_SHOULD_NOT_BE_CAPTURED" not in payload
    assert not (tmp_path / "content").exists()
    records = [json.loads(line) for line in payload.splitlines() if line]
    message = next(record for record in records if record["event_type"] == "MESSAGE_SENT")
    assert message["attributes"]["role"] == "internal_reasoning"
    assert message["attributes"]["content_suppressed_by_policy"] is True
    assert message["attributes"]["content_available"] is False
