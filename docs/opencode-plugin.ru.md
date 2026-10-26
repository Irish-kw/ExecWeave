# OpenCode Plugin

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

ExecWeave интегрируется с OpenCode через project-local plugin. OpenCode предоставляет точные `sessionID + callID` на tool before/after hooks, поэтому один логический tool call можно идентифицировать без heuristic pairing. Эта identity остаётся provider-level evidence и не является OS PID.

## Установка и запись

```bash
execweave-opencode-plugin --install
execweave-opencode-record --open -- opencode
```

Сгенерированный plugin устанавливается в `.opencode/plugins/execweave.ts`. ExecWeave не перезаписывает существующий plugin, если явно не указан `--force`.

## Полная поверхность наблюдения

v0.6.5 не ограничивается старым трёхсобытийным minimal-metadata contract. Сгенерированный plugin/hook path может сохранять content, который OpenCode предоставляет через chat messages, tool execution before/after, model-context/system transforms, завершённый assistant text, provider bus events, request headers после credential filtering, tool definitions, commands, permission requests и compaction context, когда соответствующие hooks срабатывают.

Типичные логические graph relationships по-прежнему включают Agent → tool call, tool call → tool, declared command/target и returned-result observations. Content storage не изменяет их evidence semantics.

## Full-fidelity content

Полные значения, предоставленные OpenCode plugin, сохраняются в локальном content-addressed store и referenced из semantic JSONL sidecar. Regression coverage включает полные chat message/parts, tool args/results, model context, system prompt values, assistant text, provider events, tool definitions, command arguments/parts, permission data и compaction prompts/context.

Из соответствующих headers/provider-metadata projections фильтруются известные transport credentials, например authorization/cookie. Чувствительные application-level значения внутри tool args, messages, results или других content values сохраняются. Не следует считать full-fidelity content автоматически redacted.

## Корреляция Tool к Process

`sessionID + callID` доказывает точную логическую call identity внутри OpenCode. Это не доказывает, какой OS process выполнил call. Tool → Process остаётся отдельно выведенным консервативным bridge и создаётся только когда независимое runtime evidence однозначно поддерживает один process.

```text
inferred: true
causal: false
```

Неоднозначные или unsupported calls не создают bridge.

## Конфиденциальность и граница доказательств

OpenCode run evidence может содержать prompts/messages, system/context data, tool arguments/output, commands, permission patterns, provider event content, paths, identifiers и чувствительные application-level values. Проверяйте run directory перед публикацией.

Plugin доказывает то, что OpenCode раскрыл на semantic/provider layer. Runtime collectors независимо устанавливают process/file/network observations. Full-fidelity provider content сам по себе не доказывает command execution, завершённый file access или byte-level data flow.
