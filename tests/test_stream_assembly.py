"""A streamed response must land in the record as its non-streamed twin.

The relay already parsed SSE and ndjson frames and archived them, but the canonical
response was taken as ``chunks[-1]``. In an OpenAI-style stream the final frame
carries an empty delta, so the assistant text, the reasoning and every tool call
were absent from the materialized record while surviving only as raw frames.

These tests cover the twelve reconstruction cases the 0.7.6 stage requires, and
assert canonical semantic equivalence between a streamed exchange and the
non-streamed response for the same content — not merely that something was stored.
"""

from __future__ import annotations

import json
from typing import Any

from execweave.evidence_availability import AVAILABLE, CAPTURE_INTERRUPTED
from execweave.stream_assembly import (
    OLLAMA_NDJSON,
    OPENAI_CHAT_DELTA,
    arguments_parse_cleanly,
    assemble_ollama_stream,
    assemble_openai_chat_stream,
    assemble_stream,
    assembled_tool_calls,
)


def _delta(index: int = 0, **delta: Any) -> dict[str, Any]:
    return {"choices": [{"index": index, "delta": delta, "finish_reason": None}]}


def _finish(index: int = 0, reason: str = "stop") -> dict[str, Any]:
    return {"choices": [{"index": index, "delta": {}, "finish_reason": reason}]}


def _message(assembled: Any, index: int = 0) -> dict[str, Any]:
    return assembled.response["choices"][index]["message"]


# ── case 1: text/content delta ────────────────────────────────────────────────


def test_content_deltas_accumulate_into_one_message() -> None:
    assembled = assemble_openai_chat_stream(
        [
            _delta(role="assistant", content="Hello"),
            _delta(content=", "),
            _delta(content="world"),
            _finish(),
        ]
    )
    assert _message(assembled)["content"] == "Hello, world"
    assert assembled.response["object"] == "chat.completion"
    assert assembled.availability == AVAILABLE


def test_streamed_and_non_streamed_reach_the_same_canonical_message() -> None:
    """Canonical semantic equivalence, which is the actual acceptance bar."""
    streamed = assemble_openai_chat_stream(
        [
            {"id": "cmpl-1", "model": "m", "choices": [{"index": 0, "delta": {"role": "assistant", "content": "The "}}]},
            _delta(content="answer"),
            {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}], "usage": {"total_tokens": 7}},
        ]
    )
    non_streamed = {
        "id": "cmpl-1",
        "model": "m",
        "object": "chat.completion",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "The answer"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"total_tokens": 7},
    }
    assert streamed.response == non_streamed


# ── case 2: reasoning/thinking delta ──────────────────────────────────────────


def test_reasoning_deltas_accumulate_and_stay_separate_from_content() -> None:
    assembled = assemble_openai_chat_stream(
        [
            _delta(role="assistant", reasoning_content="step one "),
            _delta(reasoning_content="step two"),
            _delta(content="final"),
            _finish(),
        ]
    )
    message = _message(assembled)
    assert message["reasoning_content"] == "step one step two"
    assert message["content"] == "final"


def test_absent_reasoning_is_not_invented() -> None:
    assembled = assemble_openai_chat_stream([_delta(content="hi"), _finish()])
    assert "reasoning_content" not in _message(assembled)


# ── case 3: fragmented tool call name ─────────────────────────────────────────


def test_tool_call_name_split_across_frames_is_rejoined() -> None:
    assembled = assemble_openai_chat_stream(
        [
            _delta(tool_calls=[{"index": 0, "id": "call_1", "type": "function",
                                "function": {"name": "read_", "arguments": ""}}]),
            _delta(tool_calls=[{"index": 0, "function": {"name": "file", "arguments": ""}}]),
            _finish(reason="tool_calls"),
        ]
    )
    calls = _message(assembled)["tool_calls"]
    assert len(calls) == 1
    assert calls[0]["function"]["name"] == "read_file"


# ── case 4: fragmented tool call arguments ────────────────────────────────────


def test_tool_arguments_split_across_frames_are_rejoined_before_recording() -> None:
    """The example from the stage spec: {"pa / th":" / foo"}."""
    assembled = assemble_openai_chat_stream(
        [
            _delta(tool_calls=[{"index": 0, "id": "call_1", "type": "function",
                                "function": {"name": "open", "arguments": '{"pa'}}]),
            _delta(tool_calls=[{"index": 0, "function": {"arguments": 'th":"'}}]),
            _delta(tool_calls=[{"index": 0, "function": {"arguments": 'foo"}'}}]),
            _finish(reason="tool_calls"),
        ]
    )
    calls = _message(assembled)["tool_calls"]
    assert len(calls) == 1, "a call split across frames must not become several calls"
    arguments = calls[0]["function"]["arguments"]
    assert arguments == '{"path":"foo"}'
    assert json.loads(arguments) == {"path": "foo"}
    assert arguments_parse_cleanly(assembled.response) is True


# ── case 5: multiple parallel tool calls ──────────────────────────────────────


def test_parallel_tool_calls_are_kept_apart_by_index() -> None:
    assembled = assemble_openai_chat_stream(
        [
            _delta(tool_calls=[
                {"index": 0, "id": "a", "function": {"name": "alpha", "arguments": '{"x'}},
                {"index": 1, "id": "b", "function": {"name": "beta", "arguments": '{"y'}},
            ]),
            _delta(tool_calls=[{"index": 1, "function": {"arguments": '":2}'}}]),
            _delta(tool_calls=[{"index": 0, "function": {"arguments": '":1}'}}]),
            _finish(reason="tool_calls"),
        ]
    )
    calls = _message(assembled)["tool_calls"]
    assert [call["function"]["name"] for call in calls] == ["alpha", "beta"]
    assert [call["function"]["arguments"] for call in calls] == ['{"x":1}', '{"y":2}']
    assert [call["id"] for call in calls] == ["a", "b"]


# ── case 6: finish reason ─────────────────────────────────────────────────────


def test_finish_reason_is_carried_onto_the_choice() -> None:
    assembled = assemble_openai_chat_stream([_delta(content="x"), _finish(reason="length")])
    assert assembled.response["choices"][0]["finish_reason"] == "length"
    assert assembled.terminated is True


# ── case 7: usage-only final chunk ────────────────────────────────────────────


def test_usage_only_final_frame_is_captured() -> None:
    assembled = assemble_openai_chat_stream(
        [
            _delta(role="assistant", content="hi"),
            _finish(),
            {"choices": [], "usage": {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7}},
        ]
    )
    assert assembled.response["usage"]["total_tokens"] == 7
    assert _message(assembled)["content"] == "hi"


# ── case 8: multi-choice responses ────────────────────────────────────────────


def test_multiple_choices_accumulate_independently() -> None:
    assembled = assemble_openai_chat_stream(
        [
            _delta(index=0, role="assistant", content="first"),
            _delta(index=1, role="assistant", content="second"),
            _delta(index=1, content=" choice"),
            _finish(index=0),
            _finish(index=1),
        ]
    )
    choices = assembled.response["choices"]
    assert [choice["index"] for choice in choices] == [0, 1]
    assert choices[0]["message"]["content"] == "first"
    assert choices[1]["message"]["content"] == "second choice"


# ── case 9: UTF-8 boundary split ──────────────────────────────────────────────


def test_multibyte_characters_split_across_frames_rejoin_intact() -> None:
    assembled = assemble_openai_chat_stream(
        [
            _delta(role="assistant", content="路徑"),
            _delta(content="："),
            _delta(content="完成 \U0001f600"),
            _finish(),
        ]
    )
    assert _message(assembled)["content"] == "路徑：完成 \U0001f600"


def test_utf8_multibyte_survives_sse_frame_parsing() -> None:
    """Guard the decode path the relay uses, not only the assembler."""
    from execweave.http_proxy import _stream_items

    payload = "\n".join(
        f"data: {json.dumps(_delta(content=piece), ensure_ascii=False)}"
        for piece in ("測試", "\U0001f600")
    ).encode("utf-8")
    chunks = _stream_items(payload, "text/event-stream", {"stream": True})
    assembled = assemble_openai_chat_stream(chunks + [_finish()])
    assert _message(assembled)["content"] == "測試\U0001f600"


# ── case 10: malformed chunk ──────────────────────────────────────────────────


def test_malformed_frames_are_counted_not_silently_dropped() -> None:
    assembled = assemble_openai_chat_stream(
        [_delta(role="assistant", content="ok"), "this is not json", _finish()]
    )
    assert _message(assembled)["content"] == "ok"
    assert assembled.malformed_chunks == 1
    assert assembled.availability == CAPTURE_INTERRUPTED
    assert "unparseable" in (assembled.notes or "")


# ── case 11: incomplete stream ────────────────────────────────────────────────


def test_stream_without_a_terminator_is_reported_as_interrupted() -> None:
    assembled = assemble_openai_chat_stream([_delta(role="assistant", content="partial")])
    assert _message(assembled)["content"] == "partial"
    assert assembled.terminated is False
    assert assembled.availability == CAPTURE_INTERRUPTED
    assert "without a terminating frame" in (assembled.notes or "")


def test_truncated_tool_arguments_are_not_claimed_to_parse() -> None:
    assembled = assemble_openai_chat_stream(
        [_delta(tool_calls=[{"index": 0, "id": "a", "function": {"name": "f", "arguments": '{"pa'}}])]
    )
    assert assembled.availability == CAPTURE_INTERRUPTED
    assert arguments_parse_cleanly(assembled.response) is False


# ── case 12: connection interruption ──────────────────────────────────────────


def test_connection_interruption_keeps_partial_content_and_marks_it() -> None:
    """A cut connection leaves whole frames plus one severed frame."""
    assembled = assemble_openai_chat_stream(
        [
            _delta(role="assistant", content="before the cut"),
            '{"choices":[{"index":0,"delta":{"content":"aft',
        ]
    )
    assert _message(assembled)["content"] == "before the cut"
    assert assembled.terminated is False
    assert assembled.malformed_chunks == 1
    assert assembled.availability == CAPTURE_INTERRUPTED


def test_empty_stream_is_interrupted_rather_than_a_confident_empty_answer() -> None:
    assembled = assemble_openai_chat_stream([])
    assert assembled.response["choices"] == []
    assert assembled.availability == CAPTURE_INTERRUPTED


# ── ollama ndjson ─────────────────────────────────────────────────────────────


def test_ollama_chat_frames_accumulate_into_one_message() -> None:
    assembled = assemble_ollama_stream(
        [
            {"model": "llama3", "message": {"role": "assistant", "content": "Hel"}, "done": False},
            {"message": {"content": "lo"}, "done": False},
            {"message": {"content": ""}, "done": True, "eval_count": 12},
        ]
    )
    assert assembled.response["message"]["content"] == "Hello"
    assert assembled.response["model"] == "llama3"
    assert assembled.response["eval_count"] == 12
    assert assembled.availability == AVAILABLE


def test_ollama_generate_frames_accumulate_into_response_text() -> None:
    assembled = assemble_ollama_stream(
        [
            {"model": "llama3", "response": "par", "done": False},
            {"response": "tial", "done": False},
            {"response": "", "done": True, "total_duration": 5},
        ]
    )
    assert assembled.response["response"] == "partial"
    assert assembled.response["total_duration"] == 5


def test_ollama_thinking_is_kept_apart_from_content() -> None:
    assembled = assemble_ollama_stream(
        [
            {"message": {"role": "assistant", "thinking": "weigh ", "content": ""}, "done": False},
            {"message": {"thinking": "options", "content": "answer"}, "done": False},
            {"message": {"content": ""}, "done": True},
        ]
    )
    message = assembled.response["message"]
    assert message["thinking"] == "weigh options"
    assert message["content"] == "answer"


def test_ollama_stream_without_done_is_interrupted() -> None:
    assembled = assemble_ollama_stream([{"message": {"content": "half"}, "done": False}])
    assert assembled.availability == CAPTURE_INTERRUPTED
    assert assembled.response["done"] is False


# ── dispatch and provenance ───────────────────────────────────────────────────


def test_dispatch_selects_the_wire_format_not_the_provider() -> None:
    frames = [_delta(role="assistant", content="x"), _finish()]
    assert assemble_stream(frames, wire_format=OPENAI_CHAT_DELTA).wire_format == OPENAI_CHAT_DELTA
    ollama = assemble_stream([{"message": {"content": "x"}, "done": True}], wire_format=OLLAMA_NDJSON)
    assert ollama.wire_format == OLLAMA_NDJSON


def test_unknown_wire_format_is_rejected_rather_than_guessed() -> None:
    try:
        assemble_stream([], wire_format="mystery")
    except ValueError as exc:
        assert "mystery" in str(exc)
    else:  # pragma: no cover - the call must raise
        raise AssertionError("an unknown wire format must not be silently assembled")


def test_assembly_attributes_record_what_was_observed() -> None:
    assembled = assemble_openai_chat_stream([_delta(content="x"), "bad", _finish()])
    attributes = assembled.attributes()
    assert attributes["stream_assembled"] is True
    assert attributes["stream_wire_format"] == OPENAI_CHAT_DELTA
    assert attributes["stream_chunk_count"] == 3
    assert attributes["stream_malformed_chunks"] == 1
    assert attributes["stream_terminated"] is True
    assert attributes["response_availability"] == CAPTURE_INTERRUPTED


def test_assembled_tool_calls_never_returns_fragments() -> None:
    assembled = assemble_openai_chat_stream(
        [
            _delta(tool_calls=[{"index": 0, "id": "a", "function": {"name": "f", "arguments": '{"a'}}]),
            _delta(tool_calls=[{"index": 0, "function": {"arguments": '":1}'}}]),
            _finish(reason="tool_calls"),
        ]
    )
    calls = assembled_tool_calls(assembled.response)
    assert len(calls) == 1
    assert calls[0]["function"]["arguments"] == '{"a":1}'
