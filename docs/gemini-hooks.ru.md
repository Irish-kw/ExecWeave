<!-- i18n-nav:start -->
<p align="center">
  <a href="gemini-hooks.md">English</a> |
  <a href="gemini-hooks.zh-TW.md">繁體中文</a> |
  <a href="gemini-hooks.zh-CN.md">简体中文</a> |
  <a href="gemini-hooks.ja.md">日本語</a> |
  <a href="gemini-hooks.ko.md">한국어</a> |
  <a href="gemini-hooks.fr.md">Français</a> |
  <a href="gemini-hooks.de.md">Deutsch</a> |
  <strong>Русский</strong>
</p>
<!-- i18n-nav:end -->

# Hooks Gemini CLI

ExecWeave может принимать lifecycle/tool hooks Gemini CLI как семантические доказательства провайдера и объединять их с независимо собранными runtime-доказательствами ОС.

Адаптер намеренно консервативен: hook-доказательства Gemini описывают, что провайдер сообщает на уровне Agent / Tool. Сами по себе они не доказывают, какой процесс ОС выполнил работу.

## Поддерживаемые hook-события

Текущий адаптер обрабатывает:

- `SessionStart`
- `BeforeTool`
- `AfterTool`

Gemini CLI передаёт вход hook как JSON через `stdin`. Успешный command hook должен вернуть корректный JSON через `stdout`, поэтому ExecWeave при успехе возвращает ровно `{}`, а предупреждения отправляет только в `stderr`.

Сгенерируйте фрагмент настроек:

```bash
execweave-gemini-hook --print-config
```

Объедините полученный объект `hooks` с `settings.json` Gemini CLI.

Сгенерированная конфигурация наблюдает все инструменты через matchers `BeforeTool` / `AfterTool` и не блокирует и не переписывает вызов инструмента.

## Запись одной командой

После настройки hooks:

```bash
execweave-gemini-record --open -- gemini
```

Recorder привязывает дочерний процесс Gemini к sidecar конкретного запуска через `EXECWEAVE_SEMANTIC_SIDECAR`, затем использует общий provider-record pipeline:

```text
runtime evidence
      +
Gemini hook evidence
      ↓
validated semantic merge
      ↓
conservative correlation
      ↓
graph + viewer
```

Интегрированный с провайдером запуск может создать:

```text
.execweave/runs/<run-id>/
├── events.jsonl
├── graph.json
├── viewer.html
├── semantic.jsonl
├── events.semantic.jsonl
├── graph.semantic.json
├── viewer.semantic.html
├── events.correlated.jsonl
├── graph.correlated.json
└── viewer.correlated.html
```

Сырые runtime-доказательства и sidecar провайдера остаются раздельными. Корреляция создаёт производный поток, а не переписывает наблюдаемые входные доказательства.

## Отображение событий

### Начало сессии

`SessionStart` становится доказательством сессии провайдера:

```text
Gemini CLI --STARTED_PROVIDER_SESSION--> provider_session
```

ExecWeave сохраняет метаданные сессии, необходимые для атрибуции, но не читает и не копирует transcript, на который указывает `transcript_path`.

### BeforeTool

Hook `BeforeTool` создаёт семантические отношения, например:

```text
Gemini CLI --REQUESTED_TOOL_CALL--> tool_call
tool_call --USES_TOOL--> tool
```

Для встроенного инструмента `run_shell_command` поле `tool_input.command` представляется как:

```text
tool_call --DECLARED_COMMAND--> command
```

Это доказательство команды может участвовать в той же консервативной корреляции Tool → Process, что и у других адаптеров провайдера.

Для выбранных файловых инструментов, например `read_file`, `write_file` и `replace`, ExecWeave может записать объявленный целевой путь как семантические метаданные. Содержимое файла не захватывается.

### MCP-инструменты

Когда Gemini CLI предоставляет `mcp_context`, ExecWeave использует явно сообщённую провайдером идентичность сервера/инструмента:

```text
tool_call --VIA_MCP--> mcp_server
mcp_server --EXPOSES_TOOL--> tool
```

Адаптер не сохраняет команду запуска MCP, аргументы или URL из `mcp_context`, поскольку эти поля могут содержать чувствительные метаданные соединения или credentials.

### AfterTool

`AfterTool` записывается как отдельное наблюдение `tool_result`.

Если `tool_response.error` непустой, адаптер записывает сообщённый провайдером сигнал ошибки. Иначе записывается нейтральный сигнал возвращённого результата.

ExecWeave **не хранит** сырой `llmContent`, `returnDisplay` или тело ошибки провайдера.

## Нет уникального ID вызова инструмента Gemini

Текущая схема входа hook Gemini CLI предоставляет `tool_name`, `tool_input` и необязательный MCP context, но не предоставляет уникальный ID вызова инструмента, общий для `BeforeTool` и `AfterTool`.

Поэтому ExecWeave **не утверждает** прямое ребро идентичности BeforeTool → AfterTool.

Каждый запрос `BeforeTool` получает локальную идентичность, привязанную к временной метке. `AfterTool` создаёт независимый узел результата. Оба могут содержать детерминированный `tool_fingerprint`, вычисленный из имени инструмента + нормализованного входа, как диагностическую подсказку, но этот fingerprint **не считается идентичностью вызова**. Повторные одинаковые команды должны оставаться различимыми.

## Корреляция Tool → Process

Hooks Gemini не предоставляют PID дочернего процесса ОС, необходимый для доказательства атрибуции Tool → Process.

Коррелированный граф может содержать:

```text
tool_call --CORRELATED_WITH_PROCESS--> process
```

только если существующий ограниченный matcher находит ровно один однозначно подтверждённый кандидат процесса из независимых runtime-доказательств.

Каждый такой мост остаётся:

```text
inferred: true
causal: false
```

Неоднозначные, несопоставленные, составные, shell-builtin или неподдерживаемые команды не создают мост.

Коррелированный Viewer показывает counts matched / ambiguous / no-match / unsupported, чтобы отсутствующее ребро не интерпретировалось незаметно как «ничего не произошло».

## Граница конфиденциальности

Нативный адаптер Gemini намеренно избегает:

- содержимого prompt
- содержимого transcript
- сырого содержимого результатов инструментов
- сырых тел ошибок провайдера
- деталей команд / аргументов / URL MCP
- содержимого файлов

При этом он может сохранять метаданные вроде текста команды, объявленных путей файлов, имён инструментов, идентификаторов сессий и имён MCP-сервера/инструмента. Проверяйте артефакты перед распространением.

## Поведение при ошибках

`execweave-gemini-hook` по умолчанию fail-open. Ошибки телеметрии записываются в `stderr` и не блокируют вызов инструмента Gemini намеренно.

Используйте `--strict` только когда нужен ненулевой код выхода телеметрии.

## Текущий upstream-контракт

Этот адаптер следует текущей документации hooks Gemini CLI:

- https://github.com/google-gemini/gemini-cli/blob/main/docs/hooks/reference.md
- https://github.com/google-gemini/gemini-cli/blob/main/docs/hooks/index.md

Схемы hooks провайдера могут развиваться. ExecWeave записывает только поля, реально доставленные провайдером, и сохраняет независимый runtime-сбор ОС полезным даже при недоступности семантических hooks.

См. также [`Семантическая телеметрия`](semantic-telemetry.ru.md).
