# ExecWeave

<p align="center">
  <strong>English</strong> |
  <a href="README.zh-TW.md">繁體中文</a> |
  <a href="README.zh-CN.md">简体中文</a> |
  <a href="README.ja.md">日本語</a> |
  <a href="README.ko.md">한국어</a>
</p>

**See what AI agents actually do on your machine.**

ExecWeave is an open-source, local-first observability project that turns AI-agent activity into an interactive execution graph while keeping observed evidence separate from inference.

> **Event is ground truth. The graph is a materialized view.**

<p align="center">
  <img src="docs/assets/execweave-viewer.png" alt="ExecWeave Live execution graph" width="100%">
</p>

## Install

ExecWeave is published on PyPI as a standard Python wheel/sdist. Install the latest published release with:

```bash
python -m pip install -U execweave
```

The `main` branch may contain a newer patch than the current PyPI release. To test the latest mainline build directly:

```bash
python -m pip install --upgrade --force-reinstall "execweave @ git+https://github.com/Irish-kw/ExecWeave.git@main"
```

For development:

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

Watch Claude Code, OpenAI Codex, or Gemini CLI live:

```bash
# Claude Code
execweave live --open -- claude

# OpenAI Codex
execweave live --open -- codex

# Gemini CLI
execweave live --open -- gemini

# Cursor
execweave live --open -- cursor
```

<!-- v0.6.3-live -->
### v0.6.3 live observability

Use the same live session in either the browser or terminal:

```bash
execweave top -- codex          # Terminal dashboard
execweave top --open -- codex   # Terminal + Web Viewer
```

Live updates use incremental snapshots/deltas with bounded history instead of repeatedly rebuilding and transferring the full graph. Live and standalone viewers support a persistent Dark/Light theme switch. On Linux, very large recursive filesystem scopes are preflighted and automatically fall back from inotify to polling when needed, so an exhausted inotify watch pool does not abort the session.

`execweave live --open -- cursor` is supported for generic runtime telemetry. For Cursor semantic hooks and conservative tool/process correlation, use `execweave-cursor-record --open -- cursor`.

Run the reproducible graph scalability benchmark with `execweave-scalability`; CI covers 10k, 100k, and 1M synthetic events.

#### Scalability benchmark

Reference GitHub Actions result for the incremental `GraphAccumulator` synthetic workload (`retain_event_ids=False`):

| Events | Apply time | Throughput | Nodes | Edges | Apply RSS Δ | Snapshot |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 10k | 0.114 s | 87,681 ev/s | 10,001 | 10,000 | 35.9 MiB | 8.5 MiB |
| 100k | 0.654 s | 152,816 ev/s | 10,001 | 10,000 | 25.8 MiB | 8.6 MiB |
| **1M** | **6.087 s** | **164,273 ev/s** | **10,001** | **10,000** | **23.5 MiB** | **8.6 MiB** |

At **1,000,000 events**, the incremental in-memory graph did not duplicate raw event IDs; raw evidence remains separate from the materialized graph. This benchmark measures graph accumulation and snapshot materialization, not end-to-end collector or browser throughput.

Or build the full artifact pipeline:

```bash
execweave record --open -- python my_agent.py
```

## Performance and footprint

ExecWeave includes a reproducible package-level overhead benchmark that is run from an installed wheel. The reference plot follows the same trade-off style commonly used for model quality/cost comparisons:

- **X-axis:** additional peak process-tree RSS, low → high.
- **Y-axis:** runtime overhead, low → high.
- **Bubble area:** median artifact size per run.
- **Preferred region:** lower-left.

![ExecWeave overhead trade-off](docs/benchmarks/v0.6.0-github-actions.svg)

Reference environment: GitHub Actions Ubuntu runner, Intel Xeon Platinum 8573C, 4 logical CPUs, Python 3.12.14, `n=7`.

| Profile | Median wall time | Runtime overhead | Additional peak RSS | Median artifacts/run |
| --- | ---: | ---: | ---: | ---: |
| ExecWeave OFF | 236.221 ms | 0.0% | 0.0 MB | 0 KB |
| Portable ON | 391.580 ms | 65.768% | 27.852 MB | 741.355 KB |
| Strace ON | 1226.076 ms | 419.038% | 37.653 MB | 572.838 KB |

The same build produced an approximately **113 KB wheel** and **198 KB sdist**. The installed ExecWeave distribution footprint was about **849 KB**, excluding Python and dependency footprints.

This is a deliberately short, file/process-heavy **reference microbenchmark**, not a universal workload claim. Percentage overhead is amplified because the uninstrumented baseline is only a few hundred milliseconds. Re-run `execweave-overhead` on the target host and representative workload before making capacity decisions.

```bash
execweave-overhead \
  --iterations 7 \
  --strace auto \
  --output-json benchmark-results.json \
  --output-svg benchmark-overhead.svg
```

Raw reference data and methodology: [`docs/benchmarks/`](docs/benchmarks/).

## Evidence layers

ExecWeave intentionally models four different layers instead of flattening them into one trace:

```text
Agent / IDE semantic evidence
          ↓
Inference gateway / routing evidence
          ↓
Model runtime / inference-server evidence
          ↓
OS runtime evidence: process / file / network
```

A relationship is only causal when the underlying telemetry supports that claim.

## Agent / IDE integrations

### Claude Code

```bash
execweave-claude-hook --print-config
execweave-claude-record --open -- claude
```

### OpenAI Codex

```bash
execweave-codex-hook --print-config
execweave-codex-record --open -- codex
```

### Gemini CLI

```bash
execweave-gemini-hook --print-config
execweave-gemini-record --open -- gemini
```

### Cursor

```bash
execweave-cursor-hook --print-config
execweave-cursor-record --open -- cursor
```

Cursor provides a stable `tool_use_id`, allowing exact logical tool-call identity across its pre/post hooks.

### OpenCode

```bash
execweave-opencode-plugin --install
execweave-opencode-record --open -- opencode
```

The project-local OpenCode plugin uses exact `sessionID + callID` identity and deliberately does not forward tool output.

Provider-integrated runs preserve runtime, semantic, and correlated artifacts separately. Tool → Process bridges remain conservative derived evidence:

```text
inferred: true
causal: false
```

Ambiguity produces no edge.

## Inference gateway integrations

OpenRouter and LiteLLM Proxy are modeled as `inference_gateway`, not as local model runtimes.

```bash
execweave-inference-gateway event \
  --gateway litellm \
  --requested-model assistant \
  --resolved-model azure/gpt-5 \
  --provider-name Azure \
  --deployment-id deployment-west \
  --sidecar gateway.jsonl
```

ExecWeave keeps requested model, resolved model, routed provider, and deployment identity distinct. Provider/deployment edges are only emitted when authoritative metadata is supplied; they are never inferred from a model-name prefix.

When the caller has an explicit shared identity across Gateway and Model Runtime observations, the two request nodes can be linked without collapsing layers:

```bash
execweave-inference-link \
  --gateway litellm \
  --gateway-request-id gw-123 \
  --runtime vllm \
  --runtime-request-id rt-456 \
  --shared-request-id trace-789 \
  --sidecar inference.jsonl
```

`SAME_INFERENCE_REQUEST` is exact identity evidence, not causal evidence:

```text
identity_exact: true
inferred: false
causal: false
```

The raw shared request ID is not persisted; only a SHA-256-derived identity hash is stored.

## Model runtime integrations

Current model-runtime integrations are **Ollama**, **llama.cpp**, **vLLM**, and **LM Studio**.

```bash
execweave-model-runtime event --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime llamacpp --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime vllm --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime lmstudio --sidecar model-runtime.jsonl
```

OpenAI-compatible runtimes share response/usage and model-catalog parsing while retaining runtime-specific evidence semantics. Prompt, generated, and reasoning content are not stored. Sensitive local model paths are redacted; llama.cpp keeps stricter GGUF-path redaction.

LM Studio model-catalog visibility is represented as `ADVERTISES_MODEL`, not as proof that model weights are loaded in memory.

## Runtime evidence

The portable collector runs on Linux, macOS, and Windows. Linux also has a syscall-backed `strace` reference backend.

```bash
execweave doctor
execweave run --backend portable -- your-command
execweave run --backend strace -- your-command
```

Since v0.6.1, child commands are resolved through a shared cross-platform launcher before execution. Linux and macOS retain normal PATH executable behavior. Windows resolves `.exe`, `.cmd`, and `.bat` launchers through PATH/PATHEXT, while an explicit `.ps1` launcher is invoked through PowerShell. Dedicated Windows CI exercises Codex and Cursor recorders from both `cmd.exe` and Windows PowerShell; the full Cursor semantic/correlation integration remains covered by the normal Windows, macOS, and Ubuntu matrix.

Portable filesystem watching is session-correlated rather than process-causal, and short-lived processes can be missed between polling intervals. The Linux `strace` path captures process-attributed syscall evidence after the command exits.

Future native collectors remain planned for Linux eBPF, Windows ETW, and macOS Endpoint Security.

## v0.6.3 safety patch

v0.6.3 hardens long-running and high-cardinality sessions without changing evidence semantics or graph schema 0.1:

- Broad recursive filesystem scopes such as a filesystem root, user home, or users-home parent are no longer recursively observed as-is; process, network, and semantic collection can continue.
- Standalone and Live Viewers stop SVG materialization above the safety budget (1,500 nodes, 4,000 edges, or an estimated 5,000 SVG elements) instead of exhausting browser memory. The canonical `graph.json` evidence artifact remains complete.
- Viewer layout/fit no longer spreads arbitrarily large arrays into `Math.min` / `Math.max`, and edge redraw during node dragging is animation-frame throttled.
- The Live server tails only newly appended `events.jsonl` bytes from a byte offset and incrementally updates an in-memory `GraphAccumulator`. `/graph.json` polling no longer replays the full event history; an incomplete trailing JSONL line is buffered until its newline arrives.
- Event-count or aggregate-count-only changes refresh Live stats/edge labels without a full topology redraw. After the Viewer budget is exceeded, live `/graph.json` switches to a counts-only compact payload while collection and the final canonical validation/full `graph.json` continue unchanged.

This is a polling + incremental-ingestion safety patch, not an SSE, SQLite, Rust, or Canvas architecture migration.

## Layered artifacts

A provider-integrated run can produce:

```text
.execweave/runs/<run-id>/
├── events.jsonl
├── graph.json
├── viewer.html
├── semantic.jsonl
├── events.semantic.jsonl
├── graph.semantic.json
├── viewer.semantic.html
├── events.correlated.jsonl
├── graph.correlated.json
└── viewer.correlated.html
```

Raw evidence is never rewritten by the derived correlation layer.

## Interactive Viewer

The standalone Viewer is local and self-contained. Current baseline includes pan/zoom, draggable nodes, node/edge inspection, node-type/relation/causal filters, **observed only**, search, evidence-sequence replay, progressive cluster expansion, focused neighborhoods, Saved Views, explicit edge semantics, and Correlation Summary.

## Graph operations

```bash
execweave graph-summary run.graph.json
execweave graph-filter run.graph.json --output causal.graph.json --causal-only
execweave graph-focus run.graph.json NODE_ID --hops 2 --output focused.graph.json
execweave path run.graph.json SOURCE TARGET --causal-only
execweave graph-condense run.graph.json --output compact.graph.json --threshold 8 --keep-expansion
```

## Security analysis

```bash
execweave analyze run.graph.json --output analysis.json
```

Security findings remain explicit about evidence limits. A possible sensitive-file → network path does not imply byte-level exfiltration:

```json
{
  "data_flow_proven": false,
  "exfiltration_proven": false
}
```

## Current status

ExecWeave `main` is currently **v0.6.3** and under active development.

The baseline includes runtime collection, graph materialization/querying, standalone/live Viewer, Claude/Codex/Gemini/Cursor/OpenCode semantic integrations, conservative Tool → Process correlation, OpenRouter/LiteLLM gateway metadata, Ollama/llama.cpp/vLLM/LM Studio runtime metadata, exact Gateway ↔ Model Runtime request identity, published PyPI wheel/sdist packaging, reproducible overhead benchmarking, cross-platform command-launcher compatibility, large-graph browser safety guards, incremental Live JSONL tail/cache, and cross-platform CI on Python 3.10/3.12.

## Privacy

ExecWeave is local-first. Runtime events, semantic sidecars, graphs, reports, and Viewers remain local by default. File contents and raw read/write byte buffers are not intentionally captured. Native adapters also avoid prompts/transcripts/tool output by default, but commands, paths, endpoint metadata, identifiers, and model metadata can still be sensitive.

Review artifacts before sharing them.

## Documentation

- [`Phase 1 — Runtime Collection`](docs/phase-1-runtime-collection.md)
- [`Phase 2 — Execution Graph`](docs/phase-2-execution-graph.md)
- [`Live Graph`](docs/live-graph.md)
- [`Semantic Telemetry`](docs/semantic-telemetry.md)
- [`Claude Code Hooks`](docs/claude-hooks.md)
- [`OpenAI Codex Hooks`](docs/codex-hooks.md)
- [`Gemini CLI Hooks`](docs/gemini-hooks.md)
- [`Cursor Hooks`](docs/cursor-hooks.md)
- [`OpenCode Plugin`](docs/opencode-plugin.md)
- [`Inference Gateway / OpenRouter / LiteLLM`](docs/inference-gateway.md)
- [`Model Runtime / Ollama / llama.cpp / vLLM / LM Studio`](docs/model-runtime.md)
- [`Performance Benchmarks`](docs/benchmarks/README.md)
- [`Security Analysis`](docs/security-analysis.md)

## Contributing

Contributions are welcome, especially around native OS collectors, additional Agent/IDE adapters, inference gateways, model runtimes, entity/correlation methods, privacy/redaction, graph UX, and performance evaluation.

## License

See [`LICENSE`](LICENSE).