<!-- i18n-nav:start -->
<p align="center">
  <a href="semantic-telemetry.md">English</a> |
  <a href="semantic-telemetry.zh-TW.md">繁體中文</a> |
  <a href="semantic-telemetry.zh-CN.md">简体中文</a> |
  <a href="semantic-telemetry.ja.md">日本語</a> |
  <a href="semantic-telemetry.ko.md">한국어</a> |
  <a href="semantic-telemetry.fr.md">Français</a> |
  <a href="semantic-telemetry.de.md">Deutsch</a> |
  <strong>Русский</strong>
</p>
<!-- i18n-nav:end -->

# Семантическая телеметрия

ExecWeave может объединять семантические события провайдеров/фреймворков с доказательствами времени выполнения ОС, не переписывая исходный runtime-capture.

Цель — разместить логические доказательства Agent/Tool/MCP и машинные доказательства process/file/network в одном графе, сохраняя информацию о том, какой источник подтверждает каждое отношение.

```text
agent --REQUESTED_TOOL_CALL--> tool_call --USES_TOOL--> tool
                                                     |
                                                     +--DECLARED_COMMAND--> command

process --OPENED_READ--> file
process --CONNECTED_TO--> network_endpoint
```

Hook провайдера может объяснить, *какое логическое действие было запрошено*. Сборщик времени выполнения объясняет, *что машина действительно сделала*. ExecWeave не превращает временную близость этих наблюдений в доказательство причинности.

## Workflow

Сначала выполните обычный capture ExecWeave:

```bash
execweave run --output run.jsonl -- claude
```

Адаптер или hook провайдера записывает отдельный семантический sidecar, например `semantic.jsonl`.

Объедините sidecar в **новый** валидированный поток событий:

```bash
execweave semantic-merge run.jsonl semantic.jsonl \
  --output run.semantic.jsonl

execweave validate run.semantic.jsonl
execweave graph run.semantic.jsonl \
  --output run.semantic.graph.json
execweave view run.semantic.graph.json \
  --output run.semantic.html \
  --open
```

`semantic-merge` никогда не изменяет `run.jsonl`.

## Контракт записей sidecar

Одна семантическая запись sidecar — один JSON-объект на строку. Адаптер предоставляет только семантическое наблюдение:

```json
{
  "timestamp": "2026-08-25T10:00:02.123Z",
  "event_type": "semantic.tool.called",
  "relation": "REQUESTED_TOOL_CALL",
  "source": {
    "type": "agent",
    "id": "agent:Claude Code",
    "name": "Claude Code",
    "attributes": {}
  },
  "target": {
    "type": "tool_call",
    "id": "tool-call:provider:session:call-id",
    "name": "Bash",
    "attributes": {}
  },
  "attributes": {
    "attribution": "provider_hook",
    "evidence_source": "provider_hook",
    "causal": false
  }
}
```

Sidecar **не обязан** предоставлять:

- ExecWeave `session_id`
- ExecWeave `schema_version`
- непрерывный `sequence`
- `event_id` (необязательно; ExecWeave создаёт его, если поле отсутствует)

`semantic-merge` добавляет идентификатор runtime-сессии, использует текущую схему событий ExecWeave, сортирует семантические и runtime body-события по временной метке, заново назначает одну непрерывную последовательность, сохраняет `session.started` первым и `session.finished` последним и валидирует объединённый результат до записи выходного файла.

## Рекомендуемые семантические сущности

Универсальная схема сущностей ExecWeave уже поддерживает дополнительные типы узлов.

| Тип | Пример ID | Значение |
| --- | --- | --- |
| `agent` | `agent:Claude Code` | Логический агент/клиент |
| `tool_call` | `tool-call:claude:session:tool-use-id` | Один конкретный логический вызов инструмента |
| `tool` | `tool:claude:Bash` | Инструмент, видимый агенту |
| `mcp_server` | `mcp-server:claude:github` | MCP-сервер/интеграция |
| `model` | `model:claude:claude-sonnet` | Идентичность модели, если провайдер её предоставляет |
| `command` | `command:sha256:...` | Метаданные объявленной команды из семантического hook |
| `process_reference` | `process-pid:1234` | Необязательный мост, когда upstream-источник действительно предоставляет PID |

Идентификаторы сущностей должны быть достаточно стабильными, чтобы дедуплицировать повторные семантические наблюдения внутри одного запуска.

## Необязательный мост ссылки на процесс

Некоторые адаптеры провайдера/фреймворка могут знать PID дочернего процесса, но не полный идентификатор процессной сущности ExecWeave. В таком случае они могут создать `process_reference` с наблюдаемым PID.

При слиянии ExecWeave разрешает такие ссылки относительно сущностей процессов, реально наблюдавшихся в runtime-потоке. Разрешение выполняется консервативно:

1. Явный `create_time` может однозначно определить процесс.
2. PID с одним runtime-кандидатом разрешается напрямую.
3. При повторном использовании PID ExecWeave может выбрать единственное наиболее позднее время создания процесса, не превышающее семантическую временную метку.
4. В противном случае узел остаётся `process_reference` с `unresolved: true`, вместо догадки.

Разрешённое событие записывает исходное-to-runtime сопоставление процесса в `attributes.resolved_process_references`.

**Не создавайте `process_reference`, если провайдер не предоставил PID.** Строка команды и близкая временная метка процесса недостаточны, чтобы утверждать точное отношение Tool → Process.

Текущий нативный адаптер Claude Code следует этому правилу: вход hook Claude идентифицирует вызовы инструментов, но не предоставляет PID дочернего процесса, поэтому адаптер не выдумывает рёбра `tool_call --SPAWNED_PROCESS--> process`.

## Граница доказательств и причинности

Текущие адаптеры провайдеров помечают семантические рёбра как `causal: false`, даже когда hook провайдера достоверно сообщает о состоявшемся логическом событии инструмента. В ExecWeave `causal: true` зарезервировано для более сильной атрибуции на уровне выполнения, а не просто для утверждения, что два логических объекта связаны.

Это сохраняет разделение между утверждениями вроде:

```text
Claude Code --REQUESTED_TOOL_CALL--> Bash call       семантическое доказательство провайдера
process     --OPENED_READ---------> ~/.ssh/id_ed25519 runtime-доказательство ОС
```

Сами по себе эти два наблюдения **не доказывают**:

```text
Bash call --caused--> that exact process
file bytes --flowed to--> a network endpoint
```

Любой будущий слой корреляции semantic/runtime должен явно указывать свой метод и уверенность и оставаться отличимым от наблюдаемой OS-атрибуции.

## Граница сессии

Каждая семантическая временная метка должна находиться внутри интервала захваченной runtime-сессии. События вне этого интервала отклоняются. Это не позволяет незаметно прикрепить несвязанную телеметрию провайдера к неправильному запуску.

## Конфиденциальность

Семантические sidecar могут содержать чувствительные метаданные, даже если сам ExecWeave не собирает содержимое файлов. Авторам адаптеров следует предпочитать идентификаторы и ограниченные метаданные полным prompt, аргументам инструментов, выводам инструментов, credentials или секретным значениям.

Адаптер Claude Code намеренно не сохраняет содержимое `Write` или `tool_response`. Объявленные shell-команды сохраняются, поскольку они важны для объяснения выполнения, но их размер ограничен, и их всё равно следует считать потенциально чувствительными метаданными.

Универсальный слой semantic merge не зависит от провайдера. Адаптеры конкретных провайдеров являются отдельными интеграциями и должны точно документировать, какие upstream-поля они используют и какие утверждения эти поля позволяют делать.

См. [`Hooks Claude Code`](claude-code-hooks.ru.md) — первый нативный адаптер провайдера.
