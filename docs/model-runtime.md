# Model Runtime Integrations

<!-- i18n-nav:start -->
<p align="center">
  <strong>English</strong> |
  <a href="model-runtime.zh-TW.md">繁體中文</a> |
  <a href="model-runtime.zh-CN.md">简体中文</a> |
  <a href="model-runtime.ja.md">日本語</a> |
  <a href="model-runtime.ko.md">한국어</a> |
  <a href="model-runtime.fr.md">Français</a> |
  <a href="model-runtime.de.md">Deutsch</a> |
  <a href="model-runtime.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

Model runtimes are separate from Agent/IDE semantic adapters and inference gateways. They describe what a local or self-hosted inference integration point reports; they do not prove which Agent initiated a request.

Current baseline supports **Ollama**, **llama.cpp**, **vLLM**, and **LM Studio**.

## CLI

Capture one supplied final runtime response from stdin:

```bash
execweave-model-runtime event --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime llamacpp --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime vllm --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime lmstudio --sidecar model-runtime.jsonl
```

Capture a caller-supplied request+response exchange:

```bash
execweave-model-runtime exchange --runtime ollama --sidecar model-runtime.jsonl
```

The `exchange` command accepts the same four runtime choices and requires JSON-object `request` and `response` fields. It records explicit caller-supplied evidence; it is not transparent network interception.

Runtime state/model catalogs remain available through `probe`. Default endpoints remain Ollama `11434`, llama.cpp `8080`, vLLM `8000`, and LM Studio `1234` on localhost.

## Full-fidelity content

v0.6.5 stores complete content exposed by the selected model-runtime integration point in a local SHA-256 content-addressed store. `event` preserves the complete supplied final response without claiming request visibility. `exchange` can preserve both the supplied request and response, including messages/prompts, tool definitions/calls/results, generated assistant content, reasoning/thinking fields when explicitly present, request-generation configuration, and provider response values supported by the runtime payload.

The semantic JSONL sidecar contains content references rather than large inline copies. Compact usage/timing/model metadata remains available for graph/query use.

`content_complete_from_source: true` means ExecWeave stored the complete value supplied to the CLI/integration point. It does **not** mean the runtime exposed hidden model state, that the request is necessarily the provider's final post-rewrite wire request, or that ExecWeave intercepted bytes it was not given.

Application-level secret values inside request/response content are preserved. Endpoint/path sanitization and provider-metadata filtering do not constitute general content redaction.

## Runtime-specific evidence

Ollama can additionally report loaded-model state through `/api/ps`. llama.cpp can expose timing/throughput, `/v1/models`, and optional aggregate `/metrics`; labeled Prometheus lines that may carry sensitive local identifiers remain restricted by the metadata adapter. vLLM and LM Studio share OpenAI-compatible response/model-catalog parsing while retaining runtime-specific relation semantics.

Catalog relations remain deliberately distinct: a runtime may `LOADED_MODEL`, `SERVES_MODEL`, or `ADVERTISES_MODEL` depending on what the source endpoint actually proves. LM Studio catalog visibility remains `ADVERTISES_MODEL`; a catalog item is not automatically proof of resident weights.

## Privacy and evidence boundary

Model-runtime content can contain complete prompts/messages, tool data, generated responses, reasoning/thinking text, model parameters, configuration values, paths, identifiers, and application-level secrets. Treat the entire run directory as sensitive and review it before sharing.

A runtime response or exchange proves only what that integration point supplied. It does not by itself prove which Agent initiated the request, which gateway routed it, which OS process caused it, or that file bytes flowed to a model/network endpoint. Cross-layer identity requires explicit shared identifiers or separately marked conservative correlation.
