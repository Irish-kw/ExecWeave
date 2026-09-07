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

ExecWeave is a local-first observability project for AI agents and AI-assisted development tools. It combines provider-level semantics with operating-system runtime evidence and presents them as one interactive execution graph.

> **Events are evidence. The graph is a materialized view.**

<p align="center">
  <img src="docs/assets/codex.gif" alt="ExecWeave live dashboard demo" width="100%">
</p>

## Why ExecWeave

An agent can say it used a tool, edited a file, or contacted a service. That is useful semantic evidence, but it is not the same as observing what happened on the machine. ExecWeave keeps those layers separate and lets you inspect them together.

- **One dashboard for live and finished runs.** The live page, completed run, and standalone `viewer.html` use the same graph and conversation model.
- **Provider-aware semantics.** Hooks, rollout transcripts, plugins, and runtime APIs are used when a provider exposes them.
- **OS-runtime evidence.** Processes, files, and network endpoints can be observed independently of provider semantics.
- **Evidence-aware attribution.** Direct observations, exact identities, conservative inference, and causal claims are not flattened into one label.
- **Local-first storage.** Run artifacts stay on the machine unless you choose to copy or share them.
- **Works beyond one agent.** You can wrap ordinary local commands even when no specialized provider adapter exists.

## Install

Install from PyPI:

```bash
python -m pip install -U execweave
```

For development:

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

## Quick start

Wrap any local command with `execweave live`:

```bash
execweave live --open -- claude
execweave live --open -- codex
execweave live --open -- antigravity
execweave live --open -- cursor
execweave live --open -- opencode
execweave live --open -- python my_agent.py
```

Use `record` when you mainly want finalized artifacts:

```bash
execweave record --open -- python my_agent.py
```

Use `top` when you want a detached overview while keeping the launched program interactive in the current terminal:

```bash
execweave top -- codex
```

### Provider integration approval

Some agents and IDEs ask for permission before enabling a local hook or plugin. Approve the ExecWeave integration if you want provider-level prompt, response, tool, model, and conversation evidence. If you do not approve it, OS-runtime observation can still work, but semantic coverage may be reduced.

Google Antigravity currently uses the `agy` CLI command. ExecWeave also accepts `antigravity` as a friendly alias.

On Windows, bare `cursor` follows the Cursor installation referenced by the user's PATH. Explicit launcher paths are respected.

## Ollama

ExecWeave supports two common local Ollama workflows.

### Managed server capture

Start Ollama through ExecWeave:

```bash
execweave live --open -- ollama serve
```

Then use Ollama normally from another terminal:

```bash
ollama run deepseek-r1:1.5b
```

SDK calls, OpenAI-compatible local requests, and `curl` requests that reach the managed local endpoint can be associated with the same ExecWeave run. The second terminal does not need another ExecWeave wrapper.

Managed relay mode is intentionally limited to local loopback endpoints. ExecWeave does not rewrite wildcard or externally exposed Ollama listeners.

### Direct client capture

If an Ollama server is already running, you can wrap the client directly:

```bash
execweave live --open -- ollama run deepseek-r1:1.5b
```

This mode does not start an Ollama server. A reachable upstream server is still required.

## Dashboard

The dashboard is designed to keep large, multi-agent runs inspectable without changing the underlying evidence.

- **Execution graph:** agents, processes, files, network endpoints, tools, model/runtime entities, and supported relations.
- **Conversation rounds:** recent and historical rounds remain associated with the correct agent instead of being overwritten by later messages.
- **Node details:** inspect process identity, file history, network endpoints, tools, and provider conversation content.
- **Stable live updates:** the dashboard updates in place instead of replacing the whole document when a run changes state.
- **Large-run folding:** high-cardinality node types can collapse older members while keeping them inspectable.
- **Selection-focused layout:** selecting an agent or runtime object de-emphasizes unrelated graph traffic.

You can tune large-run rendering with:

```text
--fold-budget N
--viewer-max-nodes N
--viewer-max-edges N
--viewer-max-dom-elements N
```

## Supported integrations

| Integration | OS-runtime observation | Specialized evidence |
| --- | --- | --- |
| Claude Code | Yes when launched under ExecWeave | native hooks and provider-supplied conversation/tool content |
| OpenAI Codex | Yes | lifecycle hooks, validated rollout transcripts, agent/subagent routing where exposed |
| Google Antigravity | Yes | passive hooks and conversation/subagent routing where exposed |
| Cursor | Yes | native hooks and task/subagent routing where exposed |
| OpenCode | Yes | project plugin, session/task routing, supplied plugin content |
| Ollama | Yes | managed local relay and model-runtime evidence |
| llama.cpp | Yes | model-runtime event/exchange/probe integration |
| vLLM | Yes | model-runtime event/exchange/probe integration |
| LM Studio | When the local process is observed | model-runtime catalog/runtime evidence |
| LiteLLM Proxy | When the local proxy is observed | gateway metadata and event integration |
| OpenRouter | Local client only; the remote service process is not observable | caller-supplied gateway event/exchange evidence |

Provider identifiers such as a tool-call ID, session ID, rollout thread ID, or subagent route are logical identities. They are not automatically OS process IDs. ExecWeave links layers only when the available evidence supports the link.

## Evidence model

ExecWeave separates four broad layers:

```text
Agent / IDE semantics and supplied content
                ↓
Inference gateway / routing evidence
                ↓
Model runtime / inference-server evidence
                ↓
OS runtime evidence: process / file / network
```

A relationship is marked causal only when the underlying telemetry supports a causal claim. Conservative bridges remain explicit derived evidence, for example:

```text
inferred: true
causal: false
```

An exact shared request identity can prove identity without proving causality:

```text
identity_exact: true
inferred: false
causal: false
```

If attribution is ambiguous, ExecWeave should leave the edge absent rather than invent a stronger relationship.

### Full-fidelity supplied content

Supported integrations can preserve complete values explicitly supplied by provider hooks, plugins, or APIs in a local SHA-256 content-addressed store:

```text
<run-root>/content/sha256/<sha256>.<json|txt|bin>
```

Depending on the integration, this can include prompts, messages, request/response objects, tool inputs/results, assistant responses, exposed reasoning text, shell output, and supplied file content.

`complete_from_source: true` means ExecWeave stored the complete value delivered by that integration point. It does **not** mean ExecWeave observed hidden model state or provider-side data that was never exposed.

## Common commands

### Agent and IDE recorders

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
execweave-model-runtime event --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime exchange --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime probe --runtime ollama --sidecar model-runtime.jsonl
```

`event` records one-sided event evidence. `exchange` records a caller-supplied request/response pair; it does not claim transparent wire interception.

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

## Run artifacts

A provider-integrated run can contain:

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
└── integrity.json
```

Raw observations remain separate from derived semantic and correlation outputs.

## Limits and privacy

- The portable collector runs on Linux, macOS, and Windows. Portable filesystem observation is session-correlated rather than always process-causal, and polling can miss sufficiently short-lived activity.
- Linux also provides a `strace` reference backend with stronger syscall-attributed evidence for supported executions.
- Provider semantics depend on what each integration actually exposes. Missing prompts, hidden reasoning, remote provider internals, and unexposed routing cannot be reconstructed reliably.
- Full-fidelity provider content may contain credentials, secrets, source code, prompts, tool values, model responses, shell output, and file contents.
- Conversation isolation is an attribution rule, not a redaction boundary. Explicitly routed content may legitimately appear at more than one participant.
- A local integrity manifest detects changes relative to the manifest; it is not an adversary-resistant trusted logging system if both evidence and manifest remain inside the same writable trust boundary.
- Review the complete run directory before sharing it.

## Development

Run the test suite:

```bash
python -m pytest
```

Run linting:

```bash
python -m ruff check .
```

Issues and pull requests are welcome. Keep new integrations evidence-aware: document what is directly observed, what is supplied by the provider, and what is derived.

## License

ExecWeave is distributed under the **PolyForm Noncommercial License 1.0.0**. See [LICENSE](LICENSE) for the full terms.
