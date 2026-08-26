# Плагин OpenCode

<!-- i18n-nav:start -->
<p align="center">
  <a href="opencode-plugin.md">English</a> |
  <a href="opencode-plugin.zh-TW.md">繁體中文</a> |
  <a href="opencode-plugin.zh-CN.md">简体中文</a> |
  <a href="opencode-plugin.ja.md">日本語</a> |
  <a href="opencode-plugin.ko.md">한국어</a> |
  <a href="opencode-plugin.fr.md">Français</a> |
  <a href="opencode-plugin.de.md">Deutsch</a> |
  <strong>Русский</strong>
</p>
<!-- i18n-nav:end -->

ExecWeave интегрируется с OpenCode через локальный для проекта плагин. OpenCode предоставляет точные значения `sessionID + callID` в `tool.execute.before` и `tool.execute.after`, поэтому один логический вызов инструмента можно идентифицировать без эвристического сопоставления lifecycle-событий.

## Установка

Установите сгенерированный плагин в текущий проект:

```bash
execweave-opencode-plugin --install
```

Он создаёт:

```text
.opencode/plugins/execweave.ts
```

OpenCode автоматически загружает плагины проекта из этого каталога. ExecWeave отказывается перезаписывать существующий плагин, если не указан `--force`.

Затем запишите запуск:

```bash
execweave-opencode-record --open -- opencode
```

## Захватываемые семантические доказательства

Базовый плагин создаёт минимальные метаданные для:

- `chat.message`
- `tool.execute.before`
- `tool.execute.after`

Типичные отношения графа:

```text
agent --USED_MODEL--> model
agent --REQUESTED_TOOL_CALL--> tool_call
tool_call --USES_TOOL--> tool
tool_call --DECLARED_COMMAND--> command
tool_call --DECLARED_TARGET--> file
tool_call --TOOL_CALL_RETURNED--> tool
```

`callID` OpenCode используется напрямую в идентичности `tool_call`.

## Граница конфиденциальности

After-hook OpenCode может видеть вывод инструмента, но сгенерированный плагин ExecWeave намеренно не передаёт `output.output` или `output.metadata`.

Аргументы сокращаются до того, как покинуть плагин:

- `bash`: объявленный `command`
- файловые инструменты: path-like поля, например `filePath`, `file_path` или `path`
- необязательные метаданные рабочего каталога

Сырое содержимое записи, части chat message и вывод инструмента не отправляются в hook ExecWeave.

## Корреляция Tool → Process

`callID` доказывает логическую идентичность вызова внутри OpenCode; это не PID ОС. Tool → Process остаётся производным консервативным мостом и создаётся только когда runtime-доказательства дают ровно один однозначно подтверждённый процесс.

Производные мосты остаются `inferred: true` и `causal: false`.

## Граница доказательств

Плагин сообщает семантическое намерение OpenCode. Runtime-сборщики независимо устанавливают наблюдения process/file/network. ExecWeave никогда не считает плагин провайдера доказательством того, что объявленная команда или файловое действие действительно произошли.
