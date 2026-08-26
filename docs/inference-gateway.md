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

When a caller has an explicit shared request identity across a gateway observation and a model-runtime observation, link the two existing request nodes:

```bash
execweave-inference-link \
  --gateway litellm \
  --gateway-request-id gw-123 \
  --runtime vllm \
  --runtime-request-id rt-456 \
  --shared-request-id trace-789 \
  --sidecar inference.jsonl
```

Gateway response JSON is read from stdin. Default endpoint identities are:

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
inference_request --SAME_INFERENCE_REQUEST--> inference_request
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

<!-- litellm-auto-live-v064 -->
### Automatic Live Viewer callback

LiteLLM Proxy can load ExecWeave as a custom callback once and then feed routing/usage metadata into the current `execweave live` sidecar automatically. Print the configuration fragment with:

```bash
execweave-litellm-callback --print-config
```

Merge the printed callback into your existing `litellm_settings.callbacks` configuration instead of replacing other callbacks. The callback import path is `execweave.litellm_callback.execweave_litellm_callback`, so ExecWeave must be importable in the Python environment that runs LiteLLM Proxy.

Then launch the configured local proxy under ExecWeave, for example:

```bash
execweave live --open -- litellm --config config.yaml
```

`execweave live` provides `EXECWEAVE_SEMANTIC_SIDECAR` to the proxy process. If that run-specific variable is absent, the callback is a no-op. `EXECWEAVE_LITELLM_ENDPOINT` can override the stored proxy endpoint identity; otherwise the callback uses `PROXY_BASE_URL` when present and falls back to `http://localhost:4000`.

The callback reads LiteLLM's `standard_logging_object` only through a strict whitelist: call ID, model group, resolved model, deployment model ID, token counts, reported cost, response time, cache-hit state, and call type. It does not persist messages, response content, model parameters, arbitrary metadata, API-key metadata, or provider `api_base`. `model_group` is preserved as the requested model, `model` as the resolved model, and `model_id` as deployment identity. Provider identity is omitted unless authoritative provider evidence is supplied separately; ExecWeave does not infer it from model names or provider URLs.


LiteLLM is modeled as an `inference_gateway`, not a `model_runtime`. Its OpenAI-compatible response contributes request/model usage metadata through the same gateway evidence layer.

`--provider-name` and `--deployment-id` are only emitted when authoritative routing metadata is available to the caller or adapter. ExecWeave does **not** infer a provider or deployment from a model string such as `azure/...`. When those routing facts are unavailable, the corresponding edges are omitted.

## Exact Gateway ↔ Model Runtime identity

`execweave-inference-link` is intentionally stricter than temporal correlation. It creates `SAME_INFERENCE_REQUEST` only when the caller already has an explicit identifier that is shared across the gateway and runtime observations. It never guesses identity from timestamps, model names, token counts, latency, or other similarity signals.

The gateway and runtime requests remain separate nodes, preserving their layer-specific metadata. The identity edge is marked:

```text
identity_exact: true
inferred: false
causal: false
```

This means the two observations refer to the same logical inference request according to the supplied shared identity. It does **not** prove that a particular Agent or OS process caused the request. If no explicit shared identity exists, ExecWeave does not create this edge.

## Usage metadata

The response parser whitelists metadata such as prompt/input tokens, completion/output tokens, total tokens, cached prompt tokens, cache-write tokens, reasoning-token counts, and reported cost.

## Privacy boundary

ExecWeave does not persist prompt text, response/completion content, reasoning text, choices, or arbitrary provider payload fields. Gateway endpoint credentials, query parameters, and fragments are stripped from stored endpoint identity.

The original requested model is never guessed from the response; it must be supplied explicitly by the caller when that evidence is available. The raw `--shared-request-id` used for exact cross-layer identity is not persisted; ExecWeave stores only a SHA-256-derived identity hash on the link event.

## Evidence boundary

Gateway response metadata proves only what that gateway reported or what authoritative routing metadata was supplied alongside the response. It does not prove which local Agent initiated the request, which model-runtime process served it, or which OS process caused it.

Gateway events therefore remain non-causal (`causal: false`) and separate from Agent/IDE semantic evidence, Model Runtime evidence, and OS Runtime evidence. Exact shared request identity can connect Gateway and Model Runtime observations without collapsing their layers. Separately inferred correlation must remain explicitly inferred and must never be represented as causal evidence.
