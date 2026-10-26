from __future__ import annotations

import io
import json
from pathlib import Path

from execweave.claude_hook_cli import main as claude_hook_main
from execweave.claude_model_observer import append_claude_transcript_model_events
from execweave.provider_lifecycle import provider_lifecycle_annotation


def _hook_payload(transcript: Path, event: str = "Stop") -> dict[str, object]:
    return {
        "session_id": "session-1",
        "cwd": str(transcript.parent),
        "transcript_path": str(transcript),
        "hook_event_name": event,
        "stop_hook_active": False,
    }


def _assistant(
    model: str,
    *,
    timestamp: str,
    message_id: str,
    text: str = "assistant text",
    sidechain: bool = False,
) -> dict[str, object]:
    return {
        "type": "assistant",
        "isSidechain": sidechain,
        "sessionId": "session-1",
        "uuid": f"uuid-{message_id}",
        "timestamp": timestamp,
        "message": {
            "id": message_id,
            "type": "message",
            "role": "assistant",
            "model": model,
            "content": [{"type": "text", "text": text}],
        },
    }


def _local_model_command(model: str, timestamp: str) -> dict[str, object]:
    return {
        "type": "user",
        "sessionId": "session-1",
        "timestamp": timestamp,
        "message": {
            "role": "user",
            "content": (
                f"<command-name>/model</command-name>"
                f"<command-args>{model}</command-args>"
                f"<local-command-stdout>Set model to {model}</local-command-stdout>"
            ),
        },
    }


def _append(path: Path, record: dict[str, object]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_first_assistant_model_is_recorded_as_actual_served_model_without_content_leak(
    tmp_path: Path,
) -> None:
    transcript = tmp_path / "transcript.jsonl"
    sidecar = tmp_path / "semantic.jsonl"
    secret = "PRIVATE_ASSISTANT_TEXT_MUST_NOT_ENTER_MODEL_EVIDENCE"
    _append(
        transcript,
        _assistant(
            "claude-haiku-4-5-20251001",
            timestamp="2026-08-27T01:00:00Z",
            message_id="msg-a",
            text=secret,
        ),
    )

    events = append_claude_transcript_model_events(
        _hook_payload(transcript),
        sidecar=sidecar,
        timestamp="2026-08-27T01:00:01Z",
    )

    assert len(events) == 1
    served = events[0]
    assert served["relation"] == "SERVED_BY_MODEL"
    assert served["source"]["id"] == "agent:Claude Code"
    assert served["target"]["name"] == "claude-haiku-4-5-20251001"
    assert served["attributes"]["model_observation"] == "assistant.message.model"
    assert served["attributes"]["evidence_source"] == "provider_transcript"
    assert served["attributes"]["switch_initiator"] == "unknown"
    assert secret not in sidecar.read_text(encoding="utf-8")

    lifecycle = provider_lifecycle_annotation(served)
    assert lifecycle is not None
    assert lifecycle.kind == "model"
    assert lifecycle.stage == "served"


def test_same_served_model_is_deduplicated_across_repeated_hooks(tmp_path: Path) -> None:
    transcript = tmp_path / "transcript.jsonl"
    sidecar = tmp_path / "semantic.jsonl"
    _append(
        transcript,
        _assistant(
            "claude-haiku-4-5-20251001",
            timestamp="2026-08-27T01:00:00Z",
            message_id="msg-a",
        ),
    )
    payload = _hook_payload(transcript)

    first = append_claude_transcript_model_events(
        payload,
        sidecar=sidecar,
        timestamp="2026-08-27T01:00:01Z",
    )
    second = append_claude_transcript_model_events(
        payload,
        sidecar=sidecar,
        timestamp="2026-08-27T01:00:02Z",
    )

    assert len(first) == 1
    assert second == []
    assert [record["relation"] for record in _read_jsonl(sidecar)] == ["SERVED_BY_MODEL"]
    assert not sidecar.with_name(sidecar.name + ".model-observer.lock").exists()


def test_actual_served_model_transition_emits_served_and_switch_edges(tmp_path: Path) -> None:
    transcript = tmp_path / "transcript.jsonl"
    sidecar = tmp_path / "semantic.jsonl"
    payload = _hook_payload(transcript)
    _append(
        transcript,
        _assistant(
            "claude-haiku-4-5-20251001",
            timestamp="2026-08-27T01:00:00Z",
            message_id="msg-a",
        ),
    )
    append_claude_transcript_model_events(
        payload,
        sidecar=sidecar,
        timestamp="2026-08-27T01:00:01Z",
    )
    _append(
        transcript,
        _assistant(
            "claude-opus-5",
            timestamp="2026-08-27T01:02:00Z",
            message_id="msg-b",
        ),
    )

    events = append_claude_transcript_model_events(
        payload,
        sidecar=sidecar,
        timestamp="2026-08-27T01:02:01Z",
    )

    assert [event["relation"] for event in events] == [
        "SERVED_BY_MODEL",
        "SWITCHED_MODEL",
    ]
    served, transition = events
    assert served["target"]["name"] == "claude-opus-5"
    assert served["attributes"]["previous_served_model"] == "claude-haiku-4-5-20251001"
    assert transition["source"]["name"] == "claude-haiku-4-5-20251001"
    assert transition["target"]["name"] == "claude-opus-5"
    assert transition["attributes"]["transition_basis"] == (
        "consecutive_served_model_observations"
    )
    assert transition["attributes"]["switch_initiator"] == "unknown"

    lifecycle = provider_lifecycle_annotation(transition)
    assert lifecycle is not None
    assert lifecycle.kind == "model"
    assert lifecycle.stage == "runtime_transition"


def test_model_picker_confirmation_does_not_count_as_runtime_switch(tmp_path: Path) -> None:
    transcript = tmp_path / "transcript.jsonl"
    sidecar = tmp_path / "semantic.jsonl"
    payload = _hook_payload(transcript)
    _append(
        transcript,
        _assistant(
            "claude-haiku-4-5-20251001",
            timestamp="2026-08-27T01:00:00Z",
            message_id="msg-a",
        ),
    )
    append_claude_transcript_model_events(
        payload,
        sidecar=sidecar,
        timestamp="2026-08-27T01:00:01Z",
    )
    _append(transcript, _local_model_command("claude-opus-5", "2026-08-27T01:01:00Z"))

    events = append_claude_transcript_model_events(
        payload,
        sidecar=sidecar,
        timestamp="2026-08-27T01:01:01Z",
    )

    assert events == []
    serialized = sidecar.read_text(encoding="utf-8")
    assert "claude-opus-5" not in serialized
    assert "Set model to" not in serialized


def test_stop_message_mismatch_fails_closed_for_model_observation(tmp_path: Path) -> None:
    transcript = tmp_path / "transcript.jsonl"
    sidecar = tmp_path / "semantic.jsonl"
    _append(
        transcript,
        _assistant(
            "claude-opus-5",
            timestamp="2026-08-27T01:00:00Z",
            message_id="msg-stale",
            text="stale transcript text",
        ),
    )
    payload = {**_hook_payload(transcript), "last_assistant_message": "current stop text"}

    events = append_claude_transcript_model_events(
        payload,
        sidecar=sidecar,
        timestamp="2026-08-27T01:05:00Z",
    )

    assert events == []
    assert not sidecar.exists()


def test_matching_stop_message_strengthens_model_observation_validation(tmp_path: Path) -> None:
    transcript = tmp_path / "transcript.jsonl"
    sidecar = tmp_path / "semantic.jsonl"
    text = "current stop text"
    _append(
        transcript,
        _assistant(
            "claude-opus-5",
            timestamp="2026-08-27T01:00:00Z",
            message_id="msg-current",
            text=text,
        ),
    )
    payload = {**_hook_payload(transcript), "last_assistant_message": text}

    events = append_claude_transcript_model_events(
        payload,
        sidecar=sidecar,
        timestamp="2026-08-27T01:00:01Z",
    )

    assert len(events) == 1
    assert events[0]["attributes"]["model_observation_validation"] == (
        "stop.last_assistant_message_match"
    )
    assert events[0]["timestamp"] == "2026-08-27T01:00:01Z"
    assert events[0]["attributes"]["claude_transcript_timestamp"] == (
        "2026-08-27T01:00:00Z"
    )


def test_subagent_and_synthetic_models_do_not_pollute_main_agent_model(tmp_path: Path) -> None:
    transcript = tmp_path / "transcript.jsonl"
    sidecar = tmp_path / "semantic.jsonl"
    payload = _hook_payload(transcript)
    _append(
        transcript,
        _assistant(
            "claude-sonnet-5",
            timestamp="2026-08-27T01:00:00Z",
            message_id="msg-main",
        ),
    )
    append_claude_transcript_model_events(
        payload,
        sidecar=sidecar,
        timestamp="2026-08-27T01:00:01Z",
    )
    _append(
        transcript,
        _assistant(
            "claude-opus-5",
            timestamp="2026-08-27T01:00:02Z",
            message_id="msg-sub",
            sidechain=True,
        ),
    )
    _append(
        transcript,
        _assistant(
            "<synthetic>",
            timestamp="2026-08-27T01:00:03Z",
            message_id="msg-synthetic",
        ),
    )

    events = append_claude_transcript_model_events(
        payload,
        sidecar=sidecar,
        timestamp="2026-08-27T01:00:04Z",
    )

    assert events == []
    serialized = sidecar.read_text(encoding="utf-8")
    assert "claude-opus-5" not in serialized
    assert "<synthetic>" not in serialized


def test_subagent_hook_payload_never_observes_main_transcript_model(tmp_path: Path) -> None:
    transcript = tmp_path / "transcript.jsonl"
    sidecar = tmp_path / "semantic.jsonl"
    _append(
        transcript,
        _assistant(
            "claude-opus-5",
            timestamp="2026-08-27T01:00:00Z",
            message_id="msg-main",
        ),
    )
    payload = {**_hook_payload(transcript), "agent_id": "agent-1", "agent_type": "Explore"}

    events = append_claude_transcript_model_events(
        payload,
        sidecar=sidecar,
        timestamp="2026-08-27T01:00:01Z",
    )

    assert events == []
    assert not sidecar.exists()


def test_non_response_hook_does_not_replay_historical_model_on_prompt_submit(tmp_path: Path) -> None:
    transcript = tmp_path / "transcript.jsonl"
    sidecar = tmp_path / "semantic.jsonl"
    _append(
        transcript,
        _assistant(
            "claude-opus-5",
            timestamp="2026-08-27T01:00:00Z",
            message_id="msg-old",
        ),
    )

    events = append_claude_transcript_model_events(
        _hook_payload(transcript, "UserPromptSubmit"),
        sidecar=sidecar,
        timestamp="2026-08-27T01:05:00Z",
    )

    assert events == []
    assert not sidecar.exists()


def test_claude_hook_cli_appends_served_model_from_stop_transcript(
    monkeypatch,
    tmp_path: Path,
) -> None:
    transcript = tmp_path / "transcript.jsonl"
    sidecar = tmp_path / "semantic.jsonl"
    text = "final answer"
    _append(
        transcript,
        _assistant(
            "claude-opus-5",
            timestamp="2026-08-27T01:00:00Z",
            message_id="msg-cli",
            text=text,
        ),
    )
    payload = {**_hook_payload(transcript), "last_assistant_message": text}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))

    assert claude_hook_main(["--sidecar", str(sidecar)]) == 0

    records = _read_jsonl(sidecar)
    served = [record for record in records if record.get("relation") == "SERVED_BY_MODEL"]
    assert len(served) == 1
    assert served[0]["target"]["name"] == "claude-opus-5"
