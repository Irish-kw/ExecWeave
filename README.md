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

ExecWeave is a source-available, local-first observability project that turns AI-agent activity into an interactive execution graph while keeping observed evidence, provider content, and derived inference explicitly separated. Starting with v0.6.8, the project is licensed for noncommercial use under PolyForm Noncommercial 1.0.0.

> **Event is ground truth. The graph is a materialized view.**

<p align="center">
  <img src="docs/assets/codex.gif" alt="ExecWeave animated live demo" width="100%">
</p>

## Install

Install the latest published wheel/sdist from PyPI:

```bash
python -m pip install -U execweave
```

The package version on `main` is currently **v0.6.8**. The published release may lag main; test the exact mainline build with:

```bash
python -m pip install --upgrade --force-reinstall "execweave @ git+https://github.com/Irish-kw/ExecWeave.git@main"
```

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

## v0.6.8: full-fidelity observability with explicit evidence boundaries

v0.6.8 extends provider/runtime observability beyond compact metadata. When a supported integration point explicitly supplies content, ExecWeave can preserve the **complete supplied value** in a local SHA-256 content-addressed store while keeping only a reference in the semantic event stream.

```text
<run-root>/content/sha256/<sha256>.<json|txt|bin>
```

Depending on the adapter and upstream hook/API surface, preserved content can include prompts/messages, model request/response objects, tool inputs/results, assistant responses, reasoning/thinking text when explicitly exposed, shell/MCP output, and file content supplied by provider hooks.

`complete_from_source: true` means ExecWeave stored the complete value delivered by that integration point. It does **not** mean ExecWeave observed hidden model state, provider-side stages that were never exposed, an unseen final wire request, or bytes it did not intercept.

Full fidelity also changes the privacy boundary: application-level secrets embedded inside content are preserved. Known transport credentials are filtered from selected provider-metadata projections where the adapter defines that behavior, but ExecWeave is **not** a general secret scanner or content redactor.

### Supported semantic / inference surfaces

| Integration | OS-runtime observation when launched under ExecWeave | Specialized evidence |
| --- | --- | --- |
| Claude Code | Yes | native hooks + full-fidelity supplied hook content |
| OpenAI Codex | Yes | lifecycle hooks + full-fidelity supplied hook content |
| Google Antigravity / Antigravity CLI | Yes | passive native hooks for invocation/tool evidence + full-fidelity values explicitly supplied to those hooks |
| Cursor | Yes | native hooks + full-fidelity supplied hook content |
| OpenCode | Yes | project plugin + full-fidelity supplied plugin content |
| Ollama | Yes | `execweave-model-runtime event/exchange/probe --runtime ollama` |
| llama.cpp | Yes | `execweave-model-runtime event/exchange/probe --runtime llamacpp` |
| vLLM | Yes | `execweave-model-runtime event/exchange/probe --runtime vllm` |
| LM Studio | Only when the local process is launched under ExecWeave | `execweave-model-runtime event/exchange/probe --runtime lmstudio` |
| LiteLLM Proxy | Yes when the configured proxy is launched under ExecWeave | metadata-oriented gateway callback/event integration |
| OpenRouter | Observe the local client, not the remote service process | `execweave-inference-gateway event/exchange/generation --gateway openrouter` |

OpenRouter `exchange` is caller-supplied request+response evidence, not transparent wire interception. LiteLLM Proxy remains a narrower metadata-oriented integration in the current baseline.

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

Provider-integrated recorders keep raw runtime, semantic, and correlated artifacts separate. Stable provider identifiers such as Cursor `tool_use_id` or OpenCode `sessionID + callID` prove logical provider identity; they are not OS PIDs. Legacy Gemini CLI hook entry points remain packaged for existing installations, but Gemini CLI is no longer advertised as a current integration; new Google CLI usage should use Antigravity (`agy`).

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

v0.6.3 added bounded filesystem/viewer protections, incremental Live JSONL tailing, and large-graph safety guards. v0.6.4 added detached Top and unified provisional live sidecars for configured provider integrations. These remain in v0.6.8; the project has **not** migrated Live to SSE, artifact storage to SQLite, the renderer to Canvas/WebGL, or collectors to Rust solely for this release.

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

ExecWeave is local-first: captures, content blobs, graphs, reports, and viewers remain local by default. The **OS runtime collector** does not intentionally capture file contents or raw read/write byte buffers. That boundary must not be confused with the v0.6.8 **provider full-fidelity content store**: supported hooks/APIs can explicitly supply prompts, tool arguments/results, model responses, reasoning/thinking text, shell output, file content, or other sensitive values, and ExecWeave can preserve those values completely.

Do not assume content has been secret-redacted. Commands, paths, endpoint metadata, identifiers, model metadata, prompts, tool values, and content blobs can all be sensitive. Review the entire run directory before sharing it.

## Current status

ExecWeave `main` is currently **v0.6.8** and under active release hardening. The latest published package/release can lag main until a GitHub Release is explicitly published; the publish workflow verifies that the release tag exactly matches the package version before PyPI upload.

v0.6.8 combines cross-platform runtime collection, materialized execution graphs, standalone/live viewing, conservative provider↔runtime correlation, full-fidelity content-addressed provider evidence, evidence grades, bounded rule packs, an explicit runtime threat/fidelity contract, and honest local run-integrity sealing. Observed evidence and inference remain separate by design.

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

Contributions are welcome, especially around native OS collectors, Agent/IDE adapters, inference gateways, model runtimes, evidence/correlation methods, privacy/redaction, graph UX, and performance evaluation.

## License

ExecWeave v0.6.8 and later are licensed under the **PolyForm Noncommercial License 1.0.0**. Noncommercial use, modification, and redistribution are permitted under those terms. Commercial use requires a separate written commercial license from the licensor. Earlier versions already released under MIT remain under the terms that accompanied those versions. See [`LICENSE`](LICENSE).
