<!-- i18n-nav:start -->
<p align="center">
  <a href="claude-code-hooks.md">English</a> |
  <a href="claude-code-hooks.zh-TW.md">繁體中文</a> |
  <a href="claude-code-hooks.zh-CN.md">简体中文</a> |
  <a href="claude-code-hooks.ja.md">日本語</a> |
  <a href="claude-code-hooks.ko.md">한국어</a> |
  <a href="claude-code-hooks.fr.md">Français</a> |
  <a href="claude-code-hooks.de.md">Deutsch</a> |
  <strong>Русский</strong>
</p>
<!-- i18n-nav:end -->

# Hooks Claude Code

ExecWeave включает нативный адаптер command hooks Claude Code, который записывает семантическую телеметрию провайдера в отдельный локальный JSONL-sidecar.

Адаптер дополняет сбор данных времени выполнения ОС. Он **не заменяет** ни переносный сборщик, ни Linux-`strace`.

## Что записывается

Текущий адаптер обрабатывает следующие события hook Claude Code:

- `SessionStart`
- `PreToolUse`
- `PostToolUse`
- `PostToolUseFailure`
- `SubagentStart`
- `SubagentStop`

Он может материализовать семантические сущности, например:

```text
Claude Code
  |
  +--REQUESTED_TOOL_CALL--> tool_call
  |                           |
  |                           +--USES_TOOL-------> Bash / Read / Edit / Write / ...
  |                           +--DECLARED_COMMAND-> command
  |                           +--DECLARED_TARGET--> file metadata
  |                           +--VIA_MCP----------> MCP server
  |
  +--SPAWNED_SUBAGENT-------> subagent
  +--USED_MODEL-------------> model        when SessionStart exposes one
```

Имена MCP-инструментов, соответствующие соглашению Claude Code `mcp__<server>__<tool>`, нормализуются в отдельные узлы `mcp_server` и `tool`.

## Установка конфигурации hooks

Сначала установите ExecWeave, чтобы консольные команды были доступны:

```bash
python -m pip install -e ".[dev]"
```

Сгенерируйте фрагмент настроек:

```bash
execweave-claude-hook --print-config
```

Объедините созданный объект `hooks` с одним из поддерживаемых JSON-файлов настроек Claude Code:

- `~/.claude/settings.json` для hooks уровня пользователя
- `.claude/settings.json` для общей конфигурации проекта
- `.claude/settings.local.json` для локальной конфигурации проекта, которую не следует commit

Не перезаписывайте несвязанные настройки Claude Code при добавлении фрагмента.

Меню `/hooks` Claude Code позволяет проверить, какие hooks сейчас настроены.

Адаптер использует command hooks и по умолчанию работает fail-open: ошибка разбора телеметрии или файловой системы записывается в stderr, но возвращается успешный статус, чтобы наблюдаемость ExecWeave не блокировала вызов инструмента Agent. `--strict` предназначен для отладки самого hook, а не для runtime-политики безопасности.

## Рекомендуется: runtime + semantic + correlation одной командой

После установки hooks используйте workflow, привязанный к запуску:

```bash
execweave-claude-record --open -- claude
```

В Linux `--backend auto` по-прежнему предпочитает более сильный backend `strace`, когда он доступен. В macOS и Windows используется переносный backend.

`execweave-claude-record` привязывает путь sidecar, уникальный для данного запуска ExecWeave, **внутри отдельного CLI-процесса**. Claude и его hook-команды наследуют этот путь, поэтому двум независимо запущенным процессам ExecWeave Claude-record не нужно угадывать, какой семантический sidecar относится к какому runtime-capture.

Если Claude создаёт семантические события hook, recorder выполняет три явных уровня доказательств:

```text
runtime evidence
    ↓ semantic merge
runtime + semantic evidence
    ↓ conservative correlation
runtime + semantic + inferred correlation
```

Каталог запуска хранит каждый уровень отдельно:

```text
.execweave/runs/<run-id>/
├── events.jsonl              # только runtime-доказательства
├── graph.json                # только runtime-граф
├── viewer.html               # только runtime-viewer
├── semantic.jsonl            # только семантические доказательства hooks Claude
├── events.semantic.jsonl     # валидированный runtime + semantic поток
├── graph.semantic.json       # runtime + semantic граф
├── viewer.semantic.html      # runtime + semantic viewer
├── events.correlated.jsonl   # runtime + semantic + выведенные мосты
├── graph.correlated.json     # граф с выведенными мостами
└── viewer.correlated.html    # viewer с отдельно оформленными выведенными рёбрами
```

`--open` открывает `viewer.correlated.html`, когда были наблюдены семантические доказательства. Если hooks не установлены или ни одно поддерживаемое событие hook не сработало, ExecWeave сообщает `semantic_status: "no_events"`, `correlation_status: "not_run_no_semantic_events"` и возвращается к runtime-only viewer.

Если семантические доказательства существуют, но ни один уникальный безопасный кандидат Tool → Process не остаётся, ExecWeave всё равно создаёт коррелированные артефакты с `correlation_status: "completed_no_matches"`. Выведенное ребро не выдумывается.

Максимальное окно корреляции по умолчанию — 3000 ms. Его можно изменить явно:

```bash
execweave-claude-record \
  --correlation-window-ms 1500 \
  --open \
  -- claude
```

При необходимости явно выберите каталог:

```bash
execweave-claude-record \
  --output-dir my-claude-run \
  --open \
  -- claude
```

Workflow, привязанный к запуску, сохраняет `events.jsonl`, `semantic.jsonl` и `events.semantic.jsonl`. Корреляция записывается только в отдельный поток `events.correlated.jsonl`.

## Расположение sidecar для автономного hook

Когда `execweave-claude-hook` используется вне recorder, привязанного к запуску, каждая сессия Claude по умолчанию пишет в:

```text
<cwd>/.execweave/semantic/claude/<Claude-session-id>.jsonl
```

Идентификатор сессии очищается перед использованием как имя файла.

Путь можно переопределить через:

```text
EXECWEAVE_SEMANTIC_SIDECAR
```

или явной hook-командой, например:

```bash
execweave-claude-hook --sidecar /path/to/semantic.jsonl
```

Для параллельных автономных сессий предпочтителен автоматический путь на уровне сессии вместо направления нескольких сессий Claude в один фиксированный sidecar.

## Продвинутый режим: ручные merge и correlation

Универсальный semantic/correlation pipeline остаётся доступным, если у вас уже есть runtime-capture и семантический sidecar:

```bash
execweave semantic-merge \
  run.jsonl \
  semantic.jsonl \
  --output run.semantic.jsonl

execweave validate run.semantic.jsonl

execweave correlate run.semantic.jsonl \
  --output run.correlated.jsonl

execweave validate run.correlated.jsonl
execweave graph run.correlated.jsonl \
  --output run.correlated.graph.json
execweave view run.correlated.graph.json \
  --output run.correlated.html \
  --open
```

Исходный runtime-поток и семантический sidecar остаются неизменными.

## Граница Tool → Process и корреляция v0.1

Вход command hook Claude Code идентифицирует логический вызов инструмента (`tool_name`, `tool_use_id` и вход инструмента), но не предоставляет фактический PID дочернего процесса, созданного вызовом Bash.

Поэтому нативный адаптер намеренно **не создаёт** наблюдаемое отношение вроде:

```text
Bash tool_call --SPAWNED_PROCESS--> process:1234
```

без дополнительных доказательств.

В одном объединённом графе всё равно могут присутствовать и семантические, и OS-доказательства:

```text
Claude Code --REQUESTED_TOOL_CALL--> Bash call --DECLARED_COMMAND--> "npm test"

session --LAUNCHED--> Claude process --SPAWNED--> shell/process ...
```

ExecWeave не утверждает, что эти пути являются одной каузальной цепочкой только потому, что их временные метки или строки команд похожи.

Этап корреляции v0.1 намеренно консервативен:

- окно поиска ограничено и при наличии данных обрезается результатом инструмента или следующим объявленным вызовом инструмента;
- идентичность executable может подтверждаться точными доказательствами executable/process/cmdline;
- канонические пути executable могут разрешать эквивалентные пути без нечёткого сопоставления имён;
- launcher-процессы могут использовать как fallback точное, непустое, сохраняющее длину сопоставление `argv[1:]`;
- мост создаётся только если остаётся ровно один кандидат процесса;
- неоднозначные кандидаты не создают мост;
- неподдерживаемые составные shell-команды и shell builtins не создают мост;
- нечёткое сопоставление версий/имён не используется;
- одной временной близости никогда недостаточно.

Производный мост представляется как:

```text
tool_call --CORRELATED_WITH_PROCESS--> process
```

и всегда имеет семантику, эквивалентную:

```json
{
  "backend": "inference",
  "causal": false,
  "inferred": true,
  "inference_method": "...",
  "confidence": 0.8,
  "confidence_semantics": "heuristic_score_not_probability",
  "supporting_event_ids": ["..."]
}
```

Точный метод и score зависят от подтверждающих доказательств. Поле confidence — эвристический score для передачи силы доказательств; это явно **не калиброванная вероятность**.

Автономный Viewer отображает выведенные отношения отдельно от каузальных наблюдаемых и некаузальных наблюдаемых рёбер, помечает их `· inferred` и показывает метаданные доказательств при выборе. Выведенный мост никогда не повышается до наблюдаемой атрибуции процесса.

## Поведение в отношении конфиденциальности

Нативный адаптер намеренно избегает нескольких высокорисковых payload:

- содержимое файлов `Write`/`Edit` не сохраняется адаптером;
- `PostToolUse.tool_response` не сохраняется;
- для общих метаданных вызова инструмента сохраняются только имена входных ключей;
- файловые инструменты сохраняют объявленный путь, а не содержимое;
- команды Bash/PowerShell сохраняются, поскольку необходимы для объяснения выполнения, но текст команды ограничен 4096 символами;
- текст ошибки ограничен краткой сводкой.

Пути и команды всё равно могут содержать credentials, tokens, имена клиентов, внутренние hostname или другую чувствительную информацию. Считайте семантические sidecar чувствительными runtime-метаданными и проверяйте их перед распространением.

## Семантика доказательств

Рёбра, создаваемые непосредственно адаптером Claude, включают:

```json
{
  "backend": "semantic",
  "attribution": "claude_hook",
  "evidence_source": "provider_hook",
  "provider": "claude",
  "causal": false
}
```

`causal: false` не означает, что hook Claude выдуман. Это означает, что логическое отношение уровня провайдера не повышается до более сильного утверждения ExecWeave об OS-атрибуции выполнения.

События корреляции — отдельные производные доказательства с `backend: "inference"`, `inferred: true` и `causal: false`. Они не изменяют исходные runtime- или Claude-hook-доказательства.

См. [`Семантическая телеметрия`](semantic-telemetry.ru.md) для универсального контракта merge и правил ссылок на процессы.
