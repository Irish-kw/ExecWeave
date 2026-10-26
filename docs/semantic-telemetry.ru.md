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

ExecWeave объединяет семантические наблюдения провайдеров и фреймворков с независимо собранными доказательствами работы ОС, не переписывая исходный runtime-capture. Доказательства провайдера описывают, что показал Agent, инструмент, gateway или интеграция model runtime; доказательства ОС описывают, что наблюдал системный collector. Корреляция остаётся отдельным производным слоем и никогда молча не повышается до причинного доказательства.

## Workflow

Provider-adapter пишет семантический sidecar, привязанный к run, после чего ExecWeave валидирует новый объединённый поток:

```bash
execweave semantic-merge run.jsonl semantic.jsonl --output run.semantic.jsonl
execweave validate run.semantic.jsonl
execweave graph run.semantic.jsonl --output run.semantic.graph.json
```

`run.jsonl` никогда не изменяется командой `semantic-merge`. Run-bound recorder сохраняет runtime, semantic и correlated artifacts в отдельных файлах.

## Full-fidelity content в v0.6.5

Семантическая телеметрия больше не ограничивается небольшими metadata-summary. Если поддерживаемая точка интеграции явно предоставляет content, v0.6.5 может сохранить полное предоставленное значение в локальном content-addressed store и поместить в JSONL-event только ссылку.

```text
<run-root>/content/sha256/<sha256>.<json|txt|bin>
```

Content reference хранит SHA-256, относительный путь, media type, размер, тип content, representation и признак полноты относительно точки интеграции. `complete_from_source: true` означает, что ExecWeave сохранил всё значение, которое получил; это **не** означает, что провайдер раскрыл скрытое состояние модели, невидимый финальный wire request или поле, которого не было в источнике.

Поддерживаемые native adapters используют этот механизм для content, реально предоставленного hook/API surface: prompts, tool inputs/results, assistant/model responses, reasoning/thinking text при явном предоставлении, file content из provider hook и request/response objects там, где это разрешено контрактом adapter.

Компактный semantic summary остаётся пригодным для graph materialization даже при сбое content store. Native hook adapters по умолчанию fail-open, поэтому ошибка хранения не должна намеренно блокировать операцию Agent.

## Граница доказательств

Semantic content — это наблюдаемое provider/integration evidence, а не OS causality. Сохранённый tool input не доказывает, что процесс его выполнил; file body из hook не доказывает завершённое чтение ОС; request/response pair, переданная CLI, не означает прозрачного сетевого перехвата.

Tool → Process bridges создаются только отдельным консервативным correlation layer и остаются:

```text
inferred: true
causal: false
```

Неизвестная или неоднозначная attribution не создаёт bridge. Byte-level data flow и exfiltration не выводятся лишь из одновременного наличия file и network observations.

## Конфиденциальность

Full-fidelity content намеренно чувствителен. Не следует считать, что prompt text, tool arguments, tool output, model responses, file content или чувствительные application-level значения были удалены. Content store сохраняет полное значение, предоставленное поддерживаемой точкой интеграции.

ExecWeave фильтрует известные transport credentials из некоторых provider-metadata projections, когда это определено контрактом adapter, но это не общий secret scanner и не удаляет чувствительные значения, встроенные в content payload. Content blobs по умолчанию остаются локальными и не вставляются напрямую в graph events, однако всё равно являются частью evidence run и должны быть проверены перед публикацией.

Документация конкретных провайдеров точно определяет наблюдаемые поля. См. документы Claude Code, Codex, Antigravity, Cursor, OpenCode, Inference Gateway и Model Runtime.
