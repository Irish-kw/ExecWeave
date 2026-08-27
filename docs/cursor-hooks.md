# Cursor Hooks

<!-- i18n-nav:start -->
<p align="center">
  <strong>English</strong> |
  <a href="cursor-hooks.zh-TW.md">繁體中文</a> |
  <a href="cursor-hooks.zh-CN.md">简体中文</a> |
  <a href="cursor-hooks.ja.md">日本語</a> |
  <a href="cursor-hooks.ko.md">한국어</a> |
  <a href="cursor-hooks.fr.md">Français</a> |
  <a href="cursor-hooks.de.md">Deutsch</a> |
  <a href="cursor-hooks.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

ExecWeave uses Cursor's native hook surface to add provider semantic/content evidence to a run without treating that evidence as OS causality.

## Quick start

```bash
execweave-cursor-hook --print-config
execweave-cursor-record --open -- cursor
```

The run-bound recorder keeps runtime, semantic, and correlated artifacts separate.

## Observation surface

The v0.6.5 hook configuration covers the broader Cursor lifecycle surface, including session start/end, tool before/after/failure, subagents, shell and MCP execution, file reads/edits, prompt submission, compaction/stop, Agent response/thought events, and tab file read/edit events when Cursor exposes them.

Cursor provides stable logical tool-call identity for its tool hooks. That identity is not an OS PID.

## Full-fidelity content

When Cursor explicitly supplies a content value, v0.6.5 stores the complete supplied value in the local content-addressed store and places only its reference in the semantic JSONL event.

Covered regressions include complete prompt text, tool input/output and failure text, shell command/output, MCP command/input/result, file content supplied by read hooks, edit structures, final Agent responses, provider-labeled thought text, and subagent summaries.

These fields are preserved as provider observations with their evidence limitations. For example, content supplied by `beforeReadFile` does not assert that an OS read completed, and an edit structure does not assert a complete post-edit file snapshot unless the provider actually supplied one.

Known transport credentials are filtered from the provider-metadata projection where defined. Secrets embedded inside content values are preserved. Full-fidelity content is not a general secret-redaction layer.

## Tool to process correlation

Cursor hook evidence does not provide the child OS PID. A Shell call therefore becomes a process bridge only when independent runtime evidence yields one uniquely supported candidate:

```text
inferred: true
causal: false
```

Ambiguous or unsupported calls produce no bridge. Stable provider tool-call identity proves logical identity inside Cursor, not machine-level process attribution.

## Privacy and evidence boundary

Cursor run evidence can contain prompts, tool arguments/results, shell output, file content, edit data, assistant responses, provider-labeled thought text, commands, paths, identifiers, MCP values, and embedded application secrets. Review the complete run directory before sharing it.

A Cursor hook proves only what Cursor reported or supplied at the provider layer. It does not by itself prove that a declared command executed, that a file was accessed by a specific process, or that bytes flowed between resources.
