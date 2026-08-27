# Model Runtime Integrations

<!-- i18n-nav:start -->
<p align="center">
  <a href="model-runtime.md">English</a> |
  <a href="model-runtime.zh-TW.md">繁體中文</a> |
  <a href="model-runtime.zh-CN.md">简体中文</a> |
  <a href="model-runtime.ja.md">日本語</a> |
  <a href="model-runtime.ko.md">한국어</a> |
  <a href="model-runtime.fr.md">Français</a> |
  <a href="model-runtime.de.md">Deutsch</a> |
  <strong>Русский</strong>
</p>
<!-- i18n-nav:end -->

Model runtimes отделены от Agent/IDE semantic adapters и inference gateways. Они описывают то, что сообщает локальная или self-hosted inference integration point; они не доказывают, какой Agent инициировал request.

Текущий baseline поддерживает **Ollama**, **llama.cpp**, **vLLM** и **LM Studio**.

## CLI

Захватить одну supplied final runtime response из stdin:

```bash
execweave-model-runtime event --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime llamacpp --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime vllm --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime lmstudio --sidecar model-runtime.jsonl
```

Захватить caller-supplied request+response exchange:

```bash
execweave-model-runtime exchange --runtime ollama --sidecar model-runtime.jsonl
```

`exchange` поддерживает те же четыре runtime и требует JSON-object поля `request` и `response`. Это явно caller-supplied evidence, а не прозрачная network interception.

Runtime state/model catalogs остаются доступными через `probe`. Default localhost endpoints: Ollama `11434`, llama.cpp `8080`, vLLM `8000`, LM Studio `1234`.

## Full-fidelity content

v0.6.5 сохраняет полный content, раскрытый выбранной model-runtime integration point, в локальном SHA-256 content-addressed store. `event` сохраняет полный supplied final response, не утверждая request visibility. `exchange` может сохранить и supplied request, и response, включая messages/prompts, tool definitions/calls/results, generated assistant content, явно присутствующие reasoning/thinking fields, request-generation configuration и provider response values, поддерживаемые runtime payload.

Semantic JSONL sidecar содержит content references вместо больших inline-копий. Компактные usage/timing/model metadata остаются доступными для graph/query.

`content_complete_from_source: true` означает, что ExecWeave сохранил полное значение, переданное CLI/integration point. Это **не** означает, что runtime раскрыл hidden model state, что request обязательно является финальным post-rewrite wire request провайдера или что ExecWeave наблюдал bytes, которые ему не были предоставлены.

Чувствительные application-level values внутри request/response content сохраняются. Endpoint/path sanitization и provider-metadata filtering не являются общей content redaction.

## Runtime-specific evidence

Ollama дополнительно может сообщать loaded-model state через `/api/ps`. llama.cpp может предоставлять timing/throughput, `/v1/models` и optional aggregate `/metrics`; labeled Prometheus lines, которые могут содержать чувствительные local identifiers, ограничиваются metadata adapter. vLLM и LM Studio используют общий OpenAI-compatible parsing response/model-catalog, сохраняя runtime-specific relation semantics.

Catalog relations намеренно различаются: в зависимости от того, что реально доказывает source endpoint, runtime может `LOADED_MODEL`, `SERVES_MODEL` или `ADVERTISES_MODEL`. Видимость каталога LM Studio остаётся `ADVERTISES_MODEL`; запись в каталоге сама по себе не доказывает, что weights находятся resident в памяти.

## Конфиденциальность и граница доказательств

Model-runtime content может содержать полные prompts/messages, tool data, generated responses, reasoning/thinking text, model parameters, configuration values, paths, identifiers и чувствительные application-level values. Проверяйте весь run directory перед публикацией.

Runtime response или exchange доказывает только то, что предоставила эта integration point. Само по себе это не доказывает, какой Agent инициировал request, какой gateway его routed, какой OS process его вызвал или что file bytes передавались model/network endpoint. Cross-layer identity требует явных shared identifiers или отдельно отмеченной консервативной correlation.
