<!-- i18n-nav:start -->
<p align="center">
  <a href="gemini-hooks.md">English</a> |
  <a href="gemini-hooks.zh-TW.md">繁體中文</a> |
  <strong>简体中文</strong> |
  <a href="gemini-hooks.ja.md">日本語</a> |
  <a href="gemini-hooks.ko.md">한국어</a> |
  <a href="gemini-hooks.fr.md">Français</a> |
  <a href="gemini-hooks.de.md">Deutsch</a> |
  <a href="gemini-hooks.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# Gemini CLI Hooks

ExecWeave 可以接收 Gemini CLI 的 lifecycle/tool hooks，把它们作为 provider semantic evidence，再与独立采集的 OS runtime evidence 放进同一个执行图。

这个 adapter 刻意保持保守：Gemini hook 描述的是 Agent / Tool layer 自己报告的语义行为，不会仅凭 hook 就声称某个 OS process 实际执行了该动作。

## 当前支持的 hook events

目前接收：

- `SessionStart`
- `BeforeTool`
- `AfterTool`

Gemini CLI 通过 `stdin` 传入 JSON。Command hook 成功时，`stdout` 必须是合法 JSON；因此 `execweave-gemini-hook` 成功时只输出 `{}`，警告只写入 `stderr`。

生成配置片段：

```bash
execweave-gemini-hook --print-config
```

把输出的 `hooks` object 合并到 Gemini CLI 的 `settings.json`。生成配置只做观测，不会 block 或 rewrite tool call。

## 一键记录

配置 hooks 后：

```bash
execweave-gemini-record --open -- gemini
```

Recorder 通过 `EXECWEAVE_SEMANTIC_SIDECAR` 将这次 Gemini child process 绑定到 run-specific sidecar，再进入共享 provider-record pipeline：

```text
runtime evidence
      +
Gemini hook evidence
      ↓
validated semantic merge
      ↓
conservative correlation
      ↓
graph + viewer
```

Provider-integrated run 可生成 runtime、semantic 和 correlated 三层 artifact，包括 `events.jsonl`、`semantic.jsonl`、`events.semantic.jsonl`、`events.correlated.jsonl` 及对应 Graph/Viewer。

Raw runtime 和 provider sidecar 保持分离；correlation 生成新的 derived stream，不改写 observed evidence。

## Event mapping

### SessionStart

```text
Gemini CLI --STARTED_PROVIDER_SESSION--> provider_session
```

ExecWeave 只保留 attribution 所需的 session metadata，不读取或复制 `transcript_path` 指向的 transcript。

### BeforeTool

```text
Gemini CLI --REQUESTED_TOOL_CALL--> tool_call
tool_call --USES_TOOL--> tool
```

对于 `run_shell_command`：

```text
tool_call --DECLARED_COMMAND--> command
```

该 command evidence 可以参与保守的 Tool → Process correlation。

对于 `read_file`、`write_file`、`replace` 等部分 file tools，可记录声明的 target path，但不采集 file content。

### MCP tools

有 `mcp_context` 时使用 provider 明确报告的 server/tool identity：

```text
tool_call --VIA_MCP--> mcp_server
mcp_server --EXPOSES_TOOL--> tool
```

Adapter 不保存 MCP launch command、arguments 或 URL，避免把可能的敏感连接信息或 credential 写入 artifact。

### AfterTool

`AfterTool` 建立独立 `tool_result` observation。只有 `tool_response.error` 非空时才记录 provider-reported error；否则记录中性的 returned-result signal。

不保存 raw `llmContent`、`returnDisplay` 或 error body。

## 没有唯一 tool-call ID

当前 Gemini CLI hook schema 没有可在 `BeforeTool` 与 `AfterTool` 之间共享的 unique tool-call ID。

因此 ExecWeave 不会伪造直接 BeforeTool → AfterTool identity edge。

`BeforeTool` 使用 timestamp-scoped local identity；`AfterTool` 生成独立 result node。两者可带 `tool_fingerprint` 作为诊断 hint，但 fingerprint **不是 call identity**，相同 command 的重复执行不会被强行合并。

## Tool → Process correlation

Gemini hook 不提供 child OS PID，所以不能直接证明 Tool → Process attribution。

只有 bounded matcher 从独立 runtime evidence 找到唯一候选时，才可能生成：

```text
tool_call --CORRELATED_WITH_PROCESS--> process
```

且始终保持：

```text
inferred: true
causal: false
```

Ambiguous、no-match、compound、shell builtin 或 unsupported command 不生成 edge。

## Privacy

默认不采集 prompt、transcript、raw tool result、raw error body、MCP command/arguments/URL 或 file content。Command、path、tool、session ID、MCP server/tool name 等 metadata 仍可能敏感，分享 artifact 前请检查。

## Failure behavior

`execweave-gemini-hook` 默认 fail-open；telemetry 错误写到 `stderr`。需要 non-zero telemetry failure 时才使用 `--strict`。

## Upstream contract

- https://github.com/google-gemini/gemini-cli/blob/main/docs/hooks/reference.md
- https://github.com/google-gemini/gemini-cli/blob/main/docs/hooks/index.md

另见 [`Semantic Telemetry`](semantic-telemetry.zh-CN.md)。
