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

Instead of reading hundreds of CLI lines, you can inspect how an agent, its tools, subprocesses, files, commands, and network activity connect to one another — while keeping observed evidence separate from inference.

> **Event is ground truth. The graph is a materialized view.**

## Quick start

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

### Watch any command live

```bash
execweave live --open -- claude
```

Other examples:

```bash
execweave live --open -- codex
execweave live --open -- gemini
execweave live --open -- opencode
execweave record --open -- python my_agent.py
```

The live server binds only to `127.0.0.1` and updates the graph while the command is still running.

```text
AI agent / command
       ↓
runtime collector
       ↓
   events.jsonl
       ↓
execution graph
       ↓
local browser viewer
```

A normal run produces:

```text
.execweave/runs/<run-id>/
├── events.jsonl
├── graph.json
└── viewer.html
```

The current live path intentionally uses the portable collector. Linux `strace` evidence is post-processed after the command exits, so ExecWeave does not present it as live telemetry.

## Native agent integrations

ExecWeave currently has native semantic adapters for **Claude Code** and **OpenAI Codex**.

Provider hooks add logical Agent / Model / Tool / Command evidence. OS collectors independently record what the machine actually observed. ExecWeave does not collapse those two evidence classes into fake causality.

### Claude Code

Generate the hook settings fragment once:

```bash
execweave-claude-hook --print-config
```

Merge its `hooks` object into your Claude Code settings, then record one run:

```bash
execweave-claude-record --open -- claude
```

When hooks fire, ExecWeave automatically produces runtime, semantic, and conservatively correlated artifacts.

See [`docs/claude-code-hooks.md`](docs/claude-code-hooks.md).

### OpenAI Codex

Generate the supported lifecycle-hook configuration fragment:

```bash
execweave-codex-hook --print-config
```

Merge the printed `hooks` object into your Codex `hooks.json`, then run:

```bash
execweave-codex-record --open -- codex
```

ExecWeave currently consumes Codex `SessionStart`, `PreToolUse`, and `PostToolUse` lifecycle events. For canonical `Bash` calls, the declared command becomes semantic evidence and can participate in the same conservative Tool → Process correlation used by Claude runs.

`PostToolUse` is deliberately represented as neutral `TOOL_CALL_RETURNED`, not as success or failure, because the current provider payload does not expose a sufficiently reliable outcome signal for that claim.

Codex lifecycle hooks are still evolving. Some `codex exec` and Windows execution paths have had upstream hook-coverage gaps, so the adapter records only the provider hooks actually delivered. The independent OS runtime collector continues to work when provider hooks are absent.

See [`docs/codex-hooks.md`](docs/codex-hooks.md).

## Layered run artifacts

A provider-integrated run can produce:

```text
.execweave/runs/<run-id>/
├── events.jsonl              # runtime evidence only
├── graph.json                # runtime-only graph
├── viewer.html               # runtime-only viewer
├── semantic.jsonl            # provider hook evidence only
├── events.semantic.jsonl     # validated runtime + semantic stream
├── graph.semantic.json       # runtime + semantic graph
├── viewer.semantic.html      # runtime + semantic viewer
├── events.correlated.jsonl   # derived stream
├── graph.correlated.json     # inferred bridges + correlation metadata
└── viewer.correlated.html    # correlation-aware viewer
```

Raw runtime and provider sidecars remain separate. Correlation derives a new stream rather than rewriting observed evidence.

## Tool → Process correlation

A provider may tell ExecWeave:

```text
tool_call --DECLARED_COMMAND--> command
```

while OS telemetry independently observes processes. ExecWeave may derive:

```text
tool_call --CORRELATED_WITH_PROCESS--> process
```

only when the existing bounded matcher finds one uniquely supported candidate.

Every bridge remains:

```text
inferred: true
causal: false
```

Ambiguous, unmatched, compound, shell-builtin, or otherwise unsupported calls produce no bridge.

The correlated Viewer includes a **Correlation Summary** with:

- matched
- ambiguous
- no match
- unsupported
- considered tool calls
- correlation window

So a missing edge does not silently mean “nothing happened”; it may mean ExecWeave intentionally refused to infer a relationship from insufficient evidence.

## Interactive Viewer

The standalone Viewer is local and self-contained — no CDN or external JavaScript dependency is required.

Current baseline includes:

- pan / zoom / draggable nodes
- node and edge inspection
- node-type and relation filters
- causal-only filter
- **observed only** filter
- search
- evidence-sequence Timeline ↔ Graph replay
- Play/Pause playback
- progressive cluster expansion
- 1-hop / 2-hop focused neighborhoods
- browser-local Saved Views
- explicit observed / non-causal / inferred edge styling
- correlation summary for correlated graphs

**Observed only** removes `inferred: true` relationships before focus traversal and layout, rather than merely hiding purple lines after the fact.

Saved Views store UI state only; they do not copy graph evidence into browser storage.

## Runtime evidence

### Portable backend

The portable collector uses `psutil` and `watchdog` on Linux, macOS, and Windows. It is also the current live-graph backend.

It records process lineage and process-level network observations. Portable filesystem watching is session-correlated rather than process-attributed, and short-lived processes can be missed between polling intervals.

### Linux `strace` backend

On Debian/Ubuntu:

```bash
sudo apt-get install strace
execweave record --backend strace --open -- claude
```

The Linux reference backend follows descendants and converts syscall evidence into process-attributed process, filesystem, and network events.

`execweave-claude-record --backend auto` and `execweave-codex-record --backend auto` prefer `strace` on Linux when available.

Future native collectors remain planned for Linux eBPF, Windows ETW, and macOS Endpoint Security.

## Graph-first evidence model

Every observation is represented as:

```text
source --RELATION--> target
```

Runtime examples:

```text
session --LAUNCHED--> process
process --SPAWNED--> process
process --EXECUTED--> executable
process --OPENED_READ--> file
process --OPENED_WRITE--> file
process --CONNECTED_TO--> network_endpoint
```

Semantic examples:

```text
agent --USED_MODEL--> model
agent --REQUESTED_TOOL_CALL--> tool_call
tool_call --USES_TOOL--> tool
tool_call --DECLARED_COMMAND--> command
```

Derived example:

```text
tool_call --CORRELATED_WITH_PROCESS--> process
```

Repeated evidence is aggregated. If one process opens the same file 17 times, the graph stores one relationship with `count = 17` instead of drawing 17 overlapping lines.

## No fake causality

ExecWeave deliberately distinguishes:

- **observed causal evidence** — e.g. syscall-attributed process actions
- **observed non-causal/session evidence** — e.g. portable filesystem changes
- **provider semantic evidence** — what the agent/tool layer reports
- **inferred relationships** — conservative bridges derived from multiple evidence sources

Provider hooks do not currently provide the child OS PID needed to prove Tool → Process attribution. Temporal proximity alone is insufficient. Ambiguity produces no edge.

Likewise, a process reading a sensitive file and later connecting to a network endpoint is not proof that those bytes were transmitted.

## Security analysis

ExecWeave includes an initial conservative analysis layer:

```bash
execweave analyze run.graph.json
execweave analyze run.graph.json --output analysis.json
```

It can flag sensitive-file access, external endpoints, and possible sensitive-file → network paths while explicitly preserving:

```json
{
  "data_flow_proven": false,
  "exfiltration_proven": false
}
```

## Graph operations

```bash
execweave graph-summary run.graph.json
execweave graph-filter run.graph.json --output causal.graph.json --causal-only
execweave graph-focus run.graph.json NODE_ID --hops 2 --output focused.graph.json
execweave path run.graph.json SOURCE_NODE_ID TARGET_NODE_ID --causal-only
```

Large repetitive leaf resources can be condensed:

```bash
execweave graph-condense run.graph.json \
  --output run.compact.graph.json \
  --threshold 8
```

Add `--keep-expansion` if you want the Viewer to restore original cluster members on demand.

## Current status

ExecWeave is currently **v0.4.0** and under active development.

Implemented baseline:

- cross-platform portable runtime collection
- Linux syscall-backed reference collection
- validated append-only JSONL evidence stream
- execution-graph materialization and queries
- standalone and live local Viewer
- Timeline replay and focused neighborhoods
- graph condensation and progressive expansion
- Saved Views
- native Claude Code semantic adapter + run-bound recorder
- native OpenAI Codex semantic adapter + run-bound recorder
- conservative Tool → Process correlation
- correlation metadata and Viewer summary
- explainable initial security-analysis rules
- Ubuntu / macOS / Windows CI across Python 3.10 and 3.12

Still ahead:

- Linux eBPF
- Windows ETW
- macOS Endpoint Security
- more agent/provider adapters
- stronger process/tool identity evidence
- richer MCP normalization
- performance and long-run scalability work

## Privacy

ExecWeave is **local-first**.

By default, runtime events, semantic sidecars, graphs, reports, and Viewers stay on the local machine. The standalone Viewer does not require an external CDN.

ExecWeave does not intentionally capture file contents or raw read/write byte buffers. Native semantic adapters also avoid prompt/transcript contents by default, but commands, paths, endpoint metadata, session identifiers, and other runtime metadata can still be sensitive.

Review artifacts before sharing them.

## Documentation

- [`Phase 1 — Runtime Collection`](docs/phase-1-runtime-collection.md)
- [`Phase 2 — Execution Graph`](docs/phase-2-execution-graph.md)
- [`Live Graph`](docs/live-graph.md)
- [`Semantic Telemetry`](docs/semantic-telemetry.md)
- [`Claude Code Hooks`](docs/claude-code-hooks.md)
- [`OpenAI Codex Hooks`](docs/codex-hooks.md)
- [`Security Analysis`](docs/security-analysis.md)

## Contributing

**Contributions are very welcome.**

Areas where help is especially useful:

- Linux eBPF
- Windows ETW
- macOS Endpoint Security
- agent / tool / MCP provider adapters
- process and entity resolution
- provenance and correlation methods
- graph visualization and large-run UX
- privacy / redaction
- testing and performance evaluation
- documentation

Open an issue, propose an architecture change, add an integration, or submit a pull request.

> **Let's make AI-agent execution understandable.**

## License

See [`LICENSE`](LICENSE).
