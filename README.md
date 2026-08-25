# ExecWeave

<p align="center">
  <strong>English</strong> |
  <a href="README.zh-TW.md">繁體中文</a> |
  <a href="README.zh-CN.md">简体中文</a> |
  <a href="README.ja.md">日本語</a> |
  <a href="README.ko.md">한국어</a>
</p>

**See what AI agents actually do on your machine.**

ExecWeave is an open-source, local-first runtime observability project that turns AI-agent activity into an interactive execution graph.

Instead of forcing users to understand hundreds of CLI lines, ExecWeave connects agents, sessions, processes, files, executables, sockets, and network endpoints into a graph backed by runtime evidence.

> **Turn opaque AI-agent execution into something humans can actually understand.**

## Fastest way to try it

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

### Watch the graph while the agent is running

```bash
execweave live --open -- claude
```

The live MVP starts a server bound only to `127.0.0.1`, opens a browser, and updates the graph while the command is still running.

```text
AI Agent
   ↓
portable runtime collector
   ↓
events.jsonl grows
   ↓
execution graph snapshots
   ↓
127.0.0.1:<random-port>
   ↓
Live browser graph
```

When the command exits, ExecWeave validates the event stream and stores:

```text
.execweave/runs/<session-id>/
├── events.jsonl
├── graph.json
└── viewer.html
```

The current live path intentionally uses the **portable** collector. The Linux `strace` backend is post-processed after the command exits, so presenting it as live would be misleading.

### Stronger Linux post-run evidence

On Debian/Ubuntu:

```bash
sudo apt-get install strace
```

Then record a run using syscall-backed attribution and open the final graph:

```bash
execweave record --backend strace --open -- claude
```

Other examples:

```bash
execweave live --open -- codex
execweave live --open -- gemini
execweave live --open -- opencode
execweave record --open -- python my_agent.py
```

Choose an explicit artifact directory:

```bash
execweave live --output-dir my-live-run --open -- claude
execweave record --output-dir my-run --open -- claude
```

ExecWeave refuses to silently overwrite existing non-empty artifacts.

## Current status

ExecWeave is currently **v0.4.0**.

### Phase 1 — Runtime Collection

**Complete for the Linux reference path and cross-platform portable fallback.**

- graph-ready JSONL event stream
- monotonic per-run sequence numbers
- root and descendant process capture
- Linux syscall-backed short-lived process capture
- Linux process-attributed file open/create/delete/rename evidence
- Linux IPv4/IPv6/Unix-socket connection evidence
- preservation of asynchronous/failed connection attempts
- psutil/watchdog portable fallback on Linux, macOS, and Windows
- explicit causal vs non-causal/session-observation semantics
- event-stream validation
- backend diagnostics and auto-selection
- benchmark harness and cross-platform CI configuration

### Phase 2 — Execution Graph

**Core materialization and query layer implemented.**

- validated JSONL → graph JSON
- node deduplication by stable entity ID
- repeated edge aggregation
- first/last temporal metadata
- supporting event IDs
- causality preservation
- graph summary
- graph filtering
- directed path queries
- large-run graph condensation for repetitive leaf resources

### Phase 3 — Interactive Viewer

**Standalone and live local viewer MVPs implemented.**

- standalone HTML with no CDN or external JavaScript dependency
- localhost live graph updates using the portable collector
- pan / zoom
- draggable nodes
- node and edge inspection
- search
- causal/non-causal edge styling
- automatic directional layout

Progressive cluster expansion and Timeline ↔ Graph synchronization remain future work.

### Security analysis

**First conservative, explainable rule layer implemented.**

- sensitive-file access findings
- external endpoint findings
- possible sensitive-file → network prioritization
- explicit `data_flow_proven: false`
- explicit `exfiltration_proven: false`

ExecWeave does not turn co-occurrence into a data-flow claim.

## Advanced manual workflow

The one-command `live` and `record` workflows are recommended. Each stage is also available separately.

```bash
execweave doctor
execweave run --output run.jsonl -- claude
execweave validate run.jsonl
execweave graph run.jsonl --output run.graph.json
execweave view run.graph.json --output run.html --open
```

### Condense a large graph

Long agent runs can touch hundreds or thousands of low-value leaf files. Collapse repetitive file/directory/executable leaves while preserving processes, agents, sessions, sockets, and network endpoints:

```bash
execweave graph-condense run.graph.json \
  --output run.compact.graph.json \
  --threshold 8
```

A cluster is only created for equivalent **leaf** resources with one incoming relationship and no outgoing behavior.

### Analyze the graph

```bash
execweave analyze run.graph.json
```

Save the report too:

```bash
execweave analyze run.graph.json --output analysis.json
```

A finding such as:

```text
process
  ├── OPENED_READ ──→ ~/.ssh/id_ed25519
  └── CONNECTED_TO ─→ external endpoint
```

is reported as a **possible sensitive-file-to-network path**, not as proof that the key bytes were transmitted.

## Graph-first event model

Every runtime observation is represented as:

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

Repeated evidence is aggregated. If one process opens the same file 17 times, the graph stores one relationship with `count = 17` instead of 17 overlapping lines.

## No fake causality

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

The portable filesystem watcher can only prove:

```text
session --OBSERVED_FILE_CHANGE--> file
```

and therefore marks it `causal: false`.

Temporal correlation is not presented as causal proof, and same-process file/network activity is not presented as byte-level data flow.

## Backends

### `strace` — Linux reference backend

The Linux reference backend follows descendants with `strace -ff` and converts process, filesystem, and network syscall evidence into graph-ready events.

Raw trace files are removed after parsing unless explicitly retained:

```bash
execweave run --keep-native-trace -- claude
```

### `portable` — cross-platform fallback and live backend

The portable backend uses psutil and watchdog on Linux, macOS, and Windows. It is also the current live-graph backend because it emits observations while the command is running.

Its limitations remain explicit: filesystem changes are session-correlated rather than process-attributed, and very short-lived processes can be missed between polling intervals.

Future native collectors are planned for Linux eBPF, Windows ETW, and macOS Endpoint Security.

## Event-stream integrity

`execweave validate` checks valid JSONL, one session ID, unique event IDs, contiguous sequence numbers, timestamps, entity fields, and completed session lifecycle by default.

ExecWeave also rejects accidental reuse of non-empty event/graph/viewer outputs rather than silently mixing runs.

## Graph queries

```bash
execweave graph-summary run.graph.json
execweave graph-filter run.graph.json --output causal.graph.json --causal-only
execweave path run.graph.json SOURCE_NODE_ID TARGET_NODE_ID --causal-only
```

See [`docs/phase-2-execution-graph.md`](docs/phase-2-execution-graph.md) for the graph contract.

## Interactive viewer

```bash
execweave view run.graph.json --output run.html --open
execweave live --open -- claude
```

Useful live options:

```bash
execweave live --port 8765 --open -- claude
execweave live --linger 10 --open -- claude
execweave live --no-files --open -- claude
```

The live HTTP server binds only to `127.0.0.1`. It is not exposed to the LAN by default.

## Privacy

ExecWeave is **local-first**.

- runtime events stay local by default
- graph construction is local
- standalone viewer data stays in the generated HTML
- live serving binds to localhost only
- no external CDN is required
- file contents are not traced
- `read()` / `write()` byte buffers are not collected
- raw Linux syscall traces are deleted after parsing unless explicitly retained

Runtime metadata can still include sensitive paths, commands, and endpoints. Review artifacts before sharing them.

## Roadmap

### Phase 1

- [x] Runtime collection contract
- [x] Linux reference backend
- [x] Portable fallback
- [x] Causality semantics
- [x] Event validation
- [x] Diagnostics / benchmark / CI configuration
- [ ] Linux eBPF backend
- [ ] Windows ETW backend
- [ ] macOS Endpoint Security backend

### Phase 2

- [x] Event → Graph materialization
- [x] Node deduplication
- [x] Edge aggregation
- [x] Temporal metadata
- [x] Summary / filter / path query
- [x] Large-run leaf-resource condensation
- [ ] Stronger entity resolution
- [ ] Time-window graph snapshots
- [ ] Compact evidence indexing for very large runs

### Phase 3

- [x] Standalone local viewer MVP
- [x] Pan / zoom / drag / search / details
- [x] Portable live graph updates during execution
- [x] Initial large-graph condensation
- [ ] Progressive cluster expansion in the viewer
- [ ] Timeline ↔ Graph synchronization
- [ ] Saved filters and focused subgraphs

### Security / research layers

- [x] Initial explainable rule analysis
- [ ] Agent / Tool / MCP semantic telemetry
- [ ] credential and secret entities
- [ ] byte-level data-flow / taint tracking
- [ ] anomaly detection
- [ ] attack-path ranking
- [ ] execution replay
- [ ] runtime allow / warn / block policy

## Documentation

- [`Phase 1 — Runtime Collection`](docs/phase-1-runtime-collection.md)
- [`Phase 2 — Execution Graph`](docs/phase-2-execution-graph.md)
- [`Live Graph`](docs/live-graph.md)
- [`Security Analysis`](docs/security-analysis.md)

## Contributing

**Contributions are very welcome.**

High-impact areas include Linux eBPF, Windows ETW, macOS Endpoint Security, graph entity resolution, live/large-graph visualization, OpenTelemetry/MCP integrations, privacy/redaction, reproducible agent workloads, and performance evaluation.

For a new collector or architecture change, open an issue first and describe the telemetry source, privilege requirements, expected graph relationships, and causal guarantees.

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
