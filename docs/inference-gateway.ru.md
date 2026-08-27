# Inference Gateway Integrations

<!-- i18n-nav:start -->
<p align="center">
  <a href="inference-gateway.md">English</a> |
  <a href="inference-gateway.zh-TW.md">繁體中文</a> |
  <a href="inference-gateway.zh-CN.md">简体中文</a> |
  <a href="inference-gateway.ja.md">日本語</a> |
  <a href="inference-gateway.ko.md">한국어</a> |
  <a href="inference-gateway.fr.md">Français</a> |
  <a href="inference-gateway.de.md">Deutsch</a> |
  <strong>Русский</strong>
</p>
<!-- i18n-nav:end -->

Inference gateways — отдельный слой evidence между Agent/client и model provider/runtime. ExecWeave сейчас моделирует **OpenRouter** и **LiteLLM Proxy**, сохраняя requested model, resolved model, routed provider и deployment identity раздельно.

## CLI

Захватить одну финальную gateway response из stdin:

```bash
execweave-inference-gateway event --gateway openrouter --sidecar gateway.jsonl
execweave-inference-gateway event --gateway litellm --sidecar gateway.jsonl
```

Только для OpenRouter можно захватить caller-supplied request+response object:

```bash
execweave-inference-gateway exchange --gateway openrouter --sidecar gateway.jsonl
```

`exchange` требует JSON-object поля `request` и `response` на stdin. Это явно caller-supplied evidence, а **не** прозрачная wire interception.

OpenRouter generation metadata остаётся доступной через `generation`.

## Граница full-fidelity OpenRouter

Для `event --gateway openrouter` v0.6.5 сохраняет полный supplied final response в локальном content-addressed store и одновременно создаёт компактный routing/usage summary. Для `exchange --gateway openrouter` можно сохранить полный caller-supplied request и response.

`content_complete_from_source: true` означает, что сохранено полное значение, переданное этой точке интеграции. Это не утверждает видимость request до provider-side rewriting, hidden routing stages, model internals или network bytes, которых ExecWeave не наблюдал.

Чувствительные application-level values внутри supplied request/response content сохраняются. Endpoint identity sanitizes отдельно; удаление query parameters/fragments и фильтрация известных transport credentials не заменяют content redaction.

## Граница LiteLLM

LiteLLM остаётся metadata-oriented integration в текущем baseline v0.6.5. Response parser и optional custom callback сохраняют routing/usage fields по строгому контракту; поддержка content storage в OpenRouter не превращает LiteLLM callback автоматически в full-fidelity capture.

Callback включается выводом его конфигурации и запуском настроенного proxy внутри текущего ExecWeave run:

```bash
execweave-litellm-callback --print-config
execweave live --open -- litellm --config config.yaml
```

Если `EXECWEAVE_SEMANTIC_SIDECAR` отсутствует, callback — no-op. Provider/deployment identity создаётся только при наличии authoritative evidence; ExecWeave не выводит её из model-name prefix или provider URL.

## Точная identity gateway ↔ model-runtime

Если caller уже имеет явный shared request identifier, `execweave-inference-link` может связать gateway и runtime request nodes, не объединяя слои. Raw shared identifier не сохраняется; link использует SHA-256-derived identity hash.

```text
identity_exact: true
inferred: false
causal: false
```

Это точная logical request identity, а не доказательство того, что конкретный Agent или OS process вызвал inference.

## Конфиденциальность и граница доказательств

OpenRouter full-fidelity artifacts могут содержать полный request/response content и чувствительные application-level values. LiteLLM artifacts следуют более узкому metadata/callback contract. Рассматривайте gateway evidence как чувствительное и проверяйте перед публикацией.

Gateway observations доказывают только то, что integration point сообщил или какие authoritative routing data были предоставлены вместе с ним. Они не доказывают сами по себе, какой local Agent инициировал request, какой model-runtime process обслужил его или какой OS process его вызвал. При отсутствии shared identity нельзя подменять её угадыванием по timestamp/model name.
