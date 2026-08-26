# ExecWeave

[![PyPI](https://img.shields.io/pypi/v/execweave?label=PyPI)](https://pypi.org/project/execweave/)
[![Python](https://img.shields.io/pypi/pyversions/execweave?label=Python)](https://pypi.org/project/execweave/)
[![CI](https://github.com/Irish-kw/ExecWeave/actions/workflows/ci.yml/badge.svg)](https://github.com/Irish-kw/ExecWeave/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/Irish-kw/ExecWeave?style=flat&label=Stars)](https://github.com/Irish-kw/ExecWeave/stargazers)

<!-- i18n-nav:start -->
<p align="center">
  <a href="README.md">English</a> |
  <a href="README.zh-TW.md">繁體中文</a> |
  <strong>简体中文</strong> |
  <a href="README.ja.md">日本語</a> |
  <a href="README.ko.md">한국어</a> |
  <a href="README.fr.md">Français</a> |
  <a href="README.de.md">Deutsch</a> |
  <a href="README.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

**看见 AI Agent 在你的电脑上实际做了什么。**

ExecWeave 是一个开源、local-first 的 observability 项目，会把 AI Agent 的活动转成互动式 execution graph，同时明确区分 observed evidence 与 inference。

> **Event 是 ground truth；Graph 是 materialized view。**

<p align="center">
  <img src="docs/assets/execweave-viewer.png" alt="ExecWeave Live execution graph" width="100%">
</p>

## 安装

ExecWeave 已发布到 PyPI，提供标准 Python wheel/sdist。安装最新 release：

```bash
python -m pip install -U execweave
```

`main` branch 可能比当前 PyPI release 更新。若要直接测试最新 mainline build：

```bash
python -m pip install --upgrade --force-reinstall "execweave @ git+https://github.com/Irish-kw/ExecWeave.git@main"
```

开发者安装：

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

实时观察 Claude Code、OpenAI Codex 或 Gemini CLI：

```bash
# Claude Code
execweave live --open -- claude

# OpenAI Codex
execweave live --open -- codex

# Gemini CLI
execweave live --open -- gemini
```

或构建完整 artifact pipeline：

```bash
execweave record --open -- python my_agent.py
```

## 性能与空间占用

ExecWeave 内置可复现的 package-level overhead benchmark，并从实际安装的 wheel 执行。Reference plot 采用常见的 quality/cost trade-off 表达方式：

- **X 轴：**额外 peak process-tree RSS，低 → 高。
- **Y 轴：**runtime overhead，低 → 高。
- **Bubble 面积：**每次运行产生的 median artifact size。
- **理想区域：**左下角。

![ExecWeave overhead trade-off](docs/benchmarks/v0.6.0-github-actions.svg)

Reference 环境：GitHub Actions Ubuntu runner、Intel Xeon Platinum 8573C、4 logical CPUs、Python 3.12.14、`n=7`。

| Profile | Median wall time | Runtime overhead | Additional peak RSS | Median artifacts/run |
| --- | ---: | ---: | ---: | ---: |
| ExecWeave OFF | 236.221 ms | 0.0% | 0.0 MB | 0 KB |
| Portable ON | 391.580 ms | 65.768% | 27.852 MB | 741.355 KB |
| Strace ON | 1226.076 ms | 419.038% | 37.653 MB | 572.838 KB |

同一个 build 产生约 **113 KB wheel** 与 **198 KB sdist**。安装后的 ExecWeave distribution 本身约 **849 KB**，不包含 Python 与 dependency footprint。

这是一个刻意很短、file/process-heavy 的 **reference microbenchmark**，不是所有 workload 的普遍性能主张。由于未监测 baseline 只有几百毫秒，百分比 overhead 会被放大。进行容量规划前，应在目标主机与代表性 workload 上重跑 `execweave-overhead`。

```bash
execweave-overhead \
  --iterations 7 \
  --strace auto \
  --output-json benchmark-results.json \
  --output-svg benchmark-overhead.svg
```

Raw reference data 与方法：[`docs/benchmarks/`](docs/benchmarks/)。

## Evidence layers

ExecWeave 有意将四种 evidence layer 分开，而不是压成同一条 trace：

```text
Agent / IDE semantic evidence
          ↓
Inference gateway / routing evidence
          ↓
Model runtime / inference-server evidence
          ↓
OS runtime evidence: process / file / network
```

只有底层 telemetry 足以支持时，relationship 才能标记为 causal。

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

Cursor 提供稳定的 `tool_use_id`，因此可以在 pre/post hooks 之间建立 exact logical tool-call identity。

### OpenCode

```bash
execweave-opencode-plugin --install
execweave-opencode-record --open -- opencode
```

Project-local OpenCode plugin 使用 exact `sessionID + callID` identity，并且刻意不转发 tool output。

Provider-integrated runs 会分别保存 runtime、semantic 与 correlated artifacts。Tool → Process bridge 始终保持保守的 derived evidence：

```text
inferred: true
causal: false
```

若 evidence ambiguous，就不建立 edge。

## Inference gateway integrations

OpenRouter 与 LiteLLM Proxy 被建模为 `inference_gateway`，而不是 local model runtime。

```bash
execweave-inference-gateway event \
  --gateway litellm \
  --requested-model assistant \
  --resolved-model azure/gpt-5 \
  --provider-name Azure \
  --deployment-id deployment-west \
  --sidecar gateway.jsonl
```

ExecWeave 会分别保存 requested model、resolved model、routed provider 与 deployment identity。只有在提供 authoritative metadata 时才建立 provider/deployment edge，不会从 model-name prefix 猜测。

当 caller 在 Gateway 与 Model Runtime observation 之间拥有明确 shared identity 时，可以连接两个 request node，而不合并 evidence layer：

```bash
execweave-inference-link \
  --gateway litellm \
  --gateway-request-id gw-123 \
  --runtime vllm \
  --runtime-request-id rt-456 \
  --shared-request-id trace-789 \
  --sidecar inference.jsonl
```

`SAME_INFERENCE_REQUEST` 是 exact identity evidence，不是 causal evidence：

```text
identity_exact: true
inferred: false
causal: false
```

Raw shared request ID 不会落盘，只保存 SHA-256-derived identity hash。

## Model runtime integrations

当前支持的 model-runtime integrations 为 **Ollama**、**llama.cpp**、**vLLM** 与 **LM Studio**。

```bash
execweave-model-runtime event --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime llamacpp --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime vllm --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime lmstudio --sidecar model-runtime.jsonl
```

OpenAI-compatible runtimes 共用 response/usage 与 model-catalog parsing，同时保留 runtime-specific evidence semantics。Prompt、generated content 与 reasoning content 不会被保存。敏感的 local model path 会 redaction；llama.cpp 对 GGUF path 采用更严格的 redaction。

LM Studio 的 model-catalog visibility 会表示为 `ADVERTISES_MODEL`，不会被当作 model weights 已载入内存的证据。

## Runtime evidence

Portable collector 可在 Linux、macOS、Windows 运行。Linux 另外提供 syscall-backed `strace` reference backend。

```bash
execweave doctor
execweave run --backend portable -- your-command
execweave run --backend strace -- your-command
```

自 v0.6.1 起，child command 在执行前会先经过共用的 cross-platform launcher resolver。Linux 与 macOS 保留一般 PATH executable 行为；Windows 会通过 PATH/PATHEXT 解析 `.exe`、`.cmd`、`.bat`，明确的 `.ps1` launcher 则通过 PowerShell 执行。专用 Windows CI 会从 `cmd.exe` 与 Windows PowerShell 实际测试 Codex 与 Cursor recorder；完整 Cursor semantic/correlation integration 也持续由 Windows、macOS、Ubuntu matrix 覆盖。

Portable filesystem watching 是 session-correlated，而不是 process-causal；非常短命的 process 可能在 polling interval 之间被漏掉。Linux `strace` path 则会在 command 结束后提供 process-attributed syscall evidence。

未来 native collectors 规划包括 Linux eBPF、Windows ETW 与 macOS Endpoint Security。

## v0.6.2 safety patch

v0.6.2 强化长时间与 high-cardinality session 的资源安全，并且不改变 evidence semantics 或 graph schema 0.1：

- 过度宽广的 recursive filesystem scope，例如 filesystem root、user home 或 users-home parent，不再直接进行 recursive observation；process、network、semantic collection 仍可继续。
- Standalone 与 Live Viewer 超过 safety budget（1,500 nodes、4,000 edges，或估计 5,000 SVG elements）时停止 SVG materialization，避免耗尽 browser memory；canonical `graph.json` evidence artifact 仍保持完整。
- Viewer layout/fit 不再把任意大型 array spread 给 `Math.min` / `Math.max`，node dragging 的 edge redraw 改为 animation-frame throttling。
- Live server 只从 byte offset tail `events.jsonl` 新增的 bytes，并通过 in-memory `GraphAccumulator` 增量更新。`/graph.json` polling 不再重播整份 event history；没有 newline 的 incomplete trailing JSONL line 会先 buffer。
- 只有 event-count 或 aggregate-count 变化时，Live stats/edge labels 会更新而不做完整 topology redraw。Viewer budget 超标后，live `/graph.json` 会改为 counts-only compact payload，同时 collection 与最终 canonical validation/full `graph.json` 仍正常完成。

这是 polling + incremental-ingestion 的 safety patch，不是 SSE、SQLite、Rust 或 Canvas architecture migration。

## Layered artifacts

Provider-integrated run 可以产生：

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

Derived correlation layer 绝不改写 raw evidence。

## Interactive Viewer

Standalone Viewer 完全 local 且 self-contained。当前 baseline 包含 pan/zoom、draggable nodes、node/edge inspection、node-type/relation/causal filters、**observed only**、search、evidence-sequence replay、progressive cluster expansion、focused neighborhoods、Saved Views、明确 edge semantics，以及 Correlation Summary。

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

Security findings 会明确保留 evidence limits。Possible sensitive-file → network path 不代表已证明 byte-level exfiltration：

```json
{
  "data_flow_proven": false,
  "exfiltration_proven": false
}
```

## 当前状态

ExecWeave `main` 当前为 **v0.6.2**，并持续开发中。

Baseline 已包含 runtime collection、graph materialization/querying、standalone/live Viewer、Claude/Codex/Gemini/Cursor/OpenCode semantic integrations、保守 Tool → Process correlation、OpenRouter/LiteLLM gateway metadata、Ollama/llama.cpp/vLLM/LM Studio runtime metadata、exact Gateway ↔ Model Runtime request identity、已发布 PyPI wheel/sdist packaging、可复现 overhead benchmarking、cross-platform command-launcher compatibility、large-graph browser safety guards、incremental Live JSONL tail/cache，以及 Python 3.10/3.12 的跨平台 CI。

## 隐私

ExecWeave 是 local-first。Runtime events、semantic sidecars、graphs、reports 与 Viewers 默认留在本地。项目不刻意收集 file contents 或 raw read/write byte buffers。Native adapters 也默认避免 prompts/transcripts/tool output，但 commands、paths、endpoint metadata、identifiers 与 model metadata 仍可能敏感。

分享 artifacts 前请先检查。

## 文档

- [`Phase 1 — Runtime Collection`](docs/phase-1-runtime-collection.zh-CN.md)
- [`Phase 2 — Execution Graph`](docs/phase-2-execution-graph.zh-CN.md)
- [`Live Graph`](docs/live-graph.zh-CN.md)
- [`Semantic Telemetry`](docs/semantic-telemetry.zh-CN.md)
- [`Claude Code Hooks`](docs/claude-code-hooks.zh-CN.md)
- [`OpenAI Codex Hooks`](docs/codex-hooks.zh-CN.md)
- [`Gemini CLI Hooks`](docs/gemini-hooks.zh-CN.md)
- [`Cursor Hooks`](docs/cursor-hooks.zh-CN.md)
- [`OpenCode Plugin`](docs/opencode-plugin.zh-CN.md)
- [`Inference Gateway / OpenRouter / LiteLLM`](docs/inference-gateway.zh-CN.md)
- [`Model Runtime / Ollama / llama.cpp / vLLM / LM Studio`](docs/model-runtime.zh-CN.md)
- [`Performance Benchmarks`](docs/benchmarks/README.md)
- [`Security Analysis`](docs/security-analysis.zh-CN.md)

## Contributing

欢迎贡献，尤其是 native OS collectors、更多 Agent/IDE adapters、inference gateways、model runtimes、entity/correlation methods、privacy/redaction、graph UX 与 performance evaluation。

## License

请参阅 [`LICENSE`](LICENSE)。