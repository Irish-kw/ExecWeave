<!-- i18n-nav:start -->
<p align="center">
  <a href="phase-2-execution-graph.md">English</a> |
  <a href="phase-2-execution-graph.zh-TW.md">繁體中文</a> |
  <a href="phase-2-execution-graph.zh-CN.md">简体中文</a> |
  <a href="phase-2-execution-graph.ja.md">日本語</a> |
  <strong>한국어</strong> |
  <a href="phase-2-execution-graph.fr.md">Français</a> |
  <a href="phase-2-execution-graph.de.md">Deutsch</a> |
  <a href="phase-2-execution-graph.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# Phase 2 — Execution Graph

Phase 2는 validated Phase 1 JSONL event stream을 query할 수 있고 이후 local UI에서 시각화할 수 있는 persistent execution graph로 변환합니다.

## Current status

첫 번째 Phase 2 graph core가 구현되어 있습니다.

```bash
execweave validate run.jsonl
execweave graph run.jsonl
execweave graph-summary run.graph.json
```

Graph builder는 raw telemetry를 다시 해석하지 않습니다. Phase 1이 만든 attribution과 causality semantics를 그대로 사용합니다.

## Graph schema

현재 graph schema version은 다음과 같습니다.

```text
0.1
```

Graph JSON document는 다음을 포함합니다.

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

각 distinct Phase 1 entity ID는 graph node 하나가 됩니다.

예:

```text
agent:Claude Code
session:<session-id>
process:<session-id>:1234
file:/repo/src/app.py
network_endpoint:1.2.3.4:443
executable:/usr/bin/python
```

Node identity는 display name이 아니라 event-stream entity ID를 기반으로 합니다.

각 node는 다음을 누적합니다.

- `type`
- `name`
- entity attributes
- first observed timestamp
- last observed timestamp
- observed event count
- 해당 entity가 나타난 event type

Phase 2는 현재 conservative attribute merging을 사용합니다. 기존 node attribute가 이후 conflicting value로 조용히 덮어써지지 않습니다.

## Edges

Source와 target을 모두 가진 event는 directed graph edge를 만들 수 있습니다.

```text
source --RELATION--> target
```

예:

```text
session --LAUNCHED--> process
process --SPAWNED--> process
process --OPENED_READ--> file
process --CONNECTED_TO--> network_endpoint
```

Edge identity는 다음 tuple입니다.

```text
(source, relation, target)
```

동일 tuple의 repeated event는 중복 line으로 렌더링되지 않고 하나의 edge로 aggregate됩니다.

Aggregated edge는 다음을 기록합니다.

- 정확한 occurrence `count`
- first/last timestamp
- first/last sequence number
- supporting event ID
- contributing event type
- backend
- attribution method
- causality state

예:

```text
process:p1 --OPENED_READ--> file:a.txt
count = 17
```

이는 동일 graph relationship을 17개의 Phase 1 event가 지원한다는 뜻입니다.

## Causality aggregation

모든 supporting event가 causal이면:

```json
{"causal": true}
```

모두 명시적으로 non-causal이면:

```json
{"causal": false}
```

Supporting evidence가 mixed이거나 uniform한 causality value가 없으면:

```json
{"causal": null}
```

Graph layer는 non-causal telemetry를 causal relationship으로 upgrade해서는 안 됩니다.

## Lifecycle events

일부 Phase 1 event는 source만 있고 target이 없습니다. 예:

```text
process EXITED
session FINISHED_SESSION
```

Phase 2는 이런 event에 fake target node나 self-edge를 만들지 않습니다.

대신 source node의 observed event metadata에 기여하도록 합니다. 이렇게 하면 모든 log event를 인위적인 node로 바꾸지 않고 graph를 relational하게 유지할 수 있습니다.

## Graph validation boundary

기본적으로 graph construction에는 valid하고 complete한 Phase 1 event stream이 필요합니다.

```bash
execweave graph run.jsonl
```

Incident recovery 또는 terminated agent session의 경우:

```bash
execweave graph --allow-incomplete interrupted.jsonl
```

Stream은 여전히 structurally valid해야 하며, 완화되는 것은 completed-session requirement뿐입니다.

## Graph summary

```bash
execweave graph-summary run.graph.json
```

Summary는 다음을 보고합니다.

- event count
- node count
- edge count
- node type별 count
- relation별 count
- causal edge count
- non-causal edge count
- mixed/unknown causality count

## Filtering

Source graph를 바꾸지 않고 더 작은 graph를 만들 수 있습니다.

```bash
execweave graph-filter run.graph.json \
  --output causal.graph.json \
  --causal-only
```

Relation으로 filter:

```bash
execweave graph-filter run.graph.json \
  --output network.graph.json \
  --relation CONNECTED_TO \
  --relation CONNECT_ATTEMPTED
```

Node type으로 filter:

```bash
execweave graph-filter run.graph.json \
  --output process-network.graph.json \
  --node-type process \
  --node-type network_endpoint
```

Backend로 filter:

```bash
execweave graph-filter run.graph.json \
  --output syscall.graph.json \
  --backend strace
```

Filter는 조합할 수 있습니다.

## Directed path queries

Phase 2는 directed runtime path를 query할 수 있습니다.

```bash
execweave path run.graph.json \
  'session:abc' \
  'network_endpoint:1.2.3.4:443'
```

Aggregated evidence가 causal인 edge로 제한:

```bash
execweave path run.graph.json SOURCE TARGET --causal-only
```

Relation 제한:

```bash
execweave path run.graph.json SOURCE TARGET \
  --relation LAUNCHED \
  --relation SPAWNED \
  --relation CONNECTED_TO
```

Path search는 현재 다음 특성을 가집니다.

- directed
- breadth-first
- simple-path only(하나의 path에서 node가 반복되지 않음)
- `--max-depth`로 bounded
- `--max-paths`로 bounded

따라서 cycle이 있는 execution graph가 unbounded query result를 생성하지 않습니다.

## Current Phase 2 acceptance criteria

- [x] Graph construction 전에 Phase 1 input validate
- [x] Entity를 node로 materialize
- [x] Stable entity ID로 node deduplicate
- [x] Repeated `(source, relation, target)` event aggregate
- [x] Edge에 event evidence 보존
- [x] Causality semantics 보존
- [x] Temporal first/last metadata 보존
- [x] Source-only lifecycle event에 fake edge를 만들지 않음
- [x] Graph summary
- [x] Graph filtering
- [x] Directed path query
- [ ] Semantically equivalent resource ID 사이의 더 나은 entity resolution
- [ ] Temporal snapshot / time-window filtering
- [ ] Very large run용 compact evidence indexing
- [ ] Graph format migration/versioning tests
- [ ] Interactive local graph UI

Interactive UI는 Phase 3입니다. Raw collector log를 직접 읽는 대신 이 graph contract를 사용해야 합니다.
