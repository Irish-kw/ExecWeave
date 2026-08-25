# Inference Gateway Integrations

<p align="center">
  <strong>English</strong> |
  <a href="inference-gateway.zh-TW.md">繁體中文</a> |
  <a href="inference-gateway.zh-CN.md">简体中文</a> |
  <a href="inference-gateway.ja.md">日本語</a> |
  <a href="inference-gateway.ko.md">한국어</a>
</p>

Inference gateways are a separate layer between an Agent/client and the model provider/runtime. The first baseline integration is **OpenRouter**.

ExecWeave preserves requested model, resolved model, and provider routing as distinct evidence instead of collapsing them into one model field.

## CLI

Convert one final OpenRouter response:

```bash
execweave-inference-gateway event \
  --gateway openrouter \
  --requested-model openrouter/auto \
  --provider-name OpenAI \
  --sidecar gateway.jsonl
```

Convert generation metadata:

```bash
execweave-inference-gateway generation \
  --gateway openrouter \
  --sidecar gateway.jsonl
```

JSON is read from stdin. The default endpoint identity is `https://openrouter.ai/api/v1`.

## Graph model

```text
inference_gateway --SERVED_INFERENCE--> inference_request
inference_request --REQUESTED_MODEL--> model
inference_request --ROUTED_TO_MODEL--> model
inference_request --ROUTED_TO_PROVIDER--> inference_provider
inference_gateway --REPORTED_GENERATION_METADATA--> inference_request
```

For example, a request can preserve:

```text
requested_model = openrouter/auto
resolved_model  = openai/gpt-5.6-sol
provider        = OpenAI
```

These are not interchangeable facts.

## Usage metadata

The response parser whitelists metadata such as prompt/completion/total tokens, cached prompt tokens, cache-write tokens, reasoning-token counts, and reported cost.

Generation metadata can add latency, generation time, total cost, native token counts, streamed status, and cancellation state when present.

## Privacy boundary

ExecWeave does not persist prompt text, response/completion content, reasoning text, choices, or arbitrary provider payload fields. Gateway endpoint credentials, query parameters, and fragments are stripped from stored endpoint identity.

The original requested model is never guessed from the response; it must be supplied explicitly by the caller when that evidence is available.

## Evidence boundary

OpenRouter response metadata proves what the gateway reported for that generation. It does not prove which local Agent initiated the request unless a shared request identity is available. Gateway routing evidence is therefore kept separate from Agent semantics and OS runtime observations.

Future gateway adapters can reuse this layer for systems such as LiteLLM without modeling them as local inference runtimes.