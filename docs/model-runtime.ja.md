# Model Runtime Integrations

<!-- i18n-nav:start -->
<p align="center">
  <a href="model-runtime.md">English</a> |
  <a href="model-runtime.zh-TW.md">繁體中文</a> |
  <a href="model-runtime.zh-CN.md">简体中文</a> |
  <strong>日本語</strong> |
  <a href="model-runtime.ko.md">한국어</a> |
  <a href="model-runtime.fr.md">Français</a> |
  <a href="model-runtime.de.md">Deutsch</a> |
  <a href="model-runtime.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

Model runtime は Agent/IDE semantic adapter や inference gateway とは別の evidence layer です。Local/self-hosted inference integration point が報告した内容を示しますが、どの Agent が request を開始したかは証明しません。

現在の baseline は **Ollama**、**llama.cpp**、**vLLM**、**LM Studio** をサポートします。

## CLI

stdin から一つの supplied final runtime response を取得します。

```bash
execweave-model-runtime event --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime llamacpp --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime vllm --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime lmstudio --sidecar model-runtime.jsonl
```

Caller-supplied request+response exchange を取得します。

```bash
execweave-model-runtime exchange --runtime ollama --sidecar model-runtime.jsonl
```

`exchange` は同じ4 runtime をサポートし、stdin に JSON-object `request` と `response` を要求します。これは caller-supplied evidence を明示的に記録するもので transparent network interception ではありません。

Runtime state/model catalog は `probe` から利用できます。Default localhost endpoints は Ollama `11434`、llama.cpp `8080`、vLLM `8000`、LM Studio `1234` です。

## Full-fidelity content

v0.6.5 は selected model-runtime integration point が公開する完全な content をローカル SHA-256 content-addressed store に保存します。`event` は完全な supplied final response を保存しますが request visibility は主張しません。`exchange` は supplied request と response の両方を保存でき、messages/prompts、tool definitions/calls/results、generated assistant content、明示的な reasoning/thinking fields、request-generation configuration、runtime payload が対応する provider response values を含められます。

Semantic JSONL sidecar は大きな inline copy ではなく content reference を保持します。Compact usage/timing/model metadata は graph/query 用に残ります。

`content_complete_from_source: true` は CLI/integration point に渡された完全な値を保存したことを意味します。Runtime が hidden model state を公開した、request が provider の final post-rewrite wire request である、または ExecWeave が与えられていない bytes を intercept したという意味ではありません。

Request/response content 内の application-level secret values は保存されます。Endpoint/path sanitization と provider-metadata filtering は汎用 content redaction ではありません。

## Runtime-specific evidence

Ollama は `/api/ps` から loaded-model state を追加で報告できます。llama.cpp は timing/throughput、`/v1/models`、optional aggregate `/metrics` を公開できます。Sensitive local identifier を含み得る labeled Prometheus lines は metadata adapter により制限されます。vLLM と LM Studio は OpenAI-compatible response/model-catalog parsing を共有しつつ runtime-specific relation semantics を保持します。

Catalog relation は意図的に区別されます。Source endpoint が実際に証明する内容に応じて runtime は `LOADED_MODEL`、`SERVES_MODEL`、`ADVERTISES_MODEL` を持ちます。LM Studio catalog visibility は `ADVERTISES_MODEL` のままで、catalog item は resident weights の証明ではありません。

## Privacy と evidence boundary

Model-runtime content には完全な prompts/messages、tool data、generated responses、reasoning/thinking text、model parameters、configuration values、paths、identifiers、application-level secrets が含まれる可能性があります。Run directory 全体を sensitive として扱い、共有前に確認してください。

Runtime response/exchange は integration point が提供した内容だけを証明します。どの Agent が request を開始したか、どの gateway が route したか、どの OS process が caused したか、file bytes が model/network endpoint に流れたかは単独では証明しません。Cross-layer identity には explicit shared identifier または明示的にマークされた conservative correlation が必要です。
