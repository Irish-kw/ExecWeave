# Model Runtime Integrations

<!-- i18n-nav:start -->
<p align="center">
  <a href="model-runtime.md">English</a> |
  <a href="model-runtime.zh-TW.md">繁體中文</a> |
  <a href="model-runtime.zh-CN.md">简体中文</a> |
  <a href="model-runtime.ja.md">日本語</a> |
  <strong>한국어</strong> |
  <a href="model-runtime.fr.md">Français</a> |
  <a href="model-runtime.de.md">Deutsch</a> |
  <a href="model-runtime.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

Model runtime은 Agent/IDE semantic adapter 및 inference gateway와 별도 계층입니다. 로컬 또는 self-hosted inference integration point가 보고한 내용을 설명하지만 어느 Agent가 request를 시작했는지를 증명하지는 않습니다.

현재 baseline은 **Ollama**, **llama.cpp**, **vLLM**, **LM Studio**를 지원합니다.

## CLI

stdin에서 하나의 supplied final runtime response를 캡처합니다.

```bash
execweave-model-runtime event --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime llamacpp --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime vllm --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime lmstudio --sidecar model-runtime.jsonl
```

Caller-supplied request+response exchange를 캡처합니다.

```bash
execweave-model-runtime exchange --runtime ollama --sidecar model-runtime.jsonl
```

`exchange`는 동일한 네 runtime choice를 지원하며 JSON object인 `request`와 `response`가 필요합니다. 이는 명시적인 caller-supplied evidence이며 transparent network interception이 아닙니다.

Runtime state/model catalog는 `probe`로 계속 사용할 수 있습니다. 기본 localhost endpoint는 Ollama `11434`, llama.cpp `8080`, vLLM `8000`, LM Studio `1234`입니다.

## Full-fidelity 콘텐츠

v0.6.5는 선택한 model-runtime integration point가 노출한 complete content를 로컬 SHA-256 content-addressed store에 저장합니다. `event`는 request visibility를 주장하지 않고 supplied final response 전체를 보존합니다. `exchange`는 supplied request와 response를 모두 보존할 수 있으며, runtime payload가 지원하는 경우 message/prompt, tool definition/call/result, generated assistant content, 명시적으로 존재하는 reasoning/thinking field, request-generation config, provider response value를 포함할 수 있습니다.

Semantic JSONL sidecar에는 큰 값을 직접 넣는 대신 content reference가 들어갑니다. Compact usage/timing/model metadata는 graph/query 용도로 계속 사용할 수 있습니다.

`content_complete_from_source: true`는 CLI/integration point에 제공된 전체 값을 저장했다는 뜻입니다. Runtime이 hidden model state를 노출했다거나 request가 반드시 provider의 최종 post-rewrite wire request라거나 ExecWeave가 제공받지 않은 byte를 관측했다는 뜻은 아닙니다.

Request/response content 안의 민감한 application-level 값은 보존됩니다. Endpoint/path sanitization과 provider-metadata filtering은 일반적인 content redaction이 아닙니다.

## Runtime-specific evidence

Ollama는 `/api/ps`를 통해 loaded-model state를 추가로 보고할 수 있습니다. llama.cpp는 timing/throughput, `/v1/models`, optional aggregate `/metrics`를 노출할 수 있으며 민감한 local identifier를 포함할 수 있는 labeled Prometheus line은 metadata adapter에서 제한됩니다. vLLM과 LM Studio는 OpenAI-compatible response/model-catalog parsing을 공유하면서 runtime-specific relation semantics를 유지합니다.

Catalog relation은 의도적으로 구분됩니다. Source endpoint가 실제로 무엇을 증명하는지에 따라 runtime은 `LOADED_MODEL`, `SERVES_MODEL`, `ADVERTISES_MODEL`을 사용할 수 있습니다. LM Studio catalog visibility는 `ADVERTISES_MODEL`이며 catalog item 자체가 weights가 memory에 resident하다는 증명은 아닙니다.

## Privacy와 evidence boundary

Model-runtime content에는 complete prompt/message, tool data, generated response, reasoning/thinking text, model parameter, configuration value, path, identifier, 민감한 application-level 값이 포함될 수 있습니다. 공유 전에 전체 run directory를 검토하십시오.

Runtime response 또는 exchange는 그 integration point가 제공한 내용만 증명합니다. 어느 Agent가 request를 시작했는지, 어느 gateway가 route했는지, 어느 OS process가 원인이었는지, file byte가 model/network endpoint로 흘렀는지를 그 자체로 증명하지 않습니다. Cross-layer identity에는 explicit shared identifier 또는 별도로 표시된 보수적 correlation이 필요합니다.
