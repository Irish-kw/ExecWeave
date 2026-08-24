# Phase 1 — Runtime Collection

Phase 1 establishes a graph-ready, local runtime event stream that Phase 2 can turn into an execution graph.

## Status

**Phase 1 is complete for the Linux reference path and portable fallback.**

ExecWeave now provides two collection backends:

- `strace` — Linux syscall-backed collection. Captures short-lived descendants and process-attributed filesystem/network actions from syscall evidence.
- `portable` — psutil + watchdog fallback for Linux, macOS, and Windows. Process/network events are polled; filesystem changes are session-correlated and explicitly non-causal.

`auto` prefers `strace` on Linux when it is installed and otherwise selects `portable`.

```bash
execweave doctor
execweave run --backend auto -- claude
```

## Install

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

On Debian/Ubuntu, install the Linux reference backend with:

```bash
sudo apt-get install strace
```

Then:

```bash
execweave run -- claude
execweave run -- codex
execweave run -- gemini
execweave run -- opencode
execweave run -- python my_agent.py
```

Events are written locally to:

```text
.execweave/runs/<session-id>.jsonl
```

Raw `strace` files are deleted after parsing by default. Keep them only for debugging:

```bash
execweave run --keep-native-trace -- claude
```

## Backend capability model

### Linux `strace` backend

The native Phase 1 reference backend follows descendants with `strace -ff` and records syscall-backed edges.

It can produce relationships such as:

```text
session --LAUNCHED--> process
process --SPAWNED--> process
process --EXECUTED--> executable
process --OPENED_READ--> file
process --OPENED_WRITE--> file
process --DELETED--> file
process --RENAMED_TO--> file
process --CHANGED_CWD_TO--> directory
process --CONNECTED_TO--> network_endpoint
process --EXITED--> ...
```

These events include:

```json
{
  "attribution": "syscall",
  "causal": true,
  "backend": "strace"
}
```

`OPENED_READ` and `OPENED_WRITE` describe the access mode proven by the open syscall. They intentionally do **not** claim that a later byte-level `read()` or `write()` occurred. Byte-level data-flow tracking belongs to a later collector.

### Portable backend

The portable backend launches the command directly and uses psutil/watchdog.

It can produce:

```text
session --LAUNCHED--> process
process --SPAWNED--> process
process --CONNECTED_TO--> network_endpoint
session --OBSERVED_FILE_CHANGE--> file
```

Filesystem changes remain explicit session observations:

```json
{
  "attribution": "session_observation",
  "causal": false
}
```

This prevents ExecWeave from presenting temporal correlation as causal attribution.

## Event ordering and identity

The JSONL sink adds a monotonically increasing `sequence` number to every event in a run. Timestamps are retained separately.

Portable process IDs use PID + process creation time because operating systems reuse PIDs.

The Linux syscall backend scopes process IDs to the ExecWeave session:

```text
process:<session-id>:<pid>
```

A process identity is therefore never globally inferred from PID alone.

## Short-lived processes

The portable backend can miss a process that starts and exits entirely between polling intervals.

The Linux reference backend removes this Phase 1 gap by tracing process syscalls and following descendants with `strace -ff`. CI includes an integration test that launches a short-lived child and checks that a `SPAWNED` edge is emitted.

## Filesystem path attribution

The Linux parser tracks per-process working directories and handles common `*at` syscalls. Relative paths are resolved against the best syscall evidence available.

Path attribution can still be imperfect for uncommon dirfd patterns. Raw syscall names and paths are retained as event attributes so downstream consumers can audit how an edge was produced.

## Network attribution

The Linux backend records successful `connect()` calls for:

- IPv4
- IPv6
- Unix-domain sockets

The portable backend uses per-process socket inspection when the operating system exposes it to the current user.

A missing event should never be interpreted as proof that no network action happened on a backend that lacks permission or coverage.

## Privacy

Runtime telemetry can contain sensitive paths, executable names, command arguments, and endpoints.

Phase 1 follows these defaults:

- all event data stays local;
- raw syscall trace files are deleted after parsing unless `--keep-native-trace` is requested;
- file contents are not traced;
- byte buffers from `read()`/`write()` are not collected;
- `execve` arguments are not copied into graph events beyond an argument count.

The session wrapper still records the command supplied to ExecWeave, so users should avoid putting secrets directly on command lines.

## Diagnostics

```bash
execweave doctor
```

Example:

```json
{
  "auto_selected": "strace",
  "platform": "linux",
  "portable": true,
  "strace": true
}
```

## Overhead benchmark harness

Phase 1 includes a repeatable smoke benchmark:

```bash
execweave benchmark --backend portable --iterations 5
execweave benchmark --backend strace --iterations 5
```

or:

```bash
python benchmarks/phase1_overhead.py
```

It reports raw baseline/instrumented timings, medians, and an overhead ratio. These are environment-specific measurements, not a published performance claim.

## Acceptance criteria

- [x] Explicit ExecWeave session wrapper
- [x] Graph-ready event schema
- [x] Monotonic event sequence numbers
- [x] Root process capture
- [x] Parent/child process capture
- [x] Portable filesystem observation
- [x] Portable per-process network observation
- [x] Linux reliable short-lived process capture
- [x] Linux process-attributed filesystem syscall telemetry
- [x] Linux process-attributed network syscall telemetry
- [x] Backend auto-selection and capability diagnostics
- [x] Raw native trace cleanup by default
- [x] Cross-platform portable fallback
- [x] Unit tests for parser and backend selection
- [x] Linux native integration test in CI
- [x] Overhead benchmark harness

## Explicitly out of Phase 1

The following remain future work rather than being falsely marked complete:

- Windows ETW process-attributed filesystem backend
- macOS Endpoint Security process-attributed backend
- Linux eBPF backend to reduce ptrace overhead
- DNS-to-domain correlation
- byte-level read/write data-flow tracking
- agent/tool/MCP semantic telemetry
- graph materialization and interactive visualization

Those capabilities can feed the same event model without changing the Phase 1 contract.

## Why `strace` before eBPF?

Phase 1 needs a correctness-oriented reference implementation of process/file/network attribution and event semantics. `strace` is simple to inspect, easy to test, and captures short-lived descendants without inventing causality.

An eBPF backend is a natural next optimization for lower overhead and always-on collection, but it should implement the same graph event semantics rather than defining them implicitly.

## Contributing

Useful next contributions include Linux eBPF, Windows ETW, macOS Endpoint Security, path/entity resolution, overhead evaluation, privacy/redaction, and reproducible agent workloads.

For a new collector backend, please preserve the distinction between proven causal attribution and session-level observation.
