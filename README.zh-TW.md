# ExecWeave

<p align="center">
  <a href="README.md">English</a> |
  <strong>繁體中文</strong> |
  <a href="README.zh-CN.md">简体中文</a> |
  <a href="README.ja.md">日本語</a> |
  <a href="README.ko.md">한국어</a>
</p>

**看清楚 AI Agent 在你的電腦上實際做了什麼。**

ExecWeave 是一個開源、local-first 的 AI Agent runtime observability 專案。它把本機 Agent 的執行行為轉成互動式 execution graph，而不是逼使用者閱讀幾百、幾千行 CLI log。

ExecWeave 會連接 Agent、session、process、file、executable、socket 與 network endpoint 等 runtime entity，並保留支撐每條 edge 的 evidence。

> **把不透明的 AI Agent 執行過程，變成人類真正看得懂的圖。**

## 最快開始方式

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

Debian / Ubuntu 若要使用 Linux reference backend：

```bash
sudo apt-get install strace
```

接著只需要一個命令：

```bash
execweave record --open -- claude
```

其他 Agent 也一樣：

```bash
execweave record --open -- codex
execweave record --open -- gemini
execweave record --open -- opencode
execweave record --open -- python my_agent.py
```

`record` 會在 Agent 結束後自動完成：

```text
AI Agent
   ↓
Runtime Collection
   ↓
events.jsonl
   ↓ validate
Execution Graph
   ↓
graph.json
   ↓
viewer.html
```

預設輸出：

```text
.execweave/runs/<session-id>/
├── events.jsonl
├── graph.json
└── viewer.html
```

也可以指定位置：

```bash
execweave record --output-dir my-run --open -- claude
```

ExecWeave 預設拒絕覆寫既有且非空的 artifact，避免不同 run 被混在一起。

## 目前狀態

ExecWeave 目前版本為 **v0.3.0**。

### Phase 1 — Runtime Collection

**Linux reference path 與跨平台 portable fallback 已完成。**

- graph-ready JSONL event stream
- monotonic sequence
- root / descendant process capture
- Linux syscall-backed short-lived process capture
- process-attributed file open/create/delete/rename
- IPv4 / IPv6 / Unix-socket connection evidence
- non-blocking / failed connection attempt 保留
- Linux / macOS / Windows portable fallback
- causal / non-causal attribution
- event validator
- diagnostics / benchmark / CI

### Phase 2 — Execution Graph

**核心 Graph materialization 與 query layer 已完成第一版。**

- validated JSONL → graph JSON
- node deduplication
- repeated edge aggregation
- temporal first/last metadata
- supporting event IDs
- causality preservation
- graph summary
- graph filtering
- directed path query

### Phase 3 — Interactive Viewer

**Standalone local Viewer MVP 已完成第一版。**

- 不依賴 CDN / 外部 JavaScript
- pan / zoom
- node drag
- node / edge detail
- search
- causal / non-causal edge 視覺區分
- automatic directional layout

目前尚未做到 Agent 執行中的 live graph update。

## 進階手動流程

一般使用者建議直接使用 `record`。每個階段也可以獨立操作。

### 1. 查看 backend

```bash
execweave doctor
```

### 2. 收集 runtime events

```bash
execweave run --output run.jsonl -- claude
```

指定 backend：

```bash
execweave run --backend strace --output run.jsonl -- claude
execweave run --backend portable --output run.jsonl -- claude
```

### 3. 驗證 event stream

```bash
execweave validate run.jsonl
```

中斷的 run：

```bash
execweave validate --allow-incomplete run.jsonl
```

### 4. 建立 Graph

```bash
execweave graph run.jsonl --output run.graph.json
```

### 5. 開啟 Viewer

```bash
execweave view run.graph.json --output run.html --open
```

## Graph-first event model

每一筆 runtime observation 都表示成：

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
process --DELETED--> file
process --CONNECTED_TO--> network_endpoint
process --CONNECT_ATTEMPTED--> network_endpoint
```

如果同一個 process 對同一個 file 發生 17 次相同行為，Phase 2 只會 materialize 一條 edge：

```text
process --OPENED_READ--> file
count = 17
```

而不是畫出 17 條重疊線。

## 不製造假的因果關係

Linux syscall evidence 可以證明：

```text
process --OPENED_WRITE--> file
```

並標記：

```json
{
  "attribution": "syscall",
  "causal": true
}
```

Portable filesystem watcher 只能證明：

```text
session --OBSERVED_FILE_CHANGE--> file
```

因此標記：

```json
{
  "attribution": "session_observation",
  "causal": false
}
```

ExecWeave 不會把 temporal correlation 包裝成 causal proof。

## Backend

### `strace` — Linux reference backend

使用 `strace -ff` 跟隨 descendant process，將 process/filesystem/network syscall evidence 轉成 graph-ready events。

Raw trace 預設解析後刪除：

```bash
execweave run --keep-native-trace -- claude
```

### `portable` — 跨平台 fallback

使用 psutil + watchdog，可在 Linux、macOS、Windows 上執行。較弱的 filesystem attribution 會維持 non-causal，不會偽裝成 process-level 因果關係。

未來 native backend：

- Linux eBPF
- Windows ETW
- macOS Endpoint Security

## Event stream 完整性

一個 JSONL event file 只代表一個 ExecWeave session。

```bash
execweave validate run.jsonl
```

Validator 會檢查：

- JSONL 結構
- 單一 session ID
- unique event ID
- 從 1 開始且連續的 sequence
- timestamp
- entity fields
- session lifecycle

ExecWeave 也會拒絕把新 run append 到既有非空 event stream。

## Graph 查詢

Graph 摘要：

```bash
execweave graph-summary run.graph.json
```

只保留 causal edge：

```bash
execweave graph-filter run.graph.json \
  --output causal.graph.json \
  --causal-only
```

只看 process / network：

```bash
execweave graph-filter run.graph.json \
  --output process-network.graph.json \
  --node-type process \
  --node-type network_endpoint
```

找 directed runtime path：

```bash
execweave path run.graph.json SOURCE_NODE_ID TARGET_NODE_ID --causal-only
```

Graph contract 請參考 [`docs/phase-2-execution-graph.md`](docs/phase-2-execution-graph.md)。

## Interactive Viewer

```bash
execweave view run.graph.json --output run.html --open
```

目前支援：

- wheel zoom
- background drag / pan
- node drag
- node / edge JSON detail
- node ID / name / type search
- causal / non-causal edge styling
- fit / reset

Viewer 是 standalone local HTML，不需要外部 CDN。

## Benchmark

```bash
execweave benchmark --backend portable --iterations 5
execweave benchmark --backend strace --iterations 5
```

這是 engineering smoke benchmark，不是正式 performance claim。

## Privacy

ExecWeave 是 **local-first**：

- runtime event 預設留在本機
- Graph 在本機建立
- Viewer 是 standalone local file
- 不需要外部 CDN
- 不蒐集 file content
- 不蒐集 `read()` / `write()` byte buffer
- raw Linux syscall trace 預設解析後刪除

Runtime metadata 仍可能包含敏感 path、command、endpoint，分享前請檢查。

## Roadmap

### Phase 1

- [x] Runtime collection contract
- [x] Linux reference backend
- [x] Portable fallback
- [x] Causality semantics
- [x] Event validation
- [x] Diagnostics / benchmark / CI
- [ ] Linux eBPF
- [ ] Windows ETW
- [ ] macOS Endpoint Security

### Phase 2

- [x] Event → Graph
- [x] Node deduplication
- [x] Edge aggregation
- [x] Temporal metadata
- [x] Summary / filter / path query
- [ ] 更強的 entity resolution
- [ ] Time-window snapshot
- [ ] Large-run compact evidence indexing

### Phase 3

- [x] Standalone local Viewer MVP
- [x] Pan / zoom / drag / search / details
- [ ] Live graph updates
- [ ] Timeline ↔ Graph synchronization
- [ ] Large graph clustering / progressive expansion
- [ ] Saved filter / focused subgraph

### 後續 Security / Research Layer

- [ ] Agent / Tool / MCP semantic telemetry
- [ ] Credential / secret entity
- [ ] Data-flow / taint tracking
- [ ] Anomaly detection
- [ ] Attack-path reconstruction
- [ ] Execution replay
- [ ] Runtime allow / warn / block policy

## 文件

- [`Phase 1 — Runtime Collection`](docs/phase-1-runtime-collection.md)
- [`Phase 2 — Execution Graph`](docs/phase-2-execution-graph.md)

## Contributing

**非常歡迎一起貢獻 ExecWeave。**

目前高影響力方向：

- Linux eBPF
- Windows ETW
- macOS Endpoint Security
- Graph entity resolution
- live / large-graph visualization
- OpenTelemetry / MCP integration
- privacy / redaction
- reproducible Agent workload
- performance evaluation
- README / documentation translation

小型修改可直接 fork 後送 Pull Request。新的 collector 或大型 architecture change 建議先開 Issue，描述 telemetry source、權限需求、Graph relationship 與 causal guarantee。

> **特別歡迎早期 contributor 一起加入。**

## 設計原則

- **Local first** — runtime evidence 預設留在本機。
- **Runtime truth over assumptions** — 優先相信 OS evidence。
- **Graph over log** — relationship 是一等資料。
- **Framework agnostic** — 不綁定單一 Agent / model provider。
- **Explainable attribution** — 每條 edge 都能追查支撐 evidence。
- **No fake causality** — temporal correlation 不等於 causal proof。

## License

請參考 [`LICENSE`](LICENSE)。

---

**開 Issue。提出想法。送 Pull Request。建立 Integration。挑戰現有 Architecture。**

> **一起讓 AI Agent 的執行行為真正變得看得懂。**
