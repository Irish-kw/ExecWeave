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

ExecWeave integrates with OpenCode through a project-local plugin. OpenCode exposes exact `sessionID + callID` values on tool before/after hooks, so one logical tool call can be identified without heuristic pairing. That identity remains provider-level evidence and is not an OS PID.

## Install and record

```bash
execweave-opencode-plugin --install
execweave-opencode-record --open -- opencode
```

The generated plugin is installed at `.opencode/plugins/execweave.ts`. ExecWeave refuses to overwrite an existing plugin unless `--force` is explicitly supplied.

## Full observation surface

v0.6.5 is not limited to the old three-event minimal-metadata contract. The generated plugin/hook path can preserve content exposed by OpenCode across chat messages, tool execution before/after, model-context/system transforms, completed assistant text, provider bus events, request headers after credential filtering, tool definitions, commands, permission requests, and compaction context when those hooks fire.

Typical logical graph relationships still include Agent → tool call, tool call → tool, declared command/target, and returned-result observations. Content storage does not change their evidence semantics.

## Full-fidelity content

Complete values supplied by the OpenCode plugin are stored in the local content-addressed store and referenced from the semantic JSONL sidecar. Covered regressions include complete chat message/parts, tool args and results, model context, system prompt values, assistant text, provider events, tool definitions, command arguments/parts, permission data, and compaction prompts/context.

Known transport credentials such as authorization/cookie fields are filtered from the relevant headers/provider-metadata projection. Application-level secrets embedded in tool args, messages, results, or other content values are preserved. Do not assume full-fidelity content has been secret-redacted.

## Tool to process correlation

`sessionID + callID` proves exact logical call identity inside OpenCode. It does not prove which OS process executed the call. Tool → Process remains a separately derived conservative bridge and is emitted only when independent runtime evidence yields one uniquely supported process.

```text
inferred: true
causal: false
```

Ambiguous or unsupported calls produce no bridge.

## Privacy and evidence boundary

OpenCode run evidence can contain prompts/messages, system/context data, tool arguments and output, commands, permission patterns, provider event content, paths, identifiers, and application secrets. Treat the run directory as sensitive and review it before sharing.

The plugin proves what OpenCode exposed at the semantic/provider layer. Runtime collectors independently establish process/file/network observations. Full-fidelity provider content does not by itself prove command execution, completed file access, or byte-level data flow.
