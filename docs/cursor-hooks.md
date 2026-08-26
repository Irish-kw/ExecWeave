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

ExecWeave uses Cursor's native hook surface to add logical Agent / Tool / Command evidence to the runtime graph without treating provider metadata as OS causality.

## Quick start

Generate a hook configuration and add it to your Cursor hook settings:

```bash
execweave-cursor-hook --print-config
```

Then record a Cursor run:

```bash
execweave-cursor-record --open -- cursor
```

The run-bound recorder preserves runtime, semantic, and correlated artifacts separately.

## Events

The baseline consumes:

- `sessionStart`
- `preToolUse`
- `postToolUse`
- `postToolUseFailure`

Cursor exposes a stable `tool_use_id`, so `preToolUse` and the corresponding post hook can share an exact logical `tool_call` identity.

Typical semantic edges are:

```text
agent --USED_MODEL--> model
agent --REQUESTED_TOOL_CALL--> tool_call
tool_call --USES_TOOL--> tool
tool_call --DECLARED_COMMAND--> command
tool_call --DECLARED_TARGET--> file
tool_call --TOOL_CALL_RETURNED--> tool
```

`postToolUseFailure` is represented separately as `TOOL_CALL_FAILED`.

## Tool to process correlation

Cursor hook evidence does not provide the OS child PID. A Shell call therefore does not directly become a process edge.

When runtime evidence independently exposes one uniquely supported process, ExecWeave may derive:

```text
tool_call --CORRELATED_WITH_PROCESS--> process
```

The bridge is always:

```text
inferred: true
causal: false
```

Ambiguous or unsupported calls produce no bridge.

## Privacy boundary

The adapter intentionally does not persist prompt text, transcript paths, user email, agent messages, or tool output. It keeps only the identifiers and declared metadata needed for observability, such as model identity, conversation/generation IDs, tool name/use ID, command, and declared file path.

Commands and paths can still be sensitive. Review artifacts before sharing them.

## Evidence boundary

A Cursor hook proves what Cursor reported at the semantic layer. It does not prove that a declared command executed, that a declared file was actually accessed, or that data moved between resources. OS collectors remain the source for runtime evidence.