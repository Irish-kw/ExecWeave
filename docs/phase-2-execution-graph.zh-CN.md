<!-- i18n-nav:start -->
<p align="center">
  <a href="phase-2-execution-graph.md">English</a> |
  <a href="phase-2-execution-graph.zh-TW.md">繁體中文</a> |
  <strong>简体中文</strong> |
  <a href="phase-2-execution-graph.ja.md">日本語</a> |
  <a href="phase-2-execution-graph.ko.md">한국어</a>
</p>
<!-- i18n-nav:end -->

# Phase 2 — Execution Graph

Phase 2 会把已通过验证的 Phase 1 JSONL event stream 转成持久化 execution graph，供 CLI query 与本机 Viewer 使用。

## 目前状态

第一版 Graph core 已完成：

```bash
execweave validate run.jsonl
execweave graph run.jsonl
execweave graph-summary run.graph.json
```

Graph builder 不会重新解读 raw telemetry；它直接保留 Phase 1 已定义的 attribution 与 causality semantics。

## Graph schema

目前 graph schema version：

```text
0.1
```

Graph JSON 的基本结构：

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

每一个不同的 event-stream entity ID 会 materialize 成一个 node，例如：

```text
agent:Claude Code
session:<session-id>
process:<session-id>:1234
file:/repo/src/app.py
network_endpoint:1.2.3.4:443
executable:/usr/bin/python
```

Node identity 以 entity ID 为准，不以 display name 判断。

每个 node 会累积：

- `type`
- `name`
- entity attributes
- first/last observed timestamp
- observed event count
- 出现过的 event types

Attribute merge 采保守策略；若后续 event 出现冲突值，不会默默覆写既有 attribute。

## Edges

有 source 与 target 的 event 可以形成 directed edge：

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

同一 tuple 的重复事件会聚合成一条 edge，而不是在 Viewer 画出大量重叠线。

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

代表有 17 笔 event 支援同一个 relationship。

## Causality aggregation

所有 supporting events 都是 causal：

```json
{"causal": true}
```

全部明确 non-causal：

```json
{"causal": false}
```

证据混合或不能形成一致 causality：

```json
{"causal": null}
```

Graph layer 永远不能把 non-causal telemetry 升级成 causal relationship。

## Lifecycle events

有些 Phase 1 event 只有 source 没有 target，例如：

```text
process EXITED
session FINISHED_SESSION
```

Phase 2 不会为它们制造假的 target node 或 self-edge；这些事件只会贡献到 source node 的 observed-event metadata。

## Graph validation boundary

预设只接受完整且合法的 Phase 1 stream：

```bash
execweave graph run.jsonl
```

Incident recovery 或 agent 被中断时可用：

```bash
execweave graph --allow-incomplete interrupted.jsonl
```

这只放宽 completed-session requirement；JSON、session、sequence、entity 等 structural validation 仍必须通过。

## Graph summary

```bash
execweave graph-summary run.graph.json
```

Summary 会显示 event/node/edge count、各 node type/relation 数量、causal/non-causal/mixed edge count，以及 correlated graph 的 metadata（若存在）。

## Filtering

建立新的子图，不修改 source graph：

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

Filters 可组合使用。

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

目前 path search 是 directed、breadth-first、simple-path，并受 `--max-depth` 与 `--max-paths` 限制，避免 cyclic graph 产生无界结果。

## Focus 与 condensation

可从一个 anchor node 建立 N-hop focused subgraph：

```bash
execweave graph-focus run.graph.json NODE_ID \
  --hops 2 \
  --output focused.graph.json
```

大型 run 可把大量 repetitive leaf resource 压成 cluster：

```bash
execweave graph-condense run.graph.json \
  --output run.compact.graph.json \
  --threshold 8 \
  --keep-expansion
```

`--keep-expansion` 会保存原始 member evidence，让 Viewer 可以按需展开；不会新增新的 causal edge。

## Acceptance criteria

- [x] 建图前验证 Phase 1 input
- [x] Entity materialization
- [x] Stable entity ID 去重
- [x] Aggregate repeated `(source, relation, target)`
- [x] Edge evidence preservation
- [x] Causality preservation
- [x] Temporal first/last metadata
- [x] Lifecycle event 不制造假 edge
- [x] Graph summary
- [x] Graph filtering
- [x] Directed path query
- [x] Focused subgraph
- [x] Condensation / progressive expansion contract

后续仍包含更强的 cross-resource entity resolution、超大型 run evidence indexing、schema migration/versioning 与长时间执行效能优化。
