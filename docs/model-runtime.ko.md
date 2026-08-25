# Model Runtime Integrations

<p align="center">
  <a href="model-runtime.md">English</a> |
  <a href="model-runtime.zh-TW.md">繁體中文</a> |
  <a href="model-runtime.zh-CN.md">简体中文</a> |
  <a href="model-runtime.ja.md">日本語</a> |
  <strong>한국어</strong>
</p>

Model Runtime은 Agent/IDE semantic adapter와 다른 계층입니다. Ollama, llama.cpp, vLLM 같은 server는 inference를 실행하며 Tool이나 Agent로 취급하지 않습니다.

현재 baseline은 **Ollama**와 **llama.cpp**를 지원합니다.

## CLI

Final response metadata를 inference events로 변환합니다.

```bash
execweave-model-runtime event --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime llamacpp --sidecar model-runtime.jsonl
```

Runtime state를 snapshot 합니다.

```bash
execweave-model-runtime probe --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime probe --runtime llamacpp --metrics --sidecar model-runtime.jsonl
```

기본 endpoint는 Ollama `http://localhost:11434`, llama.cpp `http://localhost:8080`입니다.

## Graph model

Runtime layer는 다음 관계를 만들 수 있습니다.

```text
model_runtime --SERVED_INFERENCE--> inference_request
inference_request --USED_MODEL--> model
model_runtime --LOADED_MODEL--> model
model_runtime --SERVES_MODEL--> model
model_runtime --REPORTED_METRICS--> model_runtime_snapshot
```

## Ollama

Final response metadata에서 prompt/completion token counts, load duration, prompt-evaluation duration, generation duration, finish reason을 기록할 수 있습니다.

`/api/ps` snapshot은 loaded model의 VRAM size, context length, format, family, parameter size, quantization metadata를 제공합니다.

## llama.cpp

OpenAI-compatible response에서 usage와 timing/throughput metadata를 기록할 수 있습니다. `/v1/models`는 served models를 설명하고 `/metrics`가 활성화된 경우 aggregate runtime metrics를 추가합니다.

Prometheus label에는 민감한 local model path 등이 포함될 수 있으므로 baseline은 label이 있는 metric line을 건너뜁니다.

llama.cpp model ID가 local path 또는 GGUF filename처럼 보이면 전체 native identifier는 hash-based entity identity에만 사용하고 Graph에는 basename만 표시합니다.

## 프라이버시 경계

Prompt text, response content, thinking/reasoning text, choices, logprobs, raw generated tokens는 이 layer에서 저장하지 않습니다.

Aggregate runtime metrics를 특정 Agent나 inference request에 자동 귀속하지도 않습니다.

## Evidence boundary

Runtime API가 증명하는 것은 inference server가 보고한 정보입니다. 어떤 Agent가 request를 시작했는지는 단독으로 증명할 수 없습니다. Cross-layer request identity에는 명시적 shared identifier 또는 별도로 정의된 보수적 correlation이 필요합니다.