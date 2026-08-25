# ExecWeave

<p align="center">
  <a href="README.md">English</a> |
  <a href="README.zh-TW.md">繁體中文</a> |
  <a href="README.zh-CN.md">简体中文</a> |
  <strong>日本語</strong> |
  <a href="README.ko.md">한국어</a>
</p>

**AI エージェントが実際にマシン上で何をしたのかを見る。**

ExecWeave は、AI エージェントの活動をインタラクティブな実行グラフへ変換する、ローカルファーストのオープンソース observability プロジェクトです。観測された evidence と inference を明確に分離します。

> **Event is ground truth. The graph is a materialized view.**

## Quick start

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

任意のコマンドを live で観測：

```bash
execweave live --open -- claude
```

完全な artifact pipeline：

```bash
execweave record --open -- python my_agent.py
```

## Evidence layers

ExecWeave は異なる evidence を一つの trace に潰さず、次の層として扱います：

```text
Agent / IDE semantic evidence
          ↓
Inference gateway / routing evidence
          ↓
Model runtime / inference-server evidence
          ↓
OS runtime evidence: process / file / network
```

関係を causal とするのは、基礎 telemetry がその主張を直接支える場合だけです。

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

Cursor の安定した `tool_use_id` を使い、pre/post hook 間で exact logical tool-call identity を保ちます。

### OpenCode

```bash
execweave-opencode-plugin --install
execweave-opencode-record --open -- opencode
```

project-local plugin は exact `sessionID + callID` を使い、tool output は転送しません。

Provider-integrated run では runtime / semantic / correlated artifact を別々に保存します。Tool → Process bridge は保守的な derived evidence です：

```text
inferred: true
causal: false
```

ambiguous / no-match の場合は edge を作りません。

## Inference gateway integrations

現在は **OpenRouter** と **LiteLLM Proxy** をサポートします。Gateway は local model runtime ではなく `inference_gateway` として扱います。

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

ExecWeave は次を別々の evidence として保持します：

```text
requested model → resolved model → routed provider → deployment
```

Provider / deployment edge は authoritative routing metadata がある場合だけ生成します。`azure/...` のような model string から provider や deployment を推測しません。Gateway events は `causal: false` のままです。Prompt、response、reasoning content は保存しません。

## Model runtime integrations

現在は **Ollama**、**llama.cpp**、**vLLM**、**LM Studio** をサポートします。

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

llama.cpp、vLLM、LM Studio は OpenAI-compatible response/usage と `/v1/models` catalog parser を共有しますが、runtime-specific metadata は各 adapter に残します。vLLM catalog は `SERVES_MODEL`、LM Studio catalog は `ADVERTISES_MODEL` であり、catalog に存在するだけで loaded model とは見なしません。Sensitive local model path は redact され、llama.cpp の GGUF path はより厳格に処理します。

## Runtime evidence

portable collector は Linux / macOS / Windows で動作し、Linux には syscall-backed `strace` reference backend もあります。

```bash
execweave doctor
execweave run --backend portable -- your-command
execweave run --backend strace -- your-command
```

portable filesystem event は process-causal ではなく session-correlated です。短命 process は polling interval の間に見逃す場合があります。Linux `strace` path は command 終了後に process-attributed syscall evidence を生成します。

## Interactive Viewer

Standalone Viewer はローカル・self-contained です。現在の baseline には pan / zoom、node/edge inspection、filters、**observed only**、search、Timeline ↔ Graph replay、progressive cluster expansion、1/2-hop focus、Saved Views、observed/non-causal/inferred styling、Correlation Summary が含まれます。

## Security analysis

```bash
execweave analyze run.graph.json --output analysis.json
```

sensitive-file → network の可能性は byte-level exfiltration の証明ではありません：

```json
{
  "data_flow_proven": false,
  "exfiltration_proven": false
}
```

## Current status

ExecWeave は現在 **v0.5.0** で、active development 中です。

runtime collection、graph materialization/query、standalone/live Viewer、Claude/Codex/Gemini/Cursor/OpenCode semantic integration、conservative Tool → Process correlation、OpenRouter/LiteLLM gateway metadata、Ollama/llama.cpp/vLLM/LM Studio runtime metadata、cross-platform CI が baseline として実装されています。

## Privacy

ExecWeave は local-first です。runtime events、semantic sidecars、graphs、reports、Viewers は既定でローカルに残ります。native adapters は prompt/transcript/tool output を既定で保存しません。ただし command、path、endpoint metadata、identifier、model metadata は sensitive な場合があります。

共有前に artifact を確認してください。

## Documentation

- [`Phase 1 — Runtime Collection`](docs/phase-1-runtime-collection.ja.md)
- [`Phase 2 — Execution Graph`](docs/phase-2-execution-graph.ja.md)
- [`Live Graph`](docs/live-graph.ja.md)
- [`Semantic Telemetry`](docs/semantic-telemetry.ja.md)
- [`Claude Code Hooks`](docs/claude-code-hooks.ja.md)
- [`OpenAI Codex Hooks`](docs/codex-hooks.ja.md)
- [`Gemini CLI Hooks`](docs/gemini-hooks.ja.md)
- [`Cursor Hooks`](docs/cursor-hooks.ja.md)
- [`OpenCode Plugin`](docs/opencode-plugin.ja.md)
- [`Inference Gateway / OpenRouter / LiteLLM`](docs/inference-gateway.ja.md)
- [`Model Runtime / Ollama / llama.cpp / vLLM / LM Studio`](docs/model-runtime.ja.md)
- [`Security Analysis`](docs/security-analysis.ja.md)

## Contributing

native OS collector、追加 Agent/IDE adapter、inference gateway、OpenAI-compatible runtime、correlation、privacy/redaction、graph UX、performance evaluation への貢献を歓迎します。

## License

[`LICENSE`](LICENSE) を参照してください。