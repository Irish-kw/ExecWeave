# Model Runtime Integrations

<!-- i18n-nav:start -->
<p align="center">
  <a href="model-runtime.md">English</a> |
  <strong>繁體中文</strong> |
  <a href="model-runtime.zh-CN.md">简体中文</a> |
  <a href="model-runtime.ja.md">日本語</a> |
  <a href="model-runtime.ko.md">한국어</a> |
  <a href="model-runtime.fr.md">Français</a> |
  <a href="model-runtime.de.md">Deutsch</a> |
  <a href="model-runtime.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

Model Runtime 與 Agent/IDE semantic adapter、Inference Gateway 是不同層。它描述 local 或 self-hosted inference server 自己回報的資訊，不能單獨證明是哪個 Agent 發起 request。

目前 baseline 支援 **Ollama**、**llama.cpp**、**vLLM** 與 **LM Studio**。

## CLI

把 final response metadata 轉成 inference events：

```bash
execweave-model-runtime event --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime llamacpp --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime vllm --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime lmstudio --sidecar model-runtime.jsonl
```

取得 runtime state 或 model catalog：

```bash
execweave-model-runtime probe --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime probe --runtime llamacpp --metrics --sidecar model-runtime.jsonl
execweave-model-runtime probe --runtime vllm --sidecar model-runtime.jsonl
execweave-model-runtime probe --runtime lmstudio --sidecar model-runtime.jsonl
```

預設 endpoint：

- Ollama：`http://localhost:11434`
- llama.cpp：`http://localhost:8080`
- vLLM：`http://localhost:8000`
- LM Studio：`http://localhost:1234`

## OpenAI-compatible 共用層

llama.cpp、vLLM、LM Studio 共用同一個 OpenAI-compatible parser，處理 final response usage 與 `/v1/models` catalog metadata。共用層會統一 Chat Completions 的 `prompt_tokens` / `completion_tokens` 與 Responses 的 `input_tokens` / `output_tokens`，只保留白名單 token metadata，例如 cached-token 與 reasoning-token counts。

Runtime-specific evidence 不會硬塞進共用 parser。llama.cpp 仍保留自己的 timing fields 與 Prometheus metrics adapter。

## Graph model

```text
model_runtime --SERVED_INFERENCE--> inference_request
inference_request --USED_MODEL--> model
model_runtime --LOADED_MODEL--> model
model_runtime --SERVES_MODEL--> model
model_runtime --ADVERTISES_MODEL--> model
model_runtime --REPORTED_METRICS--> model_runtime_snapshot
```

這些 relation 的 evidence semantics 不相同。

## Ollama

Final response metadata 可包含 prompt/completion token counts、load duration、prompt-evaluation duration、generation duration 與 finish reason。

`/api/ps` snapshot 可提供目前 loaded model 的 VRAM size、context length、format、family、parameter size、quantization 等 metadata，因此使用 `LOADED_MODEL`。

## llama.cpp

OpenAI-compatible response 提供 normalized usage，加上 llama.cpp 專屬 timing/throughput metadata。`/v1/models` 使用 `SERVES_MODEL`；可選的 `/metrics` 提供 aggregate runtime metrics。

含 Prometheus labels 的 metrics 會跳過，避免 labels 洩漏敏感本機 model path 或 identifiers。若 model ID 看起來是本機 path 或 GGUF filename，完整 identifier 只用於 hash-based entity identity，Graph 顯示只保留安全名稱。

## vLLM

vLLM 重用 OpenAI-compatible response 與 model-catalog 共用層。`/v1/models` 使用 `SERVES_MODEL`，表示該 serving endpoint 對外提供的 model。

不保存 prompt、response、reasoning text、choices、logprobs 或 generated token text。

## LM Studio

<!-- lmstudio-auto-live-v064 -->
若要讓 LM Studio 自動進入 Live Viewer，請由 ExecWeave 以明確的本機 port 啟動，例如 `execweave live --open -- lms server start --port 1234`。ExecWeave 會先確認 launch 前該 endpoint 尚未提供相容 API，且只有 launcher 成功結束後才 probe `/v1/models`。產生的 relation 仍是 `ADVERTISES_MODEL`；catalog entry 不會被提升成 `LOADED_MODEL`。

LM Studio 重用相同 OpenAI-compatible response parser，但 `/v1/models` 使用 `ADVERTISES_MODEL`，而不是 `LOADED_MODEL`。

這個區分是刻意的：LM Studio 可以讓已下載 model 出現在 server catalog，且某些設定可以 on-demand load；因此 catalog entry 本身不能證明 observation 當下 model weights 已 resident in memory。

## 隱私邊界

此 layer 排除 prompt text、response content、thinking/reasoning text、choices、logprobs 與 raw generated tokens。

白名單 metadata 可包含 model/request identity、prompt/input token counts、completion/output token counts、total tokens、cached-token counts、reasoning-token counts 與 runtime-specific timing metadata。支援的本機 OpenAI-compatible runtime 會 redaction absolute local model path；llama.cpp GGUF path 採更嚴格 redaction。

Aggregate runtime metrics 不會自動歸因到特定 Agent 或 inference request。

## Evidence boundary

Runtime API 只能證明 inference server 自己回報的資訊，不能單獨證明是哪個 Agent 發起 request、哪個 gateway routing，或哪個 OS process 造成 request。

跨層 identity 必須有明確 shared identifier，或另外定義的保守 correlation。Derived correlation 必須維持 inference 標記，不能改寫成 causal evidence。