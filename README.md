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

**See what AI agents actually do on your machine.**

ExecWeave is a source-available, local-first observability project that turns AI-agent activity into an interactive execution graph while keeping observed evidence, provider content, and derived inference explicitly separated.

> **Event is ground truth. The graph is a materialized view.**

<p align="center">
  <img src="docs/assets/codex.gif" alt="ExecWeave animated live demo" width="100%">
</p>

## Install

Install the latest published wheel/sdist from PyPI:

```bash
python -m pip install -U execweave
```

The current release is **v0.8.3**.

For development:

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

## Quick start

Live OS-runtime telemetry works with **any local command**. Agent/runtime names are examples, not a whitelist.

```bash
execweave live --open -- claude
execweave live --open -- codex
execweave live --open -- antigravity
execweave live --open -- cursor
execweave live --open -- opencode
execweave live --open -- ollama serve
execweave live --open -- python my_agent.py
```

> **Approve the hook when prompted.** On the first provider-integrated run, the Agent/IDE may ask whether ExecWeave is allowed to enable its local hook integration. Choose **Allow / Yes**. If the hook is not approved, OS-runtime telemetry can still work, but provider-level tool, model, and supplied-content observability will be reduced or unavailable.

Google Antigravity uses the current `agy` CLI command; ExecWeave also accepts `antigravity` as a friendly alias and resolves it to `agy`. For Cursor, `execweave live --open -- cursor` first uses a normal PATH launcher when one exists, then falls back to the standard Cursor desktop application binary on macOS and Windows.

Or build the finalized artifact pipeline:

```bash
execweave record --open -- python my_agent.py
```

`execweave top -- codex` keeps the Agent interactive in the launch terminal while opening/attaching the detached Top dashboard according to the host environment.

**v0.8.3 — every round, and every node, says what it holds.** A run is rarely one question, and the panel had room for one: it paired the oldest prompt with the newest answer, so a two-round run showed the first question beside the second question's reply while the first round's own answer stayed unreachable. Rounds are the unit now — the newest is open, older ones fold to a line naming their own moment and question, and a subagent's fold carries the timestamp and wording of the root round it came from. Two subagents had also been losing their Response: the rule that stops a provider's shared preamble from being read as one agent's assignment matched any long text appearing under two agents, and a child's answer appears both in its own record and in its parent's. That rule now reaches inbound messages only, so what an agent wrote stays its own however often the run repeats it. Selecting a process, a file or a network endpoint no longer draws an empty panel: each names what it is — a command line with its pid and parent, a path with the history that touched it, an address with the process that reached it. And a type crowded past its budget keeps its newest members drawn while the older ones collapse into a single node that still names every one it holds, so a run that touches a thousand paths stays readable without losing one of them. The provider-neutral, agent-local multi-agent conversations each agent owns are the same records they always were; what changed is that a reader can reach all of them instead of one. The budget past which a type folds is `--fold-budget N` on every command that renders a dashboard, so a deployment whose agents write hundreds of files chooses its own number instead of editing the package. v0.8.3 fixes two Dashboard regressions on top of that: older conversation rounds now keep the reader's explicit open/closed state across the 800 ms live refresh, and multi-agent graphs use a stable root/child hierarchy where lifecycle return edges do not affect rank, shared tool/model connections use separated ports and bundled trunks, and selecting an agent fades unrelated edges. These are presentation-only changes: Live, finished, and `viewer.html` still share the same renderer and raw graph evidence is unchanged.

The unified dashboard brings the execution graph, logs, and conversation records into the same inspection flow. Finalized runs generate `conversations.md` and `conversations.json`, while validated provider transcripts are copied into the run-local SHA-256 content store. Claude Code, OpenAI Codex, Cursor, OpenCode, and Google Antigravity use the strongest provider-exposed multi-agent evidence available to each integration. For gateways and local runtimes that expose only root request/response traffic, ExecWeave shows only that root conversation and does not invent subagents or hidden routing.

## v0.6.9: full-fidelity observability with explicit evidence boundaries

v0.6.9 extends provider/runtime observability beyond compact metadata. When a supported integration point explicitly supplies content, ExecWeave can preserve the **complete supplied value** in a local SHA-256 content-addressed store while keeping only a reference in the semantic event stream.

```text
<run-root>/content/sha256/<sha256>.<json|txt|bin>
```

Depending on the adapter and upstream hook/API surface, preserved content can include prompts/messages, model request/response objects, tool inputs/results, assistant responses, reasoning/thinking text when explicitly exposed, shell/MCP output, and file content supplied by provider hooks.

`complete_from_source: true` means ExecWeave stored the complete value delivered by that integration point. It does **not** mean ExecWeave observed hidden model state, provider-side stages that were never exposed, an unseen final wire request, or bytes it did not intercept.

Full fidelity also changes the privacy boundary: application-level secrets embedded inside content are preserved. Known transport credentials are filtered from selected provider-metadata projections where the adapter defines that behavior, but ExecWeave is **not** a general secret scanner or content redactor.

### Supported semantic / inference surfaces

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

OpenRouter `exchange` is caller-supplied request+response evidence, not transparent wire interception. LiteLLM Proxy remains a narrower metadata-oriented integration in the current baseline. Provider-neutral conversation projection never upgrades missing provider evidence into a fabricated agent relationship.

## Evidence layers

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

A relationship is causal only when the underlying telemetry supports that claim. Tool → Process bridges remain conservative derived evidence:

```text
inferred: true
causal: false
```

Ambiguity produces no edge. Exact shared request identity across Gateway and Model Runtime remains identity evidence rather than causal evidence:

```text
identity_exact: true
inferred: false
causal: false
```

## Agent / IDE integrations

```bash
execweave-claude-hook --print-config
execweave-claude-record --open -- claude

execweave-codex-hook --print-config
execweave-codex-record --open -- codex

execweave-antigravity-hook --print-config
execweave-antigravity-record --open -- antigravity

execweave-cursor-hook --print-config
execweave-cursor-record --open -- cursor

execweave-opencode-plugin --install
execweave-opencode-record --open -- opencode
```

Provider-integrated recorders keep raw runtime, semantic, correlated, and conversation artifacts separate. Stable provider identifiers such as Cursor `tool_use_id`, Codex rollout thread identity, or OpenCode `sessionID + callID` prove logical provider identity; they are not OS PIDs. Cross-agent content is shown only when the provider exposes an explicit route, delegation, or result. Legacy Gemini CLI hook entry points remain packaged for existing installations, but Gemini CLI is no longer advertised as a current integration; new Google CLI usage should use Antigravity (`agy`).

## Inference gateways and model runtimes

Capture OpenRouter or LiteLLM gateway evidence:

```bash
execweave-inference-gateway event --gateway openrouter --sidecar gateway.jsonl
execweave-inference-gateway event --gateway litellm --sidecar gateway.jsonl
execweave-inference-gateway exchange --gateway openrouter --sidecar gateway.jsonl
```

Capture model-runtime evidence for Ollama, llama.cpp, vLLM, or LM Studio:

```bash
execweave-model-runtime event --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime exchange --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime probe --runtime ollama --sidecar model-runtime.jsonl
```

`event` is response-only evidence; `exchange` stores a caller-supplied request+response object and does not assert transparent interception. Runtime catalog relations retain their source-specific meaning: `LOADED_MODEL`, `SERVES_MODEL`, and `ADVERTISES_MODEL` are not interchangeable. LM Studio catalog visibility remains `ADVERTISES_MODEL`, not proof that weights were resident in memory.

## Security analysis, evidence grades, and bounded rule packs

Run the built-in analysis:

```bash
execweave analyze run.graph.json --output analysis.json
```

Findings expose an evidence grade independent from severity. Current grades are `A`, `B`, `C`, `D`, and `U`, from direct syscall attribution through inferred/unknown provenance. Grades are evidence-strength categories, **not probabilities or trust scores**.

Local rule packs add bounded, explainable **single-edge observation** policies without executing third-party code:

```bash
execweave-rule-pack graph.json --rule-pack local-policy.json --output report.json
```

Rule packs cannot execute code, define regex/path programs, or assert byte-level data flow/exfiltration. Rule-pack findings remain observation-only.

Security findings continue to make stronger non-claims explicit:

```json
{
  "data_flow_proven": false,
  "exfiltration_proven": false
}
```

## Run integrity

Seal a completed run and later verify that its regular-file inventory has not changed relative to the seal:

```text
execweave-integrity seal .execweave/runs/<run-id>
execweave-integrity verify .execweave/runs/<run-id>
```

The deterministic manifest records file size/SHA-256 and rejects symbolic links. It detects missing, modified, replaced, or newly added regular files after sealing.

This local seal is deliberately **not** described as adversary-resistant tamper evidence when both evidence and manifest remain inside the same writable trust boundary. The manifest records `malicious_writer_resistance: false` and `external_trust_anchor: false`; copy/protect the manifest digest outside that boundary when a stronger trust anchor is required.

## Runtime evidence and graph operations

The portable collector runs on Linux, macOS, and Windows. Linux also has a syscall-backed `strace` reference backend.

```bash
execweave doctor
execweave run --backend portable -- your-command
execweave run --backend strace -- your-command
execweave graph-summary run.graph.json
execweave graph-filter run.graph.json --causal-only --output causal.graph.json
execweave graph-focus run.graph.json NODE_ID --hops 2 --output focused.graph.json
execweave path run.graph.json SOURCE TARGET --causal-only
```

Portable filesystem observation is session-correlated rather than process-causal, and polling can miss sufficiently short-lived activity. Linux `strace` provides stronger process-attributed syscall evidence for supported executions. Future native collectors remain planned for Linux eBPF, Windows ETW, and macOS Endpoint Security.

## Performance and large-run safety

ExecWeave includes bounded filesystem/viewer protections, incremental Live JSONL tailing, large-graph safety guards, detached Top, and provisional live sidecars for configured provider integrations.

The reproducible incremental `GraphAccumulator` reference result reaches **164,273 ev/s** at 1M synthetic events on the documented GitHub Actions workload. This is a graph-accumulation benchmark, not end-to-end collector/browser throughput.

Run the package-level overhead benchmark on a representative host/workload:

```bash
execweave-overhead --iterations 7 --strace auto --output-json benchmark-results.json
execweave-scalability
```

See [`docs/benchmarks/`](docs/benchmarks/) for reference data and methodology.

## Layered artifacts

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

Derived correlation never rewrites the raw runtime or provider sidecar evidence.

## Privacy

ExecWeave is local-first: captures, content blobs, graphs, reports, and viewers remain local by default. The **OS runtime collector** does not intentionally capture file contents or raw read/write byte buffers. That boundary must not be confused with the **provider full-fidelity content store introduced in v0.6.9**: supported hooks/APIs can explicitly supply prompts, tool arguments/results, model responses, reasoning/thinking text, shell output, file content, or other sensitive values, and ExecWeave can preserve those values completely.

Conversation isolation is an attribution/display rule, not a redaction boundary. If a provider explicitly sends Agent 1 content to Agent 2, that routed evidence can legitimately appear at the participating endpoints. Do not assume content has been secret-redacted. Commands, paths, endpoint metadata, identifiers, model metadata, prompts, tool values, and content blobs can all be sensitive. Review the entire run directory before sharing it.

## Current status

v0.8.3 combines cross-platform runtime collection, materialized execution graphs, standalone/live dashboards, conservative provider↔runtime correlation, full-fidelity content-addressed provider evidence, attributable multi-agent execution traces, direct run-local conversation access, agent-local conversation isolation across provider-neutral projections, per-round agent conversation panels, and self-describing non-agent nodes with per-type folding in the standalone and live dashboards. Supported integrations preserve the strongest identity/routing evidence actually exposed by each provider and abstain when that evidence is unavailable. Observed evidence and inference remain separate by design. v0.8.3 additionally preserves reader-controlled conversation fold state across live polling and applies topology-aware multi-agent layout/routing without changing raw evidence.

## Documentation

- [`Phase 1 — Runtime Collection`](docs/phase-1-runtime-collection.md)
- [`Phase 2 — Execution Graph`](docs/phase-2-execution-graph.md)
- [`Live Graph`](docs/live-graph.md)
- [`Semantic Telemetry`](docs/semantic-telemetry.md)
- [`Claude Code Hooks`](docs/claude-code-hooks.md)
- [`OpenAI Codex Hooks`](docs/codex-hooks.md)
- [`Google Antigravity Hooks`](docs/antigravity-hooks.md)
- [`Cursor Hooks`](docs/cursor-hooks.md)
- [`OpenCode Plugin`](docs/opencode-plugin.md)
- [`Inference Gateway / OpenRouter / LiteLLM`](docs/inference-gateway.md)
- [`Model Runtime / Ollama / llama.cpp / vLLM / LM Studio`](docs/model-runtime.md)
- [`Runtime Threat Model`](docs/runtime-threat-model.md)
- [`Evidence Grades`](docs/evidence-grades.md)
- [`Rule Packs`](docs/rule-packs.md)
- [`Run Integrity`](docs/run-integrity.md)
- [`Security Analysis`](docs/security-analysis.md)
- [`Performance Benchmarks`](docs/benchmarks/README.md)

## Contributing

Contributions are welcome, especially around native OS collectors, Agent/IDE adapters, inference gateways, model runtimes, evidence/correlation methods, privacy/redaction, graph UX, multi-agent conversation attribution, and performance evaluation.

## License

Starting with v0.6.8, ExecWeave is licensed under the **PolyForm Noncommercial License 1.0.0**. Noncommercial use, modification, and redistribution are permitted under its terms. Commercial use requires a separate written commercial license from the licensor. See [`LICENSE`](LICENSE).
