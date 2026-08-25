<!-- i18n-nav:start -->
<p align="center">
  <a href="phase-2-execution-graph.md">English</a> |
  <a href="phase-2-execution-graph.zh-TW.md">繁體中文</a> |
  <a href="phase-2-execution-graph.zh-CN.md">简体中文</a> |
  <a href="phase-2-execution-graph.ja.md">日本語</a> |
  <strong>한국어</strong>
</p>
<!-- i18n-nav:end -->

# Phase 2 — Execution Graph

Phase 2는 validated Phase 1 JSONL event stream을 persistent execution graph로 materialize합니다.

```bash
execweave validate run.jsonl
execweave graph run.jsonl
execweave graph-summary run.graph.json
```

Graph builder는 raw telemetry를 새로 해석하지 않고 Phase 1의 attribution/causality semantics를 보존합니다.

## Graph schema

현재 schema version은 `0.1`입니다.

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

Distinct entity ID마다 node가 하나 만들어집니다.

```text
agent:Claude Code
session:<session-id>
process:<session-id>:1234
file:/repo/src/app.py
network_endpoint:1.2.3.4:443
executable:/usr/bin/python
```

Node identity는 display name이 아니라 entity ID입니다. Type/name/attributes, first/last timestamp, observed event count/types를 누적하고 conflicting attribute를 조용히 overwrite하지 않습니다.

## Edges

Source와 target이 있는 event는 다음 directed relation이 됩니다.

```text
source --RELATION--> target
```

Edge identity는 `(source, relation, target)`이며 반복 event는 한 edge로 aggregate됩니다. Edge는 `count`, first/last timestamp/sequence, supporting event IDs, backend, attribution, causality를 보존합니다.

모든 supporting event가 causal이면 `true`, 전부 non-causal이면 `false`, mixed/unknown이면 `null`입니다. Graph layer는 weaker evidence를 causal로 upgrade하지 않습니다.

`EXITED`, `FINISHED_SESSION`처럼 target 없는 lifecycle event에는 fake target/self-edge를 만들지 않고 source node metadata에 반영합니다.

## Validation

```bash
execweave graph run.jsonl
execweave graph --allow-incomplete interrupted.jsonl
```

`--allow-incomplete`는 completed-session requirement만 완화하며 structural validation은 유지합니다.

## Summary / filtering / path

```bash
execweave graph-summary run.graph.json
execweave graph-filter run.graph.json --output causal.graph.json --causal-only
execweave graph-filter run.graph.json --output network.graph.json \
  --relation CONNECTED_TO --relation CONNECT_ATTEMPTED
execweave path run.graph.json SOURCE TARGET --causal-only
```

Path search는 directed BFS, simple-path이며 `--max-depth` / `--max-paths`로 bounded됩니다.

## Focus / condensation

```bash
execweave graph-focus run.graph.json NODE_ID --hops 2 --output focused.graph.json
execweave graph-condense run.graph.json \
  --output run.compact.graph.json --threshold 8 --keep-expansion
```

Condensation은 repetitive leaf resource를 cluster로 줄입니다. `--keep-expansion`은 original member evidence를 보존하지만 새 causal edge를 만들지 않습니다.

## 구현된 baseline

- Phase 1 input validation
- stable entity materialization/dedup
- repeated relation aggregation
- evidence/causality/temporal metadata preservation
- lifecycle fake-edge 방지
- graph summary/filter/path
- focused subgraph
- condensation/progressive expansion

향후 stronger entity resolution, very-large-run evidence indexing, schema migration/versioning, long-run scalability를 개선합니다.
