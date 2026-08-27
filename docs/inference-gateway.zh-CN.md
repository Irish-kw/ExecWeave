# Inference Gateway Integrations

<!-- i18n-nav:start -->
<p align="center">
  <a href="inference-gateway.md">English</a> |
  <a href="inference-gateway.zh-TW.md">繁體中文</a> |
  <strong>简体中文</strong> |
  <a href="inference-gateway.ja.md">日本語</a> |
  <a href="inference-gateway.ko.md">한국어</a> |
  <a href="inference-gateway.fr.md">Français</a> |
  <a href="inference-gateway.de.md">Deutsch</a> |
  <a href="inference-gateway.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

Inference gateway 是 Agent/client 与 model provider/runtime 之间的独立 evidence layer。ExecWeave 当前支持 **OpenRouter** 和 **LiteLLM Proxy**，并把 requested model、resolved model、routed provider 与 deployment identity 分开保存。

## CLI

从 stdin 捕获单个 final gateway response：

```bash
execweave-inference-gateway event --gateway openrouter --sidecar gateway.jsonl
execweave-inference-gateway event --gateway litellm --sidecar gateway.jsonl
```

OpenRouter 还可以捕获 caller-supplied request+response object：

```bash
execweave-inference-gateway exchange --gateway openrouter --sidecar gateway.jsonl
```

`exchange` 要求 stdin 具有 JSON-object `request` 与 `response` 字段。这是明确的 caller-supplied evidence，**不是** transparent wire interception。

OpenRouter generation metadata 仍可通过 `generation` 使用。

## OpenRouter full-fidelity boundary

对于 `event --gateway openrouter`，v0.6.5 会把完整 supplied final response 存入本地 content-addressed store，同时保留 compact routing/usage summary。对于 `exchange --gateway openrouter`，则可以保存完整 caller-supplied request 和 response。

`content_complete_from_source: true` 只表示完整保存了送入该 integration point 的值；不代表能看到 provider-side rewrite 之前的 request、hidden routing stage、model internals，或 ExecWeave 没有 intercept 的 network bytes。

Supplied request/response content 中的 application-level secrets 会被保留。Endpoint identity 会单独 sanitize，但移除 query parameter/fragment 或识别 transport credential 并不等于 content redaction。

## LiteLLM boundary

LiteLLM 在当前 v0.6.5 baseline 仍是 metadata-oriented integration。Response parser 和 optional custom callback 通过 strict contract 保存 routing/usage fields；不能因为 OpenRouter 支持 content storage，就把 LiteLLM callback 说成 full-fidelity。

打印 callback configuration，并把 configured proxy 启动在当前 ExecWeave run 内：

```bash
execweave-litellm-callback --print-config
execweave live --open -- litellm --config config.yaml
```

如果没有 `EXECWEAVE_SEMANTIC_SIDECAR`，callback 会 no-op。Provider/deployment identity 只有在 authoritative evidence 可用时才会建立；ExecWeave 不会根据 model-name prefix 或 provider URL 猜测。

## Exact gateway ↔ model-runtime identity

如果 caller 已持有明确 shared request identifier，`execweave-inference-link` 可以连接 gateway 与 runtime request nodes，而不合并两个 evidence layers。Raw shared identifier 不会保存；link 使用 SHA-256-derived identity hash。

```text
identity_exact: true
inferred: false
causal: false
```

这表示 exact logical request identity，不代表某个 Agent 或 OS process 对 inference 的 causal attribution。

## Privacy 与 evidence boundary

OpenRouter full-fidelity artifact 可能包含完整 request/response content 与 embedded application secrets；LiteLLM artifact 则遵循更窄的 metadata/callback contract。Gateway evidence 应视为敏感数据，分享前请检查。

Gateway observation 只证明 integration point 报告了什么，或旁边提供了哪些 authoritative routing data。它不能单独证明哪个 local Agent 发起 request、哪个 model-runtime process 提供服务，或哪个 OS process 造成 inference。缺少 shared identity 时，不得改用 timestamp/model-name guessing 补上关联。
