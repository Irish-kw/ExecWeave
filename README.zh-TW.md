# ExecWeave

[![PyPI](https://img.shields.io/pypi/v/execweave?label=PyPI)](https://pypi.org/project/execweave/)
[![Python](https://img.shields.io/pypi/pyversions/execweave?label=Python)](https://pypi.org/project/execweave/)
[![CI](https://github.com/Irish-kw/ExecWeave/actions/workflows/ci.yml/badge.svg)](https://github.com/Irish-kw/ExecWeave/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/Irish-kw/ExecWeave?style=flat&label=Stars)](https://github.com/Irish-kw/ExecWeave/stargazers)

<!-- i18n-nav:start -->
<p align="center">
  <a href="README.md">English</a> |
  <strong>繁體中文</strong> |
  <a href="README.zh-CN.md">简体中文</a> |
  <a href="README.ja.md">日本語</a> |
  <a href="README.ko.md">한국어</a> |
  <a href="README.fr.md">Français</a> |
  <a href="README.de.md">Deutsch</a> |
  <a href="README.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

**看見 AI Agent 在你的電腦上實際做了什麼。**

ExecWeave 是一個開源、local-first 的 observability 專案，會把 AI Agent 的活動轉成互動式 execution graph，同時明確區分 observed evidence 與 inference。

> **Event 是 ground truth；Graph 是 materialized view。**

<p align="center">
  <img src="docs/assets/execweave-viewer.png" alt="ExecWeave Live execution graph" width="100%">
</p>

## 安裝

ExecWeave 已發布到 PyPI，提供標準 Python wheel/sdist。安裝最新 release：

```bash
python -m pip install -U execweave
```

`main` branch 可能比目前 PyPI release 更新。若要直接測試最新 mainline build：

```bash
python -m pip install --upgrade --force-reinstall "execweave @ git+https://github.com/Irish-kw/ExecWeave.git@main"
```

開發者安裝：

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

即時觀察 Claude Code、OpenAI Codex 或 Gemini CLI：

```bash
# Claude Code
execweave live --open -- claude

# OpenAI Codex
execweave live --open -- codex

# Gemini CLI
execweave live --open -- gemini
```

或建立完整 artifact pipeline：

```bash
execweave record --open -- python my_agent.py
```

## 效能與空間佔用

ExecWeave 內建可重現的 package-level overhead benchmark，並從實際安裝的 wheel 執行。Reference plot 採用常見的 quality/cost trade-off 表達方式：

- **X 軸：**額外 peak process-tree RSS，低 → 高。
- **Y 軸：**runtime overhead，低 → 高。
- **Bubble 面積：**每次執行產生的 median artifact size。
- **理想區域：**左下角。

![ExecWeave overhead trade-off](docs/benchmarks/v0.6.0-github-actions.svg)

Reference 環境：GitHub Actions Ubuntu runner、Intel Xeon Platinum 8573C、4 logical CPUs、Python 3.12.14、`n=7`。

| Profile | Median wall time | Runtime overhead | Additional peak RSS | Median artifacts/run |
| --- | ---: | ---: | ---: | ---: |
| ExecWeave OFF | 236.221 ms | 0.0% | 0.0 MB | 0 KB |
| Portable ON | 391.580 ms | 65.768% | 27.852 MB | 741.355 KB |
| Strace ON | 1226.076 ms | 419.038% | 37.653 MB | 572.838 KB |

同一個 build 產生約 **113 KB wheel** 與 **198 KB sdist**。安裝後 ExecWeave distribution 本身約 **849 KB**，不包含 Python 與 dependency footprint。

這是一個刻意很短、file/process-heavy 的 **reference microbenchmark**，不是所有 workload 的普遍效能主張。因為未監測 baseline 只有數百毫秒，百分比 overhead 會被放大。進行容量規劃前，應在目標主機與代表性 workload 上重跑 `execweave-overhead`。

```bash
execweave-overhead \
  --iterations 7 \
  --strace auto \
  --output-json benchmark-results.json \
  --output-svg benchmark-overhead.svg
```

Raw reference data 與方法：[`docs/benchmarks/`](docs/benchmarks/)。

## Evidence layers

ExecWeave 刻意把四種 evidence layer 分開，而不是壓成同一條 trace：

```text
Agent / IDE semantic evidence
          ↓
Inference gateway / routing evidence
          ↓
Model runtime / inference-server evidence
          ↓
OS runtime evidence: process / file / network
```

只有底層 telemetry 足以支持時，relationship 才能標成 causal。

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

Cursor 提供穩定的 `tool_use_id`，因此可在 pre/post hooks 之間建立 exact logical tool-call identity。

### OpenCode

```bash
execweave-opencode-plugin --install
execweave-opencode-record --open -- opencode
```

Project-local OpenCode plugin 使用 exact `sessionID + callID` identity，而且刻意不轉送 tool output。

Provider-integrated runs 會分開保存 runtime、semantic 與 correlated artifacts。Tool → Process bridge 一律維持保守的 derived evidence：

```text
inferred: true
causal: false
```

若 evidence ambiguous，就不建立 edge。

## Inference gateway integrations

OpenRouter 與 LiteLLM Proxy 被建模為 `inference_gateway`，而不是 local model runtime。

```bash
execweave-inference-gateway event \
  --gateway litellm \
  --requested-model assistant \
  --resolved-model azure/gpt-5 \
  --provider-name Azure \
  --deployment-id deployment-west \
  --sidecar gateway.jsonl
```

ExecWeave 會把 requested model、resolved model、routed provider 與 deployment identity 分開保存。只有在提供 authoritative metadata 時才建立 provider/deployment edge，不會從 model-name prefix 猜測。

當 caller 在 Gateway 與 Model Runtime observation 之間擁有明確 shared identity 時，可以連結兩個 request node，而不合併 evidence layer：

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

Raw shared request ID 不會落盤，只保存 SHA-256-derived identity hash。

## Model runtime integrations

目前支援的 model-runtime integrations 為 **Ollama**、**llama.cpp**、**vLLM** 與 **LM Studio**。

```bash
execweave-model-runtime event --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime llamacpp --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime vllm --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime lmstudio --sidecar model-runtime.jsonl
```

OpenAI-compatible runtimes 共用 response/usage 與 model-catalog parsing，同時保留 runtime-specific evidence semantics。Prompt、generated content 與 reasoning content 不會被保存。敏感的 local model path 會 redaction；llama.cpp 對 GGUF path 採取更嚴格的 redaction。

LM Studio 的 model-catalog visibility 會表示成 `ADVERTISES_MODEL`，不會被當成 model weights 已載入記憶體的證據。

## Runtime evidence

Portable collector 可在 Linux、macOS、Windows 運作。Linux 另外提供 syscall-backed `strace` reference backend。

```bash
execweave doctor
execweave run --backend portable -- your-command
execweave run --backend strace -- your-command
```

自 v0.6.1 起，child command 在執行前會先經過共用的 cross-platform launcher resolver。Linux 與 macOS 保留一般 PATH executable 行為；Windows 會透過 PATH/PATHEXT 解析 `.exe`、`.cmd`、`.bat`，明確的 `.ps1` launcher 則透過 PowerShell 執行。專用 Windows CI 會從 `cmd.exe` 與 Windows PowerShell 實際測試 Codex 與 Cursor recorder；完整 Cursor semantic/correlation integration 也持續由 Windows、macOS、Ubuntu matrix 覆蓋。

Portable filesystem watching 是 session-correlated，而不是 process-causal；非常短命的 process 可能在 polling interval 之間被漏掉。Linux `strace` path 則會在 command 結束後提供 process-attributed syscall evidence。

未來 native collectors 規劃包含 Linux eBPF、Windows ETW 與 macOS Endpoint Security。

## v0.6.2 safety patch

v0.6.2 強化長時間與 high-cardinality session 的資源安全，而且不改變 evidence semantics 或 graph schema 0.1：

- 過度寬廣的 recursive filesystem scope，例如 filesystem root、user home 或 users-home parent，不再直接進行 recursive observation；process、network、semantic collection 仍可繼續。
- Standalone 與 Live Viewer 超過 safety budget（1,500 nodes、4,000 edges，或估計 5,000 SVG elements）時停止 SVG materialization，避免耗盡 browser memory；canonical `graph.json` evidence artifact 仍保持完整。
- Viewer layout/fit 不再把任意大型 array spread 給 `Math.min` / `Math.max`，node dragging 的 edge redraw 改為 animation-frame throttling。
- Live server 只從 byte offset tail `events.jsonl` 新增的 bytes，並透過 in-memory `GraphAccumulator` 增量更新。`/graph.json` polling 不再重播整份 event history；沒有 newline 的 incomplete trailing JSONL line 會先 buffer。
- 只有 event-count 或 aggregate-count 變化時，Live stats/edge labels 會更新而不做完整 topology redraw。Viewer budget 超標後，live `/graph.json` 會改成 counts-only compact payload，同時 collection 與最終 canonical validation/full `graph.json` 仍照常完成。

這是 polling + incremental-ingestion 的 safety patch，不是 SSE、SQLite、Rust 或 Canvas architecture migration。

## Layered artifacts

Provider-integrated run 可以產生：

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

Derived correlation layer 絕不改寫 raw evidence。

## Interactive Viewer

Standalone Viewer 完全 local 且 self-contained。目前 baseline 包含 pan/zoom、draggable nodes、node/edge inspection、node-type/relation/causal filters、**observed only**、search、evidence-sequence replay、progressive cluster expansion、focused neighborhoods、Saved Views、明確 edge semantics，以及 Correlation Summary。

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

Security findings 會明確保留 evidence limits。Possible sensitive-file → network path 不代表已證明 byte-level exfiltration：

```json
{
  "data_flow_proven": false,
  "exfiltration_proven": false
}
```

## 目前狀態

ExecWeave `main` 目前為 **v0.6.2**，並持續開發中。

Baseline 已包含 runtime collection、graph materialization/querying、standalone/live Viewer、Claude/Codex/Gemini/Cursor/OpenCode semantic integrations、保守 Tool → Process correlation、OpenRouter/LiteLLM gateway metadata、Ollama/llama.cpp/vLLM/LM Studio runtime metadata、exact Gateway ↔ Model Runtime request identity、已發布 PyPI wheel/sdist packaging、可重現 overhead benchmarking、cross-platform command-launcher compatibility、large-graph browser safety guards、incremental Live JSONL tail/cache，以及 Python 3.10/3.12 的跨平台 CI。

## 隱私

ExecWeave 是 local-first。Runtime events、semantic sidecars、graphs、reports 與 Viewers 預設留在本機。專案不刻意收集 file contents 或 raw read/write byte buffers。Native adapters 也預設避免 prompts/transcripts/tool output，但 commands、paths、endpoint metadata、identifiers 與 model metadata 仍可能敏感。

分享 artifacts 前請先檢查。

## 文件

- [`Phase 1 — Runtime Collection`](docs/phase-1-runtime-collection.zh-TW.md)
- [`Phase 2 — Execution Graph`](docs/phase-2-execution-graph.zh-TW.md)
- [`Live Graph`](docs/live-graph.zh-TW.md)
- [`Semantic Telemetry`](docs/semantic-telemetry.zh-TW.md)
- [`Claude Code Hooks`](docs/claude-code-hooks.zh-TW.md)
- [`OpenAI Codex Hooks`](docs/codex-hooks.zh-TW.md)
- [`Gemini CLI Hooks`](docs/gemini-hooks.zh-TW.md)
- [`Cursor Hooks`](docs/cursor-hooks.zh-TW.md)
- [`OpenCode Plugin`](docs/opencode-plugin.zh-TW.md)
- [`Inference Gateway / OpenRouter / LiteLLM`](docs/inference-gateway.zh-TW.md)
- [`Model Runtime / Ollama / llama.cpp / vLLM / LM Studio`](docs/model-runtime.zh-TW.md)
- [`Performance Benchmarks`](docs/benchmarks/README.md)
- [`Security Analysis`](docs/security-analysis.zh-TW.md)

## Contributing

歡迎貢獻，尤其是 native OS collectors、更多 Agent/IDE adapters、inference gateways、model runtimes、entity/correlation methods、privacy/redaction、graph UX 與 performance evaluation。

## License

請參閱 [`LICENSE`](LICENSE)。