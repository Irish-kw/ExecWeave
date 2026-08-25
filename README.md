# ExecWeave

<p align="center">
  <strong>English</strong> |
  <a href="README.zh-TW.md">繁體中文</a> |
  <a href="README.zh-CN.md">简体中文</a> |
  <a href="README.ja.md">日本語</a> |
  <a href="README.ko.md">한국어</a>
</p>

**See what AI agents actually do on your machine.**

ExecWeave is an open-source, local-first runtime observability project for turning AI-agent activity into an interactive execution graph.

Instead of reading long CLI logs, ExecWeave records relationships among agents, sessions, processes, files, executables, sockets, and network endpoints, materializes those events into a graph, and can render that graph as a standalone local HTML viewer.

> **Turn opaque AI-agent execution into something humans can actually understand.**

## Current status

### Phase 1 — Runtime Collection

**Complete for the Linux reference path and cross-platform portable fallback.**

- graph-ready JSONL event stream;
- monotonic event sequence numbers;
- root and descendant process capture;
- Linux syscall-backed short-lived process capture;
- Linux process-attributed file open/create/delete/rename events;
- Linux IPv4/IPv6/Unix-socket connection evidence;
- preservation of non-blocking/failed connection attempts;
- portable psutil/watchdog fallback on Linux, macOS, and Windows;
- explicit causal vs non-causal/session-observation semantics;
- event-stream validator;
- backend diagnostics and automatic selection;
- benchmark harness and cross-platform CI.

### Phase 2 — Execution Graph

**Core graph materialization and query layer implemented.**

- validated JSONL → graph JSON;
- node deduplication by entity ID;
- repeated edge aggregation;
- temporal first/last metadata;
- evidence event IDs;
- causality preservation;
- graph summary;
- graph filtering;
- directed path queries.

### Phase 3 — Interactive Viewer

**First local viewer MVP implemented.**

- standalone HTML;
- no CDN or external JavaScript dependencies;
- pan and zoom;
- draggable nodes;
- node/edge inspection;
- graph search;
- causal/non-causal edge styling.

A live viewer that updates while an agent is still running remains future work.

## Quick start

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

On Debian/Ubuntu, install the Linux reference backend:

```bash
sudo apt-get install strace
```

Check collector availability:

```bash
execweave doctor
```

### 1. Record an agent run

```bash
execweave run --output run.jsonl -- claude
```

Other examples:

```bash
execweave run --output run.jsonl -- codex
execweave run --output run.jsonl -- gemini
execweave run --output run.jsonl -- opencode
execweave run --output run.jsonl -- python my_agent.py
```

### 2. Validate the event stream

```bash
execweave validate run.jsonl
```

### 3. Build the execution graph

```bash
execweave graph run.jsonl --output run.graph.json
```

### 4. Open the interactive graph

```bash
execweave view run.graph.json --output run.html --open
```

The complete flow is:

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

## What the graph represents

Phase 1 events use a graph-first form:

```text
source --RELATION--> target
```

Examples:

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

Phase 2 aggregates repeated evidence. If a process opens the same file 17 times, the graph contains one edge:

```text
process --OPENED_READ--> file
count = 17
```

rather than 17 overlapping lines.

## No fake causality

ExecWeave distinguishes what telemetry proves from what merely happened during the same session.

Linux syscall-backed evidence can produce:

```text
process --OPENED_WRITE--> file
```

with:

```json
{
  "attribution": "syscall",
  "causal": true
}
```

The portable filesystem fallback can only prove:

```text
session --OBSERVED_FILE_CHANGE--> file
```

and marks it:

```json
{
  "attribution": "session_observation",
  "causal": false
}
```

ExecWeave does not upgrade temporal correlation into causal proof.

## Backends

### `strace` — Linux reference backend

The Linux reference backend follows descendants with `strace -ff` and converts process/filesystem/network syscall evidence into graph-ready events.

It is correctness-oriented and useful as the reference implementation of ExecWeave event semantics. Raw traces are deleted after parsing unless explicitly retained:

```bash
execweave run --keep-native-trace -- claude
```

### `portable` — cross-platform fallback

The portable backend uses psutil and watchdog on Linux, macOS, and Windows.

It provides useful process/network/runtime evidence without a native sensor, while keeping weaker filesystem attribution explicitly non-causal.

`auto` is the default and prefers `strace` on Linux when available.

## Event-stream integrity

Each event file represents one ExecWeave session.

ExecWeave refuses to append a new run to an existing non-empty event file, because silently mixing sessions would corrupt sequence and identity semantics.

Validate a completed run:

```bash
execweave validate run.jsonl
```

Validate an interrupted run without requiring `session.finished`:

```bash
execweave validate --allow-incomplete run.jsonl
```

The validator checks JSON structure, schema information, unique event IDs, one session per file, contiguous sequence numbers, timestamps, entity fields, and session lifecycle events.

## Graph queries

Summarize a graph:

```bash
execweave graph-summary run.graph.json
```

Keep only causal edges:

```bash
execweave graph-filter run.graph.json \
  --output causal.graph.json \
  --causal-only
```

Keep process/network nodes:

```bash
execweave graph-filter run.graph.json \
  --output process-network.graph.json \
  --node-type process \
  --node-type network_endpoint
```

Find a directed runtime path:

```bash
execweave path run.graph.json SOURCE_NODE_ID TARGET_NODE_ID --causal-only
```

See [`docs/phase-2-execution-graph.md`](docs/phase-2-execution-graph.md) for the graph contract and query semantics.

## Interactive viewer

Generate a standalone local HTML viewer:

```bash
execweave view run.graph.json --output run.html
```

Open it immediately:

```bash
execweave view run.graph.json --output run.html --open
```

The viewer embeds the graph data directly into the HTML file and does not load a graph library from a CDN.

Current interactions:

- wheel zoom;
- background drag to pan;
- drag nodes to rearrange;
- click nodes or edges for JSON evidence/details;
- search by node ID, name, or type;
- causal/non-causal edge distinction;
- automatic directional layout and fit-to-screen.

## Benchmark

```bash
execweave benchmark --backend portable --iterations 5
execweave benchmark --backend strace --iterations 5
```

The benchmark is a smoke/engineering harness. Results are environment-specific and are not a published performance claim.

## Privacy

ExecWeave is **local-first**.

- event data stays on the machine by default;
- graph materialization is local;
- the HTML viewer is standalone and local;
- no external JavaScript/CDN is required by the viewer;
- file contents are not traced;
- byte buffers from `read()`/`write()` are not collected;
- raw Linux syscall traces are deleted after parsing unless explicitly retained;
- `execve` argument values are not copied into graph edges.

Runtime metadata can still contain sensitive paths, commands, and endpoints. Review artifacts before sharing them.

## Roadmap

### Phase 1 — Runtime Collection

- [x] Graph-ready event schema
- [x] Process/file/network collection
- [x] Reliable Linux short-lived process capture
- [x] Causal attribution semantics
- [x] Event validation
- [x] Diagnostics
- [x] Benchmark harness
- [x] Cross-platform portable fallback

Future native collectors, not falsely counted as Phase 1 completion:

- [ ] Linux eBPF backend
- [ ] Windows ETW backend
- [ ] macOS Endpoint Security backend

### Phase 2 — Execution Graph

- [x] Event → graph materialization
- [x] Node deduplication
- [x] Edge aggregation
- [x] Temporal first/last metadata
- [x] Graph summary
- [x] Graph filtering
- [x] Directed path query
- [ ] Stronger cross-resource entity resolution
- [ ] Time-window graph snapshots
- [ ] Compact evidence indexing for very large runs

### Phase 3 — Interactive UI

- [x] Standalone local HTML viewer MVP
- [x] Pan / zoom / drag
- [x] Search
- [x] Node and edge details
- [x] Causality visualization
- [ ] Live graph updates during execution
- [ ] Timeline ↔ graph synchronization
- [ ] Large-graph clustering / progressive expansion
- [ ] Saved filters and focused subgraphs

### Later security/research layers

- [ ] Agent/tool/MCP semantic telemetry
- [ ] credential and secret entities
- [ ] data-flow / taint tracking
- [ ] anomaly detection
- [ ] attack-path reconstruction
- [ ] execution replay
- [ ] runtime allow / warn / block policy

## Documentation

- [`Phase 1 — Runtime Collection`](docs/phase-1-runtime-collection.md)
- [`Phase 2 — Execution Graph`](docs/phase-2-execution-graph.md)

## Contributing

**Contributions are very welcome.**

High-impact contribution areas include:

- Linux eBPF collectors;
- Windows ETW collectors;
- macOS Endpoint Security collectors;
- graph entity resolution;
- graph visualization and large-graph UX;
- OpenTelemetry / MCP integrations;
- privacy and redaction;
- reproducible agent workloads;
- performance evaluation;
- README and documentation translations.

For small changes, fork the repository and open a pull request. For a new collector or architecture change, open an issue first and describe the telemetry source, privilege requirements, expected graph relationships, and causal guarantees.

> **Early contributors are especially welcome.**

## Design principles

- **Local first** — runtime evidence stays local by default.
- **Runtime truth over assumptions** — prefer OS evidence over framework claims.
- **Graph over log** — relationships are first-class data.
- **Framework agnostic** — no dependency on one agent/model provider.
- **Explainable attribution** — every edge should say why it exists.
- **No fake causality** — temporal correlation is not causal proof.

## License

See [`LICENSE`](LICENSE).

---

**Open an issue. Propose an idea. Submit a pull request. Build an integration. Challenge the architecture.**

> **Let's make AI-agent execution understandable.**
