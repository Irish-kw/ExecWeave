from __future__ import annotations

import json
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:
        return

    def do_GET(self) -> None:
        if self.path == "/api/ps":
            body = json.dumps(
                {
                    "models": [
                        {
                            "model": "qwen3:8b",
                            "size": 100,
                            "size_vram": 80,
                            "context_length": 4096,
                            "details": {
                                "format": "gguf",
                                "family": "qwen3",
                                "parameter_size": "8B",
                                "quantization_level": "Q4_K_M",
                            },
                        }
                    ]
                }
            ).encode()
            content_type = "application/json"
        elif self.path == "/v1/models":
            body = json.dumps(
                {
                    "data": [
                        {
                            "id": "/Users/private/models/ci-secret.gguf",
                            "owned_by": "local-runtime",
                            "meta": {"n_ctx_train": 131072, "n_params": 8000000000},
                        }
                    ]
                }
            ).encode()
            content_type = "application/json"
        elif self.path == "/metrics":
            body = (
                "llamacpp:prompt_tokens_total 42\n"
                "llamacpp:predicted_tokens_seconds 50.5\n"
                "llamacpp:requests_processing{model=\"private.gguf\"} 1\n"
            ).encode()
            content_type = "text/plain"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _run(args: list[str], *, payload: dict | None = None) -> None:
    subprocess.run(
        args,
        input=json.dumps(payload) if payload is not None else None,
        text=True,
        check=True,
        capture_output=True,
    )


def _read(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _check_event_relations(path: Path, runtime: str) -> None:
    records = _read(path)
    summary_relations = {
        item["relation"]
        for item in records
        if item.get("attributes", {}).get("backend") == "model_runtime"
    }
    if summary_relations != {"SERVED_INFERENCE", "USED_MODEL"}:
        raise RuntimeError(
            f"unexpected {runtime} inference summary relations: {sorted(summary_relations)}"
        )

    content_relations = {
        item["relation"]
        for item in records
        if item.get("attributes", {}).get("backend") == "semantic"
    }
    required_content_relations = {
        "OBSERVED_INFERENCE_RESPONSE",
        "OBSERVED_PROVIDER_METADATA",
    }
    missing = required_content_relations - content_relations
    if missing:
        raise RuntimeError(
            f"missing {runtime} full-fidelity relations: {sorted(missing)}"
        )


def _check_openai_event(root: Path, runtime: str) -> None:
    output = root / f"{runtime}-event.jsonl"
    _run(
        [
            "execweave-model-runtime",
            "event",
            "--runtime",
            runtime,
            "--sidecar",
            str(output),
        ],
        payload={
            "id": f"resp-{runtime}-ci",
            "model": "/Users/private/models/ci-secret-model",
            "output": [{"content": [{"type": "output_text", "text": "PRIVATE_RESPONSE"}]}],
            "reasoning": {"summary": "PRIVATE_REASONING"},
            "usage": {
                "input_tokens": 5,
                "output_tokens": 6,
                "total_tokens": 11,
                "input_tokens_details": {"cached_tokens": 2},
                "output_tokens_details": {"reasoning_tokens": 1},
            },
        },
    )
    text = output.read_text(encoding="utf-8")
    if "/Users/private/models" in text or "PRIVATE_RESPONSE" in text or "PRIVATE_REASONING" in text:
        raise RuntimeError(f"{runtime} content/path leaked into model-runtime sidecar")
    _check_event_relations(output, runtime)


def main() -> int:
    root = Path("model-runtime-smoke")
    root.mkdir(exist_ok=True)

    ollama_event = root / "ollama-event.jsonl"
    _run(
        [
            "execweave-model-runtime",
            "event",
            "--runtime",
            "ollama",
            "--request-id",
            "ci-ollama-request",
            "--sidecar",
            str(ollama_event),
        ],
        payload={
            "model": "qwen3:8b",
            "message": {"content": "PRIVATE_OLLAMA_RESPONSE"},
            "thinking": "PRIVATE_OLLAMA_THINKING",
            "prompt_eval_count": 7,
            "eval_count": 9,
            "total_duration": 1000,
        },
    )
    ollama_text = ollama_event.read_text(encoding="utf-8")
    if "PRIVATE_OLLAMA_RESPONSE" in ollama_text or "PRIVATE_OLLAMA_THINKING" in ollama_text:
        raise RuntimeError("Ollama content leaked into model-runtime sidecar")
    _check_event_relations(ollama_event, "Ollama")

    llama_event = root / "llamacpp-event.jsonl"
    _run(
        [
            "execweave-model-runtime",
            "event",
            "--runtime",
            "llamacpp",
            "--sidecar",
            str(llama_event),
        ],
        payload={
            "id": "chatcmpl-ci",
            "model": "/Users/private/models/ci-secret.gguf",
            "choices": [{"message": {"content": "PRIVATE_LLAMA_RESPONSE"}}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7},
            "timings": {"predicted_per_second": 55.0},
        },
    )
    llama_text = llama_event.read_text(encoding="utf-8")
    if "/Users/private/models" in llama_text or "PRIVATE_LLAMA_RESPONSE" in llama_text:
        raise RuntimeError("llama.cpp content/path leaked into model-runtime sidecar")
    _check_event_relations(llama_event, "llama.cpp")

    _check_openai_event(root, "vllm")
    _check_openai_event(root, "lmstudio")

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        endpoint = f"http://127.0.0.1:{server.server_port}"
        ollama_probe = root / "ollama-probe.jsonl"
        _run(
            [
                "execweave-model-runtime",
                "probe",
                "--runtime",
                "ollama",
                "--endpoint",
                endpoint,
                "--sidecar",
                str(ollama_probe),
            ]
        )
        if _read(ollama_probe)[0]["relation"] != "LOADED_MODEL":
            raise RuntimeError("Ollama probe did not produce LOADED_MODEL")

        llama_probe = root / "llamacpp-probe.jsonl"
        _run(
            [
                "execweave-model-runtime",
                "probe",
                "--runtime",
                "llamacpp",
                "--endpoint",
                endpoint,
                "--metrics",
                "--sidecar",
                str(llama_probe),
            ]
        )
        probe_text = llama_probe.read_text(encoding="utf-8")
        if "/Users/private/models" in probe_text or "private.gguf" in probe_text:
            raise RuntimeError("llama.cpp probe leaked model/metric labels")
        relations = {item["relation"] for item in _read(llama_probe)}
        if relations != {"SERVES_MODEL", "REPORTED_METRICS"}:
            raise RuntimeError(f"unexpected llama.cpp probe relations: {sorted(relations)}")

        for runtime, expected_relation in (
            ("vllm", "SERVES_MODEL"),
            ("lmstudio", "ADVERTISES_MODEL"),
        ):
            probe = root / f"{runtime}-probe.jsonl"
            _run(
                [
                    "execweave-model-runtime",
                    "probe",
                    "--runtime",
                    runtime,
                    "--endpoint",
                    endpoint,
                    "--sidecar",
                    str(probe),
                ]
            )
            text = probe.read_text(encoding="utf-8")
            if "/Users/private/models" in text:
                raise RuntimeError(f"{runtime} probe leaked local model path")
            if _read(probe)[0]["relation"] != expected_relation:
                raise RuntimeError(f"{runtime} probe relation did not preserve runtime semantics")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    print("Model runtime CLI smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
