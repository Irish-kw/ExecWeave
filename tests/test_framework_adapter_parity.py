from __future__ import annotations

import json
from pathlib import Path

from execweave.framework_adapters import AdapterContext, ContentCapturePolicy, CAMELAdapter
from execweave.schema import RuntimeEvent
from execweave.semantic import LiveSemanticNormalizer, merge_semantic_sidecar


START = "2026-01-01T00:00:00Z"
MIDDLE = "2026-01-01T00:00:01Z"
FINISH = "2026-01-01T00:00:02Z"


def _runtime(path: Path) -> None:
    events = [
        RuntimeEvent.create(
            session_id="session-1",
            event_type="session.started",
            relation="STARTED_SESSION",
            timestamp=START,
        ),
        RuntimeEvent.create(
            session_id="session-1",
            event_type="session.finished",
            relation="FINISHED_SESSION",
            timestamp=FINISH,
            attributes={"return_code": 0},
        ),
    ]
    payloads = []
    for sequence, event in enumerate(events, start=1):
        payload = event.to_dict()
        payload["sequence"] = sequence
        payloads.append(payload)
    path.write_text(
        "".join(json.dumps(payload, sort_keys=True) + "\n" for payload in payloads),
        encoding="utf-8",
    )


def test_live_and_finished_semantic_records_have_same_identity_and_content_refs(tmp_path: Path) -> None:
    runtime = tmp_path / "events.jsonl"
    semantic = tmp_path / "semantic.jsonl"
    merged = tmp_path / "events.semantic.jsonl"
    _runtime(runtime)

    context = AdapterContext(
        framework="camel",
        run_id="run-1",
        session_id="session-1",
        sidecar=semantic,
        content_root=tmp_path,
        capture_policy=ContentCapturePolicy("prompt_and_response"),
    )
    adapter = CAMELAdapter(context)
    agent = adapter.agent("worker-1", name="Worker")
    record = context.emit(
        "AGENT_CREATED",
        "AGENT_CREATED",
        source=agent,
        timestamp=MIDDLE,
        attributes={"display": "worker"},
    )

    normalizer = LiveSemanticNormalizer("session-1")
    start = json.loads(runtime.read_text(encoding="utf-8").splitlines()[0])
    normalizer.observe_runtime_event(start)
    live = normalizer.normalize(record, line_number=1)
    assert live is not None

    result = merge_semantic_sidecar(runtime, semantic, merged)
    assert result.semantic_event_count == 1
    final = next(
        json.loads(line)
        for line in merged.read_text(encoding="utf-8").splitlines()
        if json.loads(line)["event_type"] == "AGENT_CREATED"
    )

    assert live["session_id"] == final["session_id"] == "session-1"
    assert live["event_type"] == final["event_type"]
    assert live["relation"] == final["relation"]
    assert live["source"] == final["source"]
    assert live["target"] == final["target"]
    assert live["attributes"]["run_id"] == final["attributes"]["run_id"]
