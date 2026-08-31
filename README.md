# ExecWeave

<!-- i18n-nav:start -->
<p align="center">
  <strong>English</strong> |
  <a href="README.zh-TW.md">繁體中文</a> |
  <a href="README.zh-CN.md">简体中文</a> |
  <a href="README.ja.md">日本語</a> |
  <a href="README.ko.md">한국어</a> |
  <a href="README.fr.md">Français</a> |
  <a href="README.de.md">Deutsch</a> |
  <a href="README.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

<p align="center">
  <a href="https://pypi.org/project/execweave/"><img src="https://img.shields.io/pypi/v/execweave" alt="PyPI"></a>
  <a href="https://github.com/Irish-kw/ExecWeave/actions/workflows/ci.yml"><img src="https://github.com/Irish-kw/ExecWeave/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue" alt="Python 3.10+">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-PolyForm%20Noncommercial-blue" alt="License"></a>
</p>

**See what AI agents actually do on your machine.**

ExecWeave is a source-available, local-first observability project that turns AI-agent activity into an interactive execution graph while keeping observed evidence, provider-supplied content, and derived inference explicitly separated.

> **Event is ground truth. The graph is a materialized view.**

<p align="center">
  <img src="docs/assets/codex.gif" alt="ExecWeave animated live demo" width="100%">
</p>

This README documents **v0.8.3**.

## Why ExecWeave

- **One local inspection surface.** Live runs, completed runs, and standalone `viewer.html` use the same dashboard renderer for graph, logs, conversations, and node details.
- **Evidence-aware by design.** Direct observations stay distinguishable from identity links, conservative inference, and causal claims.
- **Provider-aware without inventing hidden behavior.** ExecWeave uses the strongest routing and identity evidence a provider actually exposes; missing evidence stays missing.
- **Useful beyond one Agent.** OS-runtime telemetry can wrap any local command, while provider adapters add richer semantics when supported.

## Install

Install the latest published package from PyPI:

```bash
python -m pip install -U execweave
```

For development:

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

## 60-second quick start

Live OS-runtime telemetry works with **any local command**. These Agent/runtime names are examples, not a whitelist.

```bash
execweave live --open -- claude
execweave live --open -- codex
execweave live --open -- antigravity
execweave live --open -- cursor
execweave live --open -- opencode
execweave live --open -- ollama serve
execweave live --open -- python my_agent.py
```

> **Approve the hook when prompted.** On the first provider-integrated run, the Agent/IDE may ask whether ExecWeave may enable its local hook integration. Choose **Allow / Yes**. Without approval, OS-runtime telemetry can still work, but provider-level tool, model, conversation, and supplied-content visibility may be reduced or unavailable.

Google Antigravity currently uses the `agy` CLI command; ExecWeave also accepts `antigravity` as a friendly alias and resolves it to `agy`. For Cursor, `execweave live --open -- cursor` first tries a normal PATH launcher, then falls back to the standard desktop application binary on macOS and Windows.

Build finalized run artifacts with:

```bash
execweave record --open -- python my_agent.py
```

For a detached overview while keeping the Agent interactive in the launch terminal:

```bash
execweave top -- codex
```

## Dashboard

ExecWeave keeps Live, finished, and standalone viewing on the same dashboard model instead of switching renderers at the end of a run.

- **Execution graph:** agents, processes, files, network endpoints, tools, model/runtime entities, and supported semantic relations.
- **Conversation rounds:** the newest round is immediately readable; older rounds remain individually reachable instead of being overwritten by newer replies.
- **Node details:** process nodes show command/PID context, file nodes show path/history context, and network nodes show endpoint/process context.
- **Large-run readability:** per-type folding keeps recent members visible while older members collapse into an inspectable aggregate. Set the threshold with `--fold-budget N`.
- **Selection clarity:** multi-agent layout keeps a stable root/child hierarchy and de-emphasizes unrelated edges when an agent is selected.

### v0.8.3 dashboard changes

v0.8.3 focuses on making dense and multi-round runs readable without changing raw evidence:

- conversation panels are round-based instead of pairing one old prompt with one new reply;
- explicit reader open/closed state survives the 800 ms Live refresh;
- subagent responses remain attributed to the agent that produced them;
- process, file, and network selections no longer open empty detail panels;
- high-cardinality node types fold under a configurable budget rather than overwhelming the graph;
- lifecycle return edges no longer distort root/child rank, and shared tool/model traffic uses clearer routed geometry.

These are presentation-layer changes. Raw graph evidence is unchanged, and Live, finished, and `viewer.html` continue to share one renderer.

## Supported integrations

| Integration | OS-runtime observation when launched under ExecWeave | Specialized evidence |
| --- | --- | --- |
| Claude Code | Yes | native hooks + full-fidelity supplied hook content + exact subagent results when exposed |
| OpenAI Codex | Yes | lifecycle hooks + validated rollout transcripts + agent-local task/message/final-response routing |
| Google Antigravity / Antigravity CLI | Yes | passive native hooks + validated conversation/subagent routing where exposed |
| Cursor | Yes | native hooks + exact subagent task/summary routing when exposed |
| OpenCode | Yes | project plugin + session/task routing + full-fidelity supplied plugin content |
| Ollama | Yes | `execweave-model-runtime event/exchange/probe --runtime ollama` |
| llama.cpp | Yes | `execweave-model-runtime event/exchange/probe --runtime llamacpp` |
| vLLM | Yes | `execweave-model-runtime event/exchange/probe --runtime vllm` |
| LM Studio | Only when the local process is launched under ExecWeave | `execweave-model-runtime event/exchange/probe --runtime lmstudio` |
| LiteLLM Proxy | Yes when the configured proxy is launched under ExecWeave | metadata-oriented gateway callback/event integration |
| OpenRouter | Observe the local client, not the remote service process | `execweave-inference-gateway event/exchange/generation --gateway openrouter` |

Stable provider identifiers such as Cursor `tool_use_id`, Codex rollout thread identity, or OpenCode `sessionID + callID` prove logical provider identity; they are not OS PIDs. Cross-agent content is shown only when the provider exposes an explicit route, delegation, or result. Gateways or local runtimes that expose only root request/response traffic remain root-only; ExecWeave does not fabricate subagents or hidden routing.

OpenRouter `exchange` is caller-supplied request+response evidence, not transparent wire interception. LiteLLM Proxy remains a narrower metadata-oriented integration in the current baseline. Legacy Gemini CLI entry points remain packaged for compatibility, but new Google CLI usage should use Antigravity (`agy`).

## Evidence model

ExecWeave keeps evidence layers separate instead of flattening them into one trace:

```text
Agent / IDE semantic + supplied content evidence
          ↓
Inference gateway / routing evidence
          ↓
Model runtime / inference-server evidence
          ↓
OS runtime evidence: process / file / network
```

A relationship is causal only when the underlying telemetry supports that claim. Conservative Tool → Process bridges stay marked as derived evidence:

```text
inferred: true
causal: false
```

Exact shared request identity across Gateway and Model Runtime is identity evidence, not causal evidence:

```text
identity_exact: true
inferred: false
causal: false
```

Ambiguity produces no edge.

### Full-fidelity supplied content

Since **v0.6.9**, supported integration points can preserve the complete value explicitly supplied by the provider/hook/API in a local SHA-256 content-addressed store while the semantic event stream keeps a reference:

```text
<run-root>/content/sha256/<sha256>.<json|txt|bin>
```

Depending on the integration, preserved values can include prompts/messages, request/response objects, tool inputs/results, assistant responses, explicitly exposed reasoning/thinking text, shell/MCP output, and file content supplied by provider hooks.

`complete_from_source: true` means ExecWeave stored the complete value delivered by that integration point. It does **not** mean ExecWeave observed hidden model state, provider-side stages that were never exposed, an unseen final wire request, or bytes it did not intercept.

## Common commands

### Agent / IDE recorders

```bash
execweave-claude-record --open -- claude
execweave-codex-record --open -- codex
execweave-antigravity-record --open -- antigravity
execweave-cursor-record --open -- cursor
execweave-opencode-plugin --install
execweave-opencode-record --open -- opencode
```

### Gateways and model runtimes

```bash
execweave-inference-gateway event --gateway openrouter --sidecar gateway.jsonl
execweave-inference-gateway exchange --gateway openrouter --sidecar gateway.jsonl
execweave-inference-gateway event --gateway litellm --sidecar gateway.jsonl

execweave-model-runtime event --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime exchange --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime probe --runtime ollama --sidecar model-runtime.jsonl
```

`event` is response-only evidence. `exchange` stores a caller-supplied request+response object and does not assert transparent interception. Runtime catalog relations keep their source-specific meanings: `LOADED_MODEL`, `SERVES_MODEL`, and `ADVERTISES_MODEL` are not interchangeable. LM Studio catalog visibility remains `ADVERTISES_MODEL`, not proof that weights were resident in memory.

### Runtime, graph, security, and integrity

```bash
execweave doctor
execweave run --backend portable -- your-command
execweave run --backend strace -- your-command
execweave graph-summary run.graph.json
execweave graph-filter run.graph.json --causal-only --output causal.graph.json
execweave graph-focus run.graph.json NODE_ID --hops 2 --output focused.graph.json
execweave path run.graph.json SOURCE TARGET --causal-only
execweave analyze run.graph.json --output analysis.json
execweave-rule-pack graph.json --rule-pack local-policy.json --output report.json
execweave-integrity seal .execweave/runs/<run-id>
execweave-integrity verify .execweave/runs/<run-id>
```

Security findings carry an evidence grade independently from severity. Current grades are `A`, `B`, `C`, `D`, and `U`; they are evidence-strength categories, not probabilities or trust scores. Rule packs are bounded, explainable single-edge observation policies and cannot execute third-party code or prove byte-level exfiltration.

## Run artifacts

A provider-integrated run may contain:

```text
.execweave/runs/<run-id>/
├── events.jsonl
├── graph.json
├── viewer.html
├── semantic.jsonl
├── content/sha256/...
├── conversations.md
├── conversations.json
├── events.semantic.jsonl
├── graph.semantic.json
├── viewer.semantic.html
├── events.correlated.jsonl
├── graph.correlated.json
├── viewer.correlated.html
└── integrity.json            # after an explicit seal
```

Derived correlation never rewrites raw runtime or provider sidecar evidence.

## Limits and privacy

- The portable collector runs on Linux, macOS, and Windows. Portable filesystem observation is session-correlated rather than process-causal, and polling can miss sufficiently short-lived activity.
- Linux also has a syscall-backed `strace` reference backend with stronger process-attributed syscall evidence for supported executions.
- Native Linux eBPF, Windows ETW, and macOS Endpoint Security collectors remain planned work, not current claims.
- Full-fidelity provider content can preserve secrets embedded in prompts, tool values, model responses, shell output, or supplied files. ExecWeave is **not** a general secret scanner or content redactor.
- Conversation isolation is an attribution/display rule, not a redaction boundary. If a provider explicitly routes content between agents, that content can legitimately appear at participating endpoints.
- Commands, paths, endpoints, identifiers, model metadata, prompts, tool values, and content blobs can all be sensitive. Review the entire run directory before sharing it.
- A local integrity seal detects file changes relative to its manifest, but it is not adversary-resistant when both evidence and manifest remain inside the same writable trust boundary.

## Performance

ExecWeave includes bounded filesystem/viewer protections, incremental Live JSONL tailing, large-graph safety guards, detached Top, and provisional live sidecars for configured provider integrations.

The reproducible incremental `GraphAccumulator` reference result reaches **164,273 ev/s** at 1M synthetic events on the documented GitHub Actions workload. This is a graph-accumulation benchmark, not end-to-end collector/browser throughput.

Run the package-level benchmarks on a representative host/workload:

```bash
execweave-overhead --iterations 7 --strace auto --output-json benchmark-results.json
execweave-scalability
```

Reference data and methodology live in [`docs/benchmarks/`](docs/benchmarks/).

## Documentation

| Area | Documents |
| --- | --- |
| Runtime and graph | [`Phase 1 — Runtime Collection`](docs/phase-1-runtime-collection.md) · [`Phase 2 — Execution Graph`](docs/phase-2-execution-graph.md) · [`Live Graph`](docs/live-graph.md) · [`Semantic Telemetry`](docs/semantic-telemetry.md) |
| Agent / IDE integrations | [`Claude Code`](docs/claude-code-hooks.md) · [`OpenAI Codex`](docs/codex-hooks.md) · [`Google Antigravity`](docs/antigravity-hooks.md) · [`Cursor`](docs/cursor-hooks.md) · [`OpenCode`](docs/opencode-plugin.md) |
| Gateways and runtimes | [`Inference Gateway / OpenRouter / LiteLLM`](docs/inference-gateway.md) · [`Model Runtime / Ollama / llama.cpp / vLLM / LM Studio`](docs/model-runtime.md) |
| Trust and analysis | [`Runtime Threat Model`](docs/runtime-threat-model.md) · [`Evidence Grades`](docs/evidence-grades.md) · [`Rule Packs`](docs/rule-packs.md) · [`Run Integrity`](docs/run-integrity.md) · [`Security Analysis`](docs/security-analysis.md) |
| Performance | [`Benchmarks`](docs/benchmarks/README.md) |

## Contributing

Contributions are welcome, especially around native OS collectors, Agent/IDE adapters, inference gateways, model runtimes, evidence/correlation methods, privacy/redaction, graph UX, multi-agent conversation attribution, and performance evaluation.

## License

Starting with v0.6.8, ExecWeave is licensed under the **PolyForm Noncommercial License 1.0.0**. Noncommercial use, modification, and redistribution are permitted under its terms. Commercial use requires a separate written commercial license from the licensor. See [`LICENSE`](LICENSE).
