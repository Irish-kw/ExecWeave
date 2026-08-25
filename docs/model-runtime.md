# Model Runtime Integrations

<p align="center">
  <strong>English</strong> |
  <a href="model-runtime.zh-TW.md">繁體中文</a> |
  <a href="model-runtime.zh-CN.md">简体中文</a> |
  <a href="model-runtime.ja.md">日本語</a> |
  <a href="model-runtime.ko.md">한국어</a>
</p>

Model runtimes are separate from Agent/IDE semantic adapters. Ollama, llama.cpp, vLLM, and similar servers execute inference; they are not treated as Tools or Agents.

Current baseline supports **Ollama** and **llama.cpp**.

## CLI

Convert final response metadata into inference events:

```bash
execweave-model-runtime event --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime llamacpp --sidecar model-runtime.jsonl
```

Probe runtime state:

```bash
execweave-model-runtime probe --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime probe --runtime llamacpp --metrics --sidecar model-runtime.jsonl
```

Default endpoints are `http://localhost:11434` for Ollama and `http://localhost:8080` for llama.cpp.

## Graph model

The runtime layer can produce:

```text
model_runtime --SERVED_INFERENCE--> inference_request
inference_request --USED_MODEL--> model
model_runtime --LOADED_MODEL--> model
model_runtime --SERVES_MODEL--> model
model_runtime --REPORTED_METRICS--> model_runtime_snapshot
```

## Ollama

Final response metadata can include prompt/completion token counts, load duration, prompt-evaluation duration, generation duration, and finish reason.

`/api/ps` snapshots can expose loaded model metadata such as VRAM size, context length, format, family, parameter size, and quantization.

## llama.cpp

OpenAI-compatible responses can contribute usage and timing/throughput metadata. `/v1/models` describes served models and optional `/metrics` contributes aggregate runtime metrics.

Prometheus lines with labels are skipped by the baseline because labels can contain sensitive local model paths or other identifiers.

llama.cpp model IDs that look like a local path or GGUF filename are redacted: the full native identifier is hashed for entity identity while only the basename is shown.

## Privacy boundary

ExecWeave intentionally excludes prompt text, response content, thinking/reasoning text, choices, logprobs, and raw generated tokens from this layer.

Aggregate runtime metrics are not automatically attributed to a specific Agent or inference request.

## Evidence boundary

A runtime API proves what that inference server reported. It does not by itself prove which Agent initiated the request. Cross-layer request identity requires explicit shared identifiers or a separately defined conservative correlation mechanism.