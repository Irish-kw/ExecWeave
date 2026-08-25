<!-- i18n-nav:start -->
<p align="center">
  <a href="phase-2-execution-graph.md">English</a> |
  <strong>繁體中文</strong> |
  <a href="phase-2-execution-graph.zh-CN.md">简体中文</a> |
  <a href="phase-2-execution-graph.ja.md">日本語</a> |
  <a href="phase-2-execution-graph.ko.md">한국어</a>
</p>
<!-- i18n-nav:end -->

# Phase 2 — Execution Graph

Phase 2 會把已通過驗證的 Phase 1 JSONL event stream 轉成持久化 execution graph，供 CLI query 與本機 Viewer 使用。

## 目前狀態

第一版 Graph core 已完成：

```bash
execweave validate run.jsonl
execweave graph run.jsonl
execweave graph-summary run.graph.json
```

Graph builder 不會重新解讀 raw telemetry；它直接保留 Phase 1 已定義的 attribution 與 causality semantics。

## Graph schema

目前 graph schema version：

```text
0.1
```

Graph JSON 的基本結構：

```json
{
  "graph_schema_version": "0.1",
  "session_id": "...",
  "event_count": 100,
  "node_count": 24,
  "edge_count": 31,
  "nodes": [],
  "edges": []
}
```

## Nodes

每一個不同的 event-stream entity ID 會 materialize 成一個 node，例如：

```text
agent:Claude Code
session:<session-id>
process:<session-id>:1234
file:/repo/src/app.py
network_endpoint:1.2.3.4:443
executable:/usr/bin/python
```

Node identity 以 entity ID 為準，不以 display name 判斷。

每個 node 會累積：

- `type`
- `name`
- entity attributes
- first/last observed timestamp
- observed event count
- 出現過的 event types

Attribute merge 採保守策略；若後續 event 出現衝突值，不會默默覆寫既有 attribute。

## Edges

有 source 與 target 的 event 可以形成 directed edge：

```text
source --RELATION--> target
```

例如：

```text
session --LAUNCHED--> process
process --SPAWNED--> process
process --OPENED_READ--> file
process --CONNECTED_TO--> network_endpoint
```

Edge identity 是：

```text
(source, relation, target)
```

同一 tuple 的重複事件會聚合成一條 edge，而不是在 Viewer 畫出大量重疊線。

Aggregated edge 保存：

- occurrence `count`
- first/last timestamp
- first/last sequence
- supporting event IDs
- contributing event types
- backend(s)
- attribution method(s)
- causality state

例如：

```text
process:p1 --OPENED_READ--> file:a.txt
count = 17
```

代表有 17 筆 event 支援同一個 relationship。

## Causality aggregation

所有 supporting events 都是 causal：

```json
{"causal": true}
```

全部明確 non-causal：

```json
{"causal": false}
```

證據混合或不能形成一致 causality：

```json
{"causal": null}
```

Graph layer 永遠不能把 non-causal telemetry 升級成 causal relationship。

## Lifecycle events

有些 Phase 1 event 只有 source 沒有 target，例如：

```text
process EXITED
session FINISHED_SESSION
```

Phase 2 不會為它們製造假的 target node 或 self-edge；這些事件只會貢獻到 source node 的 observed-event metadata。

## Graph validation boundary

預設只接受完整且合法的 Phase 1 stream：

```bash
execweave graph run.jsonl
```

Incident recovery 或 agent 被中斷時可用：

```bash
execweave graph --allow-incomplete interrupted.jsonl
```

這只放寬 completed-session requirement；JSON、session、sequence、entity 等 structural validation 仍必須通過。

## Graph summary

```bash
execweave graph-summary run.graph.json
```

Summary 會顯示 event/node/edge count、各 node type/relation 數量、causal/non-causal/mixed edge count，以及 correlated graph 的 metadata（若存在）。

## Filtering

建立新的子圖，不修改 source graph：

```bash
execweave graph-filter run.graph.json \
  --output causal.graph.json \
  --causal-only
```

依 relation：

```bash
execweave graph-filter run.graph.json \
  --output network.graph.json \
  --relation CONNECTED_TO \
  --relation CONNECT_ATTEMPTED
```

依 node type：

```bash
execweave graph-filter run.graph.json \
  --output process-network.graph.json \
  --node-type process \
  --node-type network_endpoint
```

依 backend：

```bash
execweave graph-filter run.graph.json \
  --output syscall.graph.json \
  --backend strace
```

Filters 可組合使用。

## Directed path query

```bash
execweave path run.graph.json \
  'session:abc' \
  'network_endpoint:1.2.3.4:443'
```

只沿 causal edge：

```bash
execweave path run.graph.json SOURCE TARGET --causal-only
```

限制 relations：

```bash
execweave path run.graph.json SOURCE TARGET \
  --relation LAUNCHED \
  --relation SPAWNED \
  --relation CONNECTED_TO
```

目前 path search 是 directed、breadth-first、simple-path，並受 `--max-depth` 與 `--max-paths` 限制，避免 cyclic graph 產生無界結果。

## Focus 與 condensation

可從一個 anchor node 建立 N-hop focused subgraph：

```bash
execweave graph-focus run.graph.json NODE_ID \
  --hops 2 \
  --output focused.graph.json
```

大型 run 可把大量 repetitive leaf resource 壓成 cluster：

```bash
execweave graph-condense run.graph.json \
  --output run.compact.graph.json \
  --threshold 8 \
  --keep-expansion
```

`--keep-expansion` 會保存原始 member evidence，讓 Viewer 可以按需展開；不會新增新的 causal edge。

## Acceptance criteria

- [x] 建圖前驗證 Phase 1 input
- [x] Entity materialization
- [x] Stable entity ID 去重
- [x] Aggregate repeated `(source, relation, target)`
- [x] Edge evidence preservation
- [x] Causality preservation
- [x] Temporal first/last metadata
- [x] Lifecycle event 不製造假 edge
- [x] Graph summary
- [x] Graph filtering
- [x] Directed path query
- [x] Focused subgraph
- [x] Condensation / progressive expansion contract

後續仍包含更強的 cross-resource entity resolution、超大型 run evidence indexing、schema migration/versioning 與長時間執行效能優化。
