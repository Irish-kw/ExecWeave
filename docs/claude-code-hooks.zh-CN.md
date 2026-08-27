<!-- i18n-nav:start -->
<p align="center">
  <a href="claude-code-hooks.md">English</a> |
  <a href="claude-code-hooks.zh-TW.md">繁體中文</a> |
  <strong>简体中文</strong> |
  <a href="claude-code-hooks.ja.md">日本語</a> |
  <a href="claude-code-hooks.ko.md">한국어</a> |
  <a href="claude-code-hooks.fr.md">Français</a> |
  <a href="claude-code-hooks.de.md">Deutsch</a> |
  <a href="claude-code-hooks.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# Claude Code Hooks

ExecWeave 内置 Claude Code command-hook adapter，把 provider 的 semantic/content evidence 写入本地 sidecar，并与独立 OS runtime evidence 分开保存。Provider hook 说明 Claude Code 明确暴露了什么；它不会替代 portable 或 Linux `strace` collector，也不会仅凭 hook 建立 OS process causality。

**当前 hook surface。** `execweave-claude-hook --print-config` 当前注册：

- `SessionStart`
- `UserPromptSubmit`
- `MessageDisplay`
- `PreToolUse`
- `PostToolUse`
- `PostToolUseFailure`
- `PostToolBatch`
- `SubagentStart`
- `SubagentStop`
- `Stop`
- `StopFailure`

Hook 默认 fail-open：telemetry/storage error 会被报告，但不会有意阻断 Agent operation。调试时可用 `--strict` 要求 telemetry failure 返回 non-zero。

## 配置与记录

安装 ExecWeave、生成受支持的 settings fragment，合并到 Claude Code settings 后使用 run-bound recorder：

```bash
execweave-claude-hook --print-config
execweave-claude-record --open -- claude
```

`execweave-claude-record` 通过 child environment 绑定每个 run 独立的 semantic sidecar。Runtime、semantic、correlated evidence 始终是不同 artifacts。

```text
runtime evidence
    ↓ semantic merge
runtime + semantic evidence
    ↓ conservative correlation
runtime + semantic + inferred correlation
```

如果没有任何受支持 Claude hook event，recorder 会回退到 runtime-only artifacts。若已有 semantic evidence，但没有唯一且足够支持的 Tool → Process candidate，也不会伪造 bridge。

## v0.6.5 full-fidelity content

Claude adapter 已不再仅保留 bounded metadata summary。当 hook 明确提供内容时，v0.6.5 会把来源提供的完整值存入本地 SHA-256 content-addressed store，semantic sidecar 只留下 reference。

Regression coverage 包括：

- 完整 `UserPromptSubmit.prompt`，包括大型值；
- 完整 tool input，包括 `Write`/`Edit` 内容及 input object 中的 application-level values；
- hook 提供时的完整 structured `PostToolUse.tool_response`；
- `PostToolBatch` 提供、model 可见的 tool-result serialization；
- `MessageDisplay` assistant text/delta 与可用 ordering metadata；
- stop events 提供的 main Agent / subagent 最终 assistant message。

已知 transport credentials 只会在 adapter 可识别的独立 provider-metadata projection 中被过滤。这**不会**清理 full content 本身。若 secret 位于 prompt、tool input、file body、tool result 或 assistant message 中，它会成为保存的 full-fidelity evidence。

`content_complete_from_source: true` 表示 ExecWeave 完整保存了 Claude hook 提供的值，不表示 ExecWeave 读取了 hook 未提供的 transcript、观察到了 hidden model state，或捕获了 payload 中不存在的 provider stage。

## Logical entities 与 tool identity

Claude hook event 可以产生以下 provider-level relationships：

```text
Claude Code --REQUESTED_TOOL_CALL--> tool_call
tool_call --USES_TOOL-------------> tool
tool_call --DECLARED_COMMAND------> command
tool_call --DECLARED_TARGET-------> file metadata
tool_call --VIA_MCP---------------> mcp_server
Claude Code --SPAWNED_SUBAGENT----> subagent
```

Claude hook input 可以用 `tool_use_id` 识别 logical tool invocation，但它不是 OS PID。符合 provider `mcp__<server>__<tool>` 命名规则的 MCP 名称会在可用时规范化为独立 MCP-server/tool entities。

## Tool → Process correlation boundary

Claude command-hook input 不会提供 Bash/PowerShell tool invocation 实际创建的 child process PID，因此 ExecWeave 不会仅凭 provider hook data 创建 observed causal process edge。

只有 bounded runtime matcher 找到唯一受支持 process candidate 时，才可能建立 derived bridge：

```text
tool_call --CORRELATED_WITH_PROCESS--> process
```

所有此类 bridge 都保持：

```json
{
  "causal": false,
  "inferred": true,
  "confidence_semantics": "heuristic_score_not_probability"
}
```

仅仅时间接近是不够的。Ambiguous candidate、unsupported compound command、shell builtin 或 unmatched declaration 都不会产生 bridge；inference 永远不会升级成 observed process attribution。

## Layered artifacts

Run-bound Claude capture 可能产生：

```text
.execweave/runs/<run-id>/
├── events.jsonl
├── graph.json
├── viewer.html
├── semantic.jsonl
├── content/sha256/...
├── events.semantic.jsonl
├── graph.semantic.json
├── viewer.semantic.html
├── events.correlated.jsonl
├── graph.correlated.json
└── viewer.correlated.html
```

Correlation 不会重写原始 runtime 或 provider evidence。

## Standalone sidecar

不使用 run-bound recorder 时，默认 Claude sidecar 按 session 隔离：

```text
<cwd>/.execweave/semantic/claude/<Claude-session-id>.jsonl
```

可以用 `EXECWEAVE_SEMANTIC_SIDECAR` 或 `--sidecar` 覆盖。Parallel capture 建议使用 session/run-specific path。

## Privacy 与 evidence boundary

Claude full-fidelity artifact 可能包含 prompt、command、file path、`Write`/`Edit` body、tool argument/result、assistant text、subagent response、identifier 和 application-level secrets。整个 run directory 都应视为敏感数据，分享前需要检查。

Provider content 仍然只是 provider evidence。保存的 tool input 不代表 tool 确实执行；保存的 file body 不代表某个特定 OS process 曾经读写；保存的 tool result 也不代表 bytes 已流向其他 resource。更强 claim 必须由 OS collector 与明确标记的 correlation evidence 支持。

## 手动 merge 与 correlation

已有 runtime 与 semantic files 时，generic pipeline 仍可使用：

```bash
execweave semantic-merge run.jsonl semantic.jsonl --output run.semantic.jsonl
execweave validate run.semantic.jsonl
execweave correlate run.semantic.jsonl --output run.correlated.jsonl
execweave validate run.correlated.jsonl
```

Generic evidence/content contract 与 process-reference rules 参见 [`Semantic Telemetry`](semantic-telemetry.zh-CN.md)。
