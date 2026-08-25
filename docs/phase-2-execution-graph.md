<!-- i18n-nav:start -->
<p align="center">
  <strong>English</strong> |
  <a href="phase-2-execution-graph.zh-TW.md">繁體中文</a> |
  <a href="phase-2-execution-graph.zh-CN.md">简体中文</a> |
  <a href="phase-2-execution-graph.ja.md">日本語</a> |
  <a href="phase-2-execution-graph.ko.md">한국어</a>
</p>
<!-- i18n-nav:end -->

# Phase 2 — Execution Graph

Phase 2 turns a validated Phase 1 JSONL event stream into a persistent execution graph that can be queried and later visualized by the local UI.

## Current status

The first Phase 2 graph core is implemented.

```bash
execweave validate run.jsonl
execweave graph run.jsonl
execweave graph-summary run.graph.json
```

The graph builder does not reinterpret raw telemetry. It consumes the attribution and causality semantics produced by Phase 1.

## Graph schema

The current graph schema version is:

```text
0.1
```

A graph JSON document contains:

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

Every distinct Phase 1 entity ID becomes one graph node.

Examples:

```text
agent:Claude Code
session:<session-id>
process:<session-id>:1234
file:/repo/src/app.py
network_endpoint:1.2.3.4:443
executable:/usr/bin/python
```

Node identity is based on the event-stream entity ID, not on display names.

Each node accumulates:

- `type`
- `name`
- entity attributes
- first observed timestamp
- last observed timestamp
- observed event count
- event types in which the entity appeared

Phase 2 currently uses conservative attribute merging: an existing node attribute is not silently overwritten by a later conflicting value.

## Edges

An event with both a source and target can produce a directed graph edge:

```text
source --RELATION--> target
```

For example:

```text
session --LAUNCHED--> process
process --SPAWNED--> process
process --OPENED_READ--> file
process --CONNECTED_TO--> network_endpoint
```

The edge identity is the tuple:

```text
(source, relation, target)
```

Repeated events for the same tuple are aggregated into one edge rather than rendered as duplicate lines.

An aggregated edge records:

- exact occurrence `count`
- first/last timestamp
- first/last sequence number
- supporting event IDs
- contributing event types
- backend(s)
- attribution method(s)
- causality state

Example:

```text
process:p1 --OPENED_READ--> file:a.txt
count = 17
```

means 17 Phase 1 events support the same graph relationship.

## Causality aggregation

If all supporting events are causal:

```json
{"causal": true}
```

If all are explicitly non-causal:

```json
{"causal": false}
```

If supporting evidence is mixed or does not provide a uniform causality value:

```json
{"causal": null}
```

The graph layer must not upgrade non-causal telemetry into a causal relationship.

## Lifecycle events

Some Phase 1 events have a source but no target, for example:

```text
process EXITED
session FINISHED_SESSION
```

Phase 2 does **not** manufacture a fake target node or self-edge for these events.

Instead, they contribute to the source node's observed event metadata. This keeps the graph relational rather than turning every log event into an artificial node.

## Graph validation boundary

By default, graph construction requires a valid, complete Phase 1 event stream:

```bash
execweave graph run.jsonl
```

For incident recovery or a terminated agent session:

```bash
execweave graph --allow-incomplete interrupted.jsonl
```

The stream must still be structurally valid; only the completed-session requirement is relaxed.

## Graph summary

```bash
execweave graph-summary run.graph.json
```

The summary reports:

- event count
- node count
- edge count
- counts by node type
- counts by relation
- causal edge count
- non-causal edge count
- mixed/unknown causality count

## Filtering

Create a smaller graph without changing the source graph:

```bash
execweave graph-filter run.graph.json \
  --output causal.graph.json \
  --causal-only
```

Filter by relation:

```bash
execweave graph-filter run.graph.json \
  --output network.graph.json \
  --relation CONNECTED_TO \
  --relation CONNECT_ATTEMPTED
```

Filter by node type:

```bash
execweave graph-filter run.graph.json \
  --output process-network.graph.json \
  --node-type process \
  --node-type network_endpoint
```

Filter by backend:

```bash
execweave graph-filter run.graph.json \
  --output syscall.graph.json \
  --backend strace
```

Filters can be combined.

## Directed path queries

Phase 2 can query directed runtime paths:

```bash
execweave path run.graph.json \
  'session:abc' \
  'network_endpoint:1.2.3.4:443'
```

Restrict to edges whose aggregated evidence is causal:

```bash
execweave path run.graph.json SOURCE TARGET --causal-only
```

Restrict relations:

```bash
execweave path run.graph.json SOURCE TARGET \
  --relation LAUNCHED \
  --relation SPAWNED \
  --relation CONNECTED_TO
```

Path search is currently:

- directed
- breadth-first
- simple-path only (a node cannot repeat in one returned path)
- bounded by `--max-depth`
- bounded by `--max-paths`

This prevents an execution graph with cycles from producing unbounded query results.

## Current Phase 2 acceptance criteria

- [x] Validate Phase 1 input before graph construction
- [x] Materialize entities into nodes
- [x] Deduplicate nodes by stable entity ID
- [x] Aggregate repeated `(source, relation, target)` events
- [x] Preserve event evidence on edges
- [x] Preserve causality semantics
- [x] Preserve temporal first/last metadata
- [x] Avoid fake edges for source-only lifecycle events
- [x] Graph summary
- [x] Graph filtering
- [x] Directed path query
- [ ] Better entity resolution across semantically equivalent resource IDs
- [ ] Temporal snapshot / time-window filtering
- [ ] Compact evidence indexing for very large runs
- [ ] Graph format migration/versioning tests
- [ ] Interactive local graph UI

The interactive UI is Phase 3. It should consume this graph contract rather than reading raw collector logs directly.
