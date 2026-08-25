# Model Runtime Integrations

<p align="center">
  <a href="model-runtime.md">English</a> |
  <strong>繁體中文</strong> |
  <a href="model-runtime.zh-CN.md">简体中文</a> |
  <a href="model-runtime.ja.md">日本語</a> |
  <a href="model-runtime.ko.md">한국어</a>
</p>

Model Runtime 與 Agent/IDE semantic adapter 是不同層。Ollama、llama.cpp、vLLM 等 server 負責執行 inference，不應被當成 Tool 或 Agent。

目前 baseline 支援 **Ollama** 與 **llama.cpp**。

## CLI

把 final response metadata 轉成 inference events：

```bash
execweave-model-runtime event --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime llamacpp --sidecar model-runtime.jsonl
```

取得 runtime state snapshot：

```bash
execweave-model-runtime probe --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime probe --runtime llamacpp --metrics --sidecar model-runtime.jsonl
```

預設 endpoint：Ollama 為 `http://localhost:11434`，llama.cpp 為 `http://localhost:8080`。

## Graph model

Runtime layer 可以產生：

```text
model_runtime --SERVED_INFERENCE--> inference_request
inference_request --USED_MODEL--> model
model_runtime --LOADED_MODEL--> model
model_runtime --SERVES_MODEL--> model
model_runtime --REPORTED_METRICS--> model_runtime_snapshot
```

## Ollama

Final response metadata 可提供 prompt/completion token counts、load duration、prompt-evaluation duration、generation duration 與 finish reason。

`/api/ps` snapshot 可提供 loaded model 的 VRAM size、context length、format、family、parameter size、quantization 等 metadata。

## llama.cpp

OpenAI-compatible response 可提供 usage 與 timing/throughput metadata。`/v1/models` 描述 served models；若 server 開啟 `/metrics`，可加入 aggregate runtime metrics。

目前 baseline 會跳過含 Prometheus labels 的 metrics，因為 label 可能帶有敏感的本機 model path 或其他 identifiers。

若 llama.cpp model ID 看起來是本機 path 或 GGUF filename，ExecWeave 會 redaction：完整 native identifier 只用於 hash-based entity identity，Graph 顯示僅保留 basename。

## 隱私邊界

此 layer 預設排除 prompt text、response content、thinking/reasoning text、choices、logprobs 與 raw generated tokens。

Aggregate runtime metrics 也不會自動歸因到特定 Agent 或 inference request。

## Evidence boundary

Runtime API 能證明的是 inference server 自己回報的資訊，不能單獨證明是哪個 Agent 發起 request。跨層 request identity 必須有明確 shared identifier，或另外定義的保守 correlation 機制。