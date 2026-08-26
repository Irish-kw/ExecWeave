# Inference Gateway Integrations

<!-- i18n-nav:start -->
<p align="center">
  <a href="inference-gateway.md">English</a> |
  <a href="inference-gateway.zh-TW.md">繁體中文</a> |
  <a href="inference-gateway.zh-CN.md">简体中文</a> |
  <a href="inference-gateway.ja.md">日本語</a> |
  <strong>한국어</strong> |
  <a href="inference-gateway.fr.md">Français</a> |
  <a href="inference-gateway.de.md">Deutsch</a> |
  <a href="inference-gateway.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

Inference Gateway는 Agent/client와 model provider/runtime 사이의 독립 계층입니다. 현재 baseline은 **OpenRouter**와 **LiteLLM Proxy**를 지원합니다.

ExecWeave는 requested model, resolved model, routed provider, deployment identity를 서로 다른 evidence로 보존하며 하나의 model field로 합치지 않습니다.

## CLI

OpenRouter final response를 변환합니다.

```bash
execweave-inference-gateway event \
  --gateway openrouter \
  --requested-model openrouter/auto \
  --provider-name OpenAI \
  --sidecar gateway.jsonl
```

LiteLLM Proxy final response를 변환합니다.

```bash
execweave-inference-gateway event \
  --gateway litellm \
  --requested-model assistant \
  --resolved-model azure/gpt-5 \
  --provider-name Azure \
  --deployment-id deployment-west \
  --sidecar gateway.jsonl
```

OpenRouter generation metadata를 변환합니다.

```bash
execweave-inference-gateway generation \
  --gateway openrouter \
  --sidecar gateway.jsonl
```

Caller가 Gateway observation과 Model Runtime observation 양쪽에 대응하는 명시적 shared request identity를 가지고 있다면 기존 request node 둘을 연결할 수 있습니다.

```bash
execweave-inference-link \
  --gateway litellm \
  --gateway-request-id gw-123 \
  --runtime vllm \
  --runtime-request-id rt-456 \
  --shared-request-id trace-789 \
  --sidecar inference.jsonl
```

Gateway response JSON은 stdin에서 읽습니다. 기본 endpoint identity:

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

LiteLLM request에서는 예를 들어 다음을 별도의 evidence로 보존할 수 있습니다.

```text
requested_model = assistant
resolved_model  = azure/gpt-5
provider        = Azure
deployment      = deployment-west
```

이 값들은 서로 대체 가능한 사실이 아닙니다.

## OpenRouter

OpenRouter response metadata는 requested model과 response model을 분리하고 명시적으로 관측된 routed provider만 보존합니다. OpenRouter-specific generation metadata에서는 latency, generation time, cost, native token counts, streaming state, cancellation state도 기록할 수 있습니다.

## LiteLLM Proxy

LiteLLM은 `model_runtime`이 아니라 `inference_gateway`로 모델링합니다. OpenAI-compatible response는 동일한 gateway evidence layer를 통해 request/model usage metadata를 제공합니다.

`--provider-name`과 `--deployment-id`는 caller / adapter가 authoritative routing metadata를 가지고 있을 때만 edge를 생성합니다. ExecWeave는 `azure/...` 같은 model string에서 provider / deployment를 **추측하지 않습니다**. routing facts가 없으면 해당 edge를 만들지 않습니다.

## Exact Gateway ↔ Model Runtime identity

`execweave-inference-link`는 temporal correlation보다 의도적으로 더 엄격합니다. Caller가 Gateway와 Runtime observation 양쪽에 대응하는 명시적 shared identifier를 이미 가지고 있을 때만 `SAME_INFERENCE_REQUEST`를 생성합니다. Timestamp, model name, token counts, latency 또는 다른 유사도 신호로 identity를 추측하지 않습니다.

Gateway request와 Runtime request는 별도 node로 유지되므로 layer-specific metadata가 서로 덮어쓰이지 않습니다. Identity edge는 다음과 같이 고정됩니다.

```text
identity_exact: true
inferred: false
causal: false
```

이는 supplied shared identity에 따라 두 observation이 동일한 logical inference request를 가리킨다는 것만 의미합니다. 특정 Agent나 OS process가 request를 발생시켰다는 causal proof가 아닙니다. Explicit shared identity가 없으면 이 edge를 만들지 않습니다.

## Usage metadata

Response parser는 prompt/input tokens, completion/output tokens, total tokens, cached prompt tokens, cache-write tokens, reasoning-token counts, reported cost만 whitelist로 유지합니다.

## 프라이버시 경계

ExecWeave는 prompt text, response/completion content, reasoning text, choices, 임의의 provider payload field를 저장하지 않습니다. Gateway endpoint의 credentials, query parameters, fragment는 stored endpoint identity에서 제거합니다.

원래 requested model을 response에서 추측하지 않습니다. Caller가 명시적으로 제공할 때만 evidence로 저장합니다. Exact cross-layer identity에 사용하는 raw `--shared-request-id`도 저장하지 않고 link event에는 SHA-256에서 파생한 identity hash만 저장합니다.

## Evidence boundary

Gateway response metadata가 증명하는 것은 gateway 자체가 보고한 정보 또는 response와 함께 제공된 authoritative routing metadata뿐입니다. 어떤 local Agent가 request를 시작했는지, 어떤 model-runtime process가 실제 serving했는지, 어떤 OS process가 원인인지는 단독으로 증명할 수 없습니다.

Gateway events는 non-causal(`causal: false`)로 유지하고 Agent/IDE semantic evidence, Model Runtime evidence, OS Runtime evidence와 분리합니다. 명시적 shared request identity는 Gateway와 Model Runtime observation을 연결할 수 있지만 layer를 합치지는 않습니다. 별도로 추론된 correlation은 계속 inferred로 명시해야 하며 causal evidence로 표현해서는 안 됩니다.
