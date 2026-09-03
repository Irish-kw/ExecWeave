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

The live runtime collector intentionally uses the cross-platform `portable` backend. In v0.6.4, every live run can also ingest a second append-only stream of specialized evidence through a run-specific sidecar.

ExecWeave exports the sidecar path to the launched command as:

```text
EXECWEAVE_SEMANTIC_SIDECAR
```

Specialized evidence can arrive automatically through several attribution-safe paths:

- configured Claude Code, OpenAI Codex, Antigravity, and Cursor hooks;
- the installed OpenCode plugin;
- loopback model-catalog probes when ExecWeave launches supported local Ollama, llama.cpp, or vLLM servers;
- a success-gated post-launch LM Studio probe for `lms server start --port <port>` when that compatible endpoint did not already exist before launch;
- the ExecWeave LiteLLM custom callback, after it has been configured once and the proxy is launched inside the current `execweave live` environment.

This does **not** mean `live` silently edits provider, gateway, or runtime settings. Hook/plugin/callback integrations must be configured once where required. Automatic model-runtime probing is restricted to recognized local launch commands and loopback endpoints. OpenRouter routing metadata remains non-automatic because remote HTTPS/network observation does not reveal authoritative provider routing details.

The Linux `strace` backend currently parses trace files after the command exits. It provides stronger syscall-backed attribution, but it is not a live event source in the current implementation. ExecWeave does not label post-processed evidence as live telemetry.

For stronger Linux post-run attribution use:

```bash
execweave record --backend strace --open -- claude
```

## v0.6.4 data flow

```text
specialized producers ─┐
  Agent hooks/plugin   │
  model-runtime probe  ├─→ semantic.jsonl ────────────────┐
  LiteLLM callback     │                                  │
                      ─┘                                  │
                                                         ↓
command ─→ portable ─→ events.jsonl ───────→ incremental live normalizer
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
2. completes any attribution-safe post-command specialized observation prepared for the launched command;
3. if specialized evidence exists, performs the canonical runtime + specialized merge into `events.semantic.jsonl`;
4. rebuilds the final graph from that canonical stream rather than trusting provisional live state;
5. writes `graph.json` and standalone `viewer.html`;
6. marks the live graph finished and briefly serves the final viewer before shutting down the local server.

If no specialized events arrive, final materialization remains runtime-only.

## Automatically visible specialized integrations

| Integration | Automatic delivery into v0.6.4 Live Viewer |
| --- | --- |
| Claude Code | **Yes**, after ExecWeave hooks are configured |
| OpenAI Codex | **Yes**, after ExecWeave hooks are configured |
| Antigravity | **Yes**, after ExecWeave hooks are configured |
| Cursor | **Yes**, after ExecWeave hooks are configured |
| OpenCode | **Yes**, after the ExecWeave plugin is installed |
| Ollama | **Yes**, for recognized local `ollama serve` launches |
| llama.cpp | **Yes**, for recognized local `llama-server` launches |
| vLLM | **Yes**, for recognized local vLLM server launches |
| LM Studio | **Yes**, after successful `lms server start --port <port>` when the endpoint was absent before launch |
| LiteLLM Proxy | **Yes**, after the ExecWeave callback is configured and the proxy inherits the live sidecar |
| OpenRouter | **No** automatic routing metadata; local client OS/network activity can still be observed |

These integrations share the same per-run specialized sidecar contract but preserve their evidence layers and semantics. A model catalog does not prove an Agent caused a request; a gateway response does not prove which OS process caused it; missing identity is never invented.

## Terminal Top

`top` does not render over the Agent terminal. The original terminal stays interactive for the Agent, while the dashboard attaches to the same localhost live session in a separate terminal window:

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

`events.jsonl` remains runtime-only. `semantic.jsonl` is the raw specialized sidecar and can contain Agent/IDE, model-runtime, or inference-gateway evidence. The final `graph.json` is built from `events.semantic.jsonl` when specialized evidence exists, otherwise directly from `events.jsonl`.

Choose another directory with:

```bash
execweave live --output-dir my-live-run --open -- claude
```

Existing non-empty artifacts are rejected rather than overwritten.

## Provisional live normalization

During a live run, both JSONL streams may be incomplete because the session has not finished yet.

The live normalizer therefore works incrementally and conservatively. Runtime process identity observed so far can be used to resolve specialized process references, but missing identity is never guessed. Specialized events that cannot yet be normalized do not become stronger evidence merely because they were seen live.

Sidecar truncation causes the provisional materialization to reset and replay from the current files. Incomplete trailing JSONL records are buffered instead of being treated as complete events. The final graph is still rebuilt from the canonical merge after runtime validation succeeds.

## Automatic model-runtime probe boundary

Automatic model-runtime observation is deliberately narrow. ExecWeave probes only recognized local server launch commands and local/loopback endpoints. Probe failures are fail-open and never alter the launched command outcome.

For Ollama, llama.cpp, and vLLM, the local model state/catalog can be sampled while the launched server runs. LM Studio is different because `lms server start` is a short-lived launcher for a persistent server: ExecWeave prepares the observation before launch, refuses to claim an already-existing compatible endpoint, and materializes the post-launch catalog only after a successful launcher exit.

Catalog relations keep runtime-specific semantics. For example, LM Studio catalog visibility is `ADVERTISES_MODEL`, not proof that weights were resident in memory.

## LiteLLM callback boundary

LiteLLM Proxy can load `execweave.litellm_callback.execweave_litellm_callback` once through its custom-callback configuration. When the proxy runs inside `execweave live`, it inherits `EXECWEAVE_SEMANTIC_SIDECAR` and writes only whitelisted routing/usage metadata into that run.

The callback does not persist messages, response content, model parameters, arbitrary metadata, API-key metadata, or provider `api_base`. Provider identity is not inferred from model strings or URLs. Without the run-specific sidecar environment variable, the callback is a no-op.

Print the LiteLLM configuration fragment with:

```bash
execweave-litellm-callback --print-config
```

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
- canonical final runtime + specialized rebuild;
- automatic shared-sidecar delivery for Claude, Codex, Antigravity, Cursor, and OpenCode;
- automatic local model-runtime probes for Ollama, llama.cpp, vLLM, and attribution-safe LM Studio launch handling;
- LiteLLM callback privacy, fail-open behavior, and final live-graph materialization;
- detached Top behavior without launching a second Agent;
- localhost-only Top attach URLs;
- clean-wheel installation of the LiteLLM callback setup command.
