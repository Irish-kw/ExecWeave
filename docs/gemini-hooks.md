<!-- i18n-nav:start -->
<p align="center">
  <strong>English</strong> |
  <a href="gemini-hooks.zh-TW.md">繁體中文</a> |
  <a href="gemini-hooks.zh-CN.md">简体中文</a> |
  <a href="gemini-hooks.ja.md">日本語</a> |
  <a href="gemini-hooks.ko.md">한국어</a> |
  <a href="gemini-hooks.fr.md">Français</a> |
  <a href="gemini-hooks.de.md">Deutsch</a> |
  <a href="gemini-hooks.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# Gemini CLI Hooks

ExecWeave ingests Gemini CLI hooks as provider semantic/content evidence and keeps that layer distinct from independently collected OS runtime evidence. Gemini hooks explain what the provider exposed; they do not by themselves prove which OS process performed an action.

## Current hook surface

`execweave-gemini-hook --print-config` currently registers:

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

Tool hooks use the provider matcher surface and the generated command hook is fail-open by default. Configure the hooks, then record a run with:

```bash
execweave-gemini-hook --print-config
execweave-gemini-record --open -- gemini
```

## Full-fidelity content

v0.6.5 stores complete values explicitly supplied by the Gemini hook in a local content-addressed store. Depending on the event, this can include the user prompt, full model request object, model response/chunk object, tool input, tool response including `llmContent` / `returnDisplay` / provider error fields, final Agent response, and other provider payload values exposed by the hook.

The JSONL semantic sidecar stores content references rather than large inline copies. Repeated identical values deduplicate by SHA-256.

Provider-metadata projections exclude recognized transport-credential fields such as authorization headers. That filtering does not sanitize application-level values inside full content. For example, a secret embedded in tool input or a model request remains part of the preserved content because full fidelity means preserving the value supplied by the integration point.

`content_complete_from_source: true` means ExecWeave stored the complete field/value it received. It does not assert that Gemini exposed a hidden final wire request, internal model state, or any stage absent from the hook payload.

## Tool identity and correlation

Gemini does not provide one unique tool-call ID shared by `BeforeTool` and `AfterTool`. ExecWeave therefore does not fabricate a direct before/after identity edge. A deterministic tool fingerprint may be retained as a diagnostic hint, but repeated identical calls remain distinguishable observations.

Gemini hooks also do not provide the child OS PID. Tool → Process bridges are therefore derived only when independent runtime evidence yields one uniquely supported candidate:

```text
inferred: true
causal: false
```

Ambiguous, unmatched, compound, shell-builtin, or unsupported commands produce no bridge.

## Privacy and evidence boundary

Gemini content artifacts can contain prompts, full model request/response values, tool inputs/results, file content returned by tools, MCP/application fields, final responses, identifiers, commands, paths, and embedded secrets. Treat the run directory as sensitive and review it before sharing.

ExecWeave does not automatically read `transcript_path` merely because the hook reports it. A stored provider value also does not prove OS execution, completed file access, or byte-level data flow. Independent runtime evidence and explicitly marked correlation remain separate layers.
