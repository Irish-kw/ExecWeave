# Inference Gateway Integrations

<p align="center">
  <a href="inference-gateway.md">English</a> |
  <strong>繁體中文</strong> |
  <a href="inference-gateway.zh-CN.md">简体中文</a> |
  <a href="inference-gateway.ja.md">日本語</a> |
  <a href="inference-gateway.ko.md">한국어</a>
</p>

Inference Gateway 是 Agent/client 與 model provider/runtime 之間的獨立層。第一個 baseline integration 是 **OpenRouter**。

ExecWeave 會把 requested model、resolved model 與 provider routing 分成不同 evidence，而不是全部壓成同一個 model 欄位。

## CLI

轉換一次 OpenRouter final response：

```bash
execweave-inference-gateway event \
  --gateway openrouter \
  --requested-model openrouter/auto \
  --provider-name OpenAI \
  --sidecar gateway.jsonl
```

轉換 generation metadata：

```bash
execweave-inference-gateway generation \
  --gateway openrouter \
  --sidecar gateway.jsonl
```

JSON 從 stdin 讀取。預設 endpoint identity 為 `https://openrouter.ai/api/v1`。

## Graph model

```text
inference_gateway --SERVED_INFERENCE--> inference_request
inference_request --REQUESTED_MODEL--> model
inference_request --ROUTED_TO_MODEL--> model
inference_request --ROUTED_TO_PROVIDER--> inference_provider
inference_gateway --REPORTED_GENERATION_METADATA--> inference_request
```

例如一次 request 可以同時保存：

```text
requested_model = openrouter/auto
resolved_model  = openai/gpt-5.6-sol
provider        = OpenAI
```

這三者不是可互換的事實。

## Usage metadata

Response parser 只白名單保留 prompt/completion/total tokens、cached prompt tokens、cache-write tokens、reasoning-token counts 與 provider 回報的 cost。

Generation metadata 可再加入 latency、generation time、total cost、native token counts、streamed status 與 cancellation state。

## 隱私邊界

ExecWeave 不保存 prompt text、response/completion content、reasoning text、choices 或任意 provider payload 欄位。Gateway endpoint 中的 credentials、query parameters 與 fragment 會從 stored endpoint identity 移除。

原始 requested model 不會從 response 猜測；只有 caller 明確提供時才保存這項 evidence。

## Evidence boundary

OpenRouter response metadata 能證明的是 gateway 對該 generation 的回報，不能單獨證明是哪個本機 Agent 發起 request。Gateway routing evidence 因此與 Agent semantics、OS runtime observations 分層保存。

未來 LiteLLM 等 gateway 也可以重用此層，而不被誤建模成 local inference runtime。