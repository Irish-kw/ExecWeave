# Inference Gateway Integrations

<p align="center">
  <a href="inference-gateway.md">English</a> |
  <a href="inference-gateway.zh-TW.md">繁體中文</a> |
  <a href="inference-gateway.zh-CN.md">简体中文</a> |
  <a href="inference-gateway.ja.md">日本語</a> |
  <strong>한국어</strong>
</p>

Inference Gateway는 Agent/client와 model provider/runtime 사이의 독립 계층입니다. 첫 baseline integration은 **OpenRouter**입니다.

ExecWeave는 requested model, resolved model, provider routing을 서로 다른 evidence로 보존하며 하나의 model field로 합치지 않습니다.

## CLI

OpenRouter final response를 변환합니다.

```bash
execweave-inference-gateway event \
  --gateway openrouter \
  --requested-model openrouter/auto \
  --provider-name OpenAI \
  --sidecar gateway.jsonl
```

Generation metadata를 변환합니다.

```bash
execweave-inference-gateway generation \
  --gateway openrouter \
  --sidecar gateway.jsonl
```

JSON은 stdin에서 읽습니다. 기본 endpoint identity는 `https://openrouter.ai/api/v1`입니다.

## Graph model

```text
inference_gateway --SERVED_INFERENCE--> inference_request
inference_request --REQUESTED_MODEL--> model
inference_request --ROUTED_TO_MODEL--> model
inference_request --ROUTED_TO_PROVIDER--> inference_provider
inference_gateway --REPORTED_GENERATION_METADATA--> inference_request
```

한 request에서 다음을 동시에 보존할 수 있습니다.

```text
requested_model = openrouter/auto
resolved_model  = openai/gpt-5.6-sol
provider        = OpenAI
```

이 값들은 서로 대체 가능한 사실이 아닙니다.

## Usage metadata

Response parser는 prompt/completion/total tokens, cached prompt tokens, cache-write tokens, reasoning-token counts, provider reported cost만 whitelist로 유지합니다.

Generation metadata는 latency, generation time, total cost, native token counts, streamed status, cancellation state를 추가할 수 있습니다.

## 프라이버시 경계

ExecWeave는 prompt text, response/completion content, reasoning text, choices, 임의의 provider payload field를 저장하지 않습니다. Gateway endpoint의 credentials, query parameters, fragment는 stored endpoint identity에서 제거합니다.

원래 requested model을 response에서 추측하지 않습니다. Caller가 명시적으로 제공할 때만 evidence로 저장합니다.

## Evidence boundary

OpenRouter response metadata가 증명하는 것은 gateway가 해당 generation에 대해 보고한 정보입니다. 어떤 local Agent가 request를 시작했는지는 단독으로 증명할 수 없습니다. Gateway routing evidence는 Agent semantics 및 OS runtime observations와 분리해 저장합니다.

향후 LiteLLM 같은 gateway도 이 layer를 재사용할 수 있으며 local inference runtime으로 잘못 모델링하지 않습니다.