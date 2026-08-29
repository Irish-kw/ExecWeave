<!-- i18n-nav:start -->
<p align="center">
  <strong>English</strong> |
  <a href="codex-hooks.zh-TW.md">繁體中文</a> |
  <a href="codex-hooks.zh-CN.md">简体中文</a> |
  <a href="codex-hooks.ja.md">日本語</a> |
  <a href="codex-hooks.ko.md">한국어</a> |
  <a href="codex-hooks.fr.md">Français</a> |
  <a href="codex-hooks.de.md">Deutsch</a> |
  <a href="codex-hooks.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# OpenAI Codex lifecycle hooks

ExecWeave records Codex lifecycle-hook evidence beside independent OS runtime telemetry. Provider hooks describe logical Agent/tool activity; they do not provide the OS child PID required to claim direct Tool → Process causality.

## Current hook surface

`execweave-codex-hook --print-config` currently registers:

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

Unknown or unavailable upstream events are not invented. Hook schemas and dispatch coverage can change between Codex versions.

Configure the hook, then record a run with:

```bash
execweave-codex-hook --print-config
execweave-codex-record --open -- codex
```

The recorder binds a run-specific semantic sidecar and keeps runtime, semantic, and correlated artifacts separate.

## Full-fidelity content

v0.6.5 stores complete content values that the Codex hook actually supplies in a local content-addressed store. The JSONL sidecar contains references rather than large inline copies.

Observed content can include the complete `UserPromptSubmit.prompt`, complete `tool_input`, complete `PostToolUse.tool_response`, permission-request tool input, and final assistant/subagent messages when those fields are delivered by the hook. Application-level values inside those payloads are preserved; do not assume they have been secret-redacted.

Known transport credentials are excluded from the separate provider-metadata projection where the adapter recognizes them. This filtering does not rewrite or sanitize the content payload itself.

`content_complete_from_source: true` means the complete value supplied by the Codex integration point was stored. It does not mean ExecWeave read the transcript file, intercepted an unseen provider request, or observed hidden model state.

## Tool identity and correlation

When Codex provides `tool_use_id`, ExecWeave uses it as logical tool-call identity. Declared commands remain provider semantic evidence. The hook still does not provide the child OS PID, so a Tool → Process bridge is emitted only by the conservative correlation stage when one runtime candidate is uniquely supported.

```text
inferred: true
causal: false
```

Ambiguous, unmatched, shell-builtin, compound, or unsupported commands produce no bridge. Provider evidence is never promoted into OS attribution merely because timestamps or command strings look similar.

## Privacy and evidence boundary

Codex semantic/content artifacts can contain prompts, commands, tool arguments, tool results, final responses, paths, identifiers, and application-level secrets. Treat the entire run directory as sensitive and review it before sharing.

The adapter does not claim that every Codex execution mode exposes complete lifecycle coverage. Missing hooks reduce semantic visibility but do not disable the independent OS runtime collector. A provider hook also does not prove that a declared command executed, that a file action occurred, or that bytes flowed between resources.
