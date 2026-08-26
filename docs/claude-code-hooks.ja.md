<!-- i18n-nav:start -->
<p align="center">
  <a href="claude-code-hooks.md">English</a> |
  <a href="claude-code-hooks.zh-TW.md">繁體中文</a> |
  <a href="claude-code-hooks.zh-CN.md">简体中文</a> |
  <strong>日本語</strong> |
  <a href="claude-code-hooks.ko.md">한국어</a> |
  <a href="claude-code-hooks.fr.md">Français</a> |
  <a href="claude-code-hooks.de.md">Deutsch</a> |
  <a href="claude-code-hooks.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# Claude Code Hooks

ExecWeave は Claude Code command hooks を semantic sidecar に変換する native adapter を提供します。OS runtime collector を置き換えるものではなく、logical evidence を補完します。

## Supported hooks

- `SessionStart`
- `PreToolUse`
- `PostToolUse`
- `PostToolUseFailure`
- `SubagentStart`
- `SubagentStop`

```text
Claude Code --REQUESTED_TOOL_CALL--> tool_call
 tool_call --USES_TOOL--> Bash / Read / Edit / Write / ...
 tool_call --DECLARED_COMMAND--> command
 tool_call --DECLARED_TARGET--> file metadata
 tool_call --VIA_MCP--> MCP server
Claude Code --SPAWNED_SUBAGENT--> subagent
Claude Code --USED_MODEL--> model
```

`mcp__<server>__<tool>` は `mcp_server` と `tool` に normalization されます。

## Setup

```bash
python -m pip install -e ".[dev]"
execweave-claude-hook --print-config
```

生成された `hooks` object を `~/.claude/settings.json`、project `.claude/settings.json` または local settings に merge します。Adapter は default fail-open、`--strict` は adapter debug 用で security policy ではありません。

## One-command recording

```bash
execweave-claude-record --open -- claude
```

Recorder は run-specific semantic sidecar を child Claude/hook process に継承させ、runtime → semantic merge → conservative correlation を自動実行します。

```text
.execweave/runs/<run-id>/
├── events.jsonl
├── graph.json
├── viewer.html
├── semantic.jsonl
├── events.semantic.jsonl
├── graph.semantic.json
├── viewer.semantic.html
├── events.correlated.jsonl
├── graph.correlated.json
└── viewer.correlated.html
```

Hook event が無ければ runtime-only に安全に fallback。Semantic evidence があっても unique safe candidate が無い場合は `completed_no_matches` となり、fake edge は作りません。

Default correlation window は 3000 ms：

```bash
execweave-claude-record --correlation-window-ms 1500 --open -- claude
```

## Tool → Process boundary

Claude hook は tool identity/input を提供しますが、Bash child OS PID は提供しません。そのため native hook 自体は `SPAWNED_PROCESS` を observed relation として作りません。

Correlation v0.1 は bounded window、exact executable/process/cmdline identity、canonical path、必要時 exact non-empty `argv[1:]` fallback を使い、**候補が一つだけ**の場合に：

```text
tool_call --CORRELATED_WITH_PROCESS--> process
```

を生成します。

Derived edge は必ず `backend: inference`, `inferred: true`, `causal: false`。Ambiguous candidate、shell builtin、compound command、fuzzy matching、temporal proximity only は拒否されます。

Viewer は inferred edge を別表示し、Correlation Summary と **observed only** filter を提供します。

## Privacy

- `Write/Edit` content を保存しない
- raw `tool_response` を保存しない
- generic input は key names 中心
- file tool は declared path のみ
- Bash/PowerShell command は explanation のため保存するが 4096 chars に制限
- failure text は bounded summary

Command/path は sensitive の可能性があるため、artifact 共有前に確認してください。

Semantic edge は provider hook evidence でも `causal: false` とし、OS execution attribution と明確に分離します。

詳細は [`Semantic Telemetry`](semantic-telemetry.ja.md)。
