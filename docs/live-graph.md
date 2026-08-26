<!-- i18n-nav:start -->
<p align="center">
  <strong>English</strong> |
  <a href="live-graph.zh-TW.md">繁體中文</a> |
  <a href="live-graph.zh-CN.md">简体中文</a> |
  <a href="live-graph.ja.md">日本語</a> |
  <a href="live-graph.ko.md">한국어</a> |
  <a href="live-graph.fr.md">Français</a> |
  <a href="live-graph.de.md">Deutsch</a> |
  <a href="live-graph.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# Live Graph

ExecWeave can stream a local execution graph while an AI agent or arbitrary command is still running.

```bash
execweave live --open -- claude
```

## Current contract

The live runtime collector intentionally uses the cross-platform `portable` backend. In v0.6.4, the live session can also ingest a second append-only stream of specialized evidence through a run-specific semantic sidecar.

ExecWeave exports the sidecar path to the launched command as:

```text
EXECWEAVE_SEMANTIC_SIDECAR
```

Configured Claude Code, OpenAI Codex, Gemini CLI, and Cursor hooks inherit that variable automatically. The installed OpenCode plugin does the same. Their semantic events can therefore appear in the same Live Viewer without switching to a separate provider `*-record` command.

This does **not** mean `live` silently edits provider settings. The hook/plugin integration must already be configured once. Model-runtime and inference-gateway metadata still require their explicit emitters until those integrations gain automatic observation paths.

The Linux `strace` backend currently parses trace files after the command exits. It provides stronger syscall-backed attribution, but it is not a live event source in the current implementation. ExecWeave does not label post-processed evidence as live telemetry.

For stronger Linux post-run attribution use:

```bash
execweave record --backend strace --open -- claude
```

## v0.6.4 data flow

```text
                         ┌─ provider hook / plugin ─→ semantic.jsonl ─┐
command ─→ portable ─→ events.jsonl ─────────────────────────────────┤
                                                                    ↓
                                                     incremental live normalizer
                                                                    ↓
                                                         GraphAccumulator
                                                                    ↓
                                                     localhost HTTP server
                                                                    ↓
                                                        /live.json deltas
                                                                    ↓
                                                          browser / Top
```

OS runtime evidence remains the independent ground-truth stream. Specialized evidence is normalized into the live graph provisionally; it is not allowed to rewrite the raw runtime stream or manufacture missing evidence.

The browser and detached `execweave top` dashboard consume sequence-numbered `/live.json` snapshots/deltas. `/graph.json` remains available as a current snapshot endpoint. Incremental ingestion tails only newly appended JSONL bytes and buffers an incomplete trailing line until its newline arrives.

When the command exits, ExecWeave:

1. validates the completed runtime event stream;
2. if specialized evidence exists, performs the canonical runtime + semantic merge into `events.semantic.jsonl`;
3. rebuilds the final graph from that canonical stream rather than trusting provisional live state;
4. writes `graph.json` and standalone `viewer.html`;
5. marks the live graph finished and briefly serves the final viewer before shutting down the local server.

If no specialized events arrive, final materialization remains runtime-only.

## Automatically visible Agent integrations

| Integration | Automatic delivery into v0.6.4 Live Viewer |
| --- | --- |
| Claude Code | **Yes**, after ExecWeave hooks are configured |
| OpenAI Codex | **Yes**, after ExecWeave hooks are configured |
| Gemini CLI | **Yes**, after ExecWeave hooks are configured |
| Cursor | **Yes**, after ExecWeave hooks are configured |
| OpenCode | **Yes**, after the ExecWeave plugin is installed |

All five integrations use the same per-run sidecar contract. CI regression coverage invokes each provider adapter against one shared `EXECWEAVE_SEMANTIC_SIDECAR` and verifies that the resulting provider evidence is materialized into the live graph.

## Terminal Top

`top` no longer renders over the Agent terminal. The original terminal stays interactive for the Agent, while the dashboard attaches to the same localhost live session in a separate terminal window:

```bash
execweave top -- codex
execweave top --open -- codex
```

`--open` adds the browser Viewer. The detached dashboard is attach-only and never launches a second Agent. Its hidden attach URL is restricted to localhost HTTP.

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
├── semantic.jsonl
├── events.semantic.jsonl      # only materialized when specialized evidence exists
├── graph.json
└── viewer.html
```

`events.jsonl` remains runtime-only. `semantic.jsonl` is the raw specialized sidecar. The final `graph.json` is built from `events.semantic.jsonl` when specialized evidence exists, otherwise directly from `events.jsonl`.

Choose another directory with:

```bash
execweave live --output-dir my-live-run --open -- claude
```

Existing non-empty artifacts are rejected rather than overwritten.

## Provisional live normalization

During a live run, both JSONL streams may be incomplete because the session has not finished yet.

The live normalizer therefore works incrementally and conservatively. Runtime process identity observed so far can be used to resolve specialized process references, but missing identity is never guessed. Specialized events that cannot yet be normalized do not become stronger evidence merely because they were seen live.

Sidecar truncation causes the provisional materialization to reset and replay from the current files. Incomplete trailing JSONL records are buffered instead of being treated as complete events. The final graph is still rebuilt from the canonical merge after runtime validation succeeds.

## Portable-backend limitations

The current live runtime layer inherits the portable collector's guarantees:

- process discovery is polling-based;
- very short-lived processes may be missed;
- filesystem changes are session-correlated rather than process-attributed;
- per-process network inspection depends on operating-system visibility and permissions.

These limitations remain visible in event attribution metadata. The Live Viewer does not upgrade a non-causal observation into a causal edge.

## Large-session safety

Live updates use bounded delta history instead of replaying the full event stream on every poll. When the graph exceeds the Viewer safety budget, the live endpoint switches to a compact counts-only payload so collection and final canonical artifact generation can continue without forcing the browser to materialize an unsafe SVG graph.

## Future native live backends

Planned collectors include:

- Linux eBPF;
- Windows ETW;
- macOS Endpoint Security.

The goal is to preserve the same ExecWeave event semantics while improving completeness, process attribution, and runtime overhead.

## CI coverage

The repository CI configuration covers:

- localhost live-session startup and final artifact generation;
- sequence-numbered snapshot/delta behavior and resynchronization;
- incomplete trailing JSONL records;
- semantic sidecar arrival before runtime identity is ready;
- semantic sidecar truncation and replay;
- canonical final runtime + semantic rebuild;
- automatic shared-sidecar delivery for Claude, Codex, Gemini, Cursor, and OpenCode;
- detached Top behavior without launching a second Agent;
- localhost-only Top attach URLs.
