<!-- i18n-nav:start -->
<p align="center">
  <a href="codex-hooks.md">English</a> |
  <a href="codex-hooks.zh-TW.md">繁體中文</a> |
  <strong>简体中文</strong> |
  <a href="codex-hooks.ja.md">日本語</a> |
  <a href="codex-hooks.ko.md">한국어</a>
</p>
<!-- i18n-nav:end -->

# OpenAI Codex Lifecycle Hooks

ExecWeave 提供 OpenAI Codex lifecycle-hook adapter，将 provider-level semantic evidence 加到与 OS runtime telemetry 相同的本机 run 中。

这个 integration 采保守设计。Codex hook 可以告诉 ExecWeave 哪个 logical tool call 被要求，以及 shell execution 宣告了什么 command；它**不提供 OS child PID**，因此 provider hook 不会被呈现成直接 observed / causal 的 Tool → Process attribution。

## 目前支援

ExecWeave 接收：

- `SessionStart`
- `PreToolUse`
- `PostToolUse`

只记录 Codex 实际送达的 lifecycle events；未知 event 会被忽略，不猜测。

### `SessionStart`

若 payload 有 model：

```text
OpenAI Codex --USED_MODEL--> model
```

Adapter 不读取 transcript file 内容。

### `PreToolUse`

Provider 的 `tool_use_id` 会作为 stable logical tool-call identity：

```text
OpenAI Codex --REQUESTED_TOOL_CALL--> tool_call
tool_call --USES_TOOL--> tool
```

Canonical `Bash` tool 若有 string `tool_input.command`：

```text
tool_call --DECLARED_COMMAND--> command
```

这是 semantic evidence，可供 conservative correlation 使用，但不是特定 OS process 执行该 command 的证明。

### `PostToolUse`

目前只记录中性 relation：

```text
tool_call --TOOL_CALL_RETURNED--> tool
```

不转成 `TOOL_CALL_SUCCEEDED` / `TOOL_CALL_FAILED`，因为目前 payload 没有足够可靠的 success/failure discriminator。

Raw `tool_response` 不会存入 semantic telemetry；string response 只保存 type 与 character count。

## 设定 Codex

安装 ExecWeave 后：

```bash
execweave-codex-hook --print-config
```

把输出的 `hooks` object 合并到 Codex `hooks.json`。目前 generator 会注册 `SessionStart`、`PreToolUse`、`PostToolUse`。

Hook adapter 预设 fail-open；telemetry 问题只警告，不刻意阻断 Codex。Debug adapter 本身时可用：

```bash
execweave-codex-hook --strict
```

## 一行记录 Codex run

设定好 hooks 后：

```bash
execweave-codex-record --open -- codex
```

Recorder 不修改 Codex configuration，只透过 inherited environment variable 将 child Codex process 绑到 run-specific semantic sidecar。

Hook 有触发时会得到分层 artifacts：

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

如果没有 Codex hook event，recorder 安全退回 runtime-only artifacts。

## Tool → Process correlation

例如：

```text
tool_call --DECLARED_COMMAND--> "python task.py"
```

ExecWeave 会将 semantic declaration 与 bounded runtime process evidence 比对，只有 matcher 找到**唯一且有足够证据支持的候选**时，才产生：

```text
tool_call --CORRELATED_WITH_PROCESS--> process
```

所有 bridge 都保持：

```text
inferred: true
causal: false
```

Ambiguous、unmatched、shell builtin、compound 或 unsupported call 不会建立 bridge。

Correlated graph 会保存 run-level Correlation Summary，让 Viewer 区分 `matched / ambiguous / no match / unsupported`，而不是把所有缺 edge 都当成同一原因。Viewer 的 **observed only** 会在 focus traversal/layout 前移除 inferred edges。

## Evidence / privacy boundary

目前 Codex adapter 只保存建图需要的 semantic metadata，例如：

- Codex session ID
- turn ID（若有）
- model name
- tool name
- tool-use ID
- input key names
- declared `Bash` command
- `PostToolUse` response type / length

不主动收集：

- prompt text
- transcript-file content
- raw `tool_response`
- file content
- provider-derived Tool → Process PID

Command 本身仍可能含 secret/path，分享 artifacts 前请检查。

## 目前 upstream limitations

Codex lifecycle hooks 仍在演进，因此 ExecWeave 把这项功能定位为 native semantic adapter，而不是宣称每种 Codex execution mode 都有完整 lifecycle coverage。

目前需要注意：

1. `PostToolUse` 没有足够可靠 outcome signal，因此只标 `TOOL_CALL_RETURNED`。
2. 部分 `codex exec` path 曾有 lifecycle hook dispatch gap；初期 interactive Codex CLI 是较安全的 target。
3. 部分 Windows command execution path 曾出现 upstream hook-coverage gap。
4. Provider hook 没有 OS child PID，因此不能提供直接 observed Tool → Process attribution。

这些限制只影响 semantic coverage；独立 OS runtime collector 即使 hook 没触发仍能工作。

## Design rule

> Provider semantics 描述 Agent 说它要做什么；OS telemetry 描述机器实际观察到什么；只有 evidence 唯一且充分时，correlation 才能以 explicit、non-causal inference 把两者连起来。

通用 contract 见 [`Semantic Telemetry`](semantic-telemetry.zh-CN.md)。
