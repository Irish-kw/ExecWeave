# ExecWeave

<p align="center">
  <a href="README.md">English</a> |
  <a href="README.zh-TW.md">繁體中文</a> |
  <a href="README.zh-CN.md">简体中文</a> |
  <a href="README.ja.md">日本語</a> |
  <strong>한국어</strong>
</p>

**AI 에이전트가 실제로 머신에서 무엇을 했는지 확인하세요.**

ExecWeave는 AI 에이전트 활동을 인터랙티브 실행 그래프로 변환하는 로컬 우선 오픈소스 observability 프로젝트입니다. 관측된 evidence와 inference를 명확히 분리합니다.

> **Event is ground truth. The graph is a materialized view.**

## Quick start

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

아무 명령이나 live로 관찰:

```bash
execweave live --open -- claude
```

전체 artifact pipeline:

```bash
execweave record --open -- python my_agent.py
```

## Evidence layers

ExecWeave는 서로 다른 evidence를 하나의 trace로 평탄화하지 않고 다음 계층으로 모델링합니다:

```text
Agent / IDE semantic evidence
          ↓
Inference gateway / routing evidence
          ↓
Model runtime / inference-server evidence
          ↓
OS runtime evidence: process / file / network
```

관계가 causal이라고 표시되는 것은 기반 telemetry가 그 주장을 직접 뒷받침할 때뿐입니다.

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

Cursor의 안정적인 `tool_use_id`를 사용해 pre/post hook 사이의 exact logical tool-call identity를 유지합니다.

### OpenCode

```bash
execweave-opencode-plugin --install
execweave-opencode-record --open -- opencode
```

project-local plugin은 exact `sessionID + callID`를 사용하며 tool output을 전달하지 않습니다.

Provider-integrated run은 runtime / semantic / correlated artifact를 분리해 보존합니다. Tool → Process bridge는 보수적인 derived evidence입니다:

```text
inferred: true
causal: false
```

ambiguous 또는 no-match이면 edge를 만들지 않습니다.

## Inference gateway integrations

현재 **OpenRouter**와 **LiteLLM Proxy**를 지원합니다. Gateway는 local model runtime이 아니라 `inference_gateway`로 모델링됩니다.

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

ExecWeave는 다음을 서로 다른 evidence로 유지합니다:

```text
requested model → resolved model → routed provider → deployment
```

Provider / deployment edge는 authoritative routing metadata가 있을 때만 생성합니다. `azure/...` 같은 model string에서 provider나 deployment를 추측하지 않습니다. Gateway events는 `causal: false`로 유지됩니다. Prompt, response, reasoning content는 저장하지 않습니다.

## Model runtime integrations

현재 **Ollama**, **llama.cpp**, **vLLM**, **LM Studio**를 지원합니다.

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

llama.cpp, vLLM, LM Studio는 OpenAI-compatible response/usage와 `/v1/models` catalog parser를 공유하지만 runtime-specific metadata는 각 adapter에 남깁니다. vLLM catalog는 `SERVES_MODEL`, LM Studio catalog는 `ADVERTISES_MODEL`을 사용하므로 catalog에 존재한다는 사실만으로 loaded model이라고 주장하지 않습니다. 민감한 local model path는 redact하며 llama.cpp GGUF path는 더 엄격하게 처리합니다.

## Runtime evidence

portable collector는 Linux / macOS / Windows에서 동작하고, Linux에는 syscall-backed `strace` reference backend도 있습니다.

```bash
execweave doctor
execweave run --backend portable -- your-command
execweave run --backend strace -- your-command
```

portable filesystem event는 process-causal이 아니라 session-correlated입니다. 짧게 실행되는 process는 polling interval 사이에서 놓칠 수 있습니다. Linux `strace` path는 command 종료 후 process-attributed syscall evidence를 생성합니다.

## Interactive Viewer

Standalone Viewer는 로컬 self-contained입니다. 현재 baseline에는 pan/zoom, node/edge inspection, filters, **observed only**, search, Timeline ↔ Graph replay, progressive cluster expansion, 1/2-hop focus, Saved Views, observed/non-causal/inferred styling, Correlation Summary가 포함됩니다.

## Security analysis

```bash
execweave analyze run.graph.json --output analysis.json
```

sensitive-file → network 가능성은 byte-level exfiltration 증명이 아닙니다:

```json
{
  "data_flow_proven": false,
  "exfiltration_proven": false
}
```

## Current status

ExecWeave는 현재 **v0.5.0**이며 active development 중입니다.

runtime collection, graph materialization/query, standalone/live Viewer, Claude/Codex/Gemini/Cursor/OpenCode semantic integration, conservative Tool → Process correlation, OpenRouter/LiteLLM gateway metadata, Ollama/llama.cpp/vLLM/LM Studio runtime metadata, cross-platform CI가 baseline으로 구현되어 있습니다.

## Privacy

ExecWeave는 local-first입니다. runtime events, semantic sidecars, graphs, reports, Viewers는 기본적으로 로컬에 남습니다. native adapters는 prompt/transcript/tool output을 기본적으로 저장하지 않습니다. 다만 command, path, endpoint metadata, identifier, model metadata는 민감할 수 있습니다.

공유 전 artifact를 검토하세요.

## Documentation

- [`Phase 1 — Runtime Collection`](docs/phase-1-runtime-collection.ko.md)
- [`Phase 2 — Execution Graph`](docs/phase-2-execution-graph.ko.md)
- [`Live Graph`](docs/live-graph.ko.md)
- [`Semantic Telemetry`](docs/semantic-telemetry.ko.md)
- [`Claude Code Hooks`](docs/claude-code-hooks.ko.md)
- [`OpenAI Codex Hooks`](docs/codex-hooks.ko.md)
- [`Gemini CLI Hooks`](docs/gemini-hooks.ko.md)
- [`Cursor Hooks`](docs/cursor-hooks.ko.md)
- [`OpenCode Plugin`](docs/opencode-plugin.ko.md)
- [`Inference Gateway / OpenRouter / LiteLLM`](docs/inference-gateway.ko.md)
- [`Model Runtime / Ollama / llama.cpp / vLLM / LM Studio`](docs/model-runtime.ko.md)
- [`Security Analysis`](docs/security-analysis.ko.md)

## Contributing

native OS collector, 추가 Agent/IDE adapter, inference gateway, OpenAI-compatible runtime, correlation, privacy/redaction, graph UX, performance evaluation 기여를 환영합니다.

## License

[`LICENSE`](LICENSE)를 참조하세요.