# Model Runtime Integrations

<p align="center">
  <strong>English</strong> |
  <a href="model-runtime.zh-TW.md">繁體中文</a> |
  <a href="model-runtime.zh-CN.md">简体中文</a> |
  <a href="model-runtime.ja.md">日本語</a> |
  <a href="model-runtime.ko.md">한국어</a>
</p>

Model runtimes are separate from Agent/IDE semantic adapters and inference gateways. They describe what a local or self-hosted inference server reports; they do not prove which Agent initiated a request.

Current baseline supports **Ollama**, **llama.cpp**, **vLLM**, and **LM Studio**.

## CLI

Convert final response metadata into inference events:

```bash
execweave-model-runtime event --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime llamacpp --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime vllm --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime lmstudio --sidecar model-runtime.jsonl
```

Probe runtime state or model catalogs:

```bash
execweave-model-runtime probe --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime probe --runtime llamacpp --metrics --sidecar model-runtime.jsonl
execweave-model-runtime probe --runtime vllm --sidecar model-runtime.jsonl
execweave-model-runtime probe --runtime lmstudio --sidecar model-runtime.jsonl
```

Default endpoints are:

- Ollama: `http://localhost:11434`
- llama.cpp: `http://localhost:8080`
- vLLM: `http://localhost:8000`
- LM Studio: `http://localhost:1234`

## OpenAI-compatible shared layer

llama.cpp, vLLM, and LM Studio reuse one OpenAI-compatible parser for final response usage and `/v1/models` catalog metadata. The shared layer normalizes Chat Completions-style `prompt_tokens` / `completion_tokens` and Responses-style `input_tokens` / `output_tokens`, while retaining only whitelisted token metadata such as cached-token and reasoning-token counts.

Runtime-specific evidence stays outside the common parser. llama.cpp still owns its timing fields and Prometheus metrics adapter instead of forcing those semantics onto vLLM or LM Studio.

## Graph model

The runtime layer can produce:

```text
model_runtime --SERVED_INFERENCE--> inference_request
inference_request --USED_MODEL--> model
model_runtime --LOADED_MODEL--> model
model_runtime --SERVES_MODEL--> model
model_runtime --ADVERTISES_MODEL--> model
model_runtime --REPORTED_METRICS--> model_runtime_snapshot
```

These relations intentionally have different meanings.

## Ollama

Final response metadata can include prompt/completion token counts, load duration, prompt-evaluation duration, generation duration, and finish reason.

`/api/ps` snapshots can expose loaded-model metadata such as VRAM size, context length, format, family, parameter size, and quantization. This is represented as `LOADED_MODEL` because the endpoint reports currently loaded models.

## llama.cpp

OpenAI-compatible responses contribute normalized usage plus llama.cpp timing/throughput metadata. `/v1/models` is represented as `SERVES_MODEL`, and optional `/metrics` contributes aggregate runtime metrics.

Prometheus lines with labels are skipped because labels can contain sensitive local model paths or other identifiers.

llama.cpp model IDs that look like local paths or GGUF filenames are redacted: the full native identifier is hashed for entity identity while only the basename is shown.

## vLLM

vLLM reuses the OpenAI-compatible response and model-catalog layer. `/v1/models` is represented as `SERVES_MODEL` because it describes models exposed by that serving endpoint.

No prompt, response, reasoning text, choices, logprobs, or generated token text is copied into ExecWeave events.

## LM Studio

LM Studio reuses the same OpenAI-compatible response parser, but its `/v1/models` result is represented as `ADVERTISES_MODEL`, not `LOADED_MODEL`.

This distinction is deliberate: LM Studio can make downloaded models visible to the server, including configurations where a model may be loaded on demand. A catalog entry therefore does not by itself prove that model weights were resident in memory at observation time.

## Privacy boundary

ExecWeave intentionally excludes prompt text, response content, thinking/reasoning text, choices, logprobs, and raw generated tokens from this layer.

Whitelisted metadata can include model identity, request identity, prompt/input token counts, completion/output token counts, total tokens, cached-token counts, reasoning-token counts, and runtime-specific timing metadata. Absolute local model paths are redacted for supported OpenAI-compatible local runtimes; llama.cpp retains stricter GGUF-path redaction.

Aggregate runtime metrics are not automatically attributed to a specific Agent or inference request.

## Evidence boundary

A runtime API proves only what that inference server reported. It does not by itself prove which Agent initiated the request, which gateway routed it, or which OS process caused the request.

Cross-layer identity requires explicit shared identifiers or a separately defined conservative correlation mechanism. Derived correlation must remain marked as inference rather than causal evidence.
