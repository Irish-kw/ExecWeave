# Inference Gateway Integrations

<!-- i18n-nav:start -->
<p align="center">
  <a href="inference-gateway.md">English</a> |
  <strong>繁體中文</strong> |
  <a href="inference-gateway.zh-CN.md">简体中文</a> |
  <a href="inference-gateway.ja.md">日本語</a> |
  <a href="inference-gateway.ko.md">한국어</a> |
  <a href="inference-gateway.fr.md">Français</a> |
  <a href="inference-gateway.de.md">Deutsch</a> |
  <a href="inference-gateway.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

Inference gateway 是 Agent/client 與 model provider/runtime 之間的獨立 evidence layer。ExecWeave 目前支援 **OpenRouter** 與 **LiteLLM Proxy**，並把 requested model、resolved model、routed provider 與 deployment identity 分開保存。

## CLI

從 stdin 擷取單一 final gateway response：

```bash
execweave-inference-gateway event --gateway openrouter --sidecar gateway.jsonl
execweave-inference-gateway event --gateway litellm --sidecar gateway.jsonl
```

OpenRouter 另可擷取 caller-supplied request+response object：

```bash
execweave-inference-gateway exchange --gateway openrouter --sidecar gateway.jsonl
```

`exchange` 要求 stdin 具有 JSON-object `request` 與 `response` 欄位。這是明確的 caller-supplied evidence，**不是** transparent wire interception。

OpenRouter generation metadata 仍可透過 `generation` 使用。

## OpenRouter full-fidelity boundary

對 `event --gateway openrouter`，v0.6.5 會把完整 supplied final response 存入本機 content-addressed store，同時保留 compact routing/usage summary。對 `exchange --gateway openrouter`，則可保存完整 caller-supplied request 與 response。

`content_complete_from_source: true` 只表示完整保存了送進此 integration point 的值；不代表能看見 provider-side rewrite 前的 request、hidden routing stage、model internals，或 ExecWeave 沒有 intercept 的 network bytes。

Supplied request/response content 裡的 application-level secrets 會被保留。Endpoint identity 會另外 sanitize，但移除 query parameter/fragment 或辨識 transport credential 並不等於 content redaction。

## LiteLLM boundary

LiteLLM 在目前 v0.6.5 baseline 仍是 metadata-oriented integration。Response parser 與 optional custom callback 透過 strict contract 保存 routing/usage fields；不能因 OpenRouter 支援 content storage，就把 LiteLLM callback 說成 full-fidelity。

列印 callback configuration，並把 configured proxy 啟動在目前 ExecWeave run 內：

```bash
execweave-litellm-callback --print-config
execweave live --open -- litellm --config config.yaml
```

若沒有 `EXECWEAVE_SEMANTIC_SIDECAR`，callback 會 no-op。Provider/deployment identity 只有在 authoritative evidence 可用時才會建立；ExecWeave 不會由 model-name prefix 或 provider URL 推測。

## Exact gateway ↔ model-runtime identity

若 caller 已持有明確 shared request identifier，`execweave-inference-link` 可以連接 gateway 與 runtime request nodes，而不把兩個 evidence layers 合併。Raw shared identifier 不會保存；link 使用 SHA-256-derived identity hash。

```text
identity_exact: true
inferred: false
causal: false
```

這表示 exact logical request identity，不代表某個 Agent 或 OS process 對 inference 的 causal attribution。

## Privacy 與 evidence boundary

OpenRouter full-fidelity artifact 可能包含完整 request/response content 與 embedded application secrets；LiteLLM artifact 則遵循較窄的 metadata/callback contract。Gateway evidence 應視為敏感資料，分享前請檢查。

Gateway observation 只證明 integration point 回報了什麼，或旁邊提供了哪些 authoritative routing data。它不能單獨證明哪個 local Agent 發起 request、哪個 model-runtime process 提供服務，或哪個 OS process 造成 inference。缺少 shared identity 時，不得改用 timestamp/model-name guessing 補上關聯。
