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

ExecWeave 是一個開源、local-first 的可觀測性專案，會把 AI Agent 活動轉成互動式 execution graph，並明確區分 observed evidence、provider content 與 derived inference。

> **Event 是 ground truth；Graph 是 materialized view。**

<p align="center">
  <img src="docs/assets/execweave-launch-demo-v5-x.gif" alt="ExecWeave animated live demo" width="100%">
</p>

## 安裝

從 PyPI 安裝最新已發布的 wheel/sdist：

```bash
python -m pip install -U execweave
```

目前 `main` 的套件版本是 **v0.6.5**。正式 release 可能晚於 main；若要測試目前 mainline：

```bash
python -m pip install --upgrade --force-reinstall "execweave @ git+https://github.com/Irish-kw/ExecWeave.git@main"
```

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
execweave live --open -- gemini
execweave live --open -- cursor
execweave live --open -- opencode
execweave live --open -- ollama serve
execweave live --open -- python my_agent.py
```

或建立完整 finalized artifact pipeline：

```bash
execweave record --open -- python my_agent.py
```

`execweave top -- codex` 會讓 Agent 保持在啟動 terminal 中互動，並依主機環境開啟或附加 detached Top dashboard。

## v0.6.5：full-fidelity observability 與明確 evidence boundary

v0.6.5 不再只保留精簡 metadata。當受支援的 integration point 明確提供內容時，ExecWeave 可以把**來源實際提供的完整值**存進本機 SHA-256 content-addressed store，而 semantic event stream 只保留 reference。

```text
<run-root>/content/sha256/<sha256>.<json|txt|bin>
```

依 adapter 與上游 hook/API surface 不同，保存內容可能包含 prompt/message、model request/response object、tool input/result、上游明確曝露的 reasoning/thinking text、shell/MCP output，以及 provider hook 提供的 file content。

`complete_from_source: true` 只表示 ExecWeave 完整保存了該 integration point 提供的值；**不代表** ExecWeave 看到了 hidden model state、provider 未曝露的內部階段、未觀察到的最終 wire request，或任何沒有被攔截/提供的 bytes。

Full fidelity 同時改變 privacy boundary：如果 application-level secret 被放在 content 裡，它會被一併保存。已知 transport credential 只會在 adapter 明確定義的 provider-metadata projection 中被過濾；ExecWeave **不是**通用 secret scanner 或 content redactor。

### 支援的 semantic / inference surface

| Integration | 在 ExecWeave 下啟動時的 OS-runtime observation | Specialized evidence |
| --- | --- | --- |
| Claude Code | Yes | native hooks + hook 明確提供的 full-fidelity content |
| OpenAI Codex | Yes | lifecycle hooks + hook 明確提供的 full-fidelity content |
| Gemini CLI | Yes | native hooks + hook 明確提供的 full-fidelity content |
| Cursor | Yes | native hooks + hook 明確提供的 full-fidelity content |
| OpenCode | Yes | project plugin + plugin 明確提供的 full-fidelity content |
| Ollama | Yes | `execweave-model-runtime event/exchange/probe --runtime ollama` |
| llama.cpp | Yes | `execweave-model-runtime event/exchange/probe --runtime llamacpp` |
| vLLM | Yes | `execweave-model-runtime event/exchange/probe --runtime vllm` |
| LM Studio | 僅限本機 process 由 ExecWeave 啟動 | `execweave-model-runtime event/exchange/probe --runtime lmstudio` |
| LiteLLM Proxy | 已設定 proxy 且由 ExecWeave 啟動時為 Yes | 目前為 metadata-oriented gateway callback/event integration |
| OpenRouter | 觀察本機 client，不是遠端 service process | `execweave-inference-gateway event/exchange/generation --gateway openrouter` |

OpenRouter `exchange` 是 caller-supplied request+response evidence，不是透明 wire interception。LiteLLM Proxy 在目前 baseline 仍是範圍較窄的 metadata-oriented integration。

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

execweave-gemini-hook --print-config
execweave-gemini-record --open -- gemini

execweave-cursor-hook --print-config
execweave-cursor-record --open -- cursor

execweave-opencode-plugin --install
execweave-opencode-record --open -- opencode
```

Provider-integrated recorder 會把 raw runtime、semantic 與 correlated artifacts 分開保存。Cursor `tool_use_id` 或 OpenCode `sessionID + callID` 這類 provider stable identifier 可以證明 provider 內部的 logical identity，但它們不是 OS PID。

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
execweave graph-focus run.graph.json NODE_ID --hops 2 --output focused.graph.json
execweave path run.graph.json SOURCE TARGET --causal-only
```

Portable filesystem observation 是 session-correlated，不是 process-causal；polling 也可能漏掉足夠短暫的活動。Linux `strace` 在支援的 execution 上提供較強的 process-attributed syscall evidence。Linux eBPF、Windows ETW、macOS Endpoint Security native collector 仍是未來規劃。

## Performance 與 large-run safety

v0.6.3 加入 bounded filesystem/viewer protection、incremental Live JSONL tailing 與 large-graph safety guard；v0.6.4 加入 detached Top，以及 configured provider integration 共用的 provisional live sidecar。這些能力都保留在 v0.6.5。這次 release **沒有**僅為架構替換而把 Live 遷移到 SSE、artifact storage 改成 SQLite、renderer 改成 Canvas/WebGL，或把 collector 改寫成 Rust。

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

ExecWeave 是 local-first：capture、content blob、graph、report、viewer 預設留在本機。**OS runtime collector** 不會刻意擷取 file content 或 raw read/write byte buffer；但這個邊界不能和 v0.6.5 的 **provider full-fidelity content store** 混為一談。受支援 hook/API 若明確提供 prompt、tool argument/result、model response、reasoning/thinking text、shell output、file content 或其他敏感值，ExecWeave 可以完整保存。

不要假設 content 已經過 secret redaction。Command、path、endpoint metadata、identifier、model metadata、prompt、tool value、content blob 都可能敏感；分享前請檢查整個 run directory。

## 目前狀態

ExecWeave `main` 目前是 **v0.6.5**，正在進行 release hardening。最新公開 package/release 可能會晚於 main；只有明確發布 GitHub Release 才會觸發 publish workflow，而且 workflow 會先驗證 release tag 與 package version 完全一致再上傳 PyPI。

v0.6.5 整合 cross-platform runtime collection、materialized execution graph、standalone/live viewer、保守的 provider↔runtime correlation、content-addressed full-fidelity provider evidence、evidence grades、bounded rule packs、明確的 runtime threat/fidelity contract，以及誠實定義信任邊界的 local run-integrity sealing。Observed evidence 與 inference 仍從設計上分離。

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
- [`Runtime Threat Model`](docs/runtime-threat-model.zh-TW.md)
- [`Evidence Grades`](docs/evidence-grades.zh-TW.md)
- [`Rule Packs`](docs/rule-packs.zh-TW.md)
- [`Run Integrity`](docs/run-integrity.zh-TW.md)
- [`Security Analysis`](docs/security-analysis.zh-TW.md)
- [`Performance Benchmarks`](docs/benchmarks/README.md)

## 貢獻

歡迎貢獻，尤其是 native OS collector、Agent/IDE adapter、inference gateway、model runtime、evidence/correlation method、privacy/redaction、graph UX 與 performance evaluation。

## License

請見 [`LICENSE`](LICENSE)。
