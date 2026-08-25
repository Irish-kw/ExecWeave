<!-- i18n-nav:start -->
<p align="center">
  <a href="claude-code-hooks.md">English</a> |
  <a href="claude-code-hooks.zh-TW.md">繁體中文</a> |
  <strong>简体中文</strong> |
  <a href="claude-code-hooks.ja.md">日本語</a> |
  <a href="claude-code-hooks.ko.md">한국어</a>
</p>
<!-- i18n-nav:end -->

# Claude Code Hooks

ExecWeave 内建 Claude Code command-hook adapter，可把 provider semantic telemetry 写到独立的本机 JSONL sidecar，并与 OS runtime collection 组合。

它是 runtime collector 的补充，不会取代 portable 或 Linux `strace` collector。

## 目前记录的 hook events

- `SessionStart`
- `PreToolUse`
- `PostToolUse`
- `PostToolUseFailure`
- `SubagentStart`
- `SubagentStop`

可建立：

```text
Claude Code
  |
  +--REQUESTED_TOOL_CALL--> tool_call
  |                           |
  |                           +--USES_TOOL-------> Bash / Read / Edit / Write / ...
  |                           +--DECLARED_COMMAND-> command
  |                           +--DECLARED_TARGET--> file metadata
  |                           +--VIA_MCP----------> MCP server
  |
  +--SPAWNED_SUBAGENT-------> subagent
  +--USED_MODEL-------------> model
```

Claude Code 的 `mcp__<server>__<tool>` 命名会被拆成独立 `mcp_server` 与 `tool` node。

## 安装 hook 设定

先安装 ExecWeave：

```bash
python -m pip install -e ".[dev]"
```

产生 settings fragment：

```bash
execweave-claude-hook --print-config
```

把输出的 `hooks` object 合并到 Claude Code 支援的 settings file，例如：

- `~/.claude/settings.json`
- `.claude/settings.json`
- `.claude/settings.local.json`

不要覆写原本不相关设定。Claude Code 的 `/hooks` menu 可用来确认目前启用的 hooks。

Adapter 预设 fail-open：telemetry parse/filesystem error 会写 stderr，但不会刻意阻断 Agent tool call。`--strict` 只用来 debug adapter，不是 runtime security policy。

## 建议：一行完成 runtime + semantic + correlation

Hooks 安装后：

```bash
execweave-claude-record --open -- claude
```

Linux `--backend auto` 在可用时仍优先使用 `strace`；macOS/Windows 使用 portable backend。

`execweave-claude-record` 在自己的 CLI process 内绑定 run-specific semantic sidecar path，Claude 与它启动的 hook command 会继承，因此同一 repo 同时跑多个 recorder 时不需要靠 timestamp 猜 sidecar 归属。

Evidence pipeline：

```text
runtime evidence
    ↓ semantic merge
runtime + semantic evidence
    ↓ conservative correlation
runtime + semantic + inferred correlation
```

Artifacts 分层保存：

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

`--open` 在 semantic evidence 存在时开启 correlated viewer。若 hooks 未安装或没有支援事件，会回报 `semantic_status: "no_events"` / `correlation_status: "not_run_no_semantic_events"`，并安全退回 runtime-only viewer。

有 semantic evidence、但没有唯一安全 Tool → Process candidate 时，仍会产生 correlated artifacts，状态是 `completed_no_matches`，但不建立 inferred edge。

预设 correlation window 为 3000 ms，可调整：

```bash
execweave-claude-record \
  --correlation-window-ms 1500 \
  --open \
  -- claude
```

## Standalone hook sidecar

不使用 run-bound recorder 时，预设每个 Claude session 写到：

```text
<cwd>/.execweave/semantic/claude/<Claude-session-id>.jsonl
```

也可用 `EXECWEAVE_SEMANTIC_SIDECAR` 或 `--sidecar` 明确指定。Parallel standalone sessions 建议使用自动 session-scoped path，不要让多个 session 共写同一档案。

## Advanced manual workflow

```bash
execweave semantic-merge run.jsonl semantic.jsonl \
  --output run.semantic.jsonl
execweave validate run.semantic.jsonl
execweave correlate run.semantic.jsonl \
  --output run.correlated.jsonl
execweave validate run.correlated.jsonl
execweave graph run.correlated.jsonl \
  --output run.correlated.graph.json
execweave view run.correlated.graph.json \
  --output run.correlated.html --open
```

Raw runtime stream 与 semantic sidecar 都保持不变。

## Tool → Process boundary / correlation v0.1

Claude Code hook 能提供 `tool_name`、`tool_use_id` 与 tool input，但**没有**提供 Bash tool call 真正建立的 child OS PID。

因此 native adapter 不会直接建立：

```text
Bash tool_call --SPAWNED_PROCESS--> process:1234
```

Correlation v0.1 只有在 bounded window 中有唯一 process candidate 时才建立：

```text
tool_call --CORRELATED_WITH_PROCESS--> process
```

规则包括：

- window 可被 tool result / 下一个 declared call 截断；
- executable/process/cmdline identity 需有明确 evidence；
- canonical path 可用来确认等价 executable path；
- launcher 可使用 exact、non-empty、length-preserving `argv[1:]` fallback；
- 必须只有一个 surviving candidate；
- ambiguous 不产生 bridge；
- shell builtin / compound command 不产生 bridge；
- 不使用 fuzzy version/name matching；
- temporal proximity 单独永远不足。

Derived bridge 永远类似：

```json
{
  "backend": "inference",
  "causal": false,
  "inferred": true,
  "inference_method": "...",
  "confidence": 0.8,
  "confidence_semantics": "heuristic_score_not_probability"
}
```

Viewer 会把 inferred edge 与 observed edge 分开显示，并提供 Correlation Summary / **observed only** filter。

## Privacy

Native adapter 刻意避免保存高风险 payload：

- 不保存 `Write/Edit` file content；
- 不保存 raw `PostToolUse.tool_response`；
- generic tool input 只保留 key names；
- file tool 保存 declared path，不保存内容；
- Bash/PowerShell command 因 execution explanation 需要而保存，但上限 4096 characters；
- failure text 只保留 bounded summary。

Command/path 本身仍可能包含 token、credential、internal hostname 或其他敏感资讯，分享 artifact 前请检查。

## Evidence semantics

Claude adapter 直接产生的 semantic edge 会标示：

```json
{
  "backend": "semantic",
  "attribution": "claude_hook",
  "evidence_source": "provider_hook",
  "provider": "claude",
  "causal": false
}
```

这不代表 provider hook 不可靠，而是 provider-level logical relationship 不会被升级成 OS execution-attribution claim。Correlation 则是独立 derived evidence，保持 `backend: "inference" / inferred: true / causal: false`。

通用契约见 [`Semantic Telemetry`](semantic-telemetry.zh-CN.md)。
