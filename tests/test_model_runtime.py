from __future__ import annotations

import json
from pathlib import Path

from execweave.model_runtime import (
    append_model_runtime_records,
    llamacpp_metrics_to_events,
    llamacpp_models_to_events,
    llamacpp_response_to_events,
    lmstudio_models_to_events,
    lmstudio_response_to_events,
    ollama_ps_to_events,
    ollama_response_to_events,
    sanitize_endpoint,
    vllm_models_to_events,
    vllm_response_to_events,
)


def test_endpoint_sanitization_strips_credentials_query_and_fragment() -> None:
    assert sanitize_endpoint("http://user:secret@localhost:11434/api/?x=1#frag") == "http://localhost:11434/api"


def test_ollama_response_records_usage_without_content() -> None:
    payload = {
        "model": "qwen3:8b",
        "created_at": "2026-08-25T09:00:00Z",
        "message": {"role": "assistant", "content": "private answer", "thinking": "private thought"},
        "done": True,
        "done_reason": "stop",
        "total_duration": 1000,
        "load_duration": 100,
        "prompt_eval_count": 11,
        "prompt_eval_duration": 200,
        "eval_count": 22,
        "eval_duration": 500,
        "logprobs": [{"token": "secret-token"}],
    }
    events = ollama_response_to_events(payload, request_id="req-1")
    assert {event["relation"] for event in events} == {"SERVED_INFERENCE", "USED_MODEL"}
    rendered = json.dumps(events)
    assert "private answer" not in rendered
    assert "private thought" not in rendered
    assert "secret-token" not in rendered
    request = next(event["target"] for event in events if event["relation"] == "SERVED_INFERENCE")
    assert request["attributes"]["prompt_tokens"] == 11
    assert request["attributes"]["completion_tokens"] == 22
    assert request["attributes"]["total_duration_ns"] == 1000


def test_llamacpp_response_records_usage_and_timings_without_choices() -> None:
    payload = {
        "id": "chatcmpl-1",
        "model": "local-qwen",
        "choices": [{"message": {"content": "private answer"}}],
        "usage": {
            "prompt_tokens": 44,
            "completion_tokens": 48,
            "total_tokens": 92,
            "prompt_tokens_details": {"cached_tokens": 10},
        },
        "timings": {
            "cache_n": 10,
            "prompt_n": 34,
            "prompt_ms": 30.0,
            "prompt_per_second": 100.0,
            "predicted_n": 48,
            "predicted_ms": 900.0,
            "predicted_per_second": 53.3,
        },
    }
    events = llamacpp_response_to_events(payload)
    rendered = json.dumps(events)
    assert "private answer" not in rendered
    served = next(event for event in events if event["relation"] == "SERVED_INFERENCE")
    request = served["target"]
    endpoint_scope = served["source"]["id"].rsplit(":", 1)[-1]
    assert request["id"] == f"inference-request:llamacpp:{endpoint_scope}:chatcmpl-1"
    assert request["attributes"]["request_id_source"] == "provider_native"
    assert request["attributes"]["endpoint_scope"] == endpoint_scope
    assert request["attributes"]["total_tokens"] == 92
    assert request["attributes"]["cached_prompt_tokens"] == 10
    assert request["attributes"]["timing_predicted_per_second"] == 53.3


def test_openai_compatible_responses_usage_is_normalized_without_content() -> None:
    payload = {
        "id": "resp-1",
        "model": "org/model",
        "output": [{"content": [{"type": "output_text", "text": "private answer"}]}],
        "reasoning": {"summary": "private reasoning"},
        "usage": {
            "input_tokens": 12,
            "output_tokens": 8,
            "total_tokens": 20,
            "input_tokens_details": {"cached_tokens": 4},
            "output_tokens_details": {"reasoning_tokens": 3},
        },
    }
    for converter in (vllm_response_to_events, lmstudio_response_to_events):
        events = converter(payload)
        rendered = json.dumps(events)
        assert "private answer" not in rendered
        assert "private reasoning" not in rendered
        request = next(
            event["target"] for event in events if event["relation"] == "SERVED_INFERENCE"
        )
        assert request["attributes"]["prompt_tokens"] == 12
        assert request["attributes"]["completion_tokens"] == 8
        assert request["attributes"]["total_tokens"] == 20
        assert request["attributes"]["cached_prompt_tokens"] == 4
        assert request["attributes"]["reasoning_tokens"] == 3
        assert request["attributes"]["protocol"] == "openai_compatible"


def test_llamacpp_response_redacts_model_file_path() -> None:
    payload = {
        "id": "chatcmpl-path",
        "model": "/Users/private/models/secret-model.gguf",
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }
    events = llamacpp_response_to_events(payload)
    rendered = json.dumps(events)
    assert "/Users/private/models" not in rendered
    model = next(event["target"] for event in events if event["relation"] == "USED_MODEL")
    assert model["name"] == "secret-model.gguf"
    assert model["attributes"]["native_model_id_redacted"] is True
    assert model["id"].startswith("model:llamacpp:redacted:")


def test_openai_compatible_local_model_paths_are_redacted() -> None:
    payload = {"data": [{"id": "/Users/private/models/local-model", "owned_by": "local"}]}
    for converter in (vllm_models_to_events, lmstudio_models_to_events):
        events = converter(payload)
        rendered = json.dumps(events)
        assert "/Users/private/models" not in rendered
        assert events[0]["target"]["attributes"]["native_model_id_redacted"] is True


def test_ollama_ps_records_loaded_model_runtime_metadata() -> None:
    payload = {
        "models": [
            {
                "name": "gemma4",
                "model": "gemma4",
                "size": 6591830464,
                "digest": "abc",
                "size_vram": 5333539264,
                "context_length": 4096,
                "details": {
                    "format": "gguf",
                    "family": "gemma4",
                    "parameter_size": "8.0B",
                    "quantization_level": "Q4_K_M",
                },
            }
        ]
    }
    event = ollama_ps_to_events(payload)[0]
    assert event["relation"] == "LOADED_MODEL"
    assert event["target"]["id"] == "model:ollama:gemma4"
    assert event["attributes"]["size_vram"] == 5333539264
    assert event["attributes"]["quantization_level"] == "Q4_K_M"


def test_openai_compatible_model_catalog_preserves_runtime_semantics() -> None:
    payload = {"data": [{"id": "org/model", "owned_by": "local", "created": 123}]}
    vllm_event = vllm_models_to_events(payload)[0]
    lmstudio_event = lmstudio_models_to_events(payload)[0]
    assert vllm_event["relation"] == "SERVES_MODEL"
    assert lmstudio_event["relation"] == "ADVERTISES_MODEL"
    assert vllm_event["attributes"]["provider"] == "vllm"
    assert lmstudio_event["attributes"]["provider"] == "lmstudio"
    assert vllm_event["attributes"]["protocol"] == "openai_compatible"
    assert lmstudio_event["attributes"]["protocol"] == "openai_compatible"


def test_llamacpp_models_and_metrics_remain_runtime_scoped() -> None:
    private_model_path = "/Users/private/models/model.gguf"
    models = {
        "data": [
            {
                "id": private_model_path,
                "owned_by": "llamacpp",
                "meta": {"n_ctx_train": 131072, "n_params": 8030261312, "size": 4912898304},
            }
        ]
    }
    model_event = llamacpp_models_to_events(models)[0]
    assert model_event["relation"] == "SERVES_MODEL"
    assert model_event["target"]["name"] == "model.gguf"
    assert model_event["target"]["attributes"]["native_model_id_redacted"] is True
    assert private_model_path not in json.dumps(model_event)
    metrics = """
# HELP llamacpp:prompt_tokens_total Prompt tokens
llamacpp:prompt_tokens_total 42
llamacpp:predicted_tokens_seconds 50.5
llamacpp:requests_processing{model=\"secret-path.gguf\"} 1
other_metric 99
"""
    events = llamacpp_metrics_to_events(metrics)
    assert len(events) == 1
    snapshot = events[0]["target"]
    values = snapshot["attributes"]["metrics"]
    assert values == {
        "llamacpp:predicted_tokens_seconds": 50.5,
        "llamacpp:prompt_tokens_total": 42.0,
    }
    assert "secret-path.gguf" not in json.dumps(events)


def test_model_runtime_sidecar_io(tmp_path: Path) -> None:
    records = ollama_response_to_events(
        {
            "model": "qwen3:8b",
            "done_reason": "stop",
            "prompt_eval_count": 4,
            "eval_count": 5,
        },
        request_id="req-2",
    )
    output = append_model_runtime_records(tmp_path / "model-runtime.jsonl", records)
    lines = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert len(lines) == 2
    assert all(line["attributes"]["backend"] == "model_runtime" for line in lines)
