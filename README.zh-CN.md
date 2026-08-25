# ExecWeave

<p align="center">
  <a href="README.md">English</a> |
  <a href="README.zh-TW.md">繁體中文</a> |
  <strong>简体中文</strong> |
  <a href="README.ja.md">日本語</a> |
  <a href="README.ko.md">한국어</a>
</p>

**看清 AI Agent 在你的电脑上实际做了什么。**

ExecWeave 是一个开源、local-first 的 AI Agent runtime observability 项目，把 Agent、Tool、Command、Process、File、Network activity 转成可交互 execution graph，同时严格区分 observed evidence 与 inference。

> **Event 是 ground truth；Graph 是 materialized view。**

## 快速开始

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

实时查看：

```bash
execweave live --open -- claude
execweave live --open -- codex
execweave live --open -- gemini
```

Live server 只绑定 `127.0.0.1`。

## Native Agent Integrations

ExecWeave 当前有三个 native semantic adapter：**Claude Code、OpenAI Codex、Gemini CLI**。

Provider hook 记录 Agent/Tool/Command/MCP 层的 logical evidence；OS collector 独立记录机器实际观察到的 runtime evidence。ExecWeave 不会把两类 evidence 直接包装成假的 causality。

### Claude Code

```bash
execweave-claude-hook --print-config
execweave-claude-record --open -- claude
```

详见 [`docs/claude-code-hooks.zh-CN.md`](docs/claude-code-hooks.zh-CN.md)。

### OpenAI Codex

```bash
execweave-codex-hook --print-config
execweave-codex-record --open -- codex
```

当前 adapter 接收 `SessionStart`、`PreToolUse`、`PostToolUse`。`PostToolUse` 只表示中性的 `TOOL_CALL_RETURNED`，不直接声称 success/failure。

详见 [`docs/codex-hooks.zh-CN.md`](docs/codex-hooks.zh-CN.md)。

### Gemini CLI

```bash
execweave-gemini-hook --print-config
execweave-gemini-record --open -- gemini
```

当前 adapter 接收 `SessionStart`、`BeforeTool`、`AfterTool`。`run_shell_command` 会生成 declared command evidence；部分 file tools 会生成 declared target path；`mcp_context` 会被规范化成 MCP server/tool entities。

Gemini 当前 hook schema 没有可跨 `BeforeTool` / `AfterTool` 共享的 unique tool-call ID，所以 ExecWeave 不会伪造 direct identity edge。`tool_fingerprint` 仅作诊断 hint，不作为 call identity。

详见 [`docs/gemini-hooks.zh-CN.md`](docs/gemini-hooks.zh-CN.md)。

## 分层 artifacts

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

Raw runtime 与 provider sidecar 保持分离；correlation 只生成新的 derived stream。

## Tool → Process Correlation

只有 bounded matcher 从独立 runtime evidence 中找到**唯一候选**时，才可能生成：

```text
tool_call --CORRELATED_WITH_PROCESS--> process
```

并始终保持：

```text
inferred: true
causal: false
```

Ambiguous、no-match、compound、shell builtin、unsupported call 都不会硬建 edge。Correlated Viewer 会显示 matched / ambiguous / no match / unsupported 等统计。

## Viewer

Standalone Viewer 支持：

- pan / zoom / drag
- node / edge details
- node type / relation filters
- causal-only / **observed only**
- search
- Timeline ↔ Graph replay
- Play/Pause
- progressive cluster expansion
- 1-hop / 2-hop focus
- Saved Views
- observed / non-causal / inferred 独立样式
- Correlation Summary

## Runtime Evidence

Portable backend 支持 Linux/macOS/Windows。Linux 还可使用 syscall-backed reference backend：

```bash
sudo apt-get install strace
execweave record --backend strace --open -- claude
```

三个 provider recorder 的 `--backend auto` 在 Linux 有 `strace` 时都会优先使用它。

## 不制造假的因果关系

ExecWeave 区分 observed causal、observed non-causal、provider semantic、inferred relationship。Provider hook 没有 child OS PID 时，不会直接声称 Tool → Process。时间接近本身不足以生成 edge。

同样地，process 先读敏感文件、之后连外，不等于已经证明这些 bytes 被传输。

## Security Analysis

```bash
execweave analyze run.graph.json --output analysis.json
```

Report 会明确保留：

```json
{
  "data_flow_proven": false,
  "exfiltration_proven": false
}
```

## 当前状态

ExecWeave 当前为 **v0.4.0**。

已完成 baseline 包括 portable/strace runtime collection、execution graph、live/standalone Viewer、Timeline/focus/condensation/Saved Views、Claude/Codex/Gemini native adapters、conservative Tool→Process correlation、Correlation Summary 与初始 security analysis。

后续重点：Linux eBPF、Windows ETW、macOS Endpoint Security、更多 provider adapter、更强 process/tool identity、MCP normalization 与 long-run scalability。

## Privacy

ExecWeave 是 **local-first**。默认不采集 file content、raw read/write byte buffer、prompt/transcript content。Command、path、endpoint、session ID 等 metadata 仍可能敏感，分享 artifact 前请检查。

## 文档

- [`Phase 1 — Runtime Collection`](docs/phase-1-runtime-collection.zh-CN.md)
- [`Phase 2 — Execution Graph`](docs/phase-2-execution-graph.zh-CN.md)
- [`Live Graph`](docs/live-graph.zh-CN.md)
- [`Semantic Telemetry`](docs/semantic-telemetry.zh-CN.md)
- [`Claude Code Hooks`](docs/claude-code-hooks.zh-CN.md)
- [`OpenAI Codex Hooks`](docs/codex-hooks.zh-CN.md)
- [`Gemini CLI Hooks`](docs/gemini-hooks.zh-CN.md)
- [`Security Analysis`](docs/security-analysis.zh-CN.md)

## Contributing

欢迎 Linux eBPF、Windows ETW、macOS Endpoint Security、Agent/Tool/MCP provider adapter、provenance/correlation、Graph UX、privacy/redaction、testing/performance 与翻译贡献。

## License

见 [`LICENSE`](LICENSE)。
