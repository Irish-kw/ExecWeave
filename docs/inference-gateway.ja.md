# Inference Gateway Integrations

<p align="center">
  <a href="inference-gateway.md">English</a> |
  <a href="inference-gateway.zh-TW.md">繁體中文</a> |
  <a href="inference-gateway.zh-CN.md">简体中文</a> |
  <strong>日本語</strong> |
  <a href="inference-gateway.ko.md">한국어</a>
</p>

Inference Gateway は Agent/client と model provider/runtime の間にある独立レイヤーです。最初の baseline integration は **OpenRouter** です。

ExecWeave は requested model、resolved model、provider routing を別々の evidence として保持し、単一の model field に潰しません。

## CLI

OpenRouter の final response を変換します。

```bash
execweave-inference-gateway event \
  --gateway openrouter \
  --requested-model openrouter/auto \
  --provider-name OpenAI \
  --sidecar gateway.jsonl
```

Generation metadata を変換します。

```bash
execweave-inference-gateway generation \
  --gateway openrouter \
  --sidecar gateway.jsonl
```

JSON は stdin から読み取ります。既定 endpoint identity は `https://openrouter.ai/api/v1` です。

## Graph model

```text
inference_gateway --SERVED_INFERENCE--> inference_request
inference_request --REQUESTED_MODEL--> model
inference_request --ROUTED_TO_MODEL--> model
inference_request --ROUTED_TO_PROVIDER--> inference_provider
inference_gateway --REPORTED_GENERATION_METADATA--> inference_request
```

一つの request で次を同時に保持できます。

```text
requested_model = openrouter/auto
resolved_model  = openai/gpt-5.6-sol
provider        = OpenAI
```

これらは置き換え可能な事実ではありません。

## Usage metadata

Response parser は prompt/completion/total tokens、cached prompt tokens、cache-write tokens、reasoning-token counts、provider reported cost だけを whitelist で保持します。

Generation metadata から latency、generation time、total cost、native token counts、streamed status、cancellation state を追加できます。

## プライバシー境界

ExecWeave は prompt text、response/completion content、reasoning text、choices、任意の provider payload field を保存しません。Gateway endpoint の credentials、query parameters、fragment は stored endpoint identity から除去します。

元の requested model を response から推測しません。Caller が明示した場合だけ evidence として保存します。

## Evidence boundary

OpenRouter response metadata が証明するのは gateway がその generation について報告した情報です。どの local Agent が request を開始したかは単独では証明できません。Gateway routing evidence は Agent semantics と OS runtime observations から分離して保存します。

将来 LiteLLM などもこの gateway layer を再利用でき、local inference runtime と誤ってモデル化されません。