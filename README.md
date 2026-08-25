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

## Quick start

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

Watch any command live:

```bash
execweave live --open -- claude
```

Or build the full artifact pipeline:

```bash
execweave record --open -- python my_agent.py
```

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

### OpenRouter

OpenRouter is modeled as an `inference_gateway`, not as a local model runtime.

```bash
execweave-inference-gateway event \
  --gateway openrouter \
  --requested-model openrouter/auto \
  --sidecar gateway.jsonl
```

ExecWeave can keep these facts distinct:

```text
requested model → resolved model → routed provider
```

Whitelisted usage can include token counts, cache/reasoning counts, cost, and generation timing metadata. Prompt and response content are not persisted.

## Model runtime integrations

### Ollama

```bash
execweave-model-runtime event --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime probe --runtime ollama --sidecar model-runtime.jsonl
```

### llama.cpp

```bash
execweave-model-runtime event --runtime llamacpp --sidecar model-runtime.jsonl
execweave-model-runtime probe --runtime llamacpp --metrics --sidecar model-runtime.jsonl
```

This layer models `model_runtime`, `inference_request`, `model`, and runtime snapshots. It records selected token/timing/load metadata without prompt or generated content. Sensitive llama.cpp local model paths are redacted.

Future OpenAI-compatible runtimes such as vLLM and LM Studio can reuse this layer.

## Runtime evidence

The portable collector runs on Linux, macOS, and Windows. Linux also has a syscall-backed `strace` reference backend.

```bash
execweave doctor
execweave run --backend portable -- your-command
execweave run --backend strace -- your-command
```

Portable filesystem watching is session-correlated rather than process-causal, and short-lived processes can be missed between polling intervals. The Linux `strace` path captures process-attributed syscall evidence after the command exits.

Future native collectors remain planned for Linux eBPF, Windows ETW, and macOS Endpoint Security.

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

The standalone Viewer is local and self-contained. Current baseline includes:

- pan / zoom / draggable nodes
- node and edge inspection
- node-type / relation / causal filters
- **observed only** filter
- search
- evidence-sequence Timeline ↔ Graph replay
- progressive cluster expansion
- 1-hop / 2-hop focused neighborhoods
- browser-local Saved Views
- explicit observed / non-causal / inferred edge styling
- Correlation Summary

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

ExecWeave is currently **v0.5.0** and under active development.

Implemented baseline includes runtime collection, graph materialization/querying, standalone/live Viewer, native Claude/Codex/Gemini/Cursor/OpenCode semantic integrations, conservative Tool → Process correlation, OpenRouter gateway metadata, Ollama/llama.cpp runtime metadata, and cross-platform CI on Python 3.10/3.12.

## Privacy

ExecWeave is local-first. Runtime events, semantic sidecars, graphs, reports, and Viewers remain local by default. File contents and raw read/write byte buffers are not intentionally captured. Native adapters also avoid prompts/transcripts/tool output by default, but commands, paths, endpoint metadata, identifiers, and model metadata can still be sensitive.

Review artifacts before sharing them.

## Documentation

- [`Phase 1 — Runtime Collection`](docs/phase-1-runtime-collection.md)
- [`Phase 2 — Execution Graph`](docs/phase-2-execution-graph.md)
- [`Live Graph`](docs/live-graph.md)
- [`Semantic Telemetry`](docs/semantic-telemetry.md)
- [`Claude Code Hooks`](docs/claude-code-hooks.md)
- [`OpenAI Codex Hooks`](docs/codex-hooks.md)
- [`Gemini CLI Hooks`](docs/gemini-hooks.md)
- [`Cursor Hooks`](docs/cursor-hooks.md)
- [`OpenCode Plugin`](docs/opencode-plugin.md)
- [`Inference Gateway / OpenRouter`](docs/inference-gateway.md)
- [`Model Runtime / Ollama / llama.cpp`](docs/model-runtime.md)
- [`Security Analysis`](docs/security-analysis.md)

## Contributing

Contributions are welcome, especially around native OS collectors, additional Agent/IDE adapters, inference gateways, OpenAI-compatible model runtimes, entity/correlation methods, privacy/redaction, graph UX, and performance evaluation.

## License

See [`LICENSE`](LICENSE).