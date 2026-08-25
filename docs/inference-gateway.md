# Inference Gateway Integrations

<p align="center">
  <strong>English</strong> |
  <a href="inference-gateway.zh-TW.md">繁體中文</a> |
  <a href="inference-gateway.zh-CN.md">简体中文</a> |
  <a href="inference-gateway.ja.md">日本語</a> |
  <a href="inference-gateway.ko.md">한국어</a>
</p>

Inference gateways are a separate layer between an Agent/client and the model provider/runtime. The current baseline supports **OpenRouter** and **LiteLLM Proxy**.

ExecWeave preserves requested model, resolved model, routed provider, and deployment identity as distinct evidence instead of collapsing them into one model field.

## CLI

Convert one final OpenRouter response:

```bash
execweave-inference-gateway event \
  --gateway openrouter \
  --requested-model openrouter/auto \
  --provider-name OpenAI \
  --sidecar gateway.jsonl
```

Convert one final LiteLLM Proxy response:

```bash
execweave-inference-gateway event \
  --gateway litellm \
  --requested-model assistant \
  --resolved-model azure/gpt-5 \
  --provider-name Azure \
  --deployment-id deployment-west \
  --sidecar gateway.jsonl
```

Convert OpenRouter generation metadata:

```bash
execweave-inference-gateway generation \
  --gateway openrouter \
  --sidecar gateway.jsonl
```

JSON is read from stdin. Default endpoint identities are:

- OpenRouter: `https://openrouter.ai/api/v1`
- LiteLLM Proxy: `http://localhost:4000`

## Graph model

```text
inference_gateway --SERVED_INFERENCE--> inference_request
inference_request --REQUESTED_MODEL--> model
inference_request --ROUTED_TO_MODEL--> model
inference_request --ROUTED_TO_PROVIDER--> inference_provider
inference_request --ROUTED_TO_DEPLOYMENT--> inference_deployment
inference_gateway --REPORTED_GENERATION_METADATA--> inference_request
```

For example, a LiteLLM request can preserve:

```text
requested_model = assistant
resolved_model  = azure/gpt-5
provider        = Azure
deployment      = deployment-west
```

These are not interchangeable facts.

## OpenRouter

OpenRouter response metadata keeps the requested model separate from the response model and an explicitly observed routed provider. OpenRouter-specific generation metadata can additionally report latency, generation time, cost, native token counts, streaming state, and cancellation state.

## LiteLLM Proxy

LiteLLM is modeled as an `inference_gateway`, not a `model_runtime`. Its OpenAI-compatible response contributes request/model usage metadata through the same gateway evidence layer.

`--provider-name` and `--deployment-id` are only emitted when authoritative routing metadata is available to the caller or adapter. ExecWeave does **not** infer a provider or deployment from a model string such as `azure/...`. When those routing facts are unavailable, the corresponding edges are omitted.

## Usage metadata

The response parser whitelists metadata such as prompt/input tokens, completion/output tokens, total tokens, cached prompt tokens, cache-write tokens, reasoning-token counts, and reported cost.

## Privacy boundary

ExecWeave does not persist prompt text, response/completion content, reasoning text, choices, or arbitrary provider payload fields. Gateway endpoint credentials, query parameters, and fragments are stripped from stored endpoint identity.

The original requested model is never guessed from the response; it must be supplied explicitly by the caller when that evidence is available.

## Evidence boundary

Gateway response metadata proves only what that gateway reported or what authoritative routing metadata was supplied alongside the response. It does not prove which local Agent initiated the request, which model-runtime process served it, or which OS process caused it.

Gateway events therefore remain non-causal (`causal: false`) and separate from Agent/IDE semantic evidence, Model Runtime evidence, and OS Runtime evidence. Cross-layer attribution requires explicit shared identity or a separately defined conservative correlation mechanism; inferred correlation must never be represented as causal evidence.
