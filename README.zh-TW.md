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

ExecWeave 是一個 source-available、local-first 的可觀測性專案，會把 AI Agent 活動轉成互動式 execution graph，並明確區分 observed evidence、provider content 與 derived inference。

> **Event 是 ground truth；Graph 是 materialized view。**

<p align="center">
  <img src="docs/assets/codex.gif" alt="ExecWeave animated live demo" width="100%">
</p>

## 安裝

從 PyPI 安裝最新已發布的 wheel/sdist：

```bash
python -m pip install -U execweave
```

目前正式版本是 **v0.7.7**。

開發安裝：

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

## 快速開始

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

> **首次出現 Hook 權限提示時請同意。** 第一次使用 provider integration 時，Agent/IDE 可能會詢問是否允許 ExecWeave 啟用本機 Hook；請選 **Allow / Yes**。若不同意，OS-runtime telemetry 仍可能運作，但 provider-level 的 tool、model 與 supplied-content observability 會降低或不可用。

Google Antigravity 目前使用 `agy` CLI；ExecWeave 也接受 `antigravity` 作為友善 alias 並自動解析到 `agy`。Cursor 的 `execweave live --open -- cursor` 會先找 PATH launcher，找不到時在 macOS/Windows 自動嘗試標準 Cursor desktop application binary。

或建立 finalized artifact pipeline：

```bash
execweave record --open -- python my_agent.py
```

`execweave top -- codex` 會讓 Agent 保持在啟動 terminal 中互動，並依主機環境開啟或附加 detached Top dashboard。

**v0.7.7 — 執行期間就只看得到自己那一份對話。** live dashboard 在整段執行期間讓每個 agent 都看得到其他 agent 的對話，要等 agent 結束才會正確：它只在 finalization 才去取 conversation index，因此 per-agent scoping 從未執行，畫面改由一份平鋪的全部記錄清單頂替，而且不論選取哪個 node 都是同一份。現在該 index 改為從執行中的 graph 投影並在執行期間供應，走的是與 finalized 檔案相同的 builder，因此 live dashboard 與 recorded viewer 不可能對「什麼屬於哪個 agent」有不同答案；兩者唯一會畫出的，就是每個 agent 各自擁有的 provider-neutral、agent-local multi-agent conversation。兩個 viewer 都不再保留任何會繞過 per-agent projection 的 fallback。發布前的檢查現在會用真實瀏覽器開啟兩種 viewer 並讀回每個 agent 顯示的內容，因此 agent 看到別人的對話會讓建置失敗，而不是流到 release。

統一 dashboard 把 execution graph、logs 與 conversation records 放進同一條 inspection flow。Finalized run 會產生 `conversations.md` 與 `conversations.json`，經驗證的 provider transcript 也會複製進 run-local SHA-256 content store。Claude Code、OpenAI Codex、Cursor、OpenCode 與 Google Antigravity 都依各自實際曝露的 evidence 強度建立 multi-agent trace；若 gateway 或 local runtime 只提供 root request/response，ExecWeave 就只顯示 root conversation，不會虛構 subagent 或 hidden routing。

## v0.6.9：full-fidelity observability 與明確 evidence boundary

v0.6.9 不再只保留精簡 metadata。當受支援的 integration point 明確提供內容時，ExecWeave 可以把**來源實際提供的完整值**存進本機 SHA-256 content-addressed store，而 semantic event stream 只保留 reference。

```text
<run-root>/content/sha256/<sha256>.<json|txt|bin>
```

依 adapter 與上游 hook/API surface 不同，保存內容可能包含 prompt/message、model request/response object、tool input/result、assistant response、上游明確曝露的 reasoning/thinking text、shell/MCP output，以及 provider hook 提供的 file content。

`complete_from_source: true` 只表示 ExecWeave 完整保存了該 integration point 提供的值；**不代表** ExecWeave 看到了 hidden model state、provider 未曝露的內部階段、未觀察到的最終 wire request，或任何沒有被攔截/提供的 bytes。

Full fidelity 同時改變 privacy boundary：如果 application-level secret 被放在 content 裡，它會被一併保存。已知 transport credential 只會在 adapter 明確定義的 provider-metadata projection 中被過濾；ExecWeave **不是**通用 secret scanner 或 content redactor。

### 支援的 semantic / inference surface

| Integration | 在 ExecWeave 下啟動時的 OS-runtime observation | Specialized evidence |
| --- | --- | --- |
| Claude Code | Yes | native hooks + full-fidelity hook content + provider 明確曝露的 subagent result |
| OpenAI Codex | Yes | lifecycle hooks + validated rollout transcript + agent-local task/message/final-response routing |
| Google Antigravity / Antigravity CLI | Yes | passive native hooks + 能驗證時的 conversation/subagent routing |
| Cursor | Yes | native hooks + 能取得時的 exact subagent task/summary routing |
| OpenCode | Yes | project plugin + session/task routing + full-fidelity plugin content |
| Ollama | Yes | `execweave-model-runtime event/exchange/probe --runtime ollama` |
| llama.cpp | Yes | `execweave-model-runtime event/exchange/probe --runtime llamacpp` |
| vLLM | Yes | `execweave-model-runtime event/exchange/probe --runtime vllm` |
| LM Studio | 僅限本機 process 由 ExecWeave 啟動 | `execweave-model-runtime event/exchange/probe --runtime lmstudio` |
| LiteLLM Proxy | 已設定 proxy 且由 ExecWeave 啟動時為 Yes | metadata-oriented gateway callback/event integration |
| OpenRouter | 觀察本機 client，不是遠端 service process | `execweave-inference-gateway event/exchange/generation --gateway openrouter` |

OpenRouter `exchange` 是 caller-supplied request+response evidence，不是透明 wire interception。LiteLLM Proxy 在目前 baseline 仍是範圍較窄的 metadata-oriented integration。Provider-neutral conversation projection 不會把缺失的 provider evidence 升級成虛構 agent relationship。

## Evidence layers

ExecWeave 不會把所有訊號壓成一條 trace，而是保留不同 evidence layers：

```text
Agent / IDE semantic + supplied content evidence
          ↓
Inference gateway / routing evidence
          ↓
Model runtime / inference-server evidence
          ↓
OS runtime evidence: process / file / network
```

只有底層 telemetry 真正支援 causal claim 時，relationship 才會標為 causal。Tool → Process bridge 仍是保守的 derived evidence：

```text
inferred: true
causal: false
```

有歧義就不建立 edge。Gateway 與 Model Runtime 之間的 exact shared request identity 仍只是 identity evidence，不是 causal evidence：

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

Provider-integrated recorder 會把 raw runtime、semantic、correlated 與 conversation artifacts 分開保存。Cursor `tool_use_id`、Codex rollout thread identity、OpenCode `sessionID + callID` 這類 stable provider identifier 可以證明 provider 內部的 logical identity，但它們不是 OS PID。只有 provider 明確曝露 route、delegation 或 result 時，跨 agent content 才會被顯示。Legacy Gemini CLI hook entry points 仍保留給既有安裝相容使用；新的 Google CLI 使用方式請改用 Antigravity (`agy`)。

## Inference gateway 與 model runtime

擷取 OpenRouter 或 LiteLLM gateway evidence：

```bash
execweave-inference-gateway event --gateway openrouter --sidecar gateway.jsonl
execweave-inference-gateway event --gateway litellm --sidecar gateway.jsonl
execweave-inference-gateway exchange --gateway openrouter --sidecar gateway.jsonl
```

擷取 Ollama、llama.cpp、vLLM 或 LM Studio 的 model-runtime evidence：

```bash
execweave-model-runtime event --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime exchange --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime probe --runtime ollama --sidecar model-runtime.jsonl
```

`event` 是 response-only evidence；`exchange` 保存 caller-supplied request+response object，不宣稱透明 interception。Runtime catalog relation 保留來源本身的語意：`LOADED_MODEL`、`SERVES_MODEL`、`ADVERTISES_MODEL` 不能互換。LM Studio catalog visibility 仍表示 `ADVERTISES_MODEL`，不代表 model weights 已 resident in memory。

## Security analysis、evidence grades 與 bounded rule packs

執行內建分析：

```bash
execweave analyze run.graph.json --output analysis.json
```

Finding 會顯示獨立於 severity 的 evidence grade。目前 grade 為 `A`、`B`、`C`、`D`、`U`，從直接 syscall attribution 到 inferred/unknown provenance。這些 grade 是 evidence-strength category，**不是 probability，也不是 trust score**。

Local rule pack 可加入 bounded、可解釋的**單一 edge observation** policy，而且不執行第三方程式碼：

```bash
execweave-rule-pack graph.json --rule-pack local-policy.json --output report.json
```

Rule pack 不能執行 code、定義 regex/path program，也不能宣稱 byte-level data flow 或 exfiltration；rule-pack finding 一律維持 observation-only。

Security finding 對較強 claim 仍會明確保留 non-claim：

```json
{
  "data_flow_proven": false,
  "exfiltration_proven": false
}
```

## Run integrity

對已完成的 run 建立 seal，之後驗證 regular-file inventory 是否仍與 seal 一致：

```text
execweave-integrity seal .execweave/runs/<run-id>
execweave-integrity verify .execweave/runs/<run-id>
```

Deterministic manifest 會記錄 file size/SHA-256，並拒絕 symbolic link。封存後若有檔案遺失、修改、替換或新增 regular file，驗證會失敗。

這個 local seal **不是**在 evidence 與 manifest 都位於同一個 writable trust boundary 時的 adversary-resistant tamper evidence。Manifest 明確記錄 `malicious_writer_resistance: false` 與 `external_trust_anchor: false`；需要更強保證時，應把 manifest digest 複製/保護到該 boundary 之外。

## Runtime evidence 與 graph operations

Portable collector 支援 Linux、macOS、Windows。Linux 另有 syscall-backed `strace` reference backend。

```bash
execweave doctor
execweave run --backend portable -- your-command
execweave run --backend strace -- your-command
execweave graph-summary run.graph.json
execweave graph-filter run.graph.json --causal-only --output causal.graph.json
execweave graph-focus run.graph.json NODE_ID --hops 2 --output focused.graph.json
execweave path run.graph.json SOURCE TARGET --causal-only
```

Portable filesystem observation 是 session-correlated，不是 process-causal；polling 也可能漏掉足夠短暫的活動。Linux `strace` 在支援的 execution 上提供較強的 process-attributed syscall evidence。Linux eBPF、Windows ETW、macOS Endpoint Security native collector 仍是未來規劃。

## Performance 與 large-run safety

ExecWeave 具備 bounded filesystem/viewer protection、incremental Live JSONL tailing、large-graph safety guard、detached Top，以及 configured provider integration 使用的 provisional live sidecar。

可重現的 incremental `GraphAccumulator` reference result 在文件化的 GitHub Actions workload 上，1M synthetic events 達到 **164,273 ev/s**。這是 graph accumulation benchmark，不是 end-to-end collector/browser throughput。

請在代表性主機與 workload 上重新跑 package-level overhead benchmark：

```bash
execweave-overhead --iterations 7 --strace auto --output-json benchmark-results.json
execweave-scalability
```

Reference data 與 methodology：[`docs/benchmarks/`](docs/benchmarks/)。

## Layered artifacts

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
└── integrity.json            # explicit seal 後才會出現
```

Derived correlation 不會重寫 raw runtime 或 provider sidecar evidence。

## Privacy

ExecWeave 是 local-first：capture、content blob、graph、report、viewer 預設留在本機。**OS runtime collector** 不會刻意擷取 file content 或 raw read/write byte buffer；但這個邊界不能和 v0.6.9 的 **provider full-fidelity content store** 混為一談。受支援 hook/API 若明確提供 prompt、tool argument/result、model response、reasoning/thinking text、shell output、file content 或其他敏感值，ExecWeave 可以完整保存。

Conversation isolation 是 attribution/display 規則，不是 redaction boundary。如果 provider 明確把 Agent 1 的內容送給 Agent 2，這個 routed evidence 合法地會出現在參與端。不要假設 content 已經過 secret redaction。Command、path、endpoint metadata、identifier、model metadata、prompt、tool value、content blob 都可能敏感；分享前請檢查整個 run directory。

## 目前狀態

v0.7.7 整合 cross-platform runtime collection、materialized execution graph、standalone/live dashboard、保守的 provider↔runtime correlation、content-addressed full-fidelity provider evidence、可歸屬的 multi-agent execution trace、run-local conversation access，provider-neutral projection 上的 agent-local conversation isolation，以及 standalone 與 live dashboard 上的 per-agent conversation focus。各 integration 只保留 provider 實際曝露的最強 identity/routing evidence，證據不足時選擇 abstain。Observed evidence 與 inference 仍從設計上分離。

## 文件

- [`Phase 1 — Runtime Collection`](docs/phase-1-runtime-collection.zh-TW.md)
- [`Phase 2 — Execution Graph`](docs/phase-2-execution-graph.zh-TW.md)
- [`Live Graph`](docs/live-graph.zh-TW.md)
- [`Semantic Telemetry`](docs/semantic-telemetry.zh-TW.md)
- [`Claude Code Hooks`](docs/claude-code-hooks.zh-TW.md)
- [`OpenAI Codex Hooks`](docs/codex-hooks.zh-TW.md)
- [`Google Antigravity Hooks`](docs/antigravity-hooks.md)
- [`Cursor Hooks`](docs/cursor-hooks.zh-TW.md)
- [`OpenCode Plugin`](docs/opencode-plugin.zh-TW.md)
- [`Inference Gateway / OpenRouter / LiteLLM`](docs/inference-gateway.zh-TW.md)
- [`Model Runtime / Ollama / llama.cpp / vLLM / LM Studio`](docs/model-runtime.zh-TW.md)
- [`Runtime Threat Model`](docs/runtime-threat-model.zh-TW.md)
- [`Evidence Grades`](docs/evidence-grades.zh-TW.md)
- [`Rule Packs`](docs/rule-packs.zh-TW.md)
- [`Run Integrity`](docs/run-integrity.zh-TW.md)
- [`Security Analysis`](docs/security-analysis.zh-TW.md)
- [`Performance Benchmarks`](docs/benchmarks/README.md)

## 貢獻

歡迎貢獻，尤其是 native OS collector、Agent/IDE adapter、inference gateway、model runtime、evidence/correlation method、privacy/redaction、graph UX、multi-agent conversation attribution 與 performance evaluation。

## License

從 v0.6.8 起，ExecWeave 採用 **PolyForm Noncommercial License 1.0.0**。依授權條款可進行非商業使用、修改與散布；商業用途需要另外取得授權方的書面商業授權。詳見 [`LICENSE`](LICENSE)。
