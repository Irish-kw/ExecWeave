# Phase 1 — Runtime Collection

ExecWeave Phase 1 establishes a graph-ready local event stream before the interactive graph UI is built.

## Current MVP

Install from a local checkout:

```bash
python -m pip install -e ".[dev]"
```

Run an AI agent or any other command under ExecWeave:

```bash
execweave run -- claude
```

Other examples:

```bash
execweave run -- codex
execweave run -- gemini
execweave run -- opencode
execweave run -- python my_agent.py
```

By default, ExecWeave watches the current directory and writes events to:

```text
.execweave/runs/<session-id>.jsonl
```

Use another working/watch directory:

```bash
execweave run --watch-root /path/to/repo -- claude
```

Disable collectors individually while debugging:

```bash
execweave run --no-files -- claude
execweave run --no-network -- claude
```

## Event model

Every observation is emitted in a graph-ready form:

```text
source --RELATION--> target
```

Example process event:

```json
{
  "schema_version": "0.1",
  "event_type": "process.started",
  "relation": "SPAWNED",
  "source": {
    "type": "process",
    "id": "process:1234:1780000000000000"
  },
  "target": {
    "type": "process",
    "id": "process:1240:1780000001000000"
  }
}
```

Example network event:

```text
process --CONNECTED_TO--> network_endpoint
```

Filesystem events in the current MVP are deliberately weaker:

```text
session --OBSERVED_FILE_CHANGE--> file
```

They include:

```json
{
  "attribution": "session_observation",
  "causal": false
}
```

This distinction is intentional. A directory watcher can prove that a file changed during a session, but it cannot prove which process caused that change. ExecWeave should never present temporal correlation as causal attribution.

## What is collected now

### Session

- command
- working directory
- start/finish
- return code

### Process

- PID
- parent PID
- process creation time
- executable
- command line
- parent/child relationships

Process node IDs include both PID and creation time because operating systems reuse PIDs.

### Network

For observed processes, ExecWeave records outbound remote endpoints when the operating system exposes the connection to the current user.

### Filesystem

The current watcher records create, modify, delete, and move events under the selected watch root.

## Important limitations

This is the first collector, not the final security sensor.

### Short-lived processes

Process discovery currently uses polling. A process that starts and exits completely between two polling intervals may be missed.

Planned Linux collectors will use lower-level event sources such as eBPF to remove this gap.

### Filesystem attribution

The current filesystem watcher is session-correlated, not process-attributed.

Planned OS-specific collectors should eventually produce stronger edges such as:

```text
process --READ--> file
process --WROTE--> file
process --DELETED--> file
```

only when the underlying telemetry supports that claim.

### Network permissions

Some operating systems restrict per-process socket inspection. Missing network events do not currently imply that no connection occurred.

### Agent intent

The Phase 1 runtime collector sees system behavior. Agent/tool/MCP semantic integrations will later provide the intent-side events that can be correlated with runtime behavior.

## Phase 1 acceptance criteria

Phase 1 should eventually provide reliable versions of:

- [x] Explicit ExecWeave session wrapper
- [x] Graph-ready event schema
- [x] Root process capture
- [x] Parent/child process discovery MVP
- [x] Filesystem observation MVP
- [x] Network connection observation MVP
- [x] Session correlation
- [ ] Reliable short-lived process capture
- [ ] Process-attributed filesystem access on Linux
- [ ] Process-attributed filesystem access on Windows
- [ ] Process-attributed filesystem access on macOS
- [ ] OS-specific collector capability reporting
- [ ] Performance/overhead benchmarks

## Next collector milestone

The next major implementation target is a Linux event-driven collector that can capture process execution and process-attributed filesystem/network activity without relying on polling.

The existing JSONL schema is intentionally separated from the collection mechanism so eBPF, ETW, Endpoint Security, or future collectors can feed the same graph pipeline.

## Contributing

Phase 1 is a good place to contribute because several collector backends can be developed independently.

Useful contribution areas include:

- Linux eBPF telemetry
- Windows ETW telemetry
- macOS Endpoint Security telemetry
- process attribution
- socket attribution
- filesystem attribution
- tests and reproducible workloads
- event schema review
- overhead measurement

If you want to work on a larger collector change, please open an issue describing the telemetry source, supported platform, expected events, and privilege requirements before implementation.
