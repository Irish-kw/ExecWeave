<!-- i18n-nav:start -->
<p align="center">
  <a href="codex-hooks.md">English</a> |
  <a href="codex-hooks.zh-TW.md">繁體中文</a> |
  <a href="codex-hooks.zh-CN.md">简体中文</a> |
  <a href="codex-hooks.ja.md">日本語</a> |
  <a href="codex-hooks.ko.md">한국어</a> |
  <a href="codex-hooks.fr.md">Français</a> |
  <a href="codex-hooks.de.md">Deutsch</a> |
  <strong>Русский</strong>
</p>
<!-- i18n-nav:end -->

# Lifecycle hooks OpenAI Codex

ExecWeave записывает evidence из lifecycle hooks Codex рядом с независимо собранной OS runtime telemetry. Provider hooks описывают логическую активность Agent/tool; они не предоставляют OS child PID, необходимый для утверждения прямой причинности Tool → Process.

## Текущая поверхность hooks

`execweave-codex-hook --print-config` сейчас регистрирует:

- `PreToolUse`
- `PermissionRequest`
- `PostToolUse`
- `PreCompact`
- `PostCompact`
- `SessionStart`
- `SessionEnd`
- `UserPromptSubmit`
- `SubagentStart`
- `SubagentStop`
- `Stop`

Неизвестные или недоступные upstream events не выдумываются. Hook schemas и dispatch coverage могут меняться между версиями Codex.

Настройте hook и запишите run:

```bash
execweave-codex-hook --print-config
execweave-codex-record --open -- codex
```

Recorder привязывает отдельный semantic sidecar к run и сохраняет runtime, semantic и correlated artifacts раздельно.

## Full-fidelity content

v0.6.5 сохраняет полные content values, которые фактически предоставляет Codex hook, в локальном content-addressed store. В JSONL sidecar записываются ссылки, а не большие inline-копии.

Наблюдаемый content может включать полный `UserPromptSubmit.prompt`, полный `tool_input`, полный `PostToolUse.tool_response`, tool input из permission request и финальные assistant/subagent messages, когда эти поля реально переданы hook. Application-level values внутри payload сохраняются; не следует предполагать, что они были redacted.

Распознанные transport credentials исключаются из отдельной provider-metadata projection там, где adapter умеет их распознавать. Эта фильтрация не переписывает и не очищает сам content payload.

`content_complete_from_source: true` означает, что сохранено полное значение, предоставленное Codex integration point. Это не значит, что ExecWeave прочитал отсутствующий transcript, перехватил невидимый provider request или наблюдал hidden model state.

## Tool identity и correlation

Если Codex предоставляет `tool_use_id`, ExecWeave использует его как логическую identity tool call. Объявленные commands остаются provider semantic evidence. Hook по-прежнему не даёт child OS PID, поэтому bridge Tool → Process создаётся только консервативным correlation stage, когда независимое runtime evidence однозначно поддерживает ровно одного кандидата.

```text
inferred: true
causal: false
```

Неоднозначные, unmatched, shell-builtin, compound или unsupported commands не создают bridge. Сходство timestamp или command string само по себе никогда не повышает provider evidence до OS attribution.

## Конфиденциальность и граница доказательств

Codex semantic/content artifacts могут содержать prompts, commands, tool arguments/results, финальные responses, paths, identifiers и чувствительные application-level values. Рассматривайте весь run directory как чувствительный и проверяйте его перед публикацией.

Adapter не утверждает, что каждый режим исполнения Codex предоставляет полное lifecycle coverage. Отсутствие hooks уменьшает semantic visibility, но не отключает независимый OS runtime collector. Provider hook также не доказывает, что объявленная command была выполнена, file action произошёл или bytes перемещались между resources.
