# Inference Gateway Integrations

<!-- i18n-nav:start -->
<p align="center">
  <a href="inference-gateway.md">English</a> |
  <a href="inference-gateway.zh-TW.md">繁體中文</a> |
  <a href="inference-gateway.zh-CN.md">简体中文</a> |
  <strong>日本語</strong> |
  <a href="inference-gateway.ko.md">한국어</a> |
  <a href="inference-gateway.fr.md">Français</a> |
  <a href="inference-gateway.de.md">Deutsch</a> |
  <a href="inference-gateway.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

Inference gateway は Agent/client と model provider/runtime の間にある独立した evidence layer です。ExecWeave は現在 **OpenRouter** と **LiteLLM Proxy** をモデル化し、requested model、resolved model、routed provider、deployment identity を分離します。

## CLI

stdin から一つの final gateway response を取得します。

```bash
execweave-inference-gateway event --gateway openrouter --sidecar gateway.jsonl
execweave-inference-gateway event --gateway litellm --sidecar gateway.jsonl
```

OpenRouter のみ caller-supplied request+response object を取得できます。

```bash
execweave-inference-gateway exchange --gateway openrouter --sidecar gateway.jsonl
```

`exchange` は stdin に JSON-object `request` と `response` を要求します。これは明示的な caller-supplied evidence であり、**transparent wire interception ではありません**。

OpenRouter generation metadata は `generation` から引き続き利用できます。

## OpenRouter full-fidelity boundary

`event --gateway openrouter` では v0.6.5 が完全な supplied final response をローカル content-addressed store に保存し、compact routing/usage summary も出力します。`exchange --gateway openrouter` では完全な caller-supplied request と response を保存できます。

`content_complete_from_source: true` はこの integration point に渡された完全な値を保存したという意味です。Provider-side rewriting 前の request、hidden routing stages、model internals、ExecWeave が intercept していない network bytes を観測したという意味ではありません。

Supplied request/response content 内の application-level secrets は保存されます。Endpoint identity は別途 sanitize されますが、query parameters/fragments や認識済み transport credentials の除外は content redaction の代替ではありません。

## LiteLLM boundary

LiteLLM は現在の v0.6.5 baseline でも metadata-oriented integration のままです。Response parser と optional custom callback は strict contract で routing/usage fields を保存します。OpenRouter が content storage をサポートするからといって LiteLLM callback が full-fidelity になるわけではありません。

Callback 設定を出力し、configured proxy を現在の ExecWeave run 内で起動します。

```bash
execweave-litellm-callback --print-config
execweave live --open -- litellm --config config.yaml
```

`EXECWEAVE_SEMANTIC_SIDECAR` がなければ callback は no-op です。Provider/deployment identity は authoritative evidence がある場合のみ出力され、model-name prefix や provider URL から推測しません。

## Exact gateway ↔ model-runtime identity

Caller が明示的な shared request identifier を持つ場合、`execweave-inference-link` は layer を統合せず gateway/runtime request nodes を接続できます。Raw shared identifier は保存せず、SHA-256-derived identity hash を使用します。

```text
identity_exact: true
inferred: false
causal: false
```

これは exact logical request identity であり、特定 Agent/OS process が inference を caused した証明ではありません。

## Privacy と evidence boundary

OpenRouter full-fidelity artifact には完全な request/response content と embedded application secrets が含まれる可能性があります。LiteLLM artifact はより狭い metadata/callback contract に従います。Gateway evidence を sensitive として扱い、共有前に確認してください。

Gateway observation は integration point が報告した内容、または併記された authoritative routing data だけを証明します。どの local Agent が request を開始したか、どの model-runtime process が処理したか、どの OS process が caused したかは単独では証明しません。Shared identity がない場合、timestamp/model-name guessing で補ってはいけません。
