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

# Claude Code Hooks

ExecWeave включает нативный Claude Code command-hook adapter, который записывает semantic/content evidence, предоставленные provider, в локальный sidecar и сохраняет их отдельно от независимой OS runtime evidence. Provider hooks объясняют, что именно Claude Code явно раскрыл; они не заменяют portable или Linux `strace` collector и сами по себе не устанавливают OS process causality.

**Текущая hook surface.** `execweave-claude-hook --print-config` сейчас регистрирует:

- `SessionStart`
- `UserPromptSubmit`
- `MessageDisplay`
- `PreToolUse`
- `PostToolUse`
- `PostToolUseFailure`
- `PostToolBatch`
- `SubagentStart`
- `SubagentStop`
- `Stop`
- `StopFailure`

Конфигурация hooks по умолчанию fail-open: ошибки telemetry/storage сообщаются, но не должны намеренно блокировать Agent operation. Для отладки можно использовать `--strict`, если требуется non-zero exit при ошибке telemetry.

## Настройка и запись

Установите ExecWeave, сгенерируйте поддерживаемый settings fragment, объедините его с Claude Code settings, затем используйте run-bound recorder:

```bash
execweave-claude-hook --print-config
execweave-claude-record --open -- claude
```

`execweave-claude-record` через child environment привязывает уникальный semantic sidecar к конкретному run. Runtime, semantic и correlated evidence остаются отдельными artifacts.

```text
runtime evidence
    ↓ semantic merge
runtime + semantic evidence
    ↓ conservative correlation
runtime + semantic + inferred correlation
```

Если ни одно поддерживаемое Claude hook event не приходит, recorder возвращается к runtime-only artifacts. Если semantic evidence есть, но не остаётся ровно одного достаточно поддержанного Tool → Process candidate, bridge не создаётся.

## Full-fidelity content в v0.6.5

Claude adapter больше не ограничен bounded metadata summaries. Когда hook явно предоставляет content, v0.6.5 сохраняет полное значение, предоставленное source, в локальном SHA-256 content-addressed store, а в semantic sidecar записывает reference.

Regression coverage включает:

- полный `UserPromptSubmit.prompt`, включая большие значения;
- полный tool input, включая `Write`/`Edit` content и application-level values внутри input object;
- полный structured `PostToolUse.tool_response`, если он предоставлен;
- model-visible tool-result serialization, предоставленный через `PostToolBatch`;
- assistant text/delta из `MessageDisplay` с доступными ordering metadata;
- финальные assistant messages main Agent и subagents, предоставленные stop events.

Известные transport credentials фильтруются только из отдельной provider-metadata projection, когда adapter умеет их распознавать. Эта фильтрация **не очищает сам full content**. Secret внутри prompt, tool input, file body, tool result или assistant message остаётся частью сохранённой full-fidelity evidence.

`content_complete_from_source: true` означает, что ExecWeave сохранил полное значение, которое предоставил Claude hook. Это не означает, что ExecWeave прочитал не предоставленный transcript, наблюдал hidden model state или захватил provider stage, отсутствующий в hook payload.

## Logical entities и tool identity

Claude hook events могут материализовать provider-level relationships, например:

```text
Claude Code --REQUESTED_TOOL_CALL--> tool_call
tool_call --USES_TOOL-------------> tool
tool_call --DECLARED_COMMAND------> command
tool_call --DECLARED_TARGET-------> file metadata
tool_call --VIA_MCP---------------> mcp_server
Claude Code --SPAWNED_SUBAGENT----> subagent
```

`tool_use_id` может идентифицировать logical tool invocation, но не является OS PID. MCP-имена по provider convention `mcp__<server>__<tool>` при наличии нормализуются в отдельные MCP-server/tool entities.

## Tool → Process correlation boundary

Claude command-hook input не предоставляет реальный child process PID, созданный вызовом Bash/PowerShell tool. Поэтому ExecWeave не создаёт observed causal process edge только на основании provider hook data.

Derived bridge может появиться лишь тогда, когда bounded runtime matcher находит ровно одного поддержанного process candidate:

```text
tool_call --CORRELATED_WITH_PROCESS--> process
```

Каждый такой bridge сохраняет следующую семантику:

```json
{
  "causal": false,
  "inferred": true,
  "confidence_semantics": "heuristic_score_not_probability"
}
```

Одной temporal proximity недостаточно. Ambiguous candidates, unsupported compound commands, shell builtins или unmatched declarations не создают bridge. Inference никогда не повышается до observed process attribution.

## Layered artifacts

Run-bound Claude capture может создать:

```text
.execweave/runs/<run-id>/
├── events.jsonl
├── graph.json
├── viewer.html
├── semantic.jsonl
├── content/sha256/...
├── events.semantic.jsonl
├── graph.semantic.json
├── viewer.semantic.html
├── events.correlated.jsonl
├── graph.correlated.json
└── viewer.correlated.html
```

Correlation не переписывает исходную runtime или provider evidence.

## Standalone sidecar

Вне run-bound recorder стандартный Claude sidecar scoped по session:

```text
<cwd>/.execweave/semantic/claude/<Claude-session-id>.jsonl
```

Путь можно переопределить через `EXECWEAVE_SEMANTIC_SIDECAR` или `--sidecar`. Для parallel captures рекомендуется отдельный session/run-specific path.

## Privacy и evidence boundary

Claude full-fidelity artifacts могут содержать prompts, commands, file paths, `Write`/`Edit` bodies, tool arguments/results, assistant text, subagent responses, identifiers и application-level secrets. Рассматривайте весь run directory как sensitive data и проверяйте его перед публикацией.

Provider content остаётся provider evidence. Сохранённый tool input не доказывает, что tool был выполнен; сохранённый file body не доказывает, что конкретный OS process его прочитал или записал; сохранённый tool result не доказывает byte-level data flow. Более сильные claims требуют OS collectors и явно маркированной correlation evidence.

## Ручные merge и correlation

Если runtime и semantic files уже есть, доступен generic pipeline:

```bash
execweave semantic-merge run.jsonl semantic.jsonl --output run.semantic.jsonl
execweave validate run.semantic.jsonl
execweave correlate run.semantic.jsonl --output run.correlated.jsonl
execweave validate run.correlated.jsonl
```

Generic evidence/content contract и process-reference rules см. в [`Semantic Telemetry`](semantic-telemetry.ru.md).
