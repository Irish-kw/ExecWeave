from __future__ import annotations

import hashlib
import json
import subprocess
import sys

import pytest

from execweave.inference_identity import gateway_runtime_identity_event


def test_gateway_runtime_identity_is_exact_noncausal_and_hashes_shared_id() -> None:
    shared = "PRIVATE_SHARED_REQUEST_ID"
    record = gateway_runtime_identity_event(
        gateway="litellm",
        gateway_request_id="gw-123",
        runtime="vllm",
        runtime_request_id="rt-456",
        shared_request_id=shared,
        timestamp="2026-08-25T12:00:00Z",
    )

    assert record["relation"] == "SAME_INFERENCE_REQUEST"
    assert record["source"]["id"] == "inference-request:litellm:gw-123"
    assert record["target"]["id"] == "inference-request:vllm:rt-456"
    attrs = record["attributes"]
    assert attrs["causal"] is False
    assert attrs["inferred"] is False
    assert attrs["identity_exact"] is True
    assert attrs["identity_method"] == "shared_request_id"
    assert attrs["shared_request_id_hash"] == hashlib.sha256(shared.encode()).hexdigest()[:32]
    assert shared not in json.dumps(record)


def test_gateway_runtime_identity_requires_explicit_shared_id() -> None:
    with pytest.raises(ValueError, match="shared_request_id"):
        gateway_runtime_identity_event(
            gateway="litellm",
            gateway_request_id="gw-123",
            runtime="vllm",
            runtime_request_id="rt-456",
            shared_request_id="",
        )


def test_inference_link_cli_writes_exact_identity_sidecar(tmp_path) -> None:
    sidecar = tmp_path / "identity.jsonl"
    shared = "PRIVATE_CLI_SHARED_REQUEST_ID"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "execweave.inference_identity_cli",
            "--gateway",
            "litellm",
            "--gateway-request-id",
            "gw-cli-1",
            "--runtime",
            "vllm",
            "--runtime-request-id",
            "rt-cli-1",
            "--shared-request-id",
            shared,
            "--sidecar",
            str(sidecar),
        ],
        check=True,
        text=True,
        capture_output=True,
    )

    text = sidecar.read_text(encoding="utf-8")
    assert shared not in text
    records = [json.loads(line) for line in text.splitlines() if line.strip()]
    assert len(records) == 1
    record = records[0]
    assert record["relation"] == "SAME_INFERENCE_REQUEST"
    assert record["attributes"]["causal"] is False
    assert record["attributes"]["inferred"] is False
    assert record["attributes"]["identity_exact"] is True
