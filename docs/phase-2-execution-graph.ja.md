<!-- i18n-nav:start -->
<p align="center">
  <a href="phase-2-execution-graph.md">English</a> |
  <a href="phase-2-execution-graph.zh-TW.md">繁體中文</a> |
  <a href="phase-2-execution-graph.zh-CN.md">简体中文</a> |
  <strong>日本語</strong> |
  <a href="phase-2-execution-graph.ko.md">한국어</a>
</p>
<!-- i18n-nav:end -->

# Phase 2 — Execution Graph

Phase 2 は validated Phase 1 JSONL stream を queryable な persistent execution graph に materialize します。

```bash
execweave validate run.jsonl
execweave graph run.jsonl
execweave graph-summary run.graph.json
```

Graph builder は raw telemetry を再解釈せず、Phase 1 の attribution / causality semantics を保持します。

## Schema

現在の graph schema は `0.1` です。

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

Distinct entity ID が node になります。

```text
agent:Claude Code
session:<session-id>
process:<session-id>:1234
file:/repo/src/app.py
network_endpoint:1.2.3.4:443
executable:/usr/bin/python
```

Node identity は display name ではなく entity ID です。Node は type/name/attributes、first/last timestamp、event count、event types を蓄積します。Conflicting attributes は暗黙 overwrite しません。

## Edges

Source と target がある event は：

```text
source --RELATION--> target
```

Edge identity は `(source, relation, target)`。同じ tuple の event は一つに aggregate され、`count`、first/last timestamp/sequence、supporting event IDs、backend、attribution、causality を保持します。

全 evidence が causal なら `causal: true`、全て non-causal なら `false`、mixed/unknown は `null`。Graph layer は weaker evidence を causal に upgrade しません。

Source-only lifecycle event（`EXITED`, `FINISHED_SESSION` など）には fake target/self-edge を作らず、node metadata に反映します。

## Validation

```bash
execweave graph run.jsonl
execweave graph --allow-incomplete interrupted.jsonl
```

`--allow-incomplete` は completed-session requirement のみ緩和し、structural validation は維持します。

## Summary / filter / path

```bash
execweave graph-summary run.graph.json
execweave graph-filter run.graph.json --output causal.graph.json --causal-only
execweave graph-filter run.graph.json --output network.graph.json \
  --relation CONNECTED_TO --relation CONNECT_ATTEMPTED
execweave path run.graph.json SOURCE TARGET --causal-only
```

Path search は directed BFS、simple-path、`--max-depth` / `--max-paths` bounded です。

## Focus / condensation

```bash
execweave graph-focus run.graph.json NODE_ID --hops 2 --output focused.graph.json
execweave graph-condense run.graph.json \
  --output run.compact.graph.json --threshold 8 --keep-expansion
```

Condensation は repetitive leaf resource を cluster 化します。`--keep-expansion` は original evidence を expansion payload に保持しますが、新しい causal edge は作りません。

## 実装済み baseline

- input validation
- stable entity materialization / dedup
- repeated relation aggregation
- evidence / causality / temporal metadata preservation
- lifecycle fake-edge prevention
- summary / filtering / path query
- focused subgraph
- condensation + progressive expansion

今後はより強い entity resolution、very-large-run evidence indexing、schema migration/versioning、long-run scalability を強化します。
