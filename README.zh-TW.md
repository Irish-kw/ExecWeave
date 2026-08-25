# ExecWeave

<p align="center">
  <a href="README.md">English</a> |
  <strong>繁體中文</strong> |
  <a href="README.zh-CN.md">简体中文</a> |
  <a href="README.ja.md">日本語</a> |
  <a href="README.ko.md">한국어</a>
</p>

**看清楚 AI Agent 在你的電腦上實際做了什麼。**

ExecWeave 是一個開源、local-first 的 AI Agent runtime observability 專案。它把 Agent、Tool、Command、Process、File 與 Network activity 轉成互動式 execution graph，並且刻意把 observed evidence 與 inference 分開。

> **Event 是 ground truth；Graph 是 materialized view。**

## 快速開始

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

即時查看任意 command：

```bash
execweave live --open -- claude
```

也可以：

```bash
execweave live --open -- codex
execweave live --open -- gemini
execweave live --open -- opencode
execweave record --open -- python my_agent.py
```

Live server 只綁定 `127.0.0.1`，command 還沒結束時 Graph 就會持續更新。

## Native Agent Integrations

ExecWeave 目前已有三個 native semantic adapter：**Claude Code**、**OpenAI Codex**、**Gemini CLI**。

Provider hook 描述 Agent / Tool / Command / MCP layer 的 logical evidence；OS collector 則獨立記錄電腦實際觀察到的 runtime evidence。ExecWeave 不會把兩者直接混成假的 causality。

### Claude Code

```bash
execweave-claude-hook --print-config
execweave-claude-record --open -- claude
```

當 hook 有觸發時，ExecWeave 會自動產生 runtime、semantic 與 conservative correlation artifacts。

詳細契約見 [`docs/claude-code-hooks.zh-TW.md`](docs/claude-code-hooks.zh-TW.md)。

### OpenAI Codex

```bash
execweave-codex-hook --print-config
execweave-codex-record --open -- codex
```

目前 Codex adapter 接收 `SessionStart`、`PreToolUse`、`PostToolUse`。Canonical `Bash` 的 declared command 可進入 conservative Tool → Process correlation。

`PostToolUse` 目前只記成中性的 `TOOL_CALL_RETURNED`，不會直接宣稱 success 或 failure。

詳細說明見 [`docs/codex-hooks.zh-TW.md`](docs/codex-hooks.zh-TW.md)。

### Gemini CLI

```bash
execweave-gemini-hook --print-config
execweave-gemini-record --open -- gemini
```

目前 Gemini adapter 接收 `SessionStart`、`BeforeTool`、`AfterTool`。`run_shell_command` 會產生 declared command evidence；部分 file tools 會產生 declared target path；有 `mcp_context` 時會正規化成 MCP server/tool entities。

Gemini 目前的 hook schema 沒有可在 `BeforeTool` 與 `AfterTool` 間共享的 unique tool-call ID，所以 ExecWeave **不會**偽造 direct identity edge。`tool_fingerprint` 只作為診斷 hint，不當成 call identity。

詳細說明見 [`docs/gemini-hooks.zh-TW.md`](docs/gemini-hooks.zh-TW.md)。

## Provider-integrated run artifacts

有 semantic hook 的 run 會分層保存：

```text
.execweave/runs/<run-id>/
├── events.jsonl              # runtime evidence only
├── graph.json                # runtime-only graph
├── viewer.html               # runtime-only viewer
├── semantic.jsonl            # provider hook evidence only
├── events.semantic.jsonl     # validated runtime + semantic stream
├── graph.semantic.json       # runtime + semantic graph
├── viewer.semantic.html      # runtime + semantic viewer
├── events.correlated.jsonl   # derived stream
├── graph.correlated.json     # inferred bridges + correlation metadata
└── viewer.correlated.html    # correlation-aware viewer
```

Raw runtime 與 provider sidecar 都保持不變；correlation 產生新的 derived stream，不會回頭重寫 observed evidence。

## Tool → Process Correlation

Provider 可能告訴 ExecWeave：

```text
tool_call --DECLARED_COMMAND--> command
```

OS telemetry 則獨立觀察 process。只有 bounded matcher 找到**唯一且有足夠 evidence 支撐的候選**時，ExecWeave 才會產生：

```text
tool_call --CORRELATED_WITH_PROCESS--> process
```

所有 bridge 都維持：

```text
inferred: true
causal: false
```

Ambiguous、no-match、compound、shell builtin 或 unsupported call 都不硬建 edge。

Correlated Viewer 會顯示 matched / ambiguous / no match / unsupported / considered calls / correlation window。

## Interactive Viewer

Standalone Viewer 完全 local，不需要 CDN 或外部 JavaScript。

目前 baseline 包含：

- pan / zoom / node drag
- node / edge details
- node type / relation filters
- causal-only filter
- **observed only** filter
- search
- Evidence sequence Timeline ↔ Graph replay
- Play/Pause
- progressive cluster expansion
- 1-hop / 2-hop focused neighborhood
- browser-local Saved Views
- observed / non-causal / inferred edge 獨立樣式
- correlated graph 的 Correlation Summary

**Observed only** 會在 focus traversal 與 layout 之前排除 `inferred: true` relationships，而不是事後只把紫色線藏起來。

## Runtime Evidence

Portable collector 使用 `psutil` 與 `watchdog`，支援 Linux、macOS、Windows，也是目前 Live Graph backend。

Linux reference backend：

```bash
sudo apt-get install strace
execweave record --backend strace --open -- claude
```

`execweave-claude-record --backend auto`、`execweave-codex-record --backend auto`、`execweave-gemini-record --backend auto` 在 Linux 有 `strace` 時會優先使用它。

後續仍規劃 Linux eBPF、Windows ETW 與 macOS Endpoint Security native collector。

## Graph-first Evidence Model

```text
source --RELATION--> target
```

例如：

```text
session --LAUNCHED--> process
process --SPAWNED--> process
process --OPENED_READ--> file
process --CONNECTED_TO--> network_endpoint
agent --REQUESTED_TOOL_CALL--> tool_call
tool_call --DECLARED_COMMAND--> command
tool_call --CORRELATED_WITH_PROCESS--> process   # inferred only
```

Repeated evidence 會聚合，同一 relationship 以 `count` 表示重複 evidence。

## 不製造假的因果關係

ExecWeave 明確區分：

- **observed causal evidence**
- **observed non-causal/session evidence**
- **provider semantic evidence**
- **inferred relationship**

Provider hook 沒有提供能直接證明 Tool → Process 的 child OS PID。單純時間接近不夠；候選不唯一就不建 edge。

同樣地，一個 process 先讀 sensitive file、之後連 external endpoint，也不能被包裝成「檔案內容已經送出去」。

## Security Analysis

```bash
execweave analyze run.graph.json
execweave analyze run.graph.json --output analysis.json
```

初始 conservative analysis layer 可標記 sensitive-file access、external endpoint 與 possible sensitive-file → network path，但會明確保留：

```json
{
  "data_flow_proven": false,
  "exfiltration_proven": false
}
```

## Graph Operations

```bash
execweave graph-summary run.graph.json
execweave graph-filter run.graph.json --output causal.graph.json --causal-only
execweave graph-focus run.graph.json NODE_ID --hops 2 --output focused.graph.json
execweave path run.graph.json SOURCE_NODE_ID TARGET_NODE_ID --causal-only
```

大型 Graph 可使用：

```bash
execweave graph-condense run.graph.json \
  --output run.compact.graph.json \
  --threshold 8 \
  --keep-expansion
```

## 目前狀態

ExecWeave 目前為 **v0.4.0**，持續開發中。

已完成 baseline：

- cross-platform portable runtime collection
- Linux syscall-backed reference collection
- validated append-only JSONL evidence stream
- execution graph materialization / query
- standalone + live local Viewer
- Timeline replay / focused neighborhood
- graph condensation / progressive expansion
- Saved Views
- Claude Code native semantic adapter + run-bound recorder
- OpenAI Codex native semantic adapter + run-bound recorder
- Gemini CLI native semantic adapter + run-bound recorder
- conservative Tool → Process correlation
- Correlation Summary
- explainable initial security analysis
- Ubuntu / macOS / Windows × Python 3.10 / 3.12 CI

後續重點：Linux eBPF、Windows ETW、macOS Endpoint Security、更多 provider adapter、更強 process/tool identity evidence、更完整 MCP normalization、long-run performance / scalability。

## Privacy

ExecWeave 是 **local-first**。Runtime event、semantic sidecar、Graph、Report、Viewer 預設都留在本機；standalone Viewer 不需要外部 CDN。

ExecWeave 不主動蒐集 file content 或 raw read/write byte buffer。Native semantic adapter 預設也不抓 prompt / transcript content，但 command、path、endpoint metadata、session identifier 等仍可能是敏感資訊。

分享 artifact 前請自行檢查。

## 文件

- [`Phase 1 — Runtime Collection`](docs/phase-1-runtime-collection.zh-TW.md)
- [`Phase 2 — Execution Graph`](docs/phase-2-execution-graph.zh-TW.md)
- [`Live Graph`](docs/live-graph.zh-TW.md)
- [`Semantic Telemetry`](docs/semantic-telemetry.zh-TW.md)
- [`Claude Code Hooks`](docs/claude-code-hooks.zh-TW.md)
- [`OpenAI Codex Hooks`](docs/codex-hooks.zh-TW.md)
- [`Gemini CLI Hooks`](docs/gemini-hooks.zh-TW.md)
- [`Security Analysis`](docs/security-analysis.zh-TW.md)

## Contributing

非常歡迎 Linux eBPF、Windows ETW、macOS Endpoint Security、Agent/Tool/MCP provider adapter、process/entity resolution、provenance/correlation、Graph UX、privacy/redaction、testing/performance 與文件翻譯 contribution。

## License

見 [`LICENSE`](LICENSE)。
