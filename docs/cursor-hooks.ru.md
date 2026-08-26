# Hooks Cursor

<p align="center">
  <a href="cursor-hooks.md">English</a> |
  <a href="cursor-hooks.zh-TW.md">繁體中文</a> |
  <a href="cursor-hooks.zh-CN.md">简体中文</a> |
  <a href="cursor-hooks.ja.md">日本語</a> |
  <a href="cursor-hooks.ko.md">한국어</a> |
  <a href="cursor-hooks.fr.md">Français</a> |
  <a href="cursor-hooks.de.md">Deutsch</a> |
  <strong>Русский</strong>
</p>

ExecWeave использует нативную hook-поверхность Cursor для добавления логических доказательств Agent / Tool / Command в runtime-граф, не считая метаданные провайдера доказательством причинности ОС.

## Быстрый старт

Сгенерируйте конфигурацию hook и добавьте её в настройки hooks Cursor:

```bash
execweave-cursor-hook --print-config
```

Затем запишите запуск Cursor:

```bash
execweave-cursor-record --open -- cursor
```

Recorder, привязанный к запуску, сохраняет runtime-, semantic- и correlated-артефакты отдельно.

## События

Базовая реализация обрабатывает:

- `sessionStart`
- `preToolUse`
- `postToolUse`
- `postToolUseFailure`

Cursor предоставляет стабильный `tool_use_id`, поэтому `preToolUse` и соответствующий post hook могут использовать одну и ту же точную логическую идентичность `tool_call`.

Типичные семантические рёбра:

```text
agent --USED_MODEL--> model
agent --REQUESTED_TOOL_CALL--> tool_call
tool_call --USES_TOOL--> tool
tool_call --DECLARED_COMMAND--> command
tool_call --DECLARED_TARGET--> file
tool_call --TOOL_CALL_RETURNED--> tool
```

`postToolUseFailure` представляется отдельно как `TOOL_CALL_FAILED`.

## Корреляция Tool → Process

Hook-доказательства Cursor не предоставляют PID дочернего процесса ОС. Поэтому вызов Shell не превращается напрямую в процессное ребро.

Когда runtime-доказательства независимо показывают ровно один однозначно подтверждённый процесс, ExecWeave может вывести:

```text
tool_call --CORRELATED_WITH_PROCESS--> process
```

Мост всегда остаётся:

```text
inferred: true
causal: false
```

Неоднозначные или неподдерживаемые вызовы не создают мост.

## Граница конфиденциальности

Адаптер намеренно не сохраняет текст prompt, пути transcript, email пользователя, сообщения агента или вывод инструмента. Он сохраняет только идентификаторы и объявленные метаданные, необходимые для наблюдаемости: идентичность модели, ID conversation/generation, имя/ID использования инструмента, команду и объявленный путь файла.

Команды и пути всё ещё могут быть чувствительными. Проверяйте артефакты перед распространением.

## Граница доказательств

Hook Cursor доказывает, что Cursor сообщил на семантическом уровне. Он не доказывает, что объявленная команда была выполнена, что к объявленному файлу действительно обращались или что данные перемещались между ресурсами. Источником runtime-доказательств остаются сборщики ОС.
