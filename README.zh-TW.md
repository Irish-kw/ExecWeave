# ExecWeave

<p align="center">
  <a href="README.md">English</a> |
  <strong>繁體中文</strong> |
  <a href="README.zh-CN.md">简体中文</a> |
  <a href="README.ja.md">日本語</a> |
  <a href="README.ko.md">한국어</a>
</p>

**看見 AI Agent 在你的電腦上實際做了什麼。**

ExecWeave 是開源、local-first 的 observability 專案，會把 AI Agent 活動轉成互動式 execution graph，同時明確區分 observed evidence 與 inference。

> **Event 是 ground truth；Graph 是 materialized view。**

## 安裝

ExecWeave v0.6.0 已整理成標準 Python wheel / sdist。GitHub 端已是 PyPI-ready；第一次 Trusted Publisher release 正式發布前，可直接從 GitHub 以 pip 安裝：

```bash
python -m pip install "execweave @ git+https://github.com/Irish-kw/ExecWeave.git@main"
```

開發者安裝：

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

第一次 PyPI release 發布後即可使用：

```bash
python -m pip install execweave
```

即時觀察 command：

```bash
execweave live --open -- claude
```

建立完整 artifact pipeline：

```bash
execweave record --open -- python my_agent.py
```

## 效能與空間佔用

ExecWeave 內建可重跑的 package-level overhead benchmark，而且 reference result 是從 **實際安裝的 wheel** 執行，不是 editable source checkout。

比較圖採用類似 LLM 公司常見的 quality/cost trade-off 表達：

- **X 軸：**額外 peak process-tree RSS，低 → 高。
- **Y 軸：**runtime overhead，低 → 高。
- **Bubble 面積：**每次 run 產生的 median artifact size。
- **理想區域：**左下角。

![ExecWeave overhead trade-off](docs/benchmarks/v0.6.0-github-actions.svg)

Reference 環境：GitHub Actions Ubuntu runner、Intel Xeon Platinum 8573C、4 logical CPUs、Python 3.12.14、`n=7`。

| Profile | Median wall time | Runtime overhead | 額外 peak RSS | Median artifacts/run |
| --- | ---: | ---: | ---: | ---: |
| ExecWeave OFF | 236.221 ms | 0.0% | 0.0 MB | 0 KB |
| Portable ON | 391.580 ms | 65.768% | 27.852 MB | 741.355 KB |
| Strace ON | 1226.076 ms | 419.038% | 37.653 MB | 572.838 KB |

同一個 build 產生約 **113 KB wheel**、**198 KB sdist**；安裝後 ExecWeave distribution 本身約 **849 KB**，此數字不包含 Python 與 dependency footprint。

這是一個刻意很短、file/process-heavy 的 **reference microbenchmark**，不是所有 Agent workload 的普遍 overhead 主張。因為 OFF baseline 只有數百毫秒，百分比 overhead 會被放大；部署或容量評估前應在目標機器與實際 workload 上重跑。

```bash
execweave-overhead \
  --iterations 7 \
  --strace auto \
  --output-json benchmark-results.json \
  --output-svg benchmark-overhead.svg
```

原始 JSON、SVG 與方法說明：[`docs/benchmarks/`](docs/benchmarks/)。

## Evidence layers

ExecWeave 刻意把 evidence 分成四層，不把它們壓成同一條 trace：

```text
Agent / IDE semantic evidence
          ↓
Inference gateway / routing evidence
          ↓
Model runtime / inference-server evidence
          ↓
OS runtime evidence: process / file / network
```

只有底層 telemetry 足以支持時，relationship 才能標為 causal。

## Agent / IDE integrations

目前支援 Claude Code、OpenAI Codex、Gemini CLI、Cursor、OpenCode。Provider-integrated run 會分開保存 runtime、semantic、correlated artifacts。

Tool → Process bridge 永遠是保守 derived evidence：

```text
inferred: true
causal: false
```

ambiguous / no-match 不建立 edge。

## Inference Gateway

目前支援 OpenRouter 與 LiteLLM Proxy。Requested model、resolved model、provider、deployment 都是不同 evidence；沒有 authoritative metadata 時不推測 provider/deployment。

若 Gateway 與 Model Runtime 都具有 caller 明確提供的 shared request identity，可建立 exact link：

```bash
execweave-inference-link \
  --gateway litellm \
  --gateway-request-id gw-123 \
  --runtime vllm \
  --runtime-request-id rt-456 \
  --shared-request-id trace-789 \
  --sidecar inference.jsonl
```

其語義固定為：

```text
identity_exact: true
inferred: false
causal: false
```

Raw shared ID 不落盤，只保存 SHA-256-derived identity hash。

## Model Runtime

目前支援 **Ollama、llama.cpp、vLLM、LM Studio**。OpenAI-compatible runtimes 共用 response/usage 與 model-catalog parser，但保留 runtime-specific evidence semantics。

Prompt、generated content、reasoning content 不保存；敏感 local model path 會 redaction。LM Studio catalog 使用 `ADVERTISES_MODEL`，不把「出現在 catalog」誤當成「已載入記憶體」。

## Runtime evidence

Portable collector 支援 Linux、macOS、Windows；Linux 另有 syscall-backed `strace` reference backend。

```bash
execweave doctor
execweave run --backend portable -- your-command
execweave run --backend strace -- your-command
```

Portable filesystem observation 是 session-correlated，不是 process-causal；短命 process 可能在 polling interval 間被漏掉。Linux `strace` 則提供 process-attributed syscall evidence。

未來 native collectors 包含 Linux eBPF、Windows ETW、macOS Endpoint Security。

## Viewer 與 Graph

Standalone Viewer 完全 local、自包含，包含 pan/zoom、node/edge inspection、filters、**observed only**、search、Timeline ↔ Graph replay、cluster expansion、1/2-hop focus、Saved Views、edge semantics 與 Correlation Summary。

常用 graph command：

```bash
execweave graph-summary run.graph.json
execweave graph-filter run.graph.json --output causal.graph.json --causal-only
execweave graph-focus run.graph.json NODE_ID --hops 2 --output focused.graph.json
execweave path run.graph.json SOURCE TARGET --causal-only
```

## Security analysis

```bash
execweave analyze run.graph.json --output analysis.json
```

Possible sensitive-file → network path 不等於 byte-level exfiltration；security findings 會保留 evidence limits。

## 目前狀態

ExecWeave 目前為 **v0.6.0**。Baseline 已包含 runtime collection、graph materialization/query、standalone/live Viewer、五種 Agent/IDE semantic integrations、保守 Tool → Process correlation、OpenRouter/LiteLLM、Ollama/llama.cpp/vLLM/LM Studio、exact Gateway ↔ Model Runtime request identity、PyPI-ready packaging、可重跑 overhead benchmark，以及跨平台 CI。

## 隱私

ExecWeave 是 local-first。Runtime events、semantic sidecars、graphs、reports、Viewers 預設留在本機。專案不刻意擷取 file content 或 raw read/write byte buffers；native adapters 也預設避開 prompt/transcript/tool output，但 command、path、endpoint metadata、identifier、model metadata 仍可能敏感。

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

## License

請參閱 [`LICENSE`](LICENSE)。
