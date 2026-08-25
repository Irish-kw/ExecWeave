# Inference Gateway Integrations

<p align="center">
  <a href="inference-gateway.md">English</a> |
  <a href="inference-gateway.zh-TW.md">繁體中文</a> |
  <strong>简体中文</strong> |
  <a href="inference-gateway.ja.md">日本語</a> |
  <a href="inference-gateway.ko.md">한국어</a>
</p>

Inference Gateway 是 Agent/client 与 model provider/runtime 之间的独立层。第一个 baseline integration 是 **OpenRouter**。

ExecWeave 会把 requested model、resolved model 与 provider routing 保存为不同 evidence，而不是全部压成同一个 model 字段。

## CLI

转换一次 OpenRouter final response：

```bash
execweave-inference-gateway event \
  --gateway openrouter \
  --requested-model openrouter/auto \
  --provider-name OpenAI \
  --sidecar gateway.jsonl
```

转换 generation metadata：

```bash
execweave-inference-gateway generation \
  --gateway openrouter \
  --sidecar gateway.jsonl
```

JSON 从 stdin 读取。默认 endpoint identity 为 `https://openrouter.ai/api/v1`。

## Graph model

```text
inference_gateway --SERVED_INFERENCE--> inference_request
inference_request --REQUESTED_MODEL--> model
inference_request --ROUTED_TO_MODEL--> model
inference_request --ROUTED_TO_PROVIDER--> inference_provider
inference_gateway --REPORTED_GENERATION_METADATA--> inference_request
```

例如一次 request 可以同时保存：

```text
requested_model = openrouter/auto
resolved_model  = openai/gpt-5.6-sol
provider        = OpenAI
```

三者不是可以互换的事实。

## Usage metadata

Response parser 只白名单保留 prompt/completion/total tokens、cached prompt tokens、cache-write tokens、reasoning-token counts 和 provider 报告的 cost。

Generation metadata 可再加入 latency、generation time、total cost、native token counts、streamed status 与 cancellation state。

## 隐私边界

ExecWeave 不保存 prompt text、response/completion content、reasoning text、choices 或任意 provider payload 字段。Gateway endpoint 中的 credentials、query parameters 和 fragment 会从 stored endpoint identity 中移除。

原始 requested model 不会从 response 猜测；只有 caller 明确提供时才保存该 evidence。

## Evidence boundary

OpenRouter response metadata 能证明的是 gateway 对该 generation 的报告，不能单独证明是哪个本机 Agent 发起 request。Gateway routing evidence 因此与 Agent semantics、OS runtime observations 分层保存。

未来 LiteLLM 等 gateway 也可以复用该层，而不会被错误建模为 local inference runtime。