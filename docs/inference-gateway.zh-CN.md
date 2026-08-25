# Inference Gateway Integrations

<p align="center">
  <a href="inference-gateway.md">English</a> |
  <a href="inference-gateway.zh-TW.md">繁體中文</a> |
  <strong>简体中文</strong> |
  <a href="inference-gateway.ja.md">日本語</a> |
  <a href="inference-gateway.ko.md">한국어</a>
</p>

Inference Gateway 是 Agent/client 与 model provider/runtime 之间的独立层。当前 baseline 支持 **OpenRouter** 与 **LiteLLM Proxy**。

ExecWeave 会把 requested model、resolved model、routed provider 与 deployment identity 保存为不同 evidence，而不是全部压成同一个 model 字段。

## CLI

转换一次 OpenRouter final response：

```bash
execweave-inference-gateway event \
  --gateway openrouter \
  --requested-model openrouter/auto \
  --provider-name OpenAI \
  --sidecar gateway.jsonl
```

转换一次 LiteLLM Proxy final response：

```bash
execweave-inference-gateway event \
  --gateway litellm \
  --requested-model assistant \
  --resolved-model azure/gpt-5 \
  --provider-name Azure \
  --deployment-id deployment-west \
  --sidecar gateway.jsonl
```

转换 OpenRouter generation metadata：

```bash
execweave-inference-gateway generation \
  --gateway openrouter \
  --sidecar gateway.jsonl
```

JSON 从 stdin 读取。默认 endpoint identity：

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

例如 LiteLLM request 可以分别保存：

```text
requested_model = assistant
resolved_model  = azure/gpt-5
provider        = Azure
deployment      = deployment-west
```

这些不是可以互换的事实。

## OpenRouter

OpenRouter response metadata 会把 requested model 与 response model 分开，并只保存明确观察到的 routed provider。OpenRouter-specific generation metadata 可另外保存 latency、generation time、cost、native token counts、streaming state 与 cancellation state。

## LiteLLM Proxy

LiteLLM 被建模为 `inference_gateway`，而不是 `model_runtime`。它的 OpenAI-compatible response 通过相同 gateway evidence layer 提供 request/model usage metadata。

`--provider-name` 与 `--deployment-id` 只有在 caller 或 adapter 拥有 authoritative routing metadata 时才建立。ExecWeave **不会**从 `azure/...` 之类的 model string 推测 provider 或 deployment；没有这些 routing facts 时，就不建立对应 edge。

## Usage metadata

Response parser 只白名单保留 prompt/input tokens、completion/output tokens、total tokens、cached prompt tokens、cache-write tokens、reasoning-token counts 与 reported cost。

## 隐私边界

ExecWeave 不保存 prompt text、response/completion content、reasoning text、choices 或任意 provider payload 字段。Gateway endpoint 中的 credentials、query parameters 与 fragment 会从 stored endpoint identity 移除。

原始 requested model 不会从 response 猜测；只有 caller 明确提供时才保存该 evidence。

## Evidence boundary

Gateway response metadata 只能证明 gateway 自己报告的信息，或与 response 一起提供的 authoritative routing metadata。它不能单独证明是哪个本机 Agent 发起 request、哪个 model-runtime process 实际服务，或哪个 OS process 造成 request。

Gateway events 因此保持 non-causal（`causal: false`），并与 Agent/IDE semantic evidence、Model Runtime evidence、OS Runtime evidence 分层保存。跨层 attribution 需要明确 shared identity 或另外定义的保守 correlation；inferred correlation 永远不能被表示为 causal evidence。