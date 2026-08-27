# ExecWeave

<!-- i18n-nav:start -->
<p align="center">
  <a href="README.md">English</a> |
  <a href="README.zh-TW.md">繁體中文</a> |
  <a href="README.zh-CN.md">简体中文</a> |
  <a href="README.ja.md">日本語</a> |
  <strong>한국어</strong> |
  <a href="README.fr.md">Français</a> |
  <a href="README.de.md">Deutsch</a> |
  <a href="README.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

**AI Agent가 내 컴퓨터에서 실제로 무엇을 하는지 확인하세요.**

ExecWeave는 AI Agent 활동을 인터랙티브 execution graph로 변환하면서 observed evidence, provider content, derived inference를 명확히 분리하는 source-available, local-first observability 프로젝트입니다. v0.6.8부터 PolyForm Noncommercial 1.0.0이 적용되며 상업적 사용은 허용되지 않습니다.

> **Event가 ground truth이고, Graph는 materialized view입니다.**

<p align="center">
  <img src="docs/assets/codex.gif" alt="ExecWeave animated live demo" width="100%">
</p>

## 설치

PyPI에서 최신 공개 wheel/sdist를 설치합니다.

```bash
python -m pip install -U execweave
```

현재 `main`의 package version은 **v0.6.8**입니다. 공개 release가 main보다 늦을 수 있습니다. 현재 mainline을 직접 테스트하려면:

```bash
python -m pip install --upgrade --force-reinstall "execweave @ git+https://github.com/Irish-kw/ExecWeave.git@main"
```

개발 설치:

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

## 빠른 시작

Live OS-runtime telemetry는 **모든 로컬 명령**에 사용할 수 있습니다. 아래 Agent/runtime 이름은 예시일 뿐 whitelist가 아닙니다.

```bash
execweave live --open -- claude
execweave live --open -- codex
execweave live --open -- antigravity
execweave live --open -- cursor
execweave live --open -- opencode
execweave live --open -- ollama serve
execweave live --open -- python my_agent.py
```

> **Hook 권한 요청이 표시되면 승인하세요.** 처음 provider-integrated run을 실행할 때 Agent/IDE가 ExecWeave의 로컬 Hook integration을 허용할지 물을 수 있습니다. **Allow / Yes**를 선택하세요. 승인하지 않아도 OS-runtime telemetry는 동작할 수 있지만 provider-level tool, model, supplied-content observability는 제한되거나 사용할 수 없게 됩니다.

Google Antigravity는 현재 `agy` CLI를 사용합니다. ExecWeave는 `antigravity`를 friendly alias로 받아 `agy`로 해석합니다. Cursor의 `execweave live --open -- cursor`는 먼저 PATH launcher를 사용하고, 없으면 macOS/Windows의 표준 Cursor desktop application binary로 fallback합니다.

또는 finalized artifact pipeline을 만듭니다.

```bash
execweave record --open -- python my_agent.py
```

`execweave top -- codex`는 Agent를 시작 terminal에서 계속 대화 가능하게 유지하면서 호스트 환경에 따라 detached Top dashboard를 열거나 attach합니다.

## v0.6.8: 명확한 evidence boundary를 가진 full-fidelity observability

v0.6.8는 compact metadata에만 머물지 않습니다. 지원되는 integration point가 content를 명시적으로 제공하면 ExecWeave는 **그 source가 제공한 전체 값**을 로컬 SHA-256 content-addressed store에 보존하고 semantic event stream에는 reference만 남길 수 있습니다.

```text
<run-root>/content/sha256/<sha256>.<json|txt|bin>
```

Adapter와 upstream hook/API surface에 따라 prompt/message, model request/response object, tool input/result, 명시적으로 노출된 reasoning/thinking text, shell/MCP output, provider hook이 제공한 file content 등을 보존할 수 있습니다.

`complete_from_source: true`는 해당 integration point가 제공한 값을 ExecWeave가 완전하게 저장했다는 뜻일 뿐입니다. hidden model state, provider가 노출하지 않은 내부 stage, 관측되지 않은 최종 wire request, 또는 intercept하지 않은 bytes까지 관측했다는 뜻은 아닙니다.

Full fidelity는 privacy boundary도 바꿉니다. Application-level secret이 content 안에 들어 있으면 그대로 보존됩니다. 알려진 transport credential은 adapter가 정의한 일부 provider-metadata projection에서만 제거되며, ExecWeave는 범용 secret scanner나 content redactor가 아닙니다.

### 지원되는 semantic / inference surface

| Integration | ExecWeave 아래에서 실행될 때 OS-runtime observation | Specialized evidence |
| --- | --- | --- |
| Claude Code | Yes | native hooks + hook이 제공한 full-fidelity content |
| OpenAI Codex | Yes | lifecycle hooks + hook이 제공한 full-fidelity content |
| Google Antigravity / Antigravity CLI | Yes | passive native hooks for invocation/tool evidence + full-fidelity values explicitly supplied to those hooks |
| Cursor | Yes | native hooks + hook이 제공한 full-fidelity content |
| OpenCode | Yes | project plugin + plugin이 제공한 full-fidelity content |
| Ollama | Yes | `execweave-model-runtime event/exchange/probe --runtime ollama` |
| llama.cpp | Yes | `execweave-model-runtime event/exchange/probe --runtime llamacpp` |
| vLLM | Yes | `execweave-model-runtime event/exchange/probe --runtime vllm` |
| LM Studio | 로컬 process가 ExecWeave에서 실행된 경우만 | `execweave-model-runtime event/exchange/probe --runtime lmstudio` |
| LiteLLM Proxy | 설정된 proxy를 ExecWeave 아래에서 실행하면 Yes | 현재 metadata-oriented gateway callback/event integration |
| OpenRouter | remote service process가 아니라 local client를 관측 | `execweave-inference-gateway event/exchange/generation --gateway openrouter` |

OpenRouter `exchange`는 caller-supplied request+response evidence이며 transparent wire interception이 아닙니다. LiteLLM Proxy는 현재 baseline에서 더 제한된 metadata-oriented integration입니다.

## Evidence layers

ExecWeave는 모든 signal을 한 trace로 평탄화하지 않고 evidence layer를 분리합니다.

```text
Agent / IDE semantic + supplied content evidence
          ↓
Inference gateway / routing evidence
          ↓
Model runtime / inference-server evidence
          ↓
OS runtime evidence: process / file / network
```

Underlying telemetry가 causal claim을 지원할 때만 relationship이 causal입니다. Tool → Process bridge는 여전히 보수적인 derived evidence입니다.

```text
inferred: true
causal: false
```

모호하면 edge를 만들지 않습니다. Gateway와 Model Runtime 사이의 exact shared request identity도 causal evidence가 아니라 identity evidence입니다.

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

Provider-integrated recorder는 raw runtime, semantic, correlated artifact를 분리해서 보존합니다. Cursor `tool_use_id`나 OpenCode `sessionID + callID` 같은 stable provider identifier는 provider 내부 logical identity를 보여 주지만 OS PID는 아닙니다. Legacy Gemini CLI hook entry points는 기존 설치 호환성을 위해 남아 있지만 새로운 Google CLI 사용은 Antigravity (`agy`)를 사용해야 합니다.

## Inference gateway와 model runtime

OpenRouter / LiteLLM gateway evidence를 캡처합니다.

```bash
execweave-inference-gateway event --gateway openrouter --sidecar gateway.jsonl
execweave-inference-gateway event --gateway litellm --sidecar gateway.jsonl
execweave-inference-gateway exchange --gateway openrouter --sidecar gateway.jsonl
```

Ollama, llama.cpp, vLLM, LM Studio model-runtime evidence를 캡처합니다.

```bash
execweave-model-runtime event --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime exchange --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime probe --runtime ollama --sidecar model-runtime.jsonl
```

`event`는 response-only evidence입니다. `exchange`는 caller-supplied request+response object를 저장하며 transparent interception을 주장하지 않습니다. `LOADED_MODEL`, `SERVES_MODEL`, `ADVERTISES_MODEL`은 source-specific semantics를 가지므로 서로 바꿔 쓸 수 없습니다. LM Studio catalog visibility는 `ADVERTISES_MODEL`이며 weights가 memory resident라는 증거가 아닙니다.

## Security analysis, evidence grades, bounded rule packs

내장 analysis를 실행합니다.

```bash
execweave analyze run.graph.json --output analysis.json
```

Finding은 severity와 독립된 evidence grade를 가집니다. 현재 grade는 `A`, `B`, `C`, `D`, `U`이며 direct syscall attribution부터 inferred/unknown provenance까지를 나타냅니다. 이는 evidence-strength category이지 **probability나 trust score가 아닙니다**.

Local rule pack은 third-party code를 실행하지 않고 bounded하고 설명 가능한 **single-edge observation** policy를 추가합니다.

```bash
execweave-rule-pack graph.json --rule-pack local-policy.json --output report.json
```

Rule pack은 code 실행, regex/path program 정의, byte-level data flow 또는 exfiltration claim을 만들 수 없습니다. Rule-pack finding은 observation-only로 유지됩니다.

```json
{
  "data_flow_proven": false,
  "exfiltration_proven": false
}
```

## Run integrity

완료된 run을 seal한 뒤 regular-file inventory가 seal 시점과 동일한지 검증합니다.

```text
execweave-integrity seal .execweave/runs/<run-id>
execweave-integrity verify .execweave/runs/<run-id>
```

Deterministic manifest는 file size/SHA-256을 기록하고 symbolic link를 거부합니다. Seal 이후 missing/modified/replaced/new regular file이 생기면 verification이 실패합니다.

이 local seal은 evidence와 manifest가 같은 writable trust boundary 안에 있을 때 adversary-resistant tamper evidence가 아닙니다. Manifest는 `malicious_writer_resistance: false`와 `external_trust_anchor: false`를 명시합니다. 더 강한 보장이 필요하면 manifest digest를 boundary 밖으로 복사/보호해야 합니다.

## Runtime evidence와 graph operations

Portable collector는 Linux, macOS, Windows를 지원하며 Linux에는 syscall-backed `strace` reference backend도 있습니다.

```bash
execweave doctor
execweave run --backend portable -- your-command
execweave run --backend strace -- your-command
execweave graph-summary run.graph.json
execweave graph-focus run.graph.json NODE_ID --hops 2 --output focused.graph.json
execweave path run.graph.json SOURCE TARGET --causal-only
```

Portable filesystem observation은 session-correlated이며 process-causal이 아닙니다. Polling은 충분히 짧은 activity를 놓칠 수 있습니다. Linux `strace`는 지원되는 execution에서 더 강한 process-attributed syscall evidence를 제공합니다. Linux eBPF, Windows ETW, macOS Endpoint Security native collector는 향후 계획입니다.

## Performance와 large-run safety

v0.6.3은 bounded filesystem/viewer protection, incremental Live JSONL tailing, large-graph safety guard를 추가했고 v0.6.4는 detached Top과 configured provider integration용 provisional live sidecar를 추가했습니다. 이 기능들은 v0.6.8에도 유지됩니다. 이번 release만을 위해 Live를 SSE로, artifact storage를 SQLite로, renderer를 Canvas/WebGL로, collector를 Rust로 전환하지 않았습니다.

재현 가능한 incremental `GraphAccumulator` reference result는 문서화된 GitHub Actions workload에서 1M synthetic events 기준 **164,273 ev/s**입니다. 이는 graph accumulation benchmark이며 end-to-end collector/browser throughput이 아닙니다.

```bash
execweave-overhead --iterations 7 --strace auto --output-json benchmark-results.json
execweave-scalability
```

Reference data와 methodology: [`docs/benchmarks/`](docs/benchmarks/).

## Layered artifacts

Provider-integrated run에는 다음과 같은 artifact가 포함될 수 있습니다.

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
└── integrity.json            # explicit seal 후
```

Derived correlation은 raw runtime 또는 provider sidecar evidence를 다시 쓰지 않습니다.

## Privacy

ExecWeave는 local-first이며 capture, content blob, graph, report, viewer는 기본적으로 로컬에 남습니다. **OS runtime collector**는 file content나 raw read/write byte buffer를 의도적으로 캡처하지 않습니다. 그러나 이 경계를 v0.6.8 **provider full-fidelity content store**와 혼동하면 안 됩니다. 지원되는 hook/API가 prompt, tool argument/result, model response, reasoning/thinking text, shell output, file content 등을 명시적으로 제공하면 ExecWeave가 이를 완전히 보존할 수 있습니다.

Content가 secret-redacted되었다고 가정하지 마세요. Command, path, endpoint metadata, identifier, model metadata, prompt, tool value, content blob은 모두 sensitive할 수 있습니다. 공유하기 전에 run directory 전체를 검토하세요.

## 현재 상태

ExecWeave `main`은 현재 **v0.6.8**이며 release hardening 중입니다. 공개 package/release는 main보다 늦을 수 있습니다. GitHub Release가 명시적으로 publish될 때만 publish workflow가 실행되며 PyPI upload 전에 release tag와 package version이 정확히 일치하는지 검증합니다.

v0.6.8는 cross-platform runtime collection, materialized execution graph, standalone/live viewer, 보수적인 provider↔runtime correlation, content-addressed full-fidelity provider evidence, evidence grades, bounded rule packs, 명시적 runtime threat/fidelity contract, honest local run-integrity sealing을 결합합니다. Observed evidence와 inference는 설계상 분리됩니다.

## 문서

- [`Phase 1 — Runtime Collection`](docs/phase-1-runtime-collection.ko.md)
- [`Phase 2 — Execution Graph`](docs/phase-2-execution-graph.ko.md)
- [`Live Graph`](docs/live-graph.ko.md)
- [`Semantic Telemetry`](docs/semantic-telemetry.ko.md)
- [`Claude Code Hooks`](docs/claude-code-hooks.ko.md)
- [`OpenAI Codex Hooks`](docs/codex-hooks.ko.md)
- [`Google Antigravity Hooks`](docs/antigravity-hooks.md)
- [`Cursor Hooks`](docs/cursor-hooks.ko.md)
- [`OpenCode Plugin`](docs/opencode-plugin.ko.md)
- [`Inference Gateway / OpenRouter / LiteLLM`](docs/inference-gateway.ko.md)
- [`Model Runtime / Ollama / llama.cpp / vLLM / LM Studio`](docs/model-runtime.ko.md)
- [`Runtime Threat Model`](docs/runtime-threat-model.ko.md)
- [`Evidence Grades`](docs/evidence-grades.ko.md)
- [`Rule Packs`](docs/rule-packs.ko.md)
- [`Run Integrity`](docs/run-integrity.ko.md)
- [`Security Analysis`](docs/security-analysis.ko.md)
- [`Performance Benchmarks`](docs/benchmarks/README.md)

## 기여

특히 native OS collector, Agent/IDE adapter, inference gateway, model runtime, evidence/correlation method, privacy/redaction, graph UX, performance evaluation 관련 contribution을 환영합니다.

## License

ExecWeave v0.6.8 이상은 **PolyForm Noncommercial License 1.0.0**에 따라 제공됩니다. 비상업적 사용, 수정, 재배포는 해당 조건에 따라 허용되지만 상업적 사용에는 별도의 서면 상업 라이선스가 필요합니다. 이전에 MIT로 공개된 버전은 당시 함께 제공된 라이선스 조건을 유지합니다. 자세한 내용은 [`LICENSE`](LICENSE)를 참고하세요.
