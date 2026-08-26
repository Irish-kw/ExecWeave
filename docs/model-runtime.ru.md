# Интеграции runtime моделей

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

Runtime моделей отделены от семантических адаптеров Agent/IDE и шлюзов инференса. Они описывают, что сообщает локальный или self-hosted сервер инференса; они не доказывают, какой Agent инициировал запрос.

Текущая базовая реализация поддерживает **Ollama**, **llama.cpp**, **vLLM** и **LM Studio**.

## CLI

Преобразовать метаданные финального ответа в события инференса:

```bash
execweave-model-runtime event --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime llamacpp --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime vllm --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime lmstudio --sidecar model-runtime.jsonl
```

Запросить состояние runtime или каталоги моделей:

```bash
execweave-model-runtime probe --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime probe --runtime llamacpp --metrics --sidecar model-runtime.jsonl
execweave-model-runtime probe --runtime vllm --sidecar model-runtime.jsonl
execweave-model-runtime probe --runtime lmstudio --sidecar model-runtime.jsonl
```

Endpoints по умолчанию:

- Ollama: `http://localhost:11434`
- llama.cpp: `http://localhost:8080`
- vLLM: `http://localhost:8000`
- LM Studio: `http://localhost:1234`

## Общий OpenAI-совместимый слой

llama.cpp, vLLM и LM Studio используют один OpenAI-совместимый парсер для usage финальных ответов и метаданных каталога `/v1/models`. Общий слой нормализует `prompt_tokens` / `completion_tokens` в стиле Chat Completions и `input_tokens` / `output_tokens` в стиле Responses, сохраняя только whitelisted token-метаданные, например количества cached tokens и reasoning tokens.

Специфичные для runtime доказательства остаются вне общего парсера. llama.cpp по-прежнему отвечает за собственные timing-поля и Prometheus metrics adapter, не навязывая эту семантику vLLM или LM Studio.

## Модель графа

Runtime-слой может создавать:

```text
model_runtime --SERVED_INFERENCE--> inference_request
inference_request --USED_MODEL--> model
model_runtime --LOADED_MODEL--> model
model_runtime --SERVES_MODEL--> model
model_runtime --ADVERTISES_MODEL--> model
model_runtime --REPORTED_METRICS--> model_runtime_snapshot
```

Эти отношения намеренно имеют разные значения.

## Ollama

Метаданные финального ответа могут включать количества prompt/completion tokens, длительность загрузки, длительность оценки prompt, длительность генерации и finish reason.

Snapshots `/api/ps` могут предоставлять метаданные загруженной модели: размер VRAM, длину контекста, формат, family, размер параметров и quantization. Это представляется как `LOADED_MODEL`, поскольку endpoint сообщает о моделях, загруженных в данный момент.

## llama.cpp

OpenAI-совместимые ответы добавляют нормализованный usage и специфичные для llama.cpp timing/throughput метаданные. `/v1/models` представляется как `SERVES_MODEL`, а необязательный `/metrics` добавляет агрегированные runtime-метрики.

Строки Prometheus с labels пропускаются, потому что labels могут содержать чувствительные локальные пути моделей или другие идентификаторы.

ID моделей llama.cpp, похожие на локальные пути или имена GGUF-файлов, редактируются: полный нативный идентификатор хэшируется для идентичности сущности, а отображается только basename.

## vLLM

vLLM использует общий OpenAI-совместимый слой ответа и каталога моделей. `/v1/models` представляется как `SERVES_MODEL`, поскольку описывает модели, предоставляемые этим serving endpoint.

Текст prompt, response, reasoning, choices, logprobs и сгенерированный token-текст не копируются в события ExecWeave.

## LM Studio

<!-- lmstudio-auto-live-v064 -->
Для автоматического попадания LM Studio в Live Viewer запускайте его под ExecWeave с явно указанным локальным port, например `execweave live --open -- lms server start --port 1234`. Перед launch ExecWeave проверяет, что на endpoint ещё нет совместимого API, и probe `/v1/models` выполняется только после успешного завершения launcher. Relation остаётся `ADVERTISES_MODEL` и не повышается до `LOADED_MODEL`.

LM Studio использует тот же OpenAI-совместимый парсер ответов, но результат `/v1/models` представляется как `ADVERTISES_MODEL`, а не `LOADED_MODEL`.

Это различие намеренно: LM Studio может сделать загруженные на диск модели видимыми серверу, включая конфигурации, где модель загружается по требованию. Поэтому запись каталога сама по себе не доказывает, что веса модели находились в памяти в момент наблюдения.

## Граница конфиденциальности

ExecWeave намеренно исключает из этого слоя текст prompt, содержимое response, thinking/reasoning text, choices, logprobs и сырые сгенерированные tokens.

Whitelisted метаданные могут включать идентичность модели, идентичность запроса, количества prompt/input tokens, completion/output tokens, общее количество tokens, cached-token counts, reasoning-token counts и специфичные runtime timing-метаданные. Абсолютные локальные пути моделей редактируются для поддерживаемых OpenAI-совместимых локальных runtimes; llama.cpp использует более строгое редактирование GGUF-путей.

Агрегированные runtime-метрики автоматически не атрибутируются конкретному Agent или конкретному запросу инференса.

## Граница доказательств

Runtime API доказывает только то, что сообщил этот сервер инференса. Оно само по себе не доказывает, какой Agent инициировал запрос, какой gateway его маршрутизировал или какой процесс ОС его вызвал.

Межслойная идентичность требует явных общих идентификаторов или отдельно определённого консервативного механизма корреляции. Производная корреляция должна оставаться помеченной как inference, а не как каузальное доказательство.
