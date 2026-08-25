# ExecWeave

<p align="center">
  <a href="README.md">English</a> |
  <a href="README.zh-TW.md">繁體中文</a> |
  <strong>简体中文</strong> |
  <a href="README.ja.md">日本語</a> |
  <a href="README.ko.md">한국어</a>
</p>

**看见 AI Agent 在你的电脑上实际做了什么。**

ExecWeave 是一个开源、local-first 的 observability 项目，会把 AI Agent 活动转成互动式执行图，同时明确区分 observed evidence 与 inference。

> **Event 是 ground truth；Graph 是 materialized view。**

## 快速开始

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

实时观察任意 command：

```bash
execweave live --open -- claude
```

或建立完整 artifact pipeline：

```bash
execweave record --open -- python my_agent.py
```

## Evidence layers

ExecWeave 刻意把四类 evidence 分层，而不是压成同一条 trace：

```text
Agent / IDE semantic evidence
          ↓
Inference gateway / routing evidence
          ↓
Model runtime / inference-server evidence
          ↓
OS runtime evidence: process / file / network
```

只有底层 telemetry 足以支持时，relationship 才会被标记为 causal。

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

Cursor 提供稳定的 `tool_use_id`，因此 pre/post hooks 可以共享精确的 logical tool-call identity。

### OpenCode

```bash
execweave-opencode-plugin --install
execweave-opencode-record --open -- opencode
```

Project-local OpenCode plugin 使用精确的 `sessionID + callID`，并且刻意不转发 tool output。

Provider-integrated run 会把 runtime、semantic、correlated artifacts 分开保存。Tool → Process bridge 仍是保守的 derived evidence：

```text
inferred: true
causal: false
```

候选模糊或无 match 时不建立 edge。

## Inference Gateway integrations

当前支持 **OpenRouter** 与 **LiteLLM Proxy**。Gateway 被建模为 `inference_gateway`，而不是 local model runtime。

### OpenRouter

```bash
execweave-inference-gateway event \
  --gateway openrouter \
  --requested-model openrouter/auto \
  --provider-name OpenAI \
  --sidecar gateway.jsonl
```

### LiteLLM Proxy

```bash
execweave-inference-gateway event \
  --gateway litellm \
  --requested-model assistant \
  --resolved-model azure/gpt-5 \
  --provider-name Azure \
  --deployment-id deployment-west \
  --sidecar gateway.jsonl
```

ExecWeave 会分别保存：

```text
requested model → resolved model → routed provider → deployment
```

Provider 与 deployment 只有在 caller/adapter 拥有明确 routing metadata 时才建立；ExecWeave 不会从 `azure/...` 之类的 model string 自行推测。Gateway events 保持 `causal: false`。Prompt、response、reasoning content 不保存。

## Model Runtime integrations

当前支持 **Ollama**、**llama.cpp**、**vLLM** 与 **LM Studio**。

```bash
execweave-model-runtime event --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime llamacpp --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime vllm --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime lmstudio --sidecar model-runtime.jsonl
```

```bash
execweave-model-runtime probe --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime probe --runtime llamacpp --metrics --sidecar model-runtime.jsonl
execweave-model-runtime probe --runtime vllm --sidecar model-runtime.jsonl
execweave-model-runtime probe --runtime lmstudio --sidecar model-runtime.jsonl
```

llama.cpp、vLLM、LM Studio 共用 OpenAI-compatible response/usage 与 `/v1/models` catalog parser；runtime-specific metadata 仍保留在各自 adapter。vLLM catalog 使用 `SERVES_MODEL`，LM Studio catalog 使用 `ADVERTISES_MODEL`，不会因为 model 出现在 catalog 就宣称它已经加载到内存。敏感的本机 model path 会进行 redaction，llama.cpp GGUF path 保持更严格处理。

## Runtime evidence

Portable collector 支持 Linux、macOS、Windows；Linux 另有 syscall-backed `strace` reference backend。

```bash
execweave doctor
execweave run --backend portable -- your-command
execweave run --backend strace -- your-command
```

Portable filesystem watching 是 session-correlated，而不是 process-causal；短命 process 也可能在 polling interval 之间被漏掉。Linux `strace` 会在 command 结束后产生 process-attributed syscall evidence。

未来 native collectors 包括 Linux eBPF、Windows ETW 和 macOS Endpoint Security。

## Layered artifacts

Provider-integrated run 可产生 runtime、semantic 与 correlated artifacts；Derived correlation layer 不会重写 raw evidence。

## Interactive Viewer

Standalone Viewer 完全 local、自包含，目前包括 pan/zoom、node/edge inspection、filters、**observed only**、search、Timeline ↔ Graph replay、progressive cluster expansion、1/2-hop focus、Saved Views、observed/non-causal/inferred styling 与 Correlation Summary。

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

安全 findings 会保留 evidence limits。Sensitive-file → network 的 possible path 不代表 byte-level exfiltration。

## 当前状态

ExecWeave 当前为 **v0.5.0**，持续开发中。

Baseline 已包括 runtime collection、Graph materialization/query、standalone/live Viewer、Claude/Codex/Gemini/Cursor/OpenCode native semantic integrations、保守 Tool → Process correlation、OpenRouter/LiteLLM gateway metadata、Ollama/llama.cpp/vLLM/LM Studio runtime metadata，以及跨平台 CI。

## 隐私

ExecWeave 是 local-first。Runtime events、semantic sidecars、graphs、reports 与 Viewers 默认留在本机。项目不刻意采集 file content 或 raw read/write byte buffers；native adapters 也默认避开 prompt/transcript/tool output，但 command、path、endpoint metadata、identifier 与 model metadata 本身仍可能敏感。

分享 artifacts 前请检查。

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
- [`Security Analysis`](docs/security-analysis.zh-CN.md)

## Contributing

欢迎贡献，尤其是 native OS collectors、更多 Agent/IDE adapters、inference gateways、OpenAI-compatible model runtimes、entity/correlation methods、privacy/redaction、Graph UX 与 performance evaluation。

## License

请参阅 [`LICENSE`](LICENSE)。