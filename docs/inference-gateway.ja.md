# Inference Gateway Integrations

<!-- i18n-nav:start -->
<p align="center">
  <a href="inference-gateway.md">English</a> |
  <a href="inference-gateway.zh-TW.md">繁體中文</a> |
  <a href="inference-gateway.zh-CN.md">简体中文</a> |
  <strong>日本語</strong> |
  <a href="inference-gateway.ko.md">한국어</a> |
  <a href="inference-gateway.fr.md">Français</a> |
  <a href="inference-gateway.de.md">Deutsch</a> |
  <a href="inference-gateway.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

Inference Gateway は Agent/client と model provider/runtime の間にある独立レイヤーです。現在の baseline は **OpenRouter** と **LiteLLM Proxy** をサポートします。

ExecWeave は requested model、resolved model、routed provider、deployment identity を別々の evidence として保持し、単一の model field に潰しません。

## CLI

OpenRouter final response を変換します。

```bash
execweave-inference-gateway event \
  --gateway openrouter \
  --requested-model openrouter/auto \
  --provider-name OpenAI \
  --sidecar gateway.jsonl
```

LiteLLM Proxy final response を変換します。

```bash
execweave-inference-gateway event \
  --gateway litellm \
  --requested-model assistant \
  --resolved-model azure/gpt-5 \
  --provider-name Azure \
  --deployment-id deployment-west \
  --sidecar gateway.jsonl
```

OpenRouter generation metadata を変換します。

```bash
execweave-inference-gateway generation \
  --gateway openrouter \
  --sidecar gateway.jsonl
```

Caller が Gateway observation と Model Runtime observation の両方に対応する明示的な shared request identity を持つ場合、既存の request node 同士を接続できます。

```bash
execweave-inference-link \
  --gateway litellm \
  --gateway-request-id gw-123 \
  --runtime vllm \
  --runtime-request-id rt-456 \
  --shared-request-id trace-789 \
  --sidecar inference.jsonl
```

Gateway response JSON は stdin から読み取ります。既定 endpoint identity：

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

LiteLLM request では、たとえば次を別々に保持できます。

```text
requested_model = assistant
resolved_model  = azure/gpt-5
provider        = Azure
deployment      = deployment-west
```

これらは置き換え可能な事実ではありません。

## OpenRouter

OpenRouter response metadata では requested model と response model を分離し、明示的に観測された routed provider だけを保持します。OpenRouter-specific generation metadata では latency、generation time、cost、native token counts、streaming state、cancellation state も記録できます。

## LiteLLM Proxy

LiteLLM は `model_runtime` ではなく `inference_gateway` としてモデル化します。OpenAI-compatible response は同じ gateway evidence layer を通じて request/model usage metadata を提供します。

`--provider-name` と `--deployment-id` は caller / adapter が authoritative routing metadata を持つ場合だけ edge を生成します。ExecWeave は `azure/...` のような model string から provider / deployment を**推測しません**。routing facts がない場合は対応する edge を作りません。

## Exact Gateway ↔ Model Runtime identity

`execweave-inference-link` は temporal correlation より意図的に厳格です。Caller が Gateway と Runtime の両 observation に対応する明示的 shared identifier をすでに持つ場合にだけ `SAME_INFERENCE_REQUEST` を作成します。Timestamp、model name、token counts、latency、その他の類似度から identity を推測しません。

Gateway request と Runtime request は別 node のままなので、layer-specific metadata が互いに上書きされることはありません。Identity edge は次のように固定されます。

```text
identity_exact: true
inferred: false
causal: false
```

これは supplied shared identity に基づいて二つの observation が同じ logical inference request を指すことだけを表します。特定の Agent や OS process が request を発生させたという causal proof ではありません。Explicit shared identity がなければ edge は作りません。

## Usage metadata

Response parser は prompt/input tokens、completion/output tokens、total tokens、cached prompt tokens、cache-write tokens、reasoning-token counts、reported cost のみを whitelist で保持します。

## プライバシー境界

ExecWeave は prompt text、response/completion content、reasoning text、choices、任意の provider payload field を保存しません。Gateway endpoint の credentials、query parameters、fragment は stored endpoint identity から除去します。

元の requested model を response から推測しません。Caller が明示した場合だけ evidence として保存します。Exact cross-layer identity に使う raw `--shared-request-id` も保存せず、link event には SHA-256 由来の identity hash だけを保存します。

## Evidence boundary

Gateway response metadata が証明するのは gateway 自身が報告した情報、または response とともに与えられた authoritative routing metadata だけです。どの local Agent が request を開始したか、どの model-runtime process が実際に serving したか、どの OS process が原因かは単独では証明できません。

Gateway events は non-causal（`causal: false`）のまま Agent/IDE semantic evidence、Model Runtime evidence、OS Runtime evidence と分離します。明示的 shared request identity は Gateway と Model Runtime observation を接続できますが layer を統合しません。別途推論された correlation は inferred として明示し続け、causal evidence として表現してはいけません。
