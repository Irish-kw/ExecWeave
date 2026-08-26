# Интеграции шлюзов инференса

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

Шлюзы инференса — отдельный слой между Agent/client и провайдером/runtime модели. Текущая базовая реализация поддерживает **OpenRouter** и **LiteLLM Proxy**.

ExecWeave сохраняет запрошенную модель, разрешённую модель, выбранного маршрутизацией провайдера и идентичность deployment как отдельные доказательства вместо объединения их в одно поле модели.

## CLI

Преобразовать один финальный ответ OpenRouter:

```bash
execweave-inference-gateway event \
  --gateway openrouter \
  --requested-model openrouter/auto \
  --provider-name OpenAI \
  --sidecar gateway.jsonl
```

Преобразовать один финальный ответ LiteLLM Proxy:

```bash
execweave-inference-gateway event \
  --gateway litellm \
  --requested-model assistant \
  --resolved-model azure/gpt-5 \
  --provider-name Azure \
  --deployment-id deployment-west \
  --sidecar gateway.jsonl
```

Преобразовать метаданные генерации OpenRouter:

```bash
execweave-inference-gateway generation \
  --gateway openrouter \
  --sidecar gateway.jsonl
```

Если вызывающая сторона имеет явную общую идентичность запроса для наблюдения gateway и наблюдения model-runtime, свяжите два существующих узла запросов:

```bash
execweave-inference-link \
  --gateway litellm \
  --gateway-request-id gw-123 \
  --runtime vllm \
  --runtime-request-id rt-456 \
  --shared-request-id trace-789 \
  --sidecar inference.jsonl
```

JSON ответа gateway читается из stdin. Идентичности endpoints по умолчанию:

- OpenRouter: `https://openrouter.ai/api/v1`
- LiteLLM Proxy: `http://localhost:4000`

## Модель графа

```text
inference_gateway --SERVED_INFERENCE--> inference_request
inference_request --REQUESTED_MODEL--> model
inference_request --ROUTED_TO_MODEL--> model
inference_request --ROUTED_TO_PROVIDER--> inference_provider
inference_request --ROUTED_TO_DEPLOYMENT--> inference_deployment
inference_gateway --REPORTED_GENERATION_METADATA--> inference_request
inference_request --SAME_INFERENCE_REQUEST--> inference_request
```

Например, запрос LiteLLM может сохранить:

```text
requested_model = assistant
resolved_model  = azure/gpt-5
provider        = Azure
deployment      = deployment-west
```

Эти факты не взаимозаменяемы.

## OpenRouter

Метаданные ответа OpenRouter сохраняют запрошенную модель отдельно от модели ответа и от явно наблюдаемого маршрутизированного провайдера. Специфические метаданные генерации OpenRouter также могут сообщать latency, время генерации, стоимость, нативные количества tokens, состояние streaming и состояние отмены.

## LiteLLM Proxy

LiteLLM моделируется как `inference_gateway`, а не как `model_runtime`. Его OpenAI-совместимый ответ добавляет метаданные запроса/модели/usage через тот же слой gateway-доказательств.

`--provider-name` и `--deployment-id` создаются только когда вызывающей стороне или адаптеру доступны авторитетные routing-метаданные. ExecWeave **не выводит** провайдера или deployment из строки модели вроде `azure/...`. Когда эти routing-факты недоступны, соответствующие рёбра не создаются.

## Точная идентичность Gateway ↔ Model Runtime

`execweave-inference-link` намеренно строже временной корреляции. Он создаёт `SAME_INFERENCE_REQUEST` только когда вызывающая сторона уже имеет явный идентификатор, общий для gateway- и runtime-наблюдений. Он никогда не угадывает идентичность по временным меткам, именам моделей, количествам tokens, latency или другим сигналам сходства.

Запросы gateway и runtime остаются отдельными узлами, сохраняя метаданные своих слоёв. Ребро идентичности помечается:

```text
identity_exact: true
inferred: false
causal: false
```

Это означает, что два наблюдения относятся к одному логическому запросу инференса согласно предоставленной общей идентичности. Это **не доказывает**, что конкретный Agent или процесс ОС вызвал запрос. Если явной общей идентичности нет, ExecWeave не создаёт это ребро.

## Метаданные usage

Парсер ответа включает в whitelist метаданные вроде tokens prompt/input, completion/output, общего количества tokens, кэшированных prompt tokens, cache-write tokens, количества reasoning tokens и сообщённой стоимости.

## Граница конфиденциальности

ExecWeave не сохраняет текст prompt, содержимое response/completion, текст reasoning, choices или произвольные поля payload провайдера. Credentials endpoints gateway, query parameters и fragments удаляются из сохраняемой идентичности endpoint.

Исходная запрошенная модель никогда не угадывается из ответа; она должна быть явно предоставлена вызывающей стороной, когда такое доказательство доступно. Сырой `--shared-request-id`, используемый для точной межслойной идентичности, не сохраняется; ExecWeave хранит только производный SHA-256 hash идентичности в событии связи.

## Граница доказательств

Метаданные ответа gateway доказывают только то, что сообщил этот gateway, или то, какие авторитетные routing-метаданные были предоставлены вместе с ответом. Они не доказывают, какой локальный Agent инициировал запрос, какой процесс model-runtime его обслужил или какой процесс ОС его вызвал.

Поэтому события gateway остаются некаузальными (`causal: false`) и отделены от семантических доказательств Agent/IDE, доказательств Model Runtime и доказательств OS Runtime. Точная общая идентичность запроса может связать наблюдения Gateway и Model Runtime, не сливая их слои. Отдельно выведенная корреляция должна оставаться явно помеченной как inference и никогда не представляться как каузальное доказательство.
