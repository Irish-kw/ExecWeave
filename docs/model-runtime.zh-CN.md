# Model Runtime Integrations

<!-- i18n-nav:start -->
<p align="center">
  <a href="model-runtime.md">English</a> |
  <a href="model-runtime.zh-TW.md">繁體中文</a> |
  <strong>简体中文</strong> |
  <a href="model-runtime.ja.md">日本語</a> |
  <a href="model-runtime.ko.md">한국어</a> |
  <a href="model-runtime.fr.md">Français</a> |
  <a href="model-runtime.de.md">Deutsch</a> |
  <a href="model-runtime.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

Model Runtime 与 Agent/IDE semantic adapter、Inference Gateway 属于不同层。它描述 local 或 self-hosted inference server 自己报告的信息，不能单独证明是哪个 Agent 发起 request。

当前 baseline 支持 **Ollama**、**llama.cpp**、**vLLM** 与 **LM Studio**。

## CLI

将 final response metadata 转成 inference events：

```bash
execweave-model-runtime event --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime llamacpp --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime vllm --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime lmstudio --sidecar model-runtime.jsonl
```

获取 runtime state 或 model catalog：

```bash
execweave-model-runtime probe --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime probe --runtime llamacpp --metrics --sidecar model-runtime.jsonl
execweave-model-runtime probe --runtime vllm --sidecar model-runtime.jsonl
execweave-model-runtime probe --runtime lmstudio --sidecar model-runtime.jsonl
```

默认 endpoint：

- Ollama：`http://localhost:11434`
- llama.cpp：`http://localhost:8080`
- vLLM：`http://localhost:8000`
- LM Studio：`http://localhost:1234`

## OpenAI-compatible 共用层

llama.cpp、vLLM、LM Studio 共用同一个 OpenAI-compatible parser，处理 final response usage 与 `/v1/models` catalog metadata。共用层会统一 Chat Completions 的 `prompt_tokens` / `completion_tokens` 与 Responses 的 `input_tokens` / `output_tokens`，只保留白名单 token metadata，例如 cached-token 与 reasoning-token counts。

Runtime-specific evidence 不会被强行放入共用 parser。llama.cpp 仍保留自己的 timing fields 与 Prometheus metrics adapter。

## Graph model

```text
model_runtime --SERVED_INFERENCE--> inference_request
inference_request --USED_MODEL--> model
model_runtime --LOADED_MODEL--> model
model_runtime --SERVES_MODEL--> model
model_runtime --ADVERTISES_MODEL--> model
model_runtime --REPORTED_METRICS--> model_runtime_snapshot
```

这些 relation 的 evidence semantics 不相同。

## Ollama

Final response metadata 可包含 prompt/completion token counts、load duration、prompt-evaluation duration、generation duration 与 finish reason。

`/api/ps` snapshot 可提供当前 loaded model 的 VRAM size、context length、format、family、parameter size、quantization 等 metadata，因此使用 `LOADED_MODEL`。

## llama.cpp

OpenAI-compatible response 提供 normalized usage，加上 llama.cpp 专属 timing/throughput metadata。`/v1/models` 使用 `SERVES_MODEL`；可选 `/metrics` 提供 aggregate runtime metrics。

包含 Prometheus labels 的 metrics 会跳过，避免 labels 泄漏敏感本机 model path 或 identifiers。若 model ID 看起来是本机 path 或 GGUF filename，完整 identifier 只用于 hash-based entity identity，Graph 显示只保留安全名称。

## vLLM

vLLM 复用 OpenAI-compatible response 与 model-catalog 共用层。`/v1/models` 使用 `SERVES_MODEL`，表示该 serving endpoint 对外提供的 model。

不保存 prompt、response、reasoning text、choices、logprobs 或 generated token text。

## LM Studio

<!-- lmstudio-auto-live-v064 -->
若要让 LM Studio 自动进入 Live Viewer，请由 ExecWeave 使用明确的本地 port 启动，例如 `execweave live --open -- lms server start --port 1234`。ExecWeave 会先确认 launch 前该 endpoint 尚未提供兼容 API，并且只有 launcher 成功结束后才 probe `/v1/models`。生成的 relation 仍为 `ADVERTISES_MODEL`；catalog entry 不会被提升为 `LOADED_MODEL`。

LM Studio 复用相同 OpenAI-compatible response parser，但 `/v1/models` 使用 `ADVERTISES_MODEL`，而不是 `LOADED_MODEL`。

这个区分是刻意的：LM Studio 可以让已下载 model 出现在 server catalog，并且某些设置可以 on-demand load；因此 catalog entry 本身不能证明 observation 当下 model weights 已 resident in memory。

## 隐私边界

该 layer 排除 prompt text、response content、thinking/reasoning text、choices、logprobs 与 raw generated tokens。

白名单 metadata 可包含 model/request identity、prompt/input token counts、completion/output token counts、total tokens、cached-token counts、reasoning-token counts 与 runtime-specific timing metadata。支持的本机 OpenAI-compatible runtime 会 redaction absolute local model path；llama.cpp GGUF path 使用更严格 redaction。

Aggregate runtime metrics 不会自动归因到特定 Agent 或 inference request。

## Evidence boundary

Runtime API 只能证明 inference server 自己报告的信息，不能单独证明是哪个 Agent 发起 request、哪个 gateway routing，或哪个 OS process 造成 request。

跨层 identity 必须有明确 shared identifier，或另外定义的保守 correlation。Derived correlation 必须保持 inference 标记，不能改写为 causal evidence。