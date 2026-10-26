from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


_CALLBACK_PATH = "execweave.litellm_callback.execweave_litellm_callback"


def run_cli(args: list[str], payload: dict) -> None:
    subprocess.run(
        ["execweave-inference-gateway", *args],
        input=json.dumps(payload),
        text=True,
        check=True,
        capture_output=True,
    )


def check_litellm_callback_cli() -> None:
    config = subprocess.run(
        ["execweave-litellm-callback", "--print-config"],
        text=True,
        check=True,
        capture_output=True,
    ).stdout
    if _CALLBACK_PATH not in config or "litellm_settings:" not in config:
        raise RuntimeError("LiteLLM callback config helper returned an invalid fragment")

    callback = subprocess.run(
        ["execweave-litellm-callback", "--print-callback"],
        text=True,
        check=True,
        capture_output=True,
    ).stdout.strip()
    if callback != _CALLBACK_PATH:
        raise RuntimeError(f"unexpected LiteLLM callback path: {callback!r}")


def main() -> int:
    check_litellm_callback_cli()
    with tempfile.TemporaryDirectory() as tmp:
        sidecar = Path(tmp) / "gateway.jsonl"
        run_cli(
            [
                "event",
                "--gateway",
                "openrouter",
                "--requested-model",
                "openrouter/auto",
                "--provider-name",
                "OpenAI",
                "--sidecar",
                str(sidecar),
            ],
            {
                "id": "ci-openrouter-1",
                "model": "openai/gpt-5.6-sol",
                "choices": [{"message": {"content": "PRIVATE_RESPONSE"}}],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15,
                    "cost": 0.001,
                    "prompt_tokens_details": {"cached_tokens": 3},
                },
            },
        )
        run_cli(
            ["generation", "--gateway", "openrouter", "--sidecar", str(sidecar)],
            {
                "data": {
                    "id": "ci-openrouter-1",
                    "model": "openai/gpt-5.6-sol",
                    "provider_name": "OpenAI",
                    "latency": 0.2,
                    "total_cost": 0.001,
                    "prompt": "PRIVATE_PROMPT",
                    "completion": "PRIVATE_COMPLETION",
                }
            },
        )
        run_cli(
            [
                "event",
                "--gateway",
                "litellm",
                "--requested-model",
                "assistant",
                "--resolved-model",
                "azure/gpt-5",
                "--provider-name",
                "Azure",
                "--deployment-id",
                "deployment-west",
                "--sidecar",
                str(sidecar),
            ],
            {
                "id": "ci-litellm-1",
                "model": "proxy-alias-response",
                "output": [
                    {"content": [{"type": "output_text", "text": "PRIVATE_LITELLM_RESPONSE"}]}
                ],
                "reasoning": {"summary": "PRIVATE_LITELLM_REASONING"},
                "usage": {
                    "input_tokens": 7,
                    "output_tokens": 4,
                    "total_tokens": 11,
                    "cache_read_input_tokens": 2,
                    "output_tokens_details": {"reasoning_tokens": 1},
                },
            },
        )
        text = sidecar.read_text(encoding="utf-8")
        for secret in (
            "PRIVATE_RESPONSE",
            "PRIVATE_PROMPT",
            "PRIVATE_COMPLETION",
            "PRIVATE_LITELLM_RESPONSE",
            "PRIVATE_LITELLM_REASONING",
        ):
            if secret in text:
                raise RuntimeError(f"gateway sidecar leaked content: {secret}")
        records = [json.loads(line) for line in text.splitlines() if line.strip()]
        relations = {record["relation"] for record in records}
        expected = {
            "SERVED_INFERENCE",
            "REQUESTED_MODEL",
            "ROUTED_TO_MODEL",
            "ROUTED_TO_PROVIDER",
            "ROUTED_TO_DEPLOYMENT",
            "REPORTED_GENERATION_METADATA",
        }
        missing = expected - relations
        if missing:
            raise RuntimeError(f"gateway smoke missing relations: {sorted(missing)}")
        litellm_records = [r for r in records if r["attributes"].get("gateway") == "litellm"]
        if not litellm_records or any(
            r["attributes"].get("causal") is not False for r in litellm_records
        ):
            raise RuntimeError("LiteLLM gateway evidence must remain non-causal")
    subprocess.run(
        [sys.executable, "scripts/check_openai_compatible_cli.py"],
        check=True,
    )
    print("Inference gateway and direct API CLI smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
