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

Model runtime 与 Agent/IDE semantic adapter、inference gateway 是不同 evidence layer。它描述 local/self-hosted inference integration point 明确报告的内容；不能证明是哪个 Agent 发起 request。

当前 baseline 支持 **Ollama**、**llama.cpp**、**vLLM**、**LM Studio**。

## CLI

从 stdin 捕获单个 supplied final runtime response：

```bash
execweave-model-runtime event --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime llamacpp --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime vllm --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime lmstudio --sidecar model-runtime.jsonl
```

捕获 caller-supplied request+response exchange：

```bash
execweave-model-runtime exchange --runtime ollama --sidecar model-runtime.jsonl
```

`exchange` 支持相同四种 runtime，且 stdin 必须具有 JSON-object `request` 与 `response` 字段。它记录明确 caller-supplied evidence，不是 transparent network interception。

Runtime state/model catalog 仍可通过 `probe` 获取。默认 localhost endpoint 仍为 Ollama `11434`、llama.cpp `8080`、vLLM `8000`、LM Studio `1234`。

## Full-fidelity content

v0.6.5 会把 selected model-runtime integration point 明确暴露的完整 content 存入本地 SHA-256 content-addressed store。`event` 保存完整 supplied final response，但不声明 request visibility；`exchange` 可以保存 supplied request 与 response，包括 messages/prompts、tool definitions/calls/results、generated assistant content、明确存在的 reasoning/thinking fields、request-generation configuration，以及 runtime payload 支持的 provider response values。

Semantic JSONL sidecar 只保存 content reference，不 inline 大型值。Compact usage/timing/model metadata 仍可用于 graph/query。

`content_complete_from_source: true` 表示 ExecWeave 完整保存送入 CLI/integration point 的值；**不代表** runtime 暴露 hidden model state、request 一定就是 provider post-rewrite 的 final wire request，或 ExecWeave intercept 了未提供的 bytes。

Request/response content 中的 application-level secret value 会被保存。Endpoint/path sanitization 与 provider-metadata filtering 不构成通用 content redaction。

## Runtime-specific evidence

Ollama 可通过 `/api/ps` 额外报告 loaded-model state。llama.cpp 可暴露 timing/throughput、`/v1/models` 与 optional aggregate `/metrics`；可能携带敏感 local identifier 的 labeled Prometheus lines 仍受 metadata adapter 限制。vLLM 与 LM Studio 共享 OpenAI-compatible response/model-catalog parsing，同时保留 runtime-specific relation semantics。

Catalog relations 有意区分：根据 source endpoint 实际证明的内容，runtime 可能 `LOADED_MODEL`、`SERVES_MODEL` 或 `ADVERTISES_MODEL`。LM Studio catalog visibility 仍是 `ADVERTISES_MODEL`；catalog item 不会自动成为 resident weights 的证明。

## Privacy 与 evidence boundary

Model-runtime content 可能包含完整 prompt/message、tool data、generated response、reasoning/thinking text、model parameter、configuration value、path、identifier 与 application-level secrets。整个 run directory 都应视为敏感数据，分享前请检查。

Runtime response 或 exchange 只证明该 integration point 提供了什么；不能单独证明哪个 Agent 发起 request、哪个 gateway 路由、哪个 OS process 造成它，或 file bytes 流向 model/network endpoint。Cross-layer identity 需要 explicit shared identifier，或另外明确标记的 conservative correlation。
