# Inference Gateway Integrations

<p align="center">
  <a href="inference-gateway.md">English</a> |
  <strong>繁體中文</strong> |
  <a href="inference-gateway.zh-CN.md">简体中文</a> |
  <a href="inference-gateway.ja.md">日本語</a> |
  <a href="inference-gateway.ko.md">한국어</a>
</p>

Inference Gateway 是 Agent/client 與 model provider/runtime 之間的獨立層。目前 baseline 支援 **OpenRouter** 與 **LiteLLM Proxy**。

ExecWeave 會把 requested model、resolved model、routed provider 與 deployment identity 分成不同 evidence，而不是全部壓成同一個 model 欄位。

## CLI

轉換一次 OpenRouter final response：

```bash
execweave-inference-gateway event \
  --gateway openrouter \
  --requested-model openrouter/auto \
  --provider-name OpenAI \
  --sidecar gateway.jsonl
```

轉換一次 LiteLLM Proxy final response：

```bash
execweave-inference-gateway event \
  --gateway litellm \
  --requested-model assistant \
  --resolved-model azure/gpt-5 \
  --provider-name Azure \
  --deployment-id deployment-west \
  --sidecar gateway.jsonl
```

轉換 OpenRouter generation metadata：

```bash
execweave-inference-gateway generation \
  --gateway openrouter \
  --sidecar gateway.jsonl
```

JSON 從 stdin 讀取。預設 endpoint identity：

- OpenRouter：`https://openrouter.ai/api/v1`
- LiteLLM Proxy：`http://localhost:4000`

## Graph model

```text
inference_gateway --SERVED_INFERENCE--> inference_request
inference_request --REQUESTED_MODEL--> model
inference_request --ROUTED_TO_MODEL--> model
inference_request --ROUTED_TO_PROVIDER--> inference_provider
inference_request --ROUTED_TO_DEPLOYMENT--> inference_deployment
inference_gateway --REPORTED_GENERATION_METADATA--> inference_request
```

例如 LiteLLM request 可以分別保存：

```text
requested_model = assistant
resolved_model  = azure/gpt-5
provider        = Azure
deployment      = deployment-west
```

這些不是可互換的事實。

## OpenRouter

OpenRouter response metadata 會把 requested model 與 response model 分開，並只保存明確觀測到的 routed provider。OpenRouter-specific generation metadata 可另外保存 latency、generation time、cost、native token counts、streaming state 與 cancellation state。

## LiteLLM Proxy

LiteLLM 被建模成 `inference_gateway`，不是 `model_runtime`。它的 OpenAI-compatible response 透過相同 gateway evidence layer 提供 request/model usage metadata。

`--provider-name` 與 `--deployment-id` 只有在 caller 或 adapter 有 authoritative routing metadata 時才建立。ExecWeave **不會**從 `azure/...` 之類的 model string 推測 provider 或 deployment；沒有這些 routing facts 時，就不建立對應 edge。

## Usage metadata

Response parser 只白名單保留 prompt/input tokens、completion/output tokens、total tokens、cached prompt tokens、cache-write tokens、reasoning-token counts 與 reported cost。

## 隱私邊界

ExecWeave 不保存 prompt text、response/completion content、reasoning text、choices 或任意 provider payload 欄位。Gateway endpoint 中的 credentials、query parameters 與 fragment 會從 stored endpoint identity 移除。

原始 requested model 不會從 response 猜測；只有 caller 明確提供時才保存這項 evidence。

## Evidence boundary

Gateway response metadata 只能證明 gateway 自己回報的資訊，或與 response 一起提供的 authoritative routing metadata。它不能單獨證明是哪個本機 Agent 發起 request、哪個 model-runtime process 實際服務，或哪個 OS process 造成 request。

Gateway events 因此保持 non-causal（`causal: false`），並與 Agent/IDE semantic evidence、Model Runtime evidence、OS Runtime evidence 分層保存。跨層 attribution 需要明確 shared identity 或另外定義的保守 correlation；inferred correlation 永遠不能被表示成 causal evidence。