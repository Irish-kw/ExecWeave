# Inference Gateway Integrations

<!-- i18n-nav:start -->
<p align="center">
  <strong>English</strong> |
  <a href="inference-gateway.zh-TW.md">繁體中文</a> |
  <a href="inference-gateway.zh-CN.md">简体中文</a> |
  <a href="inference-gateway.ja.md">日本語</a> |
  <a href="inference-gateway.ko.md">한국어</a> |
  <a href="inference-gateway.fr.md">Français</a> |
  <a href="inference-gateway.de.md">Deutsch</a> |
  <a href="inference-gateway.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

Inference gateways are a separate evidence layer between an Agent/client and a model provider/runtime. ExecWeave currently models **OpenRouter** and **LiteLLM Proxy** while keeping requested model, resolved model, routed provider, and deployment identity distinct.

## CLI

Capture one final gateway response from stdin:

```bash
execweave-inference-gateway event --gateway openrouter --sidecar gateway.jsonl
execweave-inference-gateway event --gateway litellm --sidecar gateway.jsonl
```

For OpenRouter only, capture a caller-supplied request+response object:

```bash
execweave-inference-gateway exchange --gateway openrouter --sidecar gateway.jsonl
```

`exchange` requires JSON-object `request` and `response` fields on stdin. This is explicit caller-supplied evidence; it is **not** transparent wire interception.

OpenRouter generation metadata remains available through `generation`.

## OpenRouter full-fidelity boundary

For `event --gateway openrouter`, v0.6.5 stores the complete supplied final response in the local content-addressed store while also emitting the compact routing/usage summary. For `exchange --gateway openrouter`, it can preserve the complete caller-supplied request and response values.

`content_complete_from_source: true` means the complete value supplied to this integration point was stored. It does not claim visibility into a request before provider-side rewriting, hidden routing stages, model internals, or network bytes ExecWeave did not intercept.

Application-level secrets inside supplied request/response content are preserved. Endpoint identity is sanitized separately; query parameters/fragments and recognized transport credentials are not a substitute for content redaction.

## LiteLLM boundary

LiteLLM remains a metadata-oriented integration in the current v0.6.5 baseline. The response parser and optional custom callback preserve routing/usage fields through a strict contract; the callback does not become full-fidelity merely because OpenRouter supports content storage.

The callback is enabled by printing its configuration and launching the configured proxy inside the current ExecWeave run:

```bash
execweave-litellm-callback --print-config
execweave live --open -- litellm --config config.yaml
```

When `EXECWEAVE_SEMANTIC_SIDECAR` is absent, the callback is a no-op. Provider/deployment identity is emitted only when authoritative evidence is available; ExecWeave does not infer it from a model-name prefix or provider URL.

## Exact gateway ↔ model-runtime identity

When the caller already has an explicit shared request identifier, `execweave-inference-link` can connect gateway and runtime request nodes without collapsing the layers. The raw shared identifier is not persisted; the link uses a SHA-256-derived identity hash.

```text
identity_exact: true
inferred: false
causal: false
```

This is exact logical request identity, not proof that a particular Agent or OS process caused the inference.

## Privacy and evidence boundary

OpenRouter full-fidelity artifacts can contain complete request/response content and embedded application secrets. LiteLLM artifacts follow their narrower metadata/callback contract. Treat gateway evidence as sensitive and review it before sharing.

Gateway observations prove only what the gateway integration point reported or what authoritative routing data was supplied alongside it. They do not by themselves prove which local Agent initiated a request, which model-runtime process served it, or which OS process caused it. Missing shared identity must not be replaced with timestamp/model-name guessing.
