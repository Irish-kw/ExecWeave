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

Model runtime 與 Agent/IDE semantic adapter、inference gateway 是不同 evidence layer。它描述 local/self-hosted inference integration point 明確回報的內容；不能證明是哪個 Agent 發起 request。

目前 baseline 支援 **Ollama**、**llama.cpp**、**vLLM**、**LM Studio**。

## CLI

從 stdin 擷取單一 supplied final runtime response：

```bash
execweave-model-runtime event --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime llamacpp --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime vllm --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime lmstudio --sidecar model-runtime.jsonl
```

擷取 caller-supplied request+response exchange：

```bash
execweave-model-runtime exchange --runtime ollama --sidecar model-runtime.jsonl
```

`exchange` 支援相同四種 runtime，且 stdin 必須具有 JSON-object `request` 與 `response` 欄位。這記錄的是明確 caller-supplied evidence，不是 transparent network interception。

Runtime state/model catalog 仍可透過 `probe` 取得。預設 localhost endpoint 仍為 Ollama `11434`、llama.cpp `8080`、vLLM `8000`、LM Studio `1234`。

## Full-fidelity content

v0.6.5 會把 selected model-runtime integration point 明確曝露的完整 content 存入本機 SHA-256 content-addressed store。`event` 保存完整 supplied final response，但不宣稱 request visibility；`exchange` 可保存 supplied request 與 response，包括 messages/prompts、tool definitions/calls/results、generated assistant content、明確存在的 reasoning/thinking fields、request-generation configuration，以及 runtime payload 支援的 provider response values。

Semantic JSONL sidecar 只保存 content reference，不 inline 大型值。Compact usage/timing/model metadata 仍可供 graph/query 使用。

`content_complete_from_source: true` 表示 ExecWeave 完整保存送進 CLI/integration point 的值；**不代表** runtime 曝露 hidden model state、request 一定就是 provider post-rewrite 的 final wire request，或 ExecWeave intercept 了未提供的 bytes。

Request/response content 內的 application-level secret value 會被保存。Endpoint/path sanitization 與 provider-metadata filtering 不構成通用 content redaction。

## Runtime-specific evidence

Ollama 可透過 `/api/ps` 額外回報 loaded-model state。llama.cpp 可曝露 timing/throughput、`/v1/models` 與 optional aggregate `/metrics`；可能攜帶敏感 local identifier 的 labeled Prometheus lines 仍受 metadata adapter 限制。vLLM 與 LM Studio 共用 OpenAI-compatible response/model-catalog parsing，同時保留 runtime-specific relation semantics。

Catalog relations 刻意區分：依 source endpoint 實際證明的內容，runtime 可能 `LOADED_MODEL`、`SERVES_MODEL` 或 `ADVERTISES_MODEL`。LM Studio catalog visibility 仍是 `ADVERTISES_MODEL`；catalog item 不會自動變成 resident weights 的證明。

## Privacy 與 evidence boundary

Model-runtime content 可能包含完整 prompt/message、tool data、generated response、reasoning/thinking text、model parameter、configuration value、path、identifier 與 application-level secrets。整個 run directory 都應視為敏感資料，分享前請檢查。

Runtime response 或 exchange 只證明該 integration point 提供了什麼；不能單獨證明哪個 Agent 發起 request、哪個 gateway 路由、哪個 OS process 造成它，或 file bytes 流向 model/network endpoint。Cross-layer identity 需要 explicit shared identifier，或另外明確標示的 conservative correlation。
