<!-- i18n-nav:start -->
<p align="center">
  <a href="phase-2-execution-graph.md">English</a> |
  <a href="phase-2-execution-graph.zh-TW.md">繁體中文</a> |
  <a href="phase-2-execution-graph.zh-CN.md">简体中文</a> |
  <strong>日本語</strong> |
  <a href="phase-2-execution-graph.ko.md">한국어</a> |
  <a href="phase-2-execution-graph.fr.md">Français</a> |
  <a href="phase-2-execution-graph.de.md">Deutsch</a> |
  <a href="phase-2-execution-graph.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# Phase 2 — Execution Graph

Phase 2 は、validated Phase 1 JSONL event stream を永続的な execution graph に変換し、query や後続の local UI visualization に利用できるようにします。

## Current status

最初の Phase 2 graph core は実装済みです。

```bash
execweave validate run.jsonl
execweave graph run.jsonl
execweave graph-summary run.graph.json
```

Graph builder は raw telemetry を再解釈しません。Phase 1 が生成した attribution と causality semantics をそのまま消費します。

## Graph schema

現在の graph schema version は次です。

```text
0.1
```

Graph JSON document は次を含みます。

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

Phase 1 の distinct entity ID はそれぞれ 1 つの graph node になります。

例：

```text
agent:Claude Code
session:<session-id>
process:<session-id>:1234
file:/repo/src/app.py
network_endpoint:1.2.3.4:443
executable:/usr/bin/python
```

Node identity は display name ではなく event-stream entity ID に基づきます。

各 node は次を蓄積します。

- `type`
- `name`
- entity attributes
- first observed timestamp
- last observed timestamp
- observed event count
- その entity が現れた event type

Phase 2 は現在 conservative attribute merging を使用します。既存 node attribute が後続の conflicting value によって黙って上書きされることはありません。

## Edges

Source と target の両方を持つ event は directed graph edge を生成できます。

```text
source --RELATION--> target
```

例えば：

```text
session --LAUNCHED--> process
process --SPAWNED--> process
process --OPENED_READ--> file
process --CONNECTED_TO--> network_endpoint
```

Edge identity は次の tuple です。

```text
(source, relation, target)
```

同じ tuple に対する repeated event は重複 line として描画されず、1 つの edge に aggregate されます。

Aggregated edge は次を記録します。

- 正確な occurrence `count`
- first/last timestamp
- first/last sequence number
- supporting event ID
- contributing event type
- backend
- attribution method
- causality state

例：

```text
process:p1 --OPENED_READ--> file:a.txt
count = 17
```

これは同じ graph relationship を 17 個の Phase 1 event が支持していることを意味します。

## Causality aggregation

すべての supporting event が causal の場合：

```json
{"causal": true}
```

すべてが明示的に non-causal の場合：

```json
{"causal": false}
```

Supporting evidence が mixed、または uniform な causality value を持たない場合：

```json
{"causal": null}
```

Graph layer は non-causal telemetry を causal relationship に upgrade してはいけません。

## Lifecycle events

一部の Phase 1 event は source を持ち target を持ちません。例えば：

```text
process EXITED
session FINISHED_SESSION
```

Phase 2 はこれらの event に fake target node や self-edge を作りません。

代わりに source node の observed event metadata に寄与させます。これにより、すべての log event を人工的な node にするのではなく、graph を relational に保ちます。

## Graph validation boundary

デフォルトでは graph construction に valid かつ complete な Phase 1 event stream が必要です。

```bash
execweave graph run.jsonl
```

Incident recovery や terminated agent session の場合：

```bash
execweave graph --allow-incomplete interrupted.jsonl
```

Stream は依然として structurally valid でなければなりません。緩和されるのは completed-session requirement だけです。

## Graph summary

```bash
execweave graph-summary run.graph.json
```

Summary は次を報告します。

- event count
- node count
- edge count
- node type ごとの count
- relation ごとの count
- causal edge count
- non-causal edge count
- mixed/unknown causality count

## Filtering

Source graph を変更せずに小さい graph を作成できます。

```bash
execweave graph-filter run.graph.json \
  --output causal.graph.json \
  --causal-only
```

Relation で filter：

```bash
execweave graph-filter run.graph.json \
  --output network.graph.json \
  --relation CONNECTED_TO \
  --relation CONNECT_ATTEMPTED
```

Node type で filter：

```bash
execweave graph-filter run.graph.json \
  --output process-network.graph.json \
  --node-type process \
  --node-type network_endpoint
```

Backend で filter：

```bash
execweave graph-filter run.graph.json \
  --output syscall.graph.json \
  --backend strace
```

Filter は組み合わせることができます。

## Directed path queries

Phase 2 は directed runtime path を query できます。

```bash
execweave path run.graph.json \
  'session:abc' \
  'network_endpoint:1.2.3.4:443'
```

Aggregated evidence が causal の edge のみに制限：

```bash
execweave path run.graph.json SOURCE TARGET --causal-only
```

Relation を制限：

```bash
execweave path run.graph.json SOURCE TARGET \
  --relation LAUNCHED \
  --relation SPAWNED \
  --relation CONNECTED_TO
```

Path search は現在次の性質を持ちます。

- directed
- breadth-first
- simple-path only（1 つの path 内で node は繰り返さない）
- `--max-depth` で bounded
- `--max-paths` で bounded

これにより cycle を含む execution graph が unbounded な query result を生成することを防ぎます。

## Current Phase 2 acceptance criteria

- [x] Graph construction 前に Phase 1 input を validate
- [x] Entity を node に materialize
- [x] Stable entity ID で node を deduplicate
- [x] Repeated `(source, relation, target)` event を aggregate
- [x] Edge 上に event evidence を保持
- [x] Causality semantics を保持
- [x] Temporal first/last metadata を保持
- [x] Source-only lifecycle event に fake edge を作らない
- [x] Graph summary
- [x] Graph filtering
- [x] Directed path query
- [ ] Semantically equivalent resource ID 間のより良い entity resolution
- [ ] Temporal snapshot / time-window filtering
- [ ] Very large run 向け compact evidence indexing
- [ ] Graph format migration/versioning tests
- [ ] Interactive local graph UI

Interactive UI は Phase 3 です。Raw collector log を直接読むのではなく、この graph contract を消費すべきです。
