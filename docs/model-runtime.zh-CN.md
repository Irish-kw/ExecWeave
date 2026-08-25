# Model Runtime Integrations

<p align="center">
  <a href="model-runtime.md">English</a> |
  <a href="model-runtime.zh-TW.md">繁體中文</a> |
  <strong>简体中文</strong> |
  <a href="model-runtime.ja.md">日本語</a> |
  <a href="model-runtime.ko.md">한국어</a>
</p>

Model Runtime 与 Agent/IDE semantic adapter 属于不同层。Ollama、llama.cpp、vLLM 等 server 负责执行 inference，不应被当作 Tool 或 Agent。

当前 baseline 支持 **Ollama** 与 **llama.cpp**。

## CLI

将 final response metadata 转成 inference events：

```bash
execweave-model-runtime event --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime llamacpp --sidecar model-runtime.jsonl
```

获取 runtime state snapshot：

```bash
execweave-model-runtime probe --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime probe --runtime llamacpp --metrics --sidecar model-runtime.jsonl
```

默认 endpoint：Ollama 为 `http://localhost:11434`，llama.cpp 为 `http://localhost:8080`。

## Graph model

Runtime layer 可以产生：

```text
model_runtime --SERVED_INFERENCE--> inference_request
inference_request --USED_MODEL--> model
model_runtime --LOADED_MODEL--> model
model_runtime --SERVES_MODEL--> model
model_runtime --REPORTED_METRICS--> model_runtime_snapshot
```

## Ollama

Final response metadata 可提供 prompt/completion token counts、load duration、prompt-evaluation duration、generation duration 与 finish reason。

`/api/ps` snapshot 可提供 loaded model 的 VRAM size、context length、format、family、parameter size、quantization 等 metadata。

## llama.cpp

OpenAI-compatible response 可提供 usage 与 timing/throughput metadata。`/v1/models` 描述 served models；如果 server 开启 `/metrics`，则可加入 aggregate runtime metrics。

当前 baseline 会跳过包含 Prometheus labels 的 metrics，因为 label 可能带有敏感的本机 model path 或其他 identifiers。

若 llama.cpp model ID 看起来是本机 path 或 GGUF filename，ExecWeave 会进行 redaction：完整 native identifier 只用于 hash-based entity identity，Graph 显示仅保留 basename。

## 隐私边界

该 layer 默认排除 prompt text、response content、thinking/reasoning text、choices、logprobs 和 raw generated tokens。

Aggregate runtime metrics 也不会自动归因到特定 Agent 或 inference request。

## Evidence boundary

Runtime API 能证明的是 inference server 自己报告的信息，不能单独证明是哪个 Agent 发起 request。跨层 request identity 必须有明确 shared identifier，或另外定义的保守 correlation 机制。