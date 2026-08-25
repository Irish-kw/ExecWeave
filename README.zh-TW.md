# ExecWeave

<p align="center">
  <a href="README.md">English</a> |
  <strong>繁體中文</strong> |
  <a href="README.zh-CN.md">简体中文</a> |
  <a href="README.ja.md">日本語</a> |
  <a href="README.ko.md">한국어</a>
</p>

**看見 AI Agent 在你的電腦上實際做了什麼。**

ExecWeave 是一個開源、local-first 的 observability 專案，會把 AI Agent 的活動轉成互動式執行圖，同時把 observed evidence 與 inference 明確分開。

> **Event 是 ground truth；Graph 是 materialized view。**

## 快速開始

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

即時觀察任意 command：

```bash
execweave live --open -- claude
```

或建立完整 artifact pipeline：

```bash
execweave record --open -- python my_agent.py
```

## Evidence layers

ExecWeave 刻意把四種 evidence 分層，而不是壓成同一條 trace：

```text
Agent / IDE semantic evidence
          ↓
Inference gateway / routing evidence
          ↓
Model runtime / inference-server evidence
          ↓
OS runtime evidence: process / file / network
```

只有底層 telemetry 足以支持時，relationship 才會被標成 causal。

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

Cursor 提供穩定的 `tool_use_id`，因此 pre/post hooks 可以共享精確的 logical tool-call identity。

### OpenCode

```bash
execweave-opencode-plugin --install
execweave-opencode-record --open -- opencode
```

Project-local OpenCode plugin 使用精確的 `sessionID + callID`，而且刻意不轉送 tool output。

Provider-integrated run 會把 runtime、semantic、correlated artifacts 分開保存。Tool → Process bridge 仍是保守的 derived evidence：

```text
inferred: true
causal: false
```

候選模糊時不建立 edge。

## Inference Gateway integrations

### OpenRouter

OpenRouter 被建模成 `inference_gateway`，不是 local model runtime。

```bash
execweave-inference-gateway event \
  --gateway openrouter \
  --requested-model openrouter/auto \
  --sidecar gateway.jsonl
```

ExecWeave 會分開保存：

```text
requested model → resolved model → routed provider
```

白名單 metadata 可包含 token counts、cache/reasoning counts、cost 與 generation timing；prompt 與 response content 不會保存。

## Model Runtime integrations

### Ollama

```bash
execweave-model-runtime event --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime probe --runtime ollama --sidecar model-runtime.jsonl
```

### llama.cpp

```bash
execweave-model-runtime event --runtime llamacpp --sidecar model-runtime.jsonl
execweave-model-runtime probe --runtime llamacpp --metrics --sidecar model-runtime.jsonl
```

此層使用 `model_runtime`、`inference_request`、`model` 與 runtime snapshot。只保存選定的 token/timing/load metadata，不保存 prompt 或 generated content。敏感的 llama.cpp 本機 model path 會被 redaction。

未來 vLLM、LM Studio 等 OpenAI-compatible runtime 可重用此層。

## Runtime evidence

Portable collector 支援 Linux、macOS、Windows；Linux 另外有 syscall-backed `strace` reference backend。

```bash
execweave doctor
execweave run --backend portable -- your-command
execweave run --backend strace -- your-command
```

Portable filesystem watching 是 session-correlated，不是 process-causal；短命 process 也可能在 polling interval 間被漏掉。Linux `strace` 則在 command 結束後產生 process-attributed syscall evidence。

未來 native collectors 包含 Linux eBPF、Windows ETW 與 macOS Endpoint Security。

## Layered artifacts

Provider-integrated run 可產生：

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

Derived correlation layer 不會重寫 raw evidence。

## Interactive Viewer

Standalone Viewer 完全 local、自包含，目前包含：

- pan / zoom / draggable nodes
- node / edge inspection
- node-type / relation / causal filters
- **observed only** filter
- search
- evidence-sequence Timeline ↔ Graph replay
- progressive cluster expansion
- 1-hop / 2-hop focused neighborhoods
- browser-local Saved Views
- observed / non-causal / inferred edge styling
- Correlation Summary

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

安全 findings 會保留 evidence limits。Sensitive-file → network 的 possible path 不代表 byte-level exfiltration：

```json
{
  "data_flow_proven": false,
  "exfiltration_proven": false
}
```

## 目前狀態

ExecWeave 目前為 **v0.5.0**，持續開發中。

目前 baseline 已包含 runtime collection、Graph materialization/query、standalone/live Viewer、Claude/Codex/Gemini/Cursor/OpenCode native semantic integrations、保守 Tool → Process correlation、OpenRouter gateway metadata、Ollama/llama.cpp runtime metadata，以及 Python 3.10/3.12 的跨平台 CI。

## 隱私

ExecWeave 是 local-first。Runtime events、semantic sidecars、graphs、reports 與 Viewers 預設都留在本機。專案不刻意擷取 file content 或 raw read/write byte buffers；native adapters 也預設避開 prompt/transcript/tool output，但 command、path、endpoint metadata、identifier 與 model metadata 本身仍可能敏感。

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
- [`Inference Gateway / OpenRouter`](docs/inference-gateway.zh-TW.md)
- [`Model Runtime / Ollama / llama.cpp`](docs/model-runtime.zh-TW.md)
- [`Security Analysis`](docs/security-analysis.zh-TW.md)

## Contributing

歡迎貢獻，尤其是 native OS collectors、更多 Agent/IDE adapters、inference gateways、OpenAI-compatible model runtimes、entity/correlation methods、privacy/redaction、Graph UX 與 performance evaluation。

## License

請參閱 [`LICENSE`](LICENSE)。