# OpenCode Plugin

<!-- i18n-nav:start -->
<p align="center">
  <strong>English</strong> |
  <a href="opencode-plugin.zh-TW.md">繁體中文</a> |
  <a href="opencode-plugin.zh-CN.md">简体中文</a> |
  <a href="opencode-plugin.ja.md">日本語</a> |
  <a href="opencode-plugin.ko.md">한국어</a> |
  <a href="opencode-plugin.fr.md">Français</a> |
  <a href="opencode-plugin.de.md">Deutsch</a> |
  <a href="opencode-plugin.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

ExecWeave integrates with OpenCode through a project-local plugin. OpenCode exposes exact `sessionID + callID` values on `tool.execute.before` and `tool.execute.after`, so one logical tool call can be identified without heuristically pairing lifecycle events.

## Install

Install the generated plugin into the current project:

```bash
execweave-opencode-plugin --install
```

It creates:

```text
.opencode/plugins/execweave.ts
```

OpenCode automatically loads project plugins from that directory. ExecWeave refuses to overwrite an existing plugin unless `--force` is supplied.

Then record a run:

```bash
execweave-opencode-record --open -- opencode
```

## Captured semantic evidence

The baseline plugin emits minimal metadata for:

- `chat.message`
- `tool.execute.before`
- `tool.execute.after`

Typical graph relationships are:

```text
agent --USED_MODEL--> model
agent --REQUESTED_TOOL_CALL--> tool_call
tool_call --USES_TOOL--> tool
tool_call --DECLARED_COMMAND--> command
tool_call --DECLARED_TARGET--> file
tool_call --TOOL_CALL_RETURNED--> tool
```

The OpenCode `callID` is used directly in the `tool_call` identity.

## Privacy boundary

OpenCode's after-hook can see tool output, but the generated ExecWeave plugin deliberately does not forward `output.output` or `output.metadata`.

Arguments are reduced before they leave the plugin:

- `bash`: declared `command`
- file-oriented tools: path-like fields such as `filePath`, `file_path`, or `path`
- optional working-directory metadata

Raw write content, chat message parts, and tool output are not sent to the ExecWeave hook.

## Tool to process correlation

`callID` proves logical call identity inside OpenCode; it is not an OS PID. Tool → Process remains a derived conservative bridge and is created only when runtime evidence yields one uniquely supported process.

Derived bridges remain `inferred: true` and `causal: false`.

## Evidence boundary

The plugin reports OpenCode semantic intent. Runtime collectors independently establish process/file/network observations. ExecWeave never treats the provider plugin as proof that a declared command or file action actually occurred.