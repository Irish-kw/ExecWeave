from __future__ import annotations

import json
import subprocess
from pathlib import Path


def _run(args: list[str], payload: dict) -> None:
    subprocess.run(
        args,
        input=json.dumps(payload),
        text=True,
        check=True,
        capture_output=True,
    )


def _read(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _relations(path: Path, backend: str) -> set[str]:
    return {
        record["relation"]
        for record in _read(path)
        if record.get("attributes", {}).get("backend") == backend
    }


def main() -> int:
    root = Path("openai-compatible-smoke")
    root.mkdir(exist_ok=True)

    event_sidecar = root / "event.jsonl"
    _run(
        [
            "execweave-openai-compatible",
            "event",
            "--endpoint",
            "https://user:secret@api.example/v1?token=SECRET#frag",
            "--provider-name",
            "example-provider",
            "--sidecar",
            str(event_sidecar),
        ],
        {
            "id": "resp-event",
            "model": "vendor/model",
            "choices": [
                {
                    "message": {
                        "content": "PRIVATE_EVENT_RESPONSE",
                        "tool_calls": [
                            {
                                "id": "call-event",
                                "type": "function",
                                "function": {"name": "lookup", "arguments": '{"x":1}'},
                            }
                        ],
                    }
                }
            ],
        },
    )
    event_text = event_sidecar.read_text(encoding="utf-8")
    for private in ("PRIVATE_EVENT_RESPONSE", "user:secret", "token=SECRET"):
        if private in event_text:
            raise RuntimeError(f"OpenAI-compatible event leaked {private!r} into sidecar")
    if _relations(event_sidecar, "openai_compatible_api") != {
        "SERVED_INFERENCE",
        "USED_MODEL",
    }:
        raise RuntimeError("unexpected OpenAI-compatible event summary relations")
    event_semantic = _relations(event_sidecar, "semantic")
    if not {
        "OBSERVED_INFERENCE_RESPONSE",
        "OBSERVED_ASSISTANT_MESSAGES",
        "OBSERVED_ASSISTANT_TOOL_CALLS",
        "OBSERVED_PROVIDER_METADATA",
    }.issubset(event_semantic):
        raise RuntimeError("OpenAI-compatible event missing full-fidelity relations")

    exchange_sidecar = root / "exchange.jsonl"
    _run(
        [
            "execweave-openai-compatible",
            "exchange",
            "--endpoint",
            "http://user:secret@localhost:8000/v1?token=SECRET#frag",
            "--provider-name",
            "local-server",
            "--sidecar",
            str(exchange_sidecar),
        ],
        {
            "request": {
                "model": "vendor/requested-model",
                "instructions": "PRIVATE_SYSTEM_CONTEXT",
                "messages": [
                    {"role": "user", "content": "PRIVATE_PROMPT"},
                    {"role": "tool", "content": "PRIVATE_TOOL_RESULT"},
                ],
                "tools": [{"type": "function", "function": {"name": "lookup"}}],
                "temperature": 0.2,
            },
            "response": {
                "id": "resp-exchange",
                "model": "vendor/actual-model",
                "choices": [{"message": {"content": "PRIVATE_FINAL"}}],
            },
            "stream_chunks": [{"id": "chunk-1", "choices": [{"delta": {"content": "P"}}]}],
        },
    )
    exchange_text = exchange_sidecar.read_text(encoding="utf-8")
    for private in (
        "PRIVATE_SYSTEM_CONTEXT",
        "PRIVATE_PROMPT",
        "PRIVATE_TOOL_RESULT",
        "PRIVATE_FINAL",
        "user:secret",
        "token=SECRET",
    ):
        if private in exchange_text:
            raise RuntimeError(f"OpenAI-compatible exchange leaked {private!r} into sidecar")
    if _relations(exchange_sidecar, "openai_compatible_api") != {
        "SERVED_INFERENCE",
        "REQUESTED_MODEL",
        "USED_MODEL",
    }:
        raise RuntimeError("unexpected OpenAI-compatible exchange summary relations")
    exchange_semantic = _relations(exchange_sidecar, "semantic")
    if not {
        "OBSERVED_INFERENCE_REQUEST",
        "OBSERVED_INFERENCE_REQUEST_MESSAGES",
        "OBSERVED_SYSTEM_CONTEXT",
        "OBSERVED_TOOL_DEFINITIONS",
        "OBSERVED_TOOL_RESULT_MESSAGES",
        "OBSERVED_PROVIDER_REQUEST_CONFIG",
        "OBSERVED_INFERENCE_STREAM_CHUNKS",
        "OBSERVED_INFERENCE_RESPONSE",
        "OBSERVED_PROVIDER_METADATA",
    }.issubset(exchange_semantic):
        raise RuntimeError("OpenAI-compatible exchange missing full-fidelity relations")
    if not (root / "content" / "sha256").is_dir():
        raise RuntimeError("OpenAI-compatible smoke did not materialize content-addressed storage")

    print("OpenAI-compatible direct API CLI smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
