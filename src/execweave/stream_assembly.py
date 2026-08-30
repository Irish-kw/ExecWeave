"""Reassemble streamed inference responses into one canonical response.

A streamed response arrives as many partial frames. The canonical record must look
like the non-streaming response for the same exchange, because everything
downstream — conversation materialization, tool-call evidence, usage — reads that
one object. Handing it a single frame loses the body: in an OpenAI-style stream the
final frame carries an empty delta, so the assistant text never reaches the record
even though the raw frames were archived.

Assemblers are keyed by **wire format**, not by provider. ``openai_chat_delta`` is a
format shared by many upstreams, and ``ollama_ndjson`` is another. A new provider
speaking an existing format reuses its assembler and adds nothing here, which is why
this lives in its own module rather than inside a provider adapter or inside the
common conversation layer.

The assembler reports what it observed and never repairs what it did not see. A
stream that stopped without a terminator, or that carried a frame this code could not
parse, is reported as ``capture_interrupted`` with counts, not silently completed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .evidence_availability import AVAILABLE, CAPTURE_INTERRUPTED

OPENAI_CHAT_DELTA = "openai_chat_delta"
OLLAMA_NDJSON = "ollama_ndjson"

WIRE_FORMATS = (OPENAI_CHAT_DELTA, OLLAMA_NDJSON)

_REASONING_DELTA_KEYS = ("reasoning_content", "reasoning", "thinking")


@dataclass(frozen=True)
class AssembledStream:
    """One canonical response rebuilt from streamed frames, plus what was observed."""

    response: dict[str, Any]
    wire_format: str
    chunk_count: int
    malformed_chunks: int
    terminated: bool
    availability: str
    notes: str | None = None

    def attributes(self) -> dict[str, Any]:
        """Observation facts to attach to emitted events."""
        return {
            "stream_assembled": True,
            "stream_wire_format": self.wire_format,
            "stream_chunk_count": self.chunk_count,
            "stream_malformed_chunks": self.malformed_chunks,
            "stream_terminated": self.terminated,
            "response_availability": self.availability,
        }


@dataclass
class _ToolCallAccumulator:
    """One tool call rebuilt across frames.

    Both the name and the JSON argument string may arrive split across frames, so
    each is concatenated rather than overwritten. Arguments stay a string because
    that is what the non-streaming response carries; parsing here would make the
    streamed record a different shape from its non-streamed twin.
    """

    index: int
    call_id: str | None = None
    call_type: str | None = None
    name_parts: list[str] = field(default_factory=list)
    argument_parts: list[str] = field(default_factory=list)

    def absorb(self, payload: dict[str, Any]) -> None:
        identifier = payload.get("id")
        if isinstance(identifier, str) and identifier and self.call_id is None:
            self.call_id = identifier
        call_type = payload.get("type")
        if isinstance(call_type, str) and call_type and self.call_type is None:
            self.call_type = call_type
        function = payload.get("function")
        if not isinstance(function, dict):
            return
        name = function.get("name")
        if isinstance(name, str) and name:
            self.name_parts.append(name)
        arguments = function.get("arguments")
        if isinstance(arguments, str) and arguments:
            self.argument_parts.append(arguments)

    def to_dict(self) -> dict[str, Any]:
        call: dict[str, Any] = {
            "index": self.index,
            "type": self.call_type or "function",
            "function": {
                "name": "".join(self.name_parts),
                "arguments": "".join(self.argument_parts),
            },
        }
        if self.call_id is not None:
            call["id"] = self.call_id
        return call


@dataclass
class _ChoiceAccumulator:
    index: int
    role: str | None = None
    content_parts: list[str] = field(default_factory=list)
    reasoning_parts: list[str] = field(default_factory=list)
    finish_reason: Any = None
    tool_calls: dict[int, _ToolCallAccumulator] = field(default_factory=dict)
    saw_content: bool = False
    saw_reasoning: bool = False

    def absorb_delta(self, delta: dict[str, Any]) -> None:
        role = delta.get("role")
        if isinstance(role, str) and role and self.role is None:
            self.role = role

        content = delta.get("content")
        if isinstance(content, str):
            self.content_parts.append(content)
            self.saw_content = True
        elif isinstance(content, list):
            # Some upstreams stream structured content parts instead of plain text.
            for part in content:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    self.content_parts.append(part["text"])
                    self.saw_content = True

        for key in _REASONING_DELTA_KEYS:
            value = delta.get(key)
            if isinstance(value, str):
                self.reasoning_parts.append(value)
                self.saw_reasoning = True

        calls = delta.get("tool_calls")
        if isinstance(calls, list):
            for position, call in enumerate(calls):
                if not isinstance(call, dict):
                    continue
                raw_index = call.get("index")
                index = raw_index if isinstance(raw_index, int) else position
                self.tool_calls.setdefault(index, _ToolCallAccumulator(index=index)).absorb(call)

    def to_dict(self) -> dict[str, Any]:
        message: dict[str, Any] = {"role": self.role or "assistant"}
        message["content"] = "".join(self.content_parts) if self.saw_content else None
        if self.saw_reasoning:
            message["reasoning_content"] = "".join(self.reasoning_parts)
        if self.tool_calls:
            message["tool_calls"] = [
                self.tool_calls[index].to_dict() for index in sorted(self.tool_calls)
            ]
        return {
            "index": self.index,
            "message": message,
            "finish_reason": self.finish_reason,
        }


def _split_frames(chunks: list[Any]) -> tuple[list[dict[str, Any]], int]:
    """Separate parseable frames from ones the relay could not decode."""
    frames: list[dict[str, Any]] = []
    malformed = 0
    for chunk in chunks:
        if isinstance(chunk, dict):
            frames.append(chunk)
        else:
            malformed += 1
    return frames, malformed


def _availability(*, terminated: bool, malformed: int) -> tuple[str, str | None]:
    reasons: list[str] = []
    if not terminated:
        reasons.append("stream ended without a terminating frame")
    if malformed:
        reasons.append(f"{malformed} unparseable frame(s) observed")
    if reasons:
        return CAPTURE_INTERRUPTED, "; ".join(reasons)
    return AVAILABLE, None


def assemble_openai_chat_stream(chunks: list[Any]) -> AssembledStream:
    """Rebuild an OpenAI-compatible chat completion from its delta frames."""
    frames, malformed = _split_frames(chunks)
    choices: dict[int, _ChoiceAccumulator] = {}
    envelope: dict[str, Any] = {}
    usage: Any = None
    terminated = False

    for frame in frames:
        for key in ("id", "model", "system_fingerprint", "created"):
            value = frame.get(key)
            if key not in envelope and value is not None:
                envelope[key] = value
        frame_usage = frame.get("usage")
        if isinstance(frame_usage, dict) and frame_usage:
            usage = frame_usage

        raw_choices = frame.get("choices")
        if not isinstance(raw_choices, list):
            continue
        for position, raw_choice in enumerate(raw_choices):
            if not isinstance(raw_choice, dict):
                continue
            raw_index = raw_choice.get("index")
            index = raw_index if isinstance(raw_index, int) else position
            choice = choices.setdefault(index, _ChoiceAccumulator(index=index))
            delta = raw_choice.get("delta")
            if isinstance(delta, dict):
                choice.absorb_delta(delta)
            finish_reason = raw_choice.get("finish_reason")
            if finish_reason is not None:
                choice.finish_reason = finish_reason
                terminated = True

    response: dict[str, Any] = dict(envelope)
    response["object"] = "chat.completion"
    response["choices"] = [choices[index].to_dict() for index in sorted(choices)]
    if usage is not None:
        response["usage"] = usage

    availability, notes = _availability(terminated=terminated, malformed=malformed)
    return AssembledStream(
        response=response,
        wire_format=OPENAI_CHAT_DELTA,
        chunk_count=len(chunks),
        malformed_chunks=malformed,
        terminated=terminated,
        availability=availability,
        notes=notes,
    )


def assemble_ollama_stream(chunks: list[Any]) -> AssembledStream:
    """Rebuild an Ollama chat or generate response from its ndjson frames."""
    frames, malformed = _split_frames(chunks)
    response: dict[str, Any] = {}
    message_content: list[str] = []
    message_thinking: list[str] = []
    generate_parts: list[str] = []
    tool_calls: list[Any] = []
    role: str | None = None
    saw_message = False
    saw_generate = False
    terminated = False

    for frame in frames:
        for key in ("model", "created_at"):
            value = frame.get(key)
            if key not in response and value is not None:
                response[key] = value

        message = frame.get("message")
        if isinstance(message, dict):
            saw_message = True
            frame_role = message.get("role")
            if isinstance(frame_role, str) and frame_role and role is None:
                role = frame_role
            content = message.get("content")
            if isinstance(content, str):
                message_content.append(content)
            thinking = message.get("thinking")
            if isinstance(thinking, str):
                message_thinking.append(thinking)
            calls = message.get("tool_calls")
            if isinstance(calls, list):
                # Ollama emits whole tool calls rather than argument fragments.
                tool_calls.extend(calls)

        generated = frame.get("response")
        if isinstance(generated, str):
            saw_generate = True
            generate_parts.append(generated)

        if frame.get("done") is True:
            terminated = True
            for key, value in frame.items():
                if key in {"message", "response", "model", "created_at"}:
                    continue
                response[key] = value

    if saw_message:
        message_payload: dict[str, Any] = {
            "role": role or "assistant",
            "content": "".join(message_content),
        }
        if message_thinking:
            message_payload["thinking"] = "".join(message_thinking)
        if tool_calls:
            message_payload["tool_calls"] = tool_calls
        response["message"] = message_payload
    if saw_generate:
        response["response"] = "".join(generate_parts)
    response.setdefault("done", terminated)

    availability, notes = _availability(terminated=terminated, malformed=malformed)
    return AssembledStream(
        response=response,
        wire_format=OLLAMA_NDJSON,
        chunk_count=len(chunks),
        malformed_chunks=malformed,
        terminated=terminated,
        availability=availability,
        notes=notes,
    )


def assemble_stream(chunks: list[Any], *, wire_format: str) -> AssembledStream:
    if wire_format == OPENAI_CHAT_DELTA:
        return assemble_openai_chat_stream(chunks)
    if wire_format == OLLAMA_NDJSON:
        return assemble_ollama_stream(chunks)
    raise ValueError(f"unsupported stream wire format: {wire_format}")


def assembled_tool_calls(response: dict[str, Any]) -> list[Any]:
    """Return whole tool calls from an assembled response.

    Walking raw frames instead would publish one fragment per frame, so a single
    call split across frames would surface as several partial calls.
    """

    calls: list[Any] = []
    for choice in response.get("choices") or []:
        if not isinstance(choice, dict):
            continue
        message = choice.get("message")
        if isinstance(message, dict) and isinstance(message.get("tool_calls"), list):
            calls.extend(message["tool_calls"])
    message = response.get("message")
    if isinstance(message, dict) and isinstance(message.get("tool_calls"), list):
        calls.extend(message["tool_calls"])
    return calls


def arguments_parse_cleanly(response: dict[str, Any]) -> bool:
    """Whether every assembled tool-call argument string is valid JSON.

    Reported as an observation. A stream that ended early leaves a truncated
    argument string, and that fact belongs in the record rather than being hidden.
    """

    for call in assembled_tool_calls(response):
        if not isinstance(call, dict):
            continue
        function = call.get("function")
        if not isinstance(function, dict):
            continue
        arguments = function.get("arguments")
        if not isinstance(arguments, str) or not arguments:
            continue
        try:
            json.loads(arguments)
        except json.JSONDecodeError:
            return False
    return True
