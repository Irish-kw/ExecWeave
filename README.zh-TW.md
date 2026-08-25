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

### Agent 還在執行時就看 Graph

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

一般 run 會產生：

```text
.execweave/runs/<run-id>/
├── events.jsonl
├── graph.json
└── viewer.html
```

目前 live path 刻意使用 portable collector。Linux `strace` backend 是 command 結束後才解析，因此 ExecWeave 不會把 post-processing 假裝成 live telemetry。

## Native Agent Integrations

ExecWeave 目前已有兩個 native semantic adapter：**Claude Code** 與 **OpenAI Codex**。

Provider hook 描述 Agent / Model / Tool / Command 的 logical evidence；OS collector 則獨立記錄電腦實際觀察到的 runtime evidence。兩者不會被直接混成假的 causality。

### Claude Code

先產生 hook 設定：

```bash
execweave-claude-hook --print-config
```

把輸出的 `hooks` object 合併到 Claude Code settings，之後即可：

```bash
execweave-claude-record --open -- claude
```

當 hook 有觸發時，ExecWeave 會自動產生 runtime、semantic 與 conservative correlation artifacts。

詳細契約見 [`docs/claude-code-hooks.md`](docs/claude-code-hooks.md)。

### OpenAI Codex

產生目前支援的 lifecycle-hook 設定：

```bash
execweave-codex-hook --print-config
```

把輸出的 `hooks` object 合併到 Codex `hooks.json`，再執行：

```bash
execweave-codex-record --open -- codex
```

目前 Codex adapter 接收：

- `SessionStart`
- `PreToolUse`
- `PostToolUse`

對 canonical `Bash` tool，`tool_input.command` 會成為 `DECLARED_COMMAND` semantic evidence，並可進入與 Claude 共用的 conservative Tool → Process correlation。

`PostToolUse` 目前只記成中性的 `TOOL_CALL_RETURNED`，**不會**直接標記 success 或 failure，因為目前 provider payload 沒有足夠可靠的 outcome signal 可以安全地做這個判斷。

Codex lifecycle hooks 仍在快速演進。部分 `codex exec` 與 Windows execution path 曾有 upstream hook coverage gap，因此 ExecWeave 只記錄 provider 真正送出的 hook，不假設所有 execution mode 都有完整 semantic coverage。Provider hook 缺失時，獨立的 OS runtime collector 仍可正常運作。

詳細說明見 [`docs/codex-hooks.md`](docs/codex-hooks.md)。

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

任何 bridge 都保持：

```text
inferred: true
causal: false
```

Ambiguous、no-match、compound command、shell builtin 或 unsupported call 都不會硬建 edge。

Correlated Viewer 會顯示 **Correlation Summary**：

- matched
- ambiguous
- no match
- unsupported
- considered tool calls
- correlation window

所以「沒有線」不再被默認解讀成「什麼都沒發生」；它也可能代表 ExecWeave 因證據不足而刻意拒絕推論。

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

**Observed only** 不是把紫色線單純藏起來，而是在 focus traversal 與 layout **之前**就排除 `inferred: true` relationships。

Saved Views 只保存 UI state，不會把 Graph evidence 複製到 browser storage。

## Runtime Evidence

### Portable backend

Portable collector 使用 `psutil` 與 `watchdog`，支援 Linux、macOS、Windows，也是目前 Live Graph backend。

它可以觀察 process lineage 與 process-level network activity；portable filesystem watcher 只能做 session-level correlation，而且極短命 process 仍可能落在 polling interval 之間而被漏掉。

### Linux `strace` backend

Debian/Ubuntu：

```bash
sudo apt-get install strace
execweave record --backend strace --open -- claude
```

Linux reference backend 會追 descendants，並把 syscall evidence 轉成 process-attributed process / filesystem / network events。

`execweave-claude-record --backend auto` 與 `execweave-codex-record --backend auto` 在 Linux 有 `strace` 時會優先使用它。

後續仍規劃 Linux eBPF、Windows ETW 與 macOS Endpoint Security native collector。

## Graph-first Evidence Model

每一筆 observation 都是：

```text
source --RELATION--> target
```

Runtime 例子：

```text
session --LAUNCHED--> process
process --SPAWNED--> process
process --EXECUTED--> executable
process --OPENED_READ--> file
process --OPENED_WRITE--> file
process --CONNECTED_TO--> network_endpoint
```

Semantic 例子：

```text
agent --USED_MODEL--> model
agent --REQUESTED_TOOL_CALL--> tool_call
tool_call --USES_TOOL--> tool
tool_call --DECLARED_COMMAND--> command
```

Derived relation：

```text
tool_call --CORRELATED_WITH_PROCESS--> process
```

Repeated evidence 會聚合；同一 process 對同一 file open 17 次，Graph 只保留一條 edge 並記錄 `count = 17`。

## 不製造假的因果關係

ExecWeave 明確區分：

- **observed causal evidence**：例如 syscall-attributed process action
- **observed non-causal/session evidence**：例如 portable filesystem change
- **provider semantic evidence**：Agent / Tool layer 自己回報的行為
- **inferred relationship**：由多個 evidence source 保守推導出的 bridge

Provider hook 目前沒有提供能直接證明 Tool → Process 的 child OS PID。單純時間接近不夠，候選不唯一就不建 edge。

同樣地，一個 process 先讀 sensitive file、之後連 external endpoint，也不能被包裝成「檔案內容已經送出去」。

## Security Analysis

第一版 conservative analysis layer：

```bash
execweave analyze run.graph.json
execweave analyze run.graph.json --output analysis.json
```

它可標記 sensitive-file access、external endpoint 與 possible sensitive-file → network path，但會明確保留：

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

大型 Graph 可以把大量 repetitive leaf resource 壓縮：

```bash
execweave graph-condense run.graph.json \
  --output run.compact.graph.json \
  --threshold 8
```

需要 Viewer 可按需還原原始 cluster members 時，加上 `--keep-expansion`。

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
- conservative Tool → Process correlation
- Correlation Summary
- explainable initial security analysis
- Ubuntu / macOS / Windows × Python 3.10 / 3.12 CI

後續重點：

- Linux eBPF
- Windows ETW
- macOS Endpoint Security
- 更多 provider adapter
- 更強的 process/tool identity evidence
- 更完整的 MCP normalization
- long-run performance / scalability

## Privacy

ExecWeave 是 **local-first**。

Runtime event、semantic sidecar、Graph、Report、Viewer 預設都留在本機；standalone Viewer 不需要外部 CDN。

ExecWeave 不主動蒐集 file content 或 raw read/write byte buffer。Native semantic adapter 預設也不抓 prompt / transcript content，但 command、path、endpoint metadata、session identifier 等仍可能是敏感資訊。

分享 artifact 前請自行檢查。

## 文件

- [`Phase 1 — Runtime Collection`](docs/phase-1-runtime-collection.md)
- [`Phase 2 — Execution Graph`](docs/phase-2-execution-graph.md)
- [`Live Graph`](docs/live-graph.md)
- [`Semantic Telemetry`](docs/semantic-telemetry.md)
- [`Claude Code Hooks`](docs/claude-code-hooks.md)
- [`OpenAI Codex Hooks`](docs/codex-hooks.md)
- [`Security Analysis`](docs/security-analysis.md)

## Contributing

**非常歡迎一起貢獻 ExecWeave。**

目前特別需要：

- Linux eBPF
- Windows ETW
- macOS Endpoint Security
- Agent / Tool / MCP provider adapter
- process / entity resolution
- provenance / correlation methods
- Graph visualization 與大型 run UX
- privacy / redaction
- testing / performance evaluation
- documentation

可以直接開 issue、提出 architecture idea、增加 integration，或送 pull request。

> **讓 AI Agent 的執行行為真正變得可理解。**

## License

見 [`LICENSE`](LICENSE)。
