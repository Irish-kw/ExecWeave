from __future__ import annotations

import json
from pathlib import Path

from execweave.conversation_archive import antigravity_conversation_archive_events
from execweave.conversation_records import conversation_record_entries
from execweave.content_store import FullFidelityContentStore
from execweave.graph import GraphAccumulator


_CONVERSATION_ID = "sus-001-three-rounds"


def _transcript_path(tmp_path: Path) -> Path:
    path = (
        tmp_path
        / "antigravity-cli"
        / "brain"
        / _CONVERSATION_ID
        / ".system_generated"
        / "logs"
        / "transcript_full.jsonl"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _round(step_index: int, label: str) -> list[dict[str, object]]:
    return [
        {
            "step_index": step_index,
            "source": "USER",
            "type": "USER_MESSAGE",
            "content": f"question {label}",
        },
        {
            "step_index": step_index + 1,
            "source": "MODEL",
            "type": "PLANNER_RESPONSE",
            "content": f"answer {label}",
        },
    ]


def _write_snapshot(path: Path, records: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )


def _messages(graph: GraphAccumulator, run_root: Path) -> list[dict[str, object]]:
    entries = conversation_record_entries(graph.to_dict(), run_root)
    previews = [
        entry["conversation_preview"]
        for entry in entries
        if entry.get("provider") == "antigravity"
        and isinstance(entry.get("conversation_preview"), dict)
    ]
    assert len(previews) == 1
    messages = previews[0].get("messages")
    assert isinstance(messages, list)
    return messages


def test_antigravity_cumulative_stop_snapshots_preserve_three_round_history(
    tmp_path: Path,
) -> None:
    """SUS-001 replay: cumulative Stop snapshots must not re-identify old turns."""
    transcript = _transcript_path(tmp_path)
    run_root = tmp_path / "run"
    store = FullFidelityContentStore(run_root)
    graph = GraphAccumulator(session_id="sus-001", source_path=run_root / "events.jsonl")
    records: list[dict[str, object]] = []

    expected_texts: list[str] = []
    for snapshot_index, label in enumerate(("A", "B", "C"), start=1):
        records.extend(_round(snapshot_index * 10, label))
        expected_texts.extend((f"question {label}", f"answer {label}"))
        _write_snapshot(transcript, records)

        events = antigravity_conversation_archive_events(
            {
                "conversationId": _CONVERSATION_ID,
                "transcriptPath": str(transcript),
            },
            store=store,
            timestamp=f"2026-08-31T14:0{snapshot_index}:00Z",
        )
        assert len(events) == 1
        event = dict(events[0])
        event["sequence"] = snapshot_index * 100
        graph.apply(event)

        messages = _messages(graph, run_root)
        assert [message.get("text") for message in messages] == expected_texts
        assert len(messages) == snapshot_index * 2
