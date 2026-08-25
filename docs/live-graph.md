# Live Graph

ExecWeave can stream a local execution graph while an AI agent or arbitrary command is still running.

```bash
execweave live --open -- claude
```

## Current contract

The live MVP intentionally uses the `portable` collector.

The Linux `strace` backend currently parses trace files after the command exits. It provides stronger syscall-backed attribution, but it is not a live event source in the current implementation. ExecWeave does not label post-processed evidence as live telemetry.

For stronger Linux post-run attribution use:

```bash
execweave record --backend strace --open -- claude
```

## Data flow

```text
command
  ↓
portable collector
  ↓
events.jsonl
  ↓
partial graph materialization
  ↓
localhost HTTP server
  ↓
/graph.json
  ↓
browser viewer
```

The browser polls `/graph.json` while the run is active. Each snapshot is built from the same Phase 1 event-stream and Phase 2 graph contracts used by final artifacts.

When the command exits, ExecWeave:

1. validates the completed event stream;
2. writes `graph.json`;
3. writes the standalone `viewer.html`;
4. marks the live graph finished;
5. serves the final viewer briefly before shutting down the local server.

## Network exposure

The live server binds only to:

```text
127.0.0.1
```

It is not exposed on `0.0.0.0` and is not intended to be reachable from other hosts on the LAN.

Choose a port explicitly:

```bash
execweave live --port 8765 --open -- claude
```

Port `0` is the default and asks the operating system to select an available local port.

## Artifacts

The default run directory is:

```text
.execweave/runs/<session-id>/
├── events.jsonl
├── graph.json
└── viewer.html
```

Choose another directory with:

```bash
execweave live --output-dir my-live-run --open -- claude
```

Existing non-empty artifacts are rejected rather than overwritten.

## Incomplete snapshots

During a live run, `events.jsonl` is intentionally incomplete because the session has not finished yet.

Live graph snapshots therefore use the graph builder's `allow_incomplete` mode. Structural validation still applies: malformed JSON, inconsistent sessions, invalid entities, or broken sequence ordering are not treated as valid graph evidence.

The final graph is built only after normal complete-session validation succeeds.

## Portable-backend limitations

The current live MVP inherits the portable collector's guarantees:

- process discovery is polling-based;
- very short-lived processes may be missed;
- filesystem changes are session-correlated rather than process-attributed;
- per-process network inspection depends on operating-system visibility and permissions.

These limitations remain visible in event attribution metadata. The live viewer does not upgrade a non-causal observation into a causal edge.

## Future native live backends

Planned collectors include:

- Linux eBPF;
- Windows ETW;
- macOS Endpoint Security.

The goal is to preserve the same ExecWeave event semantics while improving completeness, process attribution, and runtime overhead.

## CI coverage

The repository CI configuration includes a `live` smoke path that:

- starts a local live session;
- runs a short command;
- writes final artifacts;
- validates `events.jsonl`;
- summarizes the resulting graph.

Unit/integration tests also exercise the localhost `/graph.json` endpoint directly.
