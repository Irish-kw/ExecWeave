# ExecWeave

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

ExecWeave 是開源、local-first 的 observability 專案，會把 AI Agent 活動轉成互動式 execution graph，同時明確區分 observed evidence 與 inference。

> **Event 是 ground truth；Graph 是 materialized view。**

<p align="center">
  <img src="docs/assets/execweave-live-demo.webp" alt="ExecWeave Live execution graph" width="100%">
</p>

<!-- execweave-demo:start -->
## 重現這個 Demo

上面的截圖是一個真實的 ExecWeave v0.6.3 live session。這個 workload 刻意產生足夠多種活動，讓 execution graph 能清楚展示效果：多個 Python modules、JSON/CSV 檔案、tests、檔案檢查，以及對外 HTTP requests。

把本機 Agent CLI 放在 ExecWeave 下執行，例如：

```bash
execweave live --open -- claude
```

接著把這段 workload prompt 貼給 Agent：

```text
Create a small Python project in ./execweave-demo with 8 modules,
generate sample JSON and CSV data, run the program and tests,
inspect the generated files, and fetch example.com plus the GitHub API.
```

同一個 workload 也可以用 `codex`、`gemini`、`cursor` 或 `opencode`。實際的 node、edge、event、process 與 endpoint 數量會隨 OS、Agent 版本與環境而不同。ExecWeave 記錄的是實際觀測到的 runtime evidence；上圖是一個具體執行結果，不是固定應得到的 graph。
<!-- execweave-demo:end -->

## 安裝

ExecWeave 已正式發布到 PyPI，標準安裝方式為：

```bash
python -m pip install -U execweave
```

`main` 可能比目前 PyPI release 更新。若要直接測試最新 mainline：

```bash
python -m pip install --upgrade --force-reinstall "execweave @ git+https://github.com/Irish-kw/ExecWeave.git@main"
```

開發者安裝：

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

Live OS-runtime telemetry 可用於 **任何本機 command**；下面只是例子，不是 whitelist：

```bash
# Agent / IDE CLI
execweave live --open -- claude
execweave live --open -- codex
execweave live --open -- gemini
execweave live --open -- cursor
execweave live --open -- opencode

# 任意本機程式
execweave live --open -- python my_agent.py

# 由 ExecWeave 啟動的本機 model runtime
execweave live --open -- ollama serve
```

`execweave live` 即時呈現它所啟動 command tree 的 process、file、network evidence。Agent semantic hooks、model-runtime API metadata、inference-gateway routing metadata **目前不會自動注入 Live Viewer**。

#### Live 能力矩陣

| Integration | 直接 OS-runtime live | 專用 metadata | 自動進入 Live Viewer |
| --- | --- | --- | --- |
| Claude Code | 可以 | `execweave-claude-record` / hooks | 否 |
| OpenAI Codex | 可以 | `execweave-codex-record` / hooks | 否 |
| Gemini CLI | 可以 | `execweave-gemini-record` / hooks | 否 |
| Cursor | 可以 | `execweave-cursor-record` / hooks | 否 |
| OpenCode | 可以 | `execweave-opencode-record` / plugin | 否 |
| Ollama | 可以，但需由 ExecWeave 啟動，例如 `ollama serve` | `execweave-model-runtime event/probe --runtime ollama` | 否 |
| llama.cpp | 可以，但需由 ExecWeave 啟動本機 server | `execweave-model-runtime event/probe --runtime llamacpp` | 否 |
| vLLM | 可以，但需由 ExecWeave 啟動本機 server | `execweave-model-runtime event/probe --runtime vllm` | 否 |
| LM Studio | 只有由 ExecWeave 啟動的本機 process；不會 attach 已在執行的 server | `execweave-model-runtime event/probe --runtime lmstudio` | 否 |
| LiteLLM Proxy | 可以，但需由 ExecWeave 啟動本機 proxy | `execweave-inference-gateway event --gateway litellm` | 否 |
| OpenRouter | 遠端服務本身不能直接 live；請 live 本機 client/Agent | `execweave-inference-gateway event/generation --gateway openrouter` | 否 |

若 Ollama 已經在背景執行，可用 `execweave-model-runtime probe --runtime ollama` snapshot 目前 loaded-model state。OpenRouter 則可由 `live` 觀察本機 client 與 network activity，而 gateway routing/usage metadata 仍保持為獨立 evidence layer。

<!-- v0.6.3-live -->
### v0.6.3 即時可觀測性

同一個 live session 可以用瀏覽器或 Terminal 查看：

```bash
execweave top -- codex          # Terminal dashboard
execweave top --open -- codex   # Terminal + Web Viewer
```

Live 更新改用增量 snapshot/delta 與有界歷史，不再反覆重建並傳送整張 graph。Live 與 standalone Viewer 都支援會記住偏好的 Dark/Light 切換。在 Linux 上，超大型 recursive filesystem scope 會先做資源預檢；若 inotify watch 空間不足，會自動降級為 polling，因此不會因 inotify watch exhaustion 直接中止 session。

`live` 是通用 OS-runtime view，不是 integration whitelist。Agent semantic、model-runtime、gateway metadata 仍是分離的 evidence layers，在 v0.6.3 不會自動注入 Live Viewer。

可用 `execweave-scalability` 重現 graph scalability benchmark；CI 覆蓋 10k、100k 與 1M synthetic events。

#### Scalability benchmark

以下為 GitHub Actions 上 incremental `GraphAccumulator` synthetic workload 的 reference result（`retain_event_ids=False`）：

| Events | Apply time | Throughput | Nodes | Edges | Apply RSS Δ | Snapshot |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 10k | 0.114 s | 87,681 ev/s | 10,001 | 10,000 | 35.9 MiB | 8.5 MiB |
| 100k | 0.654 s | 152,816 ev/s | 10,001 | 10,000 | 25.8 MiB | 8.6 MiB |
| **1M** | **6.087 s** | **164,273 ev/s** | **10,001** | **10,000** | **23.5 MiB** | **8.6 MiB** |

在 **1,000,000 events** 下，incremental in-memory graph 不會重複保存 raw event IDs；raw evidence 與 materialized graph 維持分離。這個 benchmark 量測的是 graph accumulation 與 snapshot materialization，不是 end-to-end collector 或 browser throughput。

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

自 v0.6.1 起，所有 recorder 在啟動 child command 前都先走共用的跨平台 launcher resolver。Linux / macOS 保持正常 PATH executable 行為；Windows 會依 PATH/PATHEXT 正確解析 `.exe`、`.cmd`、`.bat`，若明確傳入 `.ps1` 則交給 PowerShell 啟動。專用 Windows CI 會實際從 `cmd.exe` 與 Windows PowerShell 啟動 Codex / Cursor recorder；完整 Cursor semantic/correlation integration 也持續由 Windows、macOS、Ubuntu matrix 驗證。

Portable filesystem observation 是 session-correlated，不是 process-causal；短命 process 可能在 polling interval 間被漏掉。Linux `strace` 則提供 process-attributed syscall evidence。

未來 native collectors 包含 Linux eBPF、Windows ETW、macOS Endpoint Security。

## v0.6.3 Safety Patch

v0.6.3 強化長時間與高 cardinality session 的資源安全，但**不改變 evidence semantics 或 graph schema 0.1**：

- 過度寬廣的 recursive filesystem scope（例如 filesystem root、使用者 home 或 users-home parent）不再直接進行 recursive filesystem observation；process、network、semantic collection 仍可繼續。
- Standalone 與 Live Viewer 在超過安全預算（1,500 nodes、4,000 edges，或估計 5,000 SVG elements）時停止 SVG materialization，避免 browser memory 被大型 graph 拖垮；canonical `graph.json` evidence artifact 仍保持完整。
- Viewer layout/fit 不再把任意大型 array spread 給 `Math.min` / `Math.max`，node dragging 的 edge redraw 也改為 animation-frame throttling。
- Live server 以 byte offset 只 tail `events.jsonl` 新增資料，透過 in-memory `GraphAccumulator` 增量更新，不再每次 `/graph.json` request 重播整份 event history；尚未完成且沒有 newline 的 trailing JSONL line 會先 buffer。
- 僅 event count / aggregate count 變化時，Live UI 只更新 stats/edge labels，不做完整 topology redraw。超過 Viewer 預算後，live `/graph.json` 改回傳 counts-only compact payload；collection 與 session 結束後的 canonical validation/full `graph.json` 不受影響。

這是 polling + incremental ingestion 的 Safety Patch，不是 SSE、SQLite、Rust 或 Canvas 架構切換。

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

ExecWeave `main` 目前為 **v0.6.3**。Baseline 已包含 runtime collection、graph materialization/query、standalone/live Viewer、五種 Agent/IDE semantic integrations、保守 Tool → Process correlation、OpenRouter/LiteLLM、Ollama/llama.cpp/vLLM/LM Studio、exact Gateway ↔ Model Runtime request identity、已發布的 PyPI packaging、可重跑 overhead benchmark、跨平台 command launcher compatibility、large-graph browser safety guards、incremental Live JSONL tail/cache，以及跨平台 CI。

## 隱私

ExecWeave 是 local-first。Runtime events、semantic sidecars、graphs、reports、Viewers 預設留在本機。專案不刻意擷取 file content 或 raw read/write byte buffers；native adapters 也預設避開 prompt/transcript/tool output，但 command、path、endpoint metadata、identifier、model metadata 仍可能敏感。

分享 artifacts 前請先檢查。

## 文件

- [`Phase 1 — Runtime Collection`](docs/phase-1-runtime-collection.zh-TW.md)
- [`Phase 2 — Execution Graph`](docs/phase-2-execution-graph.zh-TW.md)
- [`Live Graph`](docs/live-graph.zh-TW.md)
- [`Semantic Telemetry`](docs/semantic-telemetry.zh-TW.md)
- [`Claude Code Hooks`](docs/claude-hooks.zh-TW.md)
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