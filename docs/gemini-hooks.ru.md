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

ExecWeave принимает hooks Gemini CLI как provider semantic/content evidence и сохраняет этот слой отдельно от независимо собранного OS runtime evidence. Hooks Gemini объясняют, что именно раскрыл provider; сами по себе они не доказывают, какой OS process выполнил действие.

## Текущая поверхность hooks

`execweave-gemini-hook --print-config` сейчас регистрирует:

- `SessionStart`
- `SessionEnd`
- `BeforeAgent`
- `AfterAgent`
- `BeforeModel`
- `AfterModel`
- `BeforeToolSelection`
- `BeforeTool`
- `AfterTool`
- `PreCompress`
- `Notification`

Tool hooks используют provider matcher surface, а сгенерированный command hook по умолчанию fail-open. Настройте hooks и запишите run:

```bash
execweave-gemini-hook --print-config
execweave-gemini-record --open -- gemini
```

## Full-fidelity content

v0.6.5 сохраняет полные значения, явно предоставленные Gemini hook, в локальном content-addressed store. В зависимости от события это может включать user prompt, полный model request object, model response/chunk object, tool input, tool response с `llmContent` / `returnDisplay` / provider error fields, финальный Agent response и другие provider payload values, раскрытые hook.

Semantic JSONL sidecar хранит content references вместо больших inline-копий. Повторяющиеся одинаковые значения deduplicate по SHA-256.

Provider-metadata projections исключают распознанные transport-credential fields, например authorization headers. Эта фильтрация не очищает application-level values внутри полного content. Например, чувствительное значение внутри tool input или model request остаётся частью сохранённого content.

`content_complete_from_source: true` означает, что ExecWeave сохранил полное поле/значение, которое получил. Это не утверждение, что Gemini раскрыл hidden final wire request, internal model state или этап, отсутствовавший в hook payload.

## Tool identity и correlation

Gemini не предоставляет один уникальный tool-call ID, общий между `BeforeTool` и `AfterTool`. Поэтому ExecWeave не создаёт прямой before/after identity edge. Deterministic tool fingerprint может сохраняться как диагностическая подсказка, но повторные одинаковые вызовы остаются отдельными observations.

Hooks Gemini также не предоставляют child OS PID. Поэтому Tool → Process bridges выводятся только тогда, когда независимое runtime evidence однозначно поддерживает одного кандидата:

```text
inferred: true
causal: false
```

Неоднозначные, unmatched, compound, shell-builtin или unsupported commands не создают bridge.

## Конфиденциальность и граница доказательств

Gemini content artifacts могут содержать prompts, полные model request/response values, tool inputs/results, file content, возвращённый tools, MCP/application fields, финальные responses, identifiers, commands, paths и встроенные чувствительные значения. Проверяйте run directory перед публикацией.

ExecWeave не читает `transcript_path` автоматически только потому, что hook его сообщил. Сохранённое provider value также не доказывает OS execution, завершённый file access или byte-level data flow. Независимое runtime evidence и явно отмеченная correlation остаются отдельными слоями.
