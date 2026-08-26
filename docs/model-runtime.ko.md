# Model Runtime Integrations

<!-- i18n-nav:start -->
<p align="center">
  <a href="model-runtime.md">English</a> |
  <a href="model-runtime.zh-TW.md">繁體中文</a> |
  <a href="model-runtime.zh-CN.md">简体中文</a> |
  <a href="model-runtime.ja.md">日本語</a> |
  <strong>한국어</strong> |
  <a href="model-runtime.fr.md">Français</a> |
  <a href="model-runtime.de.md">Deutsch</a> |
  <a href="model-runtime.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

Model Runtime은 Agent/IDE semantic adapter 및 Inference Gateway와 다른 계층입니다. local / self-hosted inference server가 스스로 보고한 정보를 표현하며 어떤 Agent가 request를 시작했는지는 단독으로 증명하지 않습니다.

현재 baseline은 **Ollama**, **llama.cpp**, **vLLM**, **LM Studio**를 지원합니다.

## CLI

Final response metadata를 inference events로 변환합니다.

```bash
execweave-model-runtime event --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime llamacpp --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime vllm --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime lmstudio --sidecar model-runtime.jsonl
```

Runtime state / model catalog를 probe합니다.

```bash
execweave-model-runtime probe --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime probe --runtime llamacpp --metrics --sidecar model-runtime.jsonl
execweave-model-runtime probe --runtime vllm --sidecar model-runtime.jsonl
execweave-model-runtime probe --runtime lmstudio --sidecar model-runtime.jsonl
```

기본 endpoint:

- Ollama: `http://localhost:11434`
- llama.cpp: `http://localhost:8080`
- vLLM: `http://localhost:8000`
- LM Studio: `http://localhost:1234`

## OpenAI-compatible shared layer

llama.cpp, vLLM, LM Studio는 final response usage와 `/v1/models` catalog metadata를 위해 하나의 OpenAI-compatible parser를 재사용합니다. Chat Completions의 `prompt_tokens` / `completion_tokens`와 Responses의 `input_tokens` / `output_tokens`를 정규화하고 cached-token, reasoning-token count 같은 whitelist metadata만 유지합니다.

Runtime-specific evidence는 shared parser에 억지로 합치지 않습니다. llama.cpp는 자체 timing fields와 Prometheus metrics adapter를 유지합니다.

## Graph model

```text
model_runtime --SERVED_INFERENCE--> inference_request
inference_request --USED_MODEL--> model
model_runtime --LOADED_MODEL--> model
model_runtime --SERVES_MODEL--> model
model_runtime --ADVERTISES_MODEL--> model
model_runtime --REPORTED_METRICS--> model_runtime_snapshot
```

각 relation은 의도적으로 서로 다른 evidence semantics를 가집니다.

## Ollama

Final response metadata에서 prompt/completion token counts, load duration, prompt-evaluation duration, generation duration, finish reason을 기록할 수 있습니다.

`/api/ps`는 현재 loaded model을 보고하므로 VRAM size, context length, format, family, parameter size, quantization 등을 `LOADED_MODEL`로 표현합니다.

## llama.cpp

OpenAI-compatible response에서 normalized usage와 llama.cpp 전용 timing/throughput metadata를 기록합니다. `/v1/models`는 `SERVES_MODEL`, optional `/metrics`는 aggregate runtime metrics를 제공합니다.

Prometheus label에는 sensitive local model path 등이 포함될 수 있으므로 label이 있는 metric line은 건너뜁니다. local path / GGUF filename처럼 보이는 model ID는 안전한 표시명만 남기고 전체 identifier는 hash-based entity identity에만 사용합니다.

## vLLM

vLLM은 OpenAI-compatible response / model-catalog layer를 재사용합니다. `/v1/models`는 해당 serving endpoint가 제공하는 model을 뜻하는 `SERVES_MODEL`로 표현합니다.

Prompt, response, reasoning text, choices, logprobs, generated token text는 저장하지 않습니다.

## LM Studio

<!-- lmstudio-auto-live-v064 -->
LM Studio를 Live Viewer에 자동으로 넣으려면 명시적인 로컬 port로 ExecWeave 아래에서 실행합니다. 예: `execweave live --open -- lms server start --port 1234`. ExecWeave는 launch 전에 해당 endpoint에 호환 API가 이미 존재하지 않는지 확인하고 launcher가 성공한 경우에만 `/v1/models`를 probe합니다. relation은 `ADVERTISES_MODEL`로 유지되며 catalog entry를 `LOADED_MODEL`로 승격하지 않습니다.

LM Studio도 동일한 OpenAI-compatible response parser를 사용하지만 `/v1/models`는 `LOADED_MODEL`이 아니라 `ADVERTISES_MODEL`로 표현합니다.

이는 의도적인 구분입니다. LM Studio는 downloaded model을 server catalog에 표시할 수 있고 설정에 따라 on-demand load가 가능합니다. 따라서 catalog entry만으로 observation 시점에 model weights가 memory resident였다고 증명할 수 없습니다.

## 프라이버시 경계

Prompt text, response content, thinking/reasoning text, choices, logprobs, raw generated tokens는 저장하지 않습니다.

Whitelist metadata에는 model/request identity, prompt/input token counts, completion/output token counts, total tokens, cached-token counts, reasoning-token counts, runtime-specific timing metadata가 포함될 수 있습니다. supported local OpenAI-compatible runtime의 absolute model path는 redact하고 llama.cpp GGUF path는 더 엄격하게 처리합니다.

Aggregate runtime metrics를 특정 Agent / inference request에 자동 귀속하지 않습니다.

## Evidence boundary

Runtime API가 증명하는 것은 inference server 자체가 보고한 정보뿐입니다. 어떤 Agent가 request를 시작했는지, 어떤 gateway가 routing했는지, 어떤 OS process가 원인인지는 단독으로 증명할 수 없습니다.

Cross-layer identity에는 명시적 shared identifier 또는 별도로 정의된 conservative correlation이 필요합니다. Derived correlation은 inference로 표시해야 하며 causal evidence로 표현해서는 안 됩니다.