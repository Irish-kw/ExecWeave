# Model Runtime Integrations

<p align="center">
  <a href="model-runtime.md">English</a> |
  <a href="model-runtime.zh-TW.md">繁體中文</a> |
  <a href="model-runtime.zh-CN.md">简体中文</a> |
  <strong>日本語</strong> |
  <a href="model-runtime.ko.md">한국어</a>
</p>

Model Runtime は Agent/IDE semantic adapter とは別の層です。Ollama、llama.cpp、vLLM などの server は inference を実行するためのもので、Tool や Agent として扱いません。

現在の baseline は **Ollama** と **llama.cpp** をサポートします。

## CLI

Final response metadata を inference events に変換します。

```bash
execweave-model-runtime event --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime llamacpp --sidecar model-runtime.jsonl
```

Runtime state を snapshot します。

```bash
execweave-model-runtime probe --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime probe --runtime llamacpp --metrics --sidecar model-runtime.jsonl
```

既定 endpoint は Ollama が `http://localhost:11434`、llama.cpp が `http://localhost:8080` です。

## Graph model

Runtime layer は次のような関係を生成できます。

```text
model_runtime --SERVED_INFERENCE--> inference_request
inference_request --USED_MODEL--> model
model_runtime --LOADED_MODEL--> model
model_runtime --SERVES_MODEL--> model
model_runtime --REPORTED_METRICS--> model_runtime_snapshot
```

## Ollama

Final response metadata から prompt/completion token counts、load duration、prompt-evaluation duration、generation duration、finish reason を取得できます。

`/api/ps` snapshot から loaded model の VRAM size、context length、format、family、parameter size、quantization などを記録できます。

## llama.cpp

OpenAI-compatible response から usage と timing/throughput metadata を取得できます。`/v1/models` は served models を示し、`/metrics` が有効な場合は aggregate runtime metrics を取得します。

Prometheus label には機密な local model path などが含まれる可能性があるため、baseline は label 付き metric 行をスキップします。

llama.cpp model ID が local path または GGUF filename に見える場合、完全な native identifier は hash-based entity identity のみに使い、Graph 表示には basename だけを残します。

## プライバシー境界

Prompt text、response content、thinking/reasoning text、choices、logprobs、raw generated tokens はこの layer では保存しません。

Aggregate runtime metrics を特定の Agent や inference request に自動帰属させることもありません。

## Evidence boundary

Runtime API が証明するのは inference server 自身が報告した情報です。どの Agent が request を開始したかは単独では証明できません。Cross-layer request identity には明示的な shared identifier または別途定義された保守的 correlation が必要です。