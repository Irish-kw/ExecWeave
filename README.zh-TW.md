# ExecWeave

<p align="center">
  <a href="README.md">English</a> |
  <strong>繁體中文</strong> |
  <a href="README.zh-CN.md">简体中文</a> |
  <a href="README.ja.md">日本語</a> |
  <a href="README.ko.md">한국어</a>
</p>

**看清楚 AI Agent 在你的電腦上實際做了什麼。**

ExecWeave 是一個開源、local-first 的 AI Agent runtime observability 專案。它把本機 Agent 的執行行為轉成 execution graph，而不是逼你閱讀幾百、幾千行 CLI log。

ExecWeave 會蒐集 Agent、session、process、file、executable、socket 與 network endpoint 之間的關係，將 event materialize 成 Graph，最後產生可以直接在瀏覽器開啟的互動式本機 HTML viewer。

> **把不透明的 AI Agent 執行過程，變成人類真正看得懂的圖。**

## 目前狀態

### Phase 1 — Runtime Collection

**Linux reference path 與跨平台 portable fallback 已完成。**

目前支援：

- graph-ready JSONL event stream；
- 每次 run 單調遞增的 event sequence；
- root 與 descendant process capture；
- Linux syscall-backed 短生命週期 process capture；
- Linux process-attributed file open/create/delete/rename；
- Linux IPv4/IPv6/Unix-socket connection evidence；
- 保留 non-blocking / failed `connect()` attempt；
- Linux、macOS、Windows 的 psutil/watchdog portable fallback；
- causal 與 non-causal/session-observation 明確區分；
- event-stream validator；
- backend diagnostics / auto selection；
- benchmark harness 與 cross-platform CI。

### Phase 2 — Execution Graph

**核心 Graph materialization 與 query layer 已完成第一版。**

- validated JSONL → graph JSON；
- node deduplication；
- repeated edge aggregation；
- temporal first/last metadata；
- evidence event IDs；
- causality preservation；
- graph summary；
- graph filtering；
- directed path query。

### Phase 3 — Interactive Viewer

**本機互動式 Viewer MVP 已完成第一版。**

- standalone HTML；
- 不依賴 CDN 或外部 JavaScript library；
- pan / zoom；
- node drag；
- node / edge 詳情；
- graph search；
- causal / non-causal edge 視覺區分。

目前尚未做到 Agent 執行途中即時更新 Graph；live view 會是下一步。

## 快速開始

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

Debian / Ubuntu 若要使用 Linux reference backend：

```bash
sudo apt-get install strace
```

檢查目前可用 backend：

```bash
execweave doctor
```

### 1. 記錄一次 Agent 執行

```bash
execweave run --output run.jsonl -- claude
```

也可以：

```bash
execweave run --output run.jsonl -- codex
execweave run --output run.jsonl -- gemini
execweave run --output run.jsonl -- opencode
execweave run --output run.jsonl -- python my_agent.py
```

### 2. 驗證 event stream

```bash
execweave validate run.jsonl
```

### 3. 建立 Execution Graph

```bash
execweave graph run.jsonl --output run.graph.json
```

### 4. 在瀏覽器打開互動式 Graph

```bash
execweave view run.graph.json --output run.html --open
```

完整流程：

```text
AI Agent
   ↓
Runtime Collection
   ↓
run.jsonl
   ↓ validate
Execution Graph
   ↓
run.graph.json
   ↓ view
Standalone Interactive HTML
```

## Graph-first event model

Phase 1 每一筆 observation 都以：

```text
source --RELATION--> target
```

表示，例如：

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

Phase 2 會把重複 evidence 聚合。例如某個 process 對同一檔案 open 17 次，Graph 只會有一條 edge：

```text
process --OPENED_READ--> file
count = 17
```

而不是畫 17 條重疊的線。

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

但 portable filesystem watcher 只能證明：

```text
session --OBSERVED_FILE_CHANGE--> file
```

因此會明確標記：

```json
{
  "attribution": "session_observation",
  "causal": false
}
```

ExecWeave 不會把時間上的相關性偽裝成因果證據。

## Backend

### `strace` — Linux reference backend

Linux reference backend 使用 `strace -ff` 跟隨 descendant process，再把 process/filesystem/network syscall evidence 轉成 graph-ready events。

Raw trace 預設解析後刪除；只有除錯時才保留：

```bash
execweave run --keep-native-trace -- claude
```

### `portable` — 跨平台 fallback

Portable backend 使用 psutil + watchdog，可在 Linux、macOS、Windows 執行。

它不假裝具備 native sensor 的精度：極短生命週期 process 可能漏掉，而 filesystem change 只會標成 session-correlated、non-causal observation。

`auto` 是預設設定，在 Linux 有 `strace` 時優先使用 `strace`，否則使用 `portable`。

## Event stream 完整性

一個 event file 只代表一個 ExecWeave session。

ExecWeave 預設拒絕把第二次 run append 到已存在且非空的 event file，避免 sequence 與 session identity 被污染。

驗證完成的 run：

```bash
execweave validate run.jsonl
```

若 Agent 被中斷、沒有 `session.finished`：

```bash
execweave validate --allow-incomplete run.jsonl
```

Validator 會檢查 JSON、schema、event ID、session ID、sequence、timestamp、entity fields 與 session lifecycle。

## Graph 查詢

摘要：

```bash
execweave graph-summary run.graph.json
```

只保留 causal edge：

```bash
execweave graph-filter run.graph.json \
  --output causal.graph.json \
  --causal-only
```

只看 process 與 network endpoint：

```bash
execweave graph-filter run.graph.json \
  --output process-network.graph.json \
  --node-type process \
  --node-type network_endpoint
```

查 directed runtime path：

```bash
execweave path run.graph.json SOURCE_NODE_ID TARGET_NODE_ID --causal-only
```

Graph contract 與 query semantics 請參考 [`docs/phase-2-execution-graph.md`](docs/phase-2-execution-graph.md)。

## Interactive Viewer

產生 standalone local HTML：

```bash
execweave view run.graph.json --output run.html
```

產生後直接開啟：

```bash
execweave view run.graph.json --output run.html --open
```

目前 Viewer 支援：

- 滾輪 zoom；
- 拖曳背景 pan；
- 拖曳 node 重新排列；
- 點擊 node / edge 查看 JSON evidence；
- 依 node ID、name、type 搜尋；
- causal / non-causal edge 顯示；
- 自動 directional layout 與 fit-to-screen。

## Benchmark

```bash
execweave benchmark --backend portable --iterations 5
execweave benchmark --backend strace --iterations 5
```

這是工程 smoke benchmark，數字依機器而異，不代表正式 performance claim。

## Privacy

ExecWeave 是 **local-first**：

- event data 預設留在本機；
- graph materialization 在本機完成；
- HTML viewer 是 standalone local file；
- Viewer 不需要外部 CDN；
- 不蒐集 file content；
- 不蒐集 `read()` / `write()` byte buffer；
- raw Linux syscall trace 預設解析後刪除。

Runtime metadata 仍可能包含敏感 file path、command、endpoint；分享前請自行檢查。

## Roadmap

### Phase 1 — Runtime Collection

- [x] Graph-ready event schema
- [x] Process/file/network collection
- [x] Linux short-lived process capture
- [x] Causal attribution semantics
- [x] Event validation
- [x] Diagnostics
- [x] Benchmark harness
- [x] Cross-platform portable fallback

未來 native backend：

- [ ] Linux eBPF
- [ ] Windows ETW
- [ ] macOS Endpoint Security

### Phase 2 — Execution Graph

- [x] Event → Graph materialization
- [x] Node deduplication
- [x] Edge aggregation
- [x] Temporal first/last metadata
- [x] Graph summary
- [x] Graph filtering
- [x] Directed path query
- [ ] 更強的跨 resource entity resolution
- [ ] Time-window graph snapshot
- [ ] 大型 run 的 compact evidence indexing

### Phase 3 — Interactive UI

- [x] Standalone local HTML viewer MVP
- [x] Pan / zoom / drag
- [x] Search
- [x] Node / edge details
- [x] Causality visualization
- [ ] Agent 執行中的 live graph update
- [ ] Timeline ↔ graph synchronization
- [ ] Large graph clustering / progressive expansion
- [ ] Saved filter / focused subgraph

### 後續 Security / Research Layer

- [ ] Agent / Tool / MCP semantic telemetry
- [ ] Credential / secret entities
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

目前高影響力方向包括：

- Linux eBPF collector；
- Windows ETW collector；
- macOS Endpoint Security collector；
- Graph entity resolution；
- Graph visualization / large-graph UX；
- OpenTelemetry / MCP integration；
- privacy / redaction；
- reproducible agent workload；
- performance evaluation；
- README 與文件翻譯。

小型修改可以直接 fork repository 並送 Pull Request。新的 collector 或大型 architecture change 建議先開 Issue，說明 telemetry source、需要的權限、預期 Graph relationship 與 causal guarantee。

> **特別歡迎早期 contributor 一起加入。**

## 設計原則

- **Local first** — runtime evidence 預設留在本機。
- **Runtime truth over assumptions** — 優先相信 OS evidence，而不是只相信 Agent framework。
- **Graph over log** — relationship 是一等資料。
- **Framework agnostic** — 不綁單一 model / agent provider。
- **Explainable attribution** — 每條 edge 都應該能說明為什麼存在。
- **No fake causality** — temporal correlation 不是 causal proof。

## License

請參考 [`LICENSE`](LICENSE)。

---

**開 Issue。提出想法。送 Pull Request。建立 Integration。挑戰現有 Architecture。**

> **一起讓 AI Agent 的執行行為真正變得看得懂。**
