# Cursor Hooks

<!-- i18n-nav:start -->
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
<!-- i18n-nav:end -->

ExecWeave использует native hook surface Cursor, чтобы добавлять provider semantic/content evidence в run, не трактуя это evidence как OS causality.

## Быстрый старт

```bash
execweave-cursor-hook --print-config
execweave-cursor-record --open -- cursor
```

Run-bound recorder сохраняет runtime, semantic и correlated artifacts раздельно.

## Поверхность наблюдения

Конфигурация hooks v0.6.5 охватывает более широкую lifecycle surface Cursor, когда Cursor её предоставляет: session start/end, tool before/after/failure, subagents, shell и MCP execution, file reads/edits, prompt submission, compaction/stop, Agent response/thought events и tab file read/edit events.

Cursor предоставляет стабильную логическую tool-call identity для своих tool hooks. Эта identity не является OS PID.

## Full-fidelity content

Когда Cursor явно предоставляет content value, v0.6.5 сохраняет полное предоставленное значение в локальном content-addressed store и помещает в semantic JSONL event только ссылку.

Regression coverage включает полный prompt text, tool input/output и failure text, shell command/output, MCP command/input/result, file content из read hooks, edit structures, финальные Agent responses, provider-labeled thought text и subagent summaries.

Эти поля сохраняются как provider observations вместе с их ограничениями. Например, content из `beforeReadFile` не доказывает завершённое OS read, а edit structure не доказывает полный post-edit snapshot, если provider его фактически не предоставил.

Из provider-metadata projection фильтруются известные transport credentials там, где это определено контрактом. Чувствительные значения внутри content сохраняются. Full-fidelity content не является общим слоем secret redaction.

## Корреляция Tool к Process

Cursor hook evidence не предоставляет child OS PID. Поэтому Shell call становится process bridge только тогда, когда независимое runtime evidence однозначно поддерживает одного кандидата:

```text
inferred: true
causal: false
```

Неоднозначные или unsupported calls не создают bridge. Стабильная provider tool-call identity доказывает логическую identity внутри Cursor, а не machine-level process attribution.

## Конфиденциальность и граница доказательств

Cursor run evidence может содержать prompts, tool arguments/results, shell output, file content, edit data, assistant responses, provider-labeled thought text, commands, paths, identifiers, MCP values и чувствительные application-level values. Проверяйте весь run directory перед публикацией.

Cursor hook доказывает только то, что Cursor сообщил или предоставил на provider layer. Сам по себе он не доказывает выполнение объявленной команды, доступ к файлу конкретным процессом или передачу bytes между resources.
