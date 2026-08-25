# Model Runtime Integrations

<p align="center">
  <a href="model-runtime.md">English</a> |
  <a href="model-runtime.zh-TW.md">繁體中文</a> |
  <a href="model-runtime.zh-CN.md">简体中文</a> |
  <strong>日本語</strong> |
  <a href="model-runtime.ko.md">한국어</a>
</p>

Model Runtime は Agent/IDE semantic adapter や Inference Gateway とは別の層です。local / self-hosted inference server 自身が報告する情報を表し、どの Agent が request を開始したかを単独では証明しません。

現在の baseline は **Ollama**、**llama.cpp**、**vLLM**、**LM Studio** をサポートします。

## CLI

Final response metadata を inference events に変換します。

```bash
execweave-model-runtime event --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime llamacpp --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime vllm --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime lmstudio --sidecar model-runtime.jsonl
```

Runtime state / model catalog を probe します。

```bash
execweave-model-runtime probe --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime probe --runtime llamacpp --metrics --sidecar model-runtime.jsonl
execweave-model-runtime probe --runtime vllm --sidecar model-runtime.jsonl
execweave-model-runtime probe --runtime lmstudio --sidecar model-runtime.jsonl
```

既定 endpoint：

- Ollama: `http://localhost:11434`
- llama.cpp: `http://localhost:8080`
- vLLM: `http://localhost:8000`
- LM Studio: `http://localhost:1234`

## OpenAI-compatible shared layer

llama.cpp、vLLM、LM Studio は final response usage と `/v1/models` catalog metadata のために同じ OpenAI-compatible parser を再利用します。Chat Completions の `prompt_tokens` / `completion_tokens` と Responses の `input_tokens` / `output_tokens` を正規化し、cached-token や reasoning-token count など whitelist metadata のみ保持します。

Runtime-specific evidence は shared parser に押し込みません。llama.cpp は独自の timing fields と Prometheus metrics adapter を保持します。

## Graph model

```text
model_runtime --SERVED_INFERENCE--> inference_request
inference_request --USED_MODEL--> model
model_runtime --LOADED_MODEL--> model
model_runtime --SERVES_MODEL--> model
model_runtime --ADVERTISES_MODEL--> model
model_runtime --REPORTED_METRICS--> model_runtime_snapshot
```

これらの relation は意図的に異なる evidence semantics を持ちます。

## Ollama

Final response metadata から prompt/completion token counts、load duration、prompt-evaluation duration、generation duration、finish reason を取得できます。

`/api/ps` は現在 loaded な model を報告するため、VRAM size、context length、format、family、parameter size、quantization などを `LOADED_MODEL` として表します。

## llama.cpp

OpenAI-compatible response から normalized usage と llama.cpp 固有 timing/throughput metadata を記録します。`/v1/models` は `SERVES_MODEL`、optional `/metrics` は aggregate runtime metrics を提供します。

Prometheus label には sensitive local model path 等が含まれる可能性があるため、label 付き metric line はスキップします。local path / GGUF filename に見える model ID は、安全な表示名だけを残し、完全な identifier は hash-based entity identity にのみ利用します。

## vLLM

vLLM は OpenAI-compatible response / model-catalog layer を再利用します。`/v1/models` はその serving endpoint が公開する model を示す `SERVES_MODEL` として扱います。

Prompt、response、reasoning text、choices、logprobs、generated token text は保存しません。

## LM Studio

LM Studio も同じ OpenAI-compatible response parser を使いますが、`/v1/models` は `LOADED_MODEL` ではなく `ADVERTISES_MODEL` として扱います。

これは意図的な区別です。LM Studio は downloaded model を server catalog に表示でき、設定によっては on-demand load も可能です。そのため catalog entry だけでは observation 時点で model weights が memory resident だったとは証明できません。

## プライバシー境界

Prompt text、response content、thinking/reasoning text、choices、logprobs、raw generated tokens は保存しません。

Whitelist metadata には model/request identity、prompt/input token counts、completion/output token counts、total tokens、cached-token counts、reasoning-token counts、runtime-specific timing metadata を含められます。supported local OpenAI-compatible runtime の absolute model path は redact し、llama.cpp の GGUF path はより厳格に処理します。

Aggregate runtime metrics を特定の Agent / inference request に自動帰属させません。

## Evidence boundary

Runtime API が証明するのは inference server 自身が報告した情報だけです。どの Agent が request を開始したか、どの gateway が routing したか、どの OS process が原因かは単独では証明できません。

Cross-layer identity には明示的 shared identifier または別途定義された conservative correlation が必要です。Derived correlation は inference として表示し、causal evidence として表現してはいけません。