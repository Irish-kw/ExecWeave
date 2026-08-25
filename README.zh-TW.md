# ExecWeave

<p align="center">
  <a href="README.md">English</a> |
  <strong>繁體中文</strong> |
  <a href="README.zh-CN.md">简体中文</a> |
  <a href="README.ja.md">日本語</a> |
  <a href="README.ko.md">한국어</a>
</p>

**看清楚 AI Agent 在你的電腦上實際做了什麼。**

ExecWeave 是一個開源、local-first 的 AI Agent runtime observability 專案。它把 Agent 的執行行為轉成有 runtime evidence 支撐的互動式 execution graph，而不是逼使用者閱讀幾百、幾千行 CLI log。

> **把不透明的 AI Agent 執行過程，變成人類真正看得懂的圖。**

## 最快開始方式

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

### Agent 還在跑時就看 Graph

```bash
execweave live --open -- claude
```

Live MVP 只會在 `127.0.0.1` 啟動本機 server，Agent 還在執行時瀏覽器裡的 Graph 就會持續更新。Agent 結束後會保存：

```text
.execweave/runs/<session-id>/
├── events.jsonl
├── graph.json
└── viewer.html
```

目前 live 模式刻意只使用 **portable** collector。Linux `strace` backend 是 command 結束後才解析 trace，因此不會把 post-processing 假裝成 live telemetry。

### Claude Code：runtime + semantic graph

ExecWeave 已內建 Claude Code native hook adapter，可把 logical Agent / Tool / MCP / Model evidence 與 runtime evidence 放在同一個 run 中。

先產生一次 hook 設定片段：

```bash
execweave-claude-hook --print-config
```

把輸出的 `hooks` object 合併到 Claude Code settings 後即可一起錄製：

```bash
execweave-claude-record --open -- claude
```

當 semantic hooks 有觸發時，同一個 run directory 會保留分層 evidence 與 merged graph：

```text
.execweave/runs/<run-id>/
├── events.jsonl              # runtime only
├── graph.json                # runtime-only graph
├── viewer.html               # runtime-only viewer
├── semantic.jsonl            # Claude hook evidence only
├── events.semantic.jsonl     # validated merged stream
├── graph.semantic.json       # runtime + semantic graph
└── viewer.semantic.html      # runtime + semantic viewer
```

Claude hook 知道 logical tool call，但 payload 不會提供實際 Bash child PID，因此 ExecWeave **不會把 Tool → Process 假裝成直接 observed 或 causal edge**。

需要保守 bridge 時，可以顯式執行：

```bash
execweave correlate run.semantic.jsonl \
  --output run.correlated.jsonl
execweave graph run.correlated.jsonl \
  --output run.correlated.graph.json
execweave view run.correlated.graph.json \
  --output run.correlated.html \
  --open
```

`execweave correlate` 只有在 bounded tool-call window 內找到**唯一候選**，而且有 exact executable / process / cmdline identity evidence 時才會產生 `CORRELATED_WITH_PROCESS`。像 macOS Python framework 這類 launcher process，也只能使用完整、非空且逐項完全一致的 `argv[1:]` 作 fallback。候選不唯一或沒有 match 就完全不建立 bridge。

任何 correlation edge 都維持：

```text
inferred: true
causal: false
```

並保留 inference method、supporting event IDs 與 heuristic confidence；confidence 明確是 **heuristic score，不是 probability**。

### Linux 上需要更強的 process-level evidence

```bash
sudo apt-get install strace
execweave record --backend strace --open -- claude
```

`execweave-claude-record --backend auto` 在 Linux 有 `strace` 時也會優先使用它。

其他例子：

```bash
execweave live --open -- codex
execweave live --open -- gemini
execweave live --open -- opencode
execweave record --open -- python my_agent.py
```

## 目前狀態

ExecWeave 目前版本為 **v0.4.0**。

### Phase 1 — Runtime Collection

- [x] graph-ready JSONL event stream
- [x] root / descendant process capture
- [x] Linux syscall-backed short-lived process capture
- [x] process-attributed filesystem/network evidence
- [x] portable fallback on Linux / macOS / Windows
- [x] causal / non-causal attribution
- [x] validator / diagnostics / benchmark / CI configuration
- [ ] Linux eBPF
- [ ] Windows ETW
- [ ] macOS Endpoint Security

### Phase 2 — Execution Graph

- [x] validated JSONL → graph JSON
- [x] node deduplication
- [x] repeated edge aggregation
- [x] temporal metadata
- [x] graph summary / filtering / directed path query
- [x] N-hop focused graph artifact
- [x] large-run leaf-resource condensation
- [x] cluster optional exact expansion evidence

### Phase 3 — Interactive Viewer

- [x] standalone local HTML viewer
- [x] localhost Live Graph MVP
- [x] pan / zoom / node drag / search / details
- [x] node type / relation / causal-only filter
- [x] Timeline ↔ Graph synchronization
- [x] evidence-sequence slider + Play/Pause replay
- [x] progressive cluster expansion
- [x] 1-hop / 2-hop focused runtime neighborhood
- [x] browser-local Saved View presets
- [x] causal observed / non-causal observed / inferred edge 獨立樣式
- [x] inferred edge 明確顯示 `· inferred`

Phase 3 的 viewer baseline 已包含 replay、cluster 按需展開、focused neighborhood、本機保存的 view preset，以及明確的 inferred-edge semantics。

### Semantic Telemetry

- [x] provider-agnostic semantic JSONL sidecar
- [x] validated `semantic-merge`，不重寫原始 runtime evidence
- [x] `agent` / `tool_call` / `tool` / `mcp_server` / `model` / `command` entities
- [x] 有 provider PID 時才做 conservative `process_reference` resolution
- [x] Claude Code native session/tool/subagent/model hooks
- [x] `mcp__<server>__<tool>` normalization
- [x] Linux / macOS / Windows 的 run-bound `execweave-claude-record`
- [x] conservative Tool → Process correlation v0.1
- [x] unique-candidate hard requirement；ambiguous / no-match 不建 edge
- [x] inference method / supporting event IDs / bounded time window / heuristic confidence
- [x] correlation edge 永遠維持 `causal: false`

其他 provider adapter、更強的 identity resolution 與更豐富的 correlation evidence 仍是後續工作。

### Security Analysis

第一版 explainable rule layer 已加入：

```bash
execweave analyze run.graph.json
execweave analyze run.graph.json --output analysis.json
```

目前會標記 sensitive-file access、external endpoint，以及 possible sensitive-file → network path。

這只能說明 evidence 的關係與順序，**不能證明檔案內容真的被送出去**。Report 會明確保留：

```json
{
  "data_flow_proven": false,
  "exfiltration_proven": false
}
```

## 手動流程

```bash
execweave doctor
execweave run --output run.jsonl -- claude
execweave validate run.jsonl
execweave graph run.jsonl --output run.graph.json
execweave view run.graph.json --output run.html --open
```

### Merge semantic sidecar

```bash
execweave semantic-merge run.jsonl semantic.jsonl \
  --output run.semantic.jsonl
execweave validate run.semantic.jsonl
```

### Correlate semantic tool call 與 runtime process evidence

```bash
execweave correlate run.semantic.jsonl \
  --output run.correlated.jsonl
execweave graph run.correlated.jsonl \
  --output run.correlated.graph.json
```

這一步會產生新的 derived stream，不會重寫 input evidence。`CORRELATED_WITH_PROCESS` 的意思是「目前 bounded evidence 在既定 heuristic 下只支持一個候選」，不是「provider 提供了 PID」，也不是「已證明 causality」。

### Focus 一個 runtime neighborhood

```bash
execweave graph-focus run.graph.json PROCESS_NODE_ID \
  --hops 2 \
  --direction both \
  --causal-only \
  --output focused.graph.json

execweave view focused.graph.json \
  --output focused.html \
  --open
```

`--direction` 支援 `in`、`out`、`both`；可以重複使用 `--relation` 限定 traversal edge。所有限制都會在 traversal **之前**套用，`graph-focus` 只複製原本存在的 node 與 evidence edge，不會創造 shortcut 或新的 causal relationship。

Viewer 中也能直接點 node，選 **Focus 1 hop** 或 **Focus 2 hops**；按 **Clear focus** 回到目前 filter 下的完整 Graph。

### 大型 Graph condensation

```bash
execweave graph-condense run.graph.json \
  --output run.compact.graph.json \
  --threshold 8
```

只有「單一 incoming relationship 且沒有 downstream behavior」的 file/directory/executable leaf 才會被折疊。Process、Agent、Session、Socket、Network Endpoint 預設不折疊。

如果希望 Viewer 可以按需展開 cluster：

```bash
execweave graph-condense run.graph.json \
  --output run.expandable.graph.json \
  --threshold 8 \
  --keep-expansion

execweave view run.expandable.graph.json \
  --output run.expandable.html \
  --open
```

可展開 cluster 會以虛線外框顯示。點擊 cluster 後選 **Expand cluster**，只會把該 cluster 換回原始 member nodes 與 evidence edges，其他 cluster 維持折疊。按 **Collapse clusters** 可全部還原成 compact view。

`--keep-expansion` 只是把原始 observed nodes/edges 保存到 expansion payload，**不會創造新的 causal relationship**。

## Timeline ↔ Graph

Standalone Viewer 會依 Graph edge 的 `first_sequence` / `last_sequence` 提供 **Evidence sequence** 滑桿與 Play/Pause replay。

把滑桿往回拉，就能看到 Agent 的行為圖依 evidence 順序逐步長出來。若同一條 aggregated edge 在目前 sequence 只出現部分 evidence，Viewer 會顯示 `partial`，**不會提前把最終 `count` 洩漏到過去時間點**。

Timeline 可以和 node type、relation、causal-only、search、focused neighborhood，以及逐步展開的 cluster 一起使用。

## Saved Views

Viewer 的 **Save view** 會保存目前的 node/relation/causal filter、search、timeline 位置、focus 狀態與已展開 cluster。

Preset 預設只存放在瀏覽器本機 storage，而且**只包含 UI state，不包含 Graph node、edge、event evidence、file content 或 prompt**。如果瀏覽器不允許 local storage，會安全退化成目前頁面 session 內的暫存 preset，不影響 Viewer 使用。

## Graph-first event model

```text
source --RELATION--> target
```

例如：

```text
session --LAUNCHED--> process
process --SPAWNED--> process
process --EXECUTED--> executable
process --OPENED_READ--> file
process --OPENED_WRITE--> file
process --CONNECTED_TO--> network_endpoint
process --CONNECT_ATTEMPTED--> network_endpoint
agent --REQUESTED_TOOL_CALL--> tool_call
tool_call --DECLARED_COMMAND--> command
tool_call --CORRELATED_WITH_PROCESS--> process   # inferred only
```

Repeated evidence 會聚合到同一條 edge 的 `count`，不會畫出大量重疊線。

## 不製造假的因果關係

Linux syscall-backed evidence 可以有 `causal: true` 的 process-level edge；portable filesystem watcher 只能證明 session 期間發生變化，因此維持 `causal: false`。

Claude hook 沒提供 child PID 時，semantic evidence 也不會被當成 OS attribution。Correlation stage 即使找到唯一候選，edge 仍保持 `inferred: true` / `causal: false`。單純時間接近不夠，ambiguous 就不建 edge。

ExecWeave 也不會把同一 process 的 file/network activity 包裝成 byte-level data flow。

## Live Graph

```bash
execweave live --open -- claude
execweave live --port 8765 --open -- claude
execweave live --linger 10 --open -- claude
```

Live HTTP server 只綁定 `127.0.0.1`，預設不暴露到 LAN。詳細契約見 [`docs/live-graph.md`](docs/live-graph.md)。

## Privacy

ExecWeave 是 **local-first**：runtime event、Graph、Viewer、semantic sidecar 與 merged graph 預設留在本機；Saved View 只保存 UI state；不需要外部 CDN；不蒐集 file content 或 `read()` / `write()` byte buffer；raw Linux syscall trace 預設解析後刪除。

Runtime / semantic metadata 仍可能包含敏感 path、command、endpoint 與 provider identifier，分享 artifact 前請檢查。

## 文件

- [`Phase 1 — Runtime Collection`](docs/phase-1-runtime-collection.md)
- [`Phase 2 — Execution Graph`](docs/phase-2-execution-graph.md)
- [`Live Graph`](docs/live-graph.md)
- [`Semantic Telemetry`](docs/semantic-telemetry.md)
- [`Claude Code Hooks`](docs/claude-code-hooks.md)
- [`Security Analysis`](docs/security-analysis.md)

## Contributing

**非常歡迎一起貢獻 ExecWeave。** 特別需要 Linux eBPF、Windows ETW、macOS Endpoint Security、Graph entity resolution、更多 Agent/Tool/MCP provider adapter、更強的 semantic/runtime correlation evidence、OpenTelemetry/MCP、privacy/redaction、testing 與 performance evaluation。

`README.md` 是 canonical English source，README 與文件翻譯也非常歡迎貢獻。

## License

請參考 [`LICENSE`](LICENSE)。