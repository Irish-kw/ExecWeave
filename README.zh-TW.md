> Codex + AGY 與其餘受支援 provider 現已完成 conversation history、dashboard graph、raw event 與 file target 對齊。

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

<p align="center">
  <a href="https://pypi.org/project/execweave/"><img src="https://img.shields.io/pypi/v/execweave" alt="PyPI"></a>
  <a href="https://github.com/Irish-kw/ExecWeave/actions/workflows/ci.yml"><img src="https://github.com/Irish-kw/ExecWeave/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue" alt="Python 3.10+">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-PolyForm%20Noncommercial-blue" alt="License"></a>
</p>

**看見 AI Agent 在你的電腦上實際做了什麼。**

ExecWeave 是一個 source-available、local-first 的可觀測性專案，會把 AI Agent 活動轉成互動式 execution graph，並明確區分 observed evidence、provider 明確提供的內容與 derived inference。

> **Event 是 ground truth；Graph 是 materialized view。**

<p align="center">
  <img src="docs/assets/codex.gif" alt="ExecWeave animated live demo" width="100%">
</p>

本 README 對應 **v0.8.10**。

## 為什麼是 ExecWeave

- **一個本機 inspection surface。** Live run、完成後的 run 與 standalone `viewer.html` 使用同一套 dashboard renderer，把 graph、logs、conversation 與 node details 放在同一個介面。
- **Evidence-aware。** Direct observation、identity link、保守 inference 與 causal claim 不會被混成同一種關係。
- **理解 Provider，但不虛構 Provider 沒提供的行為。** ExecWeave 只使用 provider 真正曝露的 routing / identity evidence；缺少的證據就保持缺少。
- **不只支援特定 Agent。** OS-runtime telemetry 可以包住任何本機命令；有 provider adapter 時再補上更強的 semantic evidence。

## 安裝

從 PyPI 安裝最新已發布版本：

```bash
python -m pip install -U execweave
```

開發安裝：

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

## 60 秒快速開始

Live OS-runtime telemetry 可用於**任何本機命令**。下列 Agent/runtime 名稱只是例子，不是白名單。

```bash
execweave live --open -- claude
execweave live --open -- codex
execweave live --open -- antigravity
execweave live --open -- cursor
execweave live --open -- opencode
execweave live --open -- ollama serve
execweave live --open -- python my_agent.py
```

> **首次出現 Hook 權限提示時請同意。** 第一次使用 provider integration 時，Agent/IDE 可能會詢問是否允許 ExecWeave 啟用本機 Hook；請選 **Allow / Yes**。若不同意，OS-runtime telemetry 仍可能運作，但 provider-level 的 tool、model、conversation 與 supplied-content observability 會降低或不可用。

Google Antigravity 目前使用 `agy` CLI；ExecWeave 也接受 `antigravity` 作為 friendly alias 並解析到 `agy`。Cursor 的 `execweave live --open -- cursor` 會先找一般 PATH launcher，找不到時在 macOS / Windows 嘗試標準 Cursor desktop application binary。

建立 finalized run artifacts：

```bash
execweave record --open -- python my_agent.py
```

如果想讓 Agent 保持在原 terminal 互動，同時開 detached overview：

```bash
execweave top -- codex
```

## Dashboard

ExecWeave 不會在 run 結束時換成另一套 viewer；Live、finished 與 standalone viewing 都沿用同一個 dashboard model。

- **Execution graph：** 顯示 agents、processes、files、network endpoints、tools、model/runtime entities 與受支援的 semantic relations。
- **Conversation rounds：** 最新一輪可直接讀，較舊的輪次仍各自可展開，不會被新回答蓋掉。
- **Node details：** process node 顯示 command / PID context，file node 顯示 path / history context，network node 顯示 endpoint / process context。
- **Large-run readability：** 每種類型超過預算後只保留最新成員直接畫出，舊成員收進可檢視 aggregate。門檻由 `--fold-budget N` 控制。
- **Selection clarity：** multi-agent layout 維持穩定 root / child hierarchy，選取 agent 時會淡化無關 edges。

### v0.8.3 Dashboard 變更

v0.8.3 的重點是讓 dense、multi-round run 更容易讀，同時不改 raw evidence：

- conversation panel 改成以 round 為單位，不再把舊 prompt 與新 reply 錯配；
- 使用者明確設定的展開 / 收合狀態會跨 800 ms Live refresh 保留；
- subagent response 會維持歸屬於真正產生它的 agent；
- 選取 process、file、network 不再看到空白 detail panel；
- 高基數 node type 會依可調整預算摺疊，不讓 graph 被數百或數千個 node 淹沒；
- lifecycle return edge 不再扭曲 root / child rank，共用 tool/model traffic 使用更清楚的 routed geometry。

這些都是 presentation-layer change。Raw graph evidence 不變，Live、finished 與 `viewer.html` 仍共用同一 renderer。

## 支援的 Integrations

| Integration | 在 ExecWeave 下啟動時的 OS-runtime observation | Specialized evidence |
| --- | --- | --- |
| Claude Code | Yes | native hooks + full-fidelity supplied hook content + provider 明確曝露時的 exact subagent results |
| OpenAI Codex | Yes | lifecycle hooks + validated rollout transcripts + agent-local task/message/final-response routing |
| Google Antigravity / Antigravity CLI | Yes | passive native hooks + 可驗證時的 conversation/subagent routing |
| Cursor | Yes | native hooks + 能取得時的 exact subagent task/summary routing |
| OpenCode | Yes | project plugin + session/task routing + full-fidelity supplied plugin content |
| Ollama | Yes | `execweave-model-runtime event/exchange/probe --runtime ollama` |
| llama.cpp | Yes | `execweave-model-runtime event/exchange/probe --runtime llamacpp` |
| vLLM | Yes | `execweave-model-runtime event/exchange/probe --runtime vllm` |
| LM Studio | 僅限本機 process 由 ExecWeave 啟動 | `execweave-model-runtime event/exchange/probe --runtime lmstudio` |
| LiteLLM Proxy | 設定好的 proxy 由 ExecWeave 啟動時為 Yes | metadata-oriented gateway callback/event integration |
| OpenRouter | 觀察本機 client，而不是遠端 service process | `execweave-inference-gateway event/exchange/generation --gateway openrouter` |

Cursor `tool_use_id`、Codex rollout thread identity、OpenCode `sessionID + callID` 這類 stable provider identifier 能證明 logical provider identity，但它們不是 OS PID。只有 provider 明確曝露 route、delegation 或 result 時，cross-agent content 才會被顯示。若 gateway / local runtime 只提供 root request/response，ExecWeave 就維持 root-only，不會虛構 subagent 或 hidden routing。

OpenRouter `exchange` 是 caller-supplied request+response evidence，不是 transparent wire interception。LiteLLM Proxy 在目前 baseline 仍屬較窄的 metadata-oriented integration。Google CLI 使用情境應改用 Antigravity (`agy`)。

## Evidence model

ExecWeave 不會把所有 signal 壓成一條 trace，而是維持 evidence layer 邊界：

```text
Agent / IDE semantic + supplied content evidence
          ↓
Inference gateway / routing evidence
          ↓
Model runtime / inference-server evidence
          ↓
OS runtime evidence: process / file / network
```

只有底層 telemetry 真正支援 causal claim 時，relationship 才會標成 causal。保守的 Tool → Process bridge 會維持 derived evidence 標記：

```text
inferred: true
causal: false
```

Gateway 與 Model Runtime 之間 exact shared request identity 代表 identity evidence，不代表 causal evidence：

```text
identity_exact: true
inferred: false
causal: false
```

有歧義時就不建立 edge。

### Full-fidelity supplied content

從 **v0.6.9** 起，受支援的 integration point 可以把 provider / hook / API 明確提供的完整值保存進本機 SHA-256 content-addressed store，而 semantic event stream 只保留 reference：

```text
<run-root>/content/sha256/<sha256>.<json|txt|bin>
```

依 integration 不同，保存內容可能包括 prompt/message、request/response object、tool input/result、assistant response、上游明確曝露的 reasoning/thinking text、shell/MCP output，以及 provider hook 提供的 file content。

`complete_from_source: true` 只表示 ExecWeave 完整保存了該 integration point 提供的值；**不代表**看到了 hidden model state、provider 未曝露的內部階段、未觀察到的 final wire request，或沒有被攔截的 bytes。

## 常用命令

### Agent / IDE recorders

```bash
execweave-claude-record --open -- claude
execweave-codex-record --open -- codex
execweave-antigravity-record --open -- antigravity
execweave-cursor-record --open -- cursor
execweave-opencode-plugin --install
execweave-opencode-record --open -- opencode
```

### Gateways 與 model runtimes

```bash
execweave-inference-gateway event --gateway openrouter --sidecar gateway.jsonl
execweave-inference-gateway exchange --gateway openrouter --sidecar gateway.jsonl
execweave-inference-gateway event --gateway litellm --sidecar gateway.jsonl

execweave-model-runtime event --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime exchange --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime probe --runtime ollama --sidecar model-runtime.jsonl
```

`event` 是 response-only evidence；`exchange` 保存 caller-supplied request+response object，不會宣稱 transparent interception。Runtime catalog relation 仍保留各自來源語義：`LOADED_MODEL`、`SERVES_MODEL`、`ADVERTISES_MODEL` 不可互換。LM Studio catalog visibility 仍是 `ADVERTISES_MODEL`，不能視為 weights 已在 memory 中 resident 的證明。

### Runtime、graph、security 與 integrity

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

Security finding 的 evidence grade 與 severity 分開。現有 grade 為 `A`、`B`、`C`、`D`、`U`；它們是 evidence-strength category，不是 probability 或 trust score。Rule pack 是 bounded、explainable 的 single-edge observation policy，不會執行 third-party code，也不能證明 byte-level exfiltration。

## Run artifacts

Provider-integrated run 可能包含：

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

Derived correlation 不會覆寫 raw runtime 或 provider sidecar evidence。

## 限制與隱私

- Portable collector 可在 Linux、macOS、Windows 執行。Portable filesystem observation 是 session-correlated，不是 process-causal；polling 也可能漏掉非常短命的 activity。
- Linux 另有 syscall-backed `strace` reference backend，可為受支援執行提供較強的 process-attributed syscall evidence。
- Native Linux eBPF、Windows ETW、macOS Endpoint Security collector 仍是 planned work，不是目前已完成的能力宣稱。
- Full-fidelity provider content 可能完整保存 prompt、tool value、model response、shell output 或 supplied file 內的 secret。ExecWeave **不是**通用 secret scanner 或 content redactor。
- Conversation isolation 是 attribution/display rule，不是 redaction boundary。若 provider 明確把內容 route 到其他 agent，參與端點仍可能合理地看到該內容。
- Commands、paths、endpoints、identifiers、model metadata、prompts、tool values 與 content blobs 都可能敏感；分享前請檢查整個 run directory。
- Local integrity seal 可偵測相對於 manifest 的檔案變更，但如果 evidence 與 manifest 都位在同一個可寫 trust boundary，就不能把它描述成 adversary-resistant tamper evidence。

## 效能

ExecWeave 包含 bounded filesystem/viewer protection、incremental Live JSONL tailing、large-graph safety guard、detached Top，以及針對已設定 provider integration 的 provisional live sidecar。

可重現的 incremental `GraphAccumulator` reference result 在文件化 GitHub Actions workload 上、1M synthetic events 時達到 **164,273 ev/s**。這是 graph-accumulation benchmark，不是 end-to-end collector / browser throughput。

請在代表性的 host/workload 上執行 package-level benchmark：

```bash
execweave-overhead --iterations 7 --strace auto --output-json benchmark-results.json
execweave-scalability
```

Reference data 與 methodology 位於 [`docs/benchmarks/`](docs/benchmarks/)。

## 文件

| 區域 | 文件 |
| --- | --- |
| Runtime 與 graph | [`Phase 1 — Runtime Collection`](docs/phase-1-runtime-collection.md) · [`Phase 2 — Execution Graph`](docs/phase-2-execution-graph.md) · [`Live Graph`](docs/live-graph.md) · [`Semantic Telemetry`](docs/semantic-telemetry.md) |
| Agent / IDE integrations | [`Claude Code`](docs/claude-code-hooks.md) · [`OpenAI Codex`](docs/codex-hooks.md) · [`Google Antigravity`](docs/antigravity-hooks.md) · [`Cursor`](docs/cursor-hooks.md) · [`OpenCode`](docs/opencode-plugin.md) |
| Gateways 與 runtimes | [`Inference Gateway / OpenRouter / LiteLLM`](docs/inference-gateway.md) · [`Model Runtime / Ollama / llama.cpp / vLLM / LM Studio`](docs/model-runtime.md) |
| Trust 與 analysis | [`Runtime Threat Model`](docs/runtime-threat-model.md) · [`Evidence Grades`](docs/evidence-grades.md) · [`Rule Packs`](docs/rule-packs.md) · [`Run Integrity`](docs/run-integrity.md) · [`Security Analysis`](docs/security-analysis.md) |
| 效能 | [`Benchmarks`](docs/benchmarks/README.md) |

## 貢獻

歡迎針對 native OS collector、Agent/IDE adapter、inference gateway、model runtime、evidence/correlation method、privacy/redaction、graph UX、multi-agent conversation attribution 與 performance evaluation 提交貢獻。

## 授權

從 v0.6.8 起，ExecWeave 採用 **PolyForm Noncommercial License 1.0.0**。依授權條款可進行非商業使用、修改與再散布；商業使用需要與 licensor 另行取得書面 commercial license。詳見 [`LICENSE`](LICENSE)。
