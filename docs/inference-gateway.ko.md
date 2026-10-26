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

Inference gateway는 Agent/client와 model provider/runtime 사이의 별도 evidence layer입니다. ExecWeave는 현재 **OpenRouter**와 **LiteLLM Proxy**를 모델링하며 requested model, resolved model, routed provider, deployment identity를 구분해서 유지합니다.

## CLI

stdin에서 하나의 최종 gateway response를 캡처합니다.

```bash
execweave-inference-gateway event --gateway openrouter --sidecar gateway.jsonl
execweave-inference-gateway event --gateway litellm --sidecar gateway.jsonl
```

OpenRouter에서만 caller-supplied request+response object를 캡처할 수 있습니다.

```bash
execweave-inference-gateway exchange --gateway openrouter --sidecar gateway.jsonl
```

`exchange`는 stdin에 JSON object인 `request`와 `response`가 필요합니다. 이는 명시적인 caller-supplied evidence이며 **transparent wire interception이 아닙니다**.

OpenRouter generation metadata는 `generation`을 통해 계속 사용할 수 있습니다.

## OpenRouter full-fidelity boundary

`event --gateway openrouter`에서 v0.6.5는 compact routing/usage summary와 함께 supplied final response 전체를 로컬 content-addressed store에 저장합니다. `exchange --gateway openrouter`는 caller가 제공한 request와 response 전체 값을 보존할 수 있습니다.

`content_complete_from_source: true`는 이 integration point에 제공된 전체 값을 저장했다는 뜻입니다. Provider-side rewriting 전 request, hidden routing stage, model internals 또는 ExecWeave가 직접 보지 못한 network byte를 관측했다는 뜻은 아닙니다.

Supplied request/response content 안의 민감한 application-level 값은 보존됩니다. Endpoint identity는 별도로 sanitize되며 query parameter/fragment 또는 알려진 transport credential filtering은 content redaction을 대신하지 않습니다.

## LiteLLM boundary

LiteLLM은 현재 v0.6.5 baseline에서 metadata-oriented integration으로 유지됩니다. Response parser와 optional custom callback은 strict contract를 통해 routing/usage field를 보존하며, OpenRouter가 content storage를 지원한다고 해서 callback이 full-fidelity가 되는 것은 아닙니다.

다음처럼 callback 설정을 출력하고 설정된 proxy를 현재 ExecWeave run 안에서 실행합니다.

```bash
execweave-litellm-callback --print-config
execweave live --open -- litellm --config config.yaml
```

`EXECWEAVE_SEMANTIC_SIDECAR`가 없으면 callback은 no-op입니다. Provider/deployment identity는 authoritative evidence가 있을 때만 방출되며 model-name prefix나 provider URL에서 추론하지 않습니다.

## Exact gateway ↔ model-runtime identity

Caller가 명시적인 shared request identifier를 이미 가지고 있으면 `execweave-inference-link`가 layer를 합치지 않고 gateway와 runtime request node를 연결할 수 있습니다. Raw shared identifier는 저장하지 않고 SHA-256-derived identity hash를 사용합니다.

```text
identity_exact: true
inferred: false
causal: false
```

이는 정확한 logical request identity이지 특정 Agent나 OS process가 inference를 일으켰다는 증명은 아닙니다.

## Privacy와 evidence boundary

OpenRouter full-fidelity artifact에는 complete request/response content와 민감한 application-level 값이 포함될 수 있습니다. LiteLLM artifact는 더 좁은 metadata/callback contract를 따릅니다. Gateway evidence를 민감한 자료로 취급하고 공유 전에 검토하십시오.

Gateway observation은 integration point가 보고한 내용 또는 함께 제공된 authoritative routing data만 증명합니다. 그 자체로 어느 local Agent가 request를 시작했는지, 어느 model-runtime process가 처리했는지, 어느 OS process가 원인이었는지 증명하지 않습니다. Shared identity가 없을 때 timestamp/model-name guessing으로 대체해서는 안 됩니다.
