# ExecWeave

<p align="center">
  <strong>English</strong> |
  <a href="README.zh-TW.md">繁體中文</a> |
  <a href="README.zh-CN.md">简体中文</a> |
  <a href="README.ja.md">日本語</a> |
  <a href="README.ko.md">한국어</a>
</p>

**See what AI agents actually do on your machine.**

ExecWeave turns local AI-agent runtime activity into a graph-ready event stream. Instead of treating CLI logs as the interface, it records relationships among sessions, processes, files, executables, sockets, and network endpoints so they can become an interactive execution graph.

> **Turn opaque AI-agent execution into something humans can actually understand.**

## Current status

**Phase 1 — Runtime Collection is complete for the Linux reference path and the cross-platform portable fallback.**

The interactive graph UI is the next major phase and is **not implemented yet**.

### What works now

- graph-ready JSONL event stream;
- monotonic per-run event sequence numbers;
- root and descendant process capture;
- Linux syscall-backed short-lived process capture;
- Linux process-attributed file open/create/delete/rename events;
- Linux process-attributed IPv4/IPv6/Unix-socket `connect()` events;
- portable psutil/watchdog fallback on Linux, macOS, and Windows;
- explicit causal vs session-observation labels;
- backend diagnostics and automatic selection;
- Phase 1 overhead benchmark harness;
- cross-platform CI plus Linux native integration tests.

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

Check what ExecWeave will use:

```bash
execweave doctor
```

Run an agent:

```bash
execweave run -- claude
execweave run -- codex
execweave run -- gemini
execweave run -- opencode
```

Or any command:

```bash
execweave run -- python my_agent.py
```

Events are stored locally at:

```text
.execweave/runs/<session-id>.jsonl
```

Choose a backend explicitly:

```bash
execweave run --backend strace -- claude
execweave run --backend portable -- claude
```

`auto` is the default. It prefers `strace` on Linux when available and otherwise uses `portable`.

See [`docs/phase-1-runtime-collection.md`](docs/phase-1-runtime-collection.md) for backend guarantees, limitations, privacy behavior, and acceptance criteria.

## Graph-first event model

Every observation is represented as:

```text
source --RELATION--> target
```

Examples from the Linux reference backend:

```text
session --LAUNCHED--> process
process --SPAWNED--> process
process --EXECUTED--> executable
process --OPENED_READ--> file
process --OPENED_WRITE--> file
process --DELETED--> file
process --CONNECTED_TO--> network_endpoint
```

A simplified event:

```json
{
  "schema_version": "0.2",
  "sequence": 42,
  "session_id": "...",
  "event_type": "filesystem.open",
  "relation": "OPENED_READ",
  "source": {
    "type": "process",
    "id": "process:<session-id>:1234"
  },
  "target": {
    "type": "file",
    "id": "file:/home/user/project/README.md"
  },
  "attributes": {
    "attribution": "syscall",
    "causal": true,
    "backend": "strace"
  }
}
```

## No fake causality

ExecWeave distinguishes what the telemetry proves from what merely happened during the same session.

Linux syscall-backed event:

```text
process --OPENED_WRITE--> file
```

Portable filesystem fallback:

```text
session --OBSERVED_FILE_CHANGE--> file
```

The portable event is marked:

```json
{
  "attribution": "session_observation",
  "causal": false
}
```

A directory watcher cannot prove which process changed a file, so ExecWeave does not pretend it can.

## Why a graph?

A process tree might show:

```text
agent
└── bash
    └── git
        └── ssh
```

ExecWeave is designed to eventually show the relationships around those processes:

```text
                     ┌── OPENED_READ ──→ ~/.ssh/config
                     │
Agent → bash → git ──┼── EXECUTED ─────→ ssh
                     │
                     ├── OPENED_READ ──→ repository
                     │
                     └── CONNECTED_TO ─→ github.com / IP endpoint
```

The runtime event stream is the evidence layer for that graph.

## Backends

### Linux reference: `strace`

ExecWeave follows descendants with `strace -ff` and parses process, filesystem, and network syscalls into graph-ready events. This path reliably captures short-lived children that polling can miss.

Raw strace files are deleted after parsing by default. Keep them only when debugging:

```bash
execweave run --keep-native-trace -- claude
```

### Portable fallback

The portable collector uses psutil and watchdog. It runs on Linux, macOS, and Windows without a native tracing backend.

It provides useful runtime evidence, but its limitations remain explicit: very short-lived processes can be missed, and filesystem changes are session-correlated rather than process-attributed.

## Phase 1 roadmap

- [x] Explicit ExecWeave session wrapper
- [x] Graph-ready event schema
- [x] Event ordering / sequence numbers
- [x] Root process capture
- [x] Parent/child process capture
- [x] Portable filesystem observation
- [x] Portable network observation
- [x] Linux reliable short-lived process capture
- [x] Linux process-attributed filesystem syscall telemetry
- [x] Linux process-attributed network syscall telemetry
- [x] Backend diagnostics and automatic selection
- [x] Cross-platform portable fallback
- [x] Raw native trace cleanup by default
- [x] Unit + Linux native integration tests
- [x] Runtime overhead benchmark harness

Phase 1 is intentionally **not** claiming native ETW/Endpoint Security/eBPF support yet. Those are future collector backends that should feed the same event model.

## Benchmark

```bash
execweave benchmark --backend portable --iterations 5
execweave benchmark --backend strace --iterations 5
```

The harness reports baseline and instrumented timings plus an overhead ratio. Results are machine-specific; the project does not publish an overhead claim from this smoke benchmark.

## Privacy

ExecWeave is **local-first**.

- Events stay on the machine by default.
- File contents are not traced.
- Byte buffers from `read()`/`write()` are not collected.
- Raw Linux syscall traces are deleted after parsing unless explicitly retained.
- `execve` argument values are not copied into graph events.

Runtime metadata can still be sensitive. Review event files before sharing them.

## Next: Phase 2 — Execution Graph

Phase 2 will materialize the event stream into the thing ExecWeave is ultimately about:

- entity resolution and deduplication;
- process/file/network graph construction;
- temporal relationships;
- graph filtering;
- causal/runtime path queries;
- exportable graph snapshots.

Phase 3 will build the live interactive UI on top of that graph.

## Contributing

**Contributions are very welcome.**

High-impact areas now include:

- Linux eBPF backend;
- Windows ETW backend;
- macOS Endpoint Security backend;
- graph entity resolution;
- interactive graph visualization;
- OpenTelemetry / MCP integrations;
- privacy and redaction;
- reproducible agent workloads;
- performance evaluation;
- README and documentation translations.

For small changes, fork the repository and open a pull request. For a new collector or architecture change, open an issue first and document the telemetry source, privilege requirements, expected graph relationships, and causal guarantees.

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
