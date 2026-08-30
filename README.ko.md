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

**AI Agent가 내 컴퓨터에서 실제로 무엇을 했는지 확인하세요.**

ExecWeave는 source-available, local-first observability 프로젝트입니다. AI Agent 활동을 interactive execution graph로 바꾸고 observed evidence, provider content, derived inference를 명확하게 분리합니다.

> **Event가 ground truth이고 Graph는 materialized view입니다.**

<p align="center">
  <img src="docs/assets/codex.gif" alt="ExecWeave animated live demo" width="100%">
</p>

## 설치

PyPI에서 최신 wheel/sdist를 설치합니다.

```bash
python -m pip install -U execweave
```

현재 릴리스는 **v0.7.7** 입니다.

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

> **Hook 권한 요청이 나오면 승인하세요.** provider integration을 처음 사용할 때 Agent/IDE가 ExecWeave의 로컬 Hook 활성화를 허용할지 물을 수 있습니다. **Allow / Yes**를 선택하세요. 승인하지 않아도 OS-runtime telemetry는 동작할 수 있지만 provider-level tool, model, supplied-content observability는 제한됩니다.

Google Antigravity의 현재 CLI 명령은 `agy`입니다. ExecWeave는 `antigravity`도 friendly alias로 받아 `agy`로 해석합니다. Cursor의 `execweave live --open -- cursor`는 먼저 일반 PATH launcher를 찾고, 없으면 macOS/Windows의 표준 Cursor desktop application binary로 fallback합니다.

finalized artifact pipeline을 만들려면:

```bash
execweave record --open -- python my_agent.py
```

`execweave top -- codex`는 Agent를 시작 terminal에서 interactive 상태로 유지하면서 host 환경에 따라 detached Top dashboard를 열거나 attach합니다.

**v0.7.7 — 실행 중에도 각 agent 는 자신의 conversation 만 본다.** live dashboard 는 실행 내내 모든 agent 에게 다른 agent 의 conversation 을 보여 주었고, agent 가 종료된 뒤에야 올바르게 동작했습니다. conversation index 를 finalization 에서만 가져왔기 때문에 per-agent scoping 이 한 번도 실행되지 않았고, 그 자리에 저장된 모든 레코드를 평평하게 나열한 목록이 그려졌으며 어떤 node 를 선택하든 같은 목록이었습니다. 이제 그 index 는 실행 중인 graph 에서 투영되어, finalized 파일이 기록되는 것과 동일한 builder 를 거쳐 실행 중에 제공됩니다. 따라서 live dashboard 와 recorded viewer 가 무엇이 어떤 agent 의 것인지에 대해 어긋날 수 없으며, 둘이 그리는 것은 각 agent 가 소유한 provider-neutral, agent-local multi-agent conversation 뿐입니다. 두 viewer 모두 per-agent projection 을 거치지 않은 conversation record 를 그리는 fallback 을 남기지 않습니다. 릴리스 검사는 이제 실제 브라우저로 두 viewer 를 열어 각 agent 가 보여 주는 내용을 되읽으므로, agent 가 다른 agent 의 conversation 을 보는 상태는 release 에 도달하는 대신 빌드를 실패시킵니다.

통합 dashboard는 execution graph, logs, conversation records를 하나의 inspection flow에서 제공합니다. Finalized run은 `conversations.md`와 `conversations.json`을 만들며, 검증된 provider transcript는 run-local SHA-256 content store로 복사됩니다. Claude Code, OpenAI Codex, Cursor, OpenCode, Google Antigravity는 각 integration이 실제로 노출하는 가장 강한 multi-agent evidence를 사용합니다. gateway나 local runtime이 root request/response만 노출하면 ExecWeave는 root conversation만 보여 주며 subagent나 hidden routing을 만들어내지 않습니다.

## v0.6.9: 명확한 evidence boundary를 가진 full-fidelity observability

v0.6.9부터 ExecWeave는 compact metadata를 넘어, 지원되는 integration point가 명시적으로 제공한 **완전한 값**을 로컬 SHA-256 content-addressed store에 저장할 수 있습니다. semantic event stream에는 reference만 남깁니다.

```text
<run-root>/content/sha256/<sha256>.<json|txt|bin>
```

adapter와 upstream hook/API surface에 따라 prompt/message, model request/response object, tool input/result, assistant response, 명시적으로 노출된 reasoning/thinking text, shell/MCP output, provider hook이 제공한 file content 등을 저장할 수 있습니다.

`complete_from_source: true`는 해당 integration point가 전달한 값을 ExecWeave가 완전하게 저장했다는 뜻일 뿐입니다. hidden model state, 공개되지 않은 provider-side stage, 관측하지 못한 최종 wire request, 수집하지 않은 bytes까지 봤다는 뜻이 아닙니다.

Full fidelity는 privacy boundary도 바꿉니다. content 안의 application-level secret도 그대로 저장될 수 있습니다. 알려진 transport credential은 adapter가 명시적으로 정의한 일부 provider-metadata projection에서만 필터링됩니다. ExecWeave는 범용 secret scanner나 content redactor가 아닙니다.

### 지원되는 semantic / inference surface

| Integration | ExecWeave 아래에서 실행했을 때 OS-runtime observation | Specialized evidence |
| --- | --- | --- |
| Claude Code | Yes | native hooks + full-fidelity hook content + provider가 노출한 subagent result |
| OpenAI Codex | Yes | lifecycle hooks + validated rollout transcript + agent-local task/message/final-response routing |
| Google Antigravity / Antigravity CLI | Yes | passive native hooks + 검증 가능한 conversation/subagent routing |
| Cursor | Yes | native hooks + 사용 가능한 exact subagent task/summary routing |
| OpenCode | Yes | project plugin + session/task routing + full-fidelity plugin content |
| Ollama | Yes | `execweave-model-runtime event/exchange/probe --runtime ollama` |
| llama.cpp | Yes | `execweave-model-runtime event/exchange/probe --runtime llamacpp` |
| vLLM | Yes | `execweave-model-runtime event/exchange/probe --runtime vllm` |
| LM Studio | 로컬 process를 ExecWeave가 실행한 경우에만 | `execweave-model-runtime event/exchange/probe --runtime lmstudio` |
| LiteLLM Proxy | 설정된 proxy를 ExecWeave가 실행한 경우 Yes | metadata-oriented gateway callback/event integration |
| OpenRouter | 원격 service process가 아니라 로컬 client를 관측 | `execweave-inference-gateway event/exchange/generation --gateway openrouter` |

OpenRouter `exchange`는 caller-supplied request+response evidence이며 transparent wire interception이 아닙니다. LiteLLM Proxy는 현재 baseline에서 더 제한된 metadata-oriented integration입니다. Provider-neutral conversation projection은 존재하지 않는 provider evidence를 가짜 agent relationship으로 승격하지 않습니다.

## Evidence layers

ExecWeave는 모든 신호를 하나의 trace로 평탄화하지 않고 evidence layer를 분리해서 유지합니다.

```text
Agent / IDE semantic + supplied content evidence
          ↓
Inference gateway / routing evidence
          ↓
Model runtime / inference-server evidence
          ↓
OS runtime evidence: process / file / network
```

relationship을 causal로 표시하는 것은 underlying telemetry가 그 claim을 지원할 때뿐입니다. Tool → Process bridge는 보수적인 derived evidence로 유지됩니다.

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

Provider-integrated recorder는 raw runtime, semantic, correlated, conversation artifacts를 분리해 저장합니다. Cursor `tool_use_id`, Codex rollout thread identity, OpenCode `sessionID + callID` 같은 stable provider identifier는 provider 내부 logical identity를 증명하지만 OS PID는 아닙니다. cross-agent content는 provider가 명시적인 route, delegation, result를 노출할 때만 표시됩니다. Legacy Gemini CLI hook entry point는 기존 설치 호환성을 위해 유지되지만 새로운 Google CLI 사용은 Antigravity (`agy`)를 권장합니다.

## Inference gateway와 model runtime

OpenRouter 또는 LiteLLM gateway evidence를 수집합니다.

```bash
execweave-inference-gateway event --gateway openrouter --sidecar gateway.jsonl
execweave-inference-gateway event --gateway litellm --sidecar gateway.jsonl
execweave-inference-gateway exchange --gateway openrouter --sidecar gateway.jsonl
```

Ollama, llama.cpp, vLLM, LM Studio의 model-runtime evidence를 수집합니다.

```bash
execweave-model-runtime event --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime exchange --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime probe --runtime ollama --sidecar model-runtime.jsonl
```

`event`는 response-only evidence입니다. `exchange`는 caller-supplied request+response object를 저장하지만 transparent interception을 주장하지 않습니다. Runtime catalog relation은 source별 의미를 유지하며 `LOADED_MODEL`, `SERVES_MODEL`, `ADVERTISES_MODEL`은 서로 바꿔 쓸 수 없습니다. LM Studio의 catalog visibility가 `ADVERTISES_MODEL`이어도 weights가 memory resident였다는 증거는 아닙니다.

## Security analysis, evidence grades, bounded rule packs

내장 analysis를 실행합니다.

```bash
execweave analyze run.graph.json --output analysis.json
```

Finding은 severity와 별개의 evidence grade를 노출합니다. 현재 grade는 `A`, `B`, `C`, `D`, `U`이며 direct syscall attribution부터 inferred/unknown provenance까지를 표현합니다. probability나 trust score가 아닙니다.

Local rule pack은 third-party code를 실행하지 않고 bounded하고 설명 가능한 **single-edge observation** policy를 추가할 수 있습니다.

```bash
execweave-rule-pack graph.json --rule-pack local-policy.json --output report.json
```

Rule pack은 code 실행, regex/path program 정의, byte-level data flow 또는 exfiltration 단정을 할 수 없습니다. rule-pack finding은 observation-only로 유지됩니다.

Security finding은 더 강한 claim을 하지 않는다는 점도 명시합니다.

```json
{
  "data_flow_proven": false,
  "exfiltration_proven": false
}
```

## Run integrity

완료된 run을 seal하고 나중에 regular-file inventory가 seal 시점과 달라지지 않았는지 검증할 수 있습니다.

```text
execweave-integrity seal .execweave/runs/<run-id>
execweave-integrity verify .execweave/runs/<run-id>
```

Deterministic manifest는 file size/SHA-256을 기록하고 symbolic link를 거부합니다. seal 후 regular file이 누락, 변경, 교체, 추가되면 검증에 실패합니다.

이 local seal은 evidence와 manifest가 같은 writable trust boundary 안에 있을 때 adversary-resistant tamper evidence라고 설명하지 않습니다. Manifest에는 `malicious_writer_resistance: false`와 `external_trust_anchor: false`가 기록됩니다. 더 강한 trust anchor가 필요하면 manifest digest를 boundary 밖에 복사하거나 보호해야 합니다.

## Runtime evidence와 graph operations

Portable collector는 Linux, macOS, Windows에서 동작합니다. Linux에는 syscall-backed `strace` reference backend도 있습니다.

```bash
execweave doctor
execweave run --backend portable -- your-command
execweave run --backend strace -- your-command
execweave graph-summary run.graph.json
execweave graph-filter run.graph.json --causal-only --output causal.graph.json
execweave graph-focus run.graph.json NODE_ID --hops 2 --output focused.graph.json
execweave path run.graph.json SOURCE TARGET --causal-only
```

Portable filesystem observation은 session-correlated이며 process-causal이 아닙니다. polling은 충분히 짧은 활동을 놓칠 수 있습니다. Linux `strace`는 지원 execution에서 더 강한 process-attributed syscall evidence를 제공합니다. Linux eBPF, Windows ETW, macOS Endpoint Security native collector는 향후 계획입니다.

## Performance와 large-run safety

ExecWeave에는 bounded filesystem/viewer protection, incremental Live JSONL tailing, large-graph safety guard, detached Top, configured provider integration용 provisional live sidecar가 포함됩니다.

재현 가능한 incremental `GraphAccumulator` reference result는 문서화된 GitHub Actions workload의 1M synthetic events에서 **164,273 ev/s**에 도달합니다. 이는 graph accumulation benchmark이며 end-to-end collector/browser throughput이 아닙니다.

대표 host/workload에서 package-level overhead benchmark를 다시 실행할 수 있습니다.

```bash
execweave-overhead --iterations 7 --strace auto --output-json benchmark-results.json
execweave-scalability
```

Reference data와 methodology는 [`docs/benchmarks/`](docs/benchmarks/)에 있습니다.

## Layered artifacts

Provider-integrated run에는 다음 artifact가 포함될 수 있습니다.

```text
.execweave/runs/<run-id>/
├── events.jsonl
├── graph.json
├── viewer.html
├── semantic.jsonl
├── content/sha256/...
├── conversations.md
├── conversations.json
├── events.semantic.jsonl
├── graph.semantic.json
├── viewer.semantic.html
├── events.correlated.jsonl
├── graph.correlated.json
├── viewer.correlated.html
└── integrity.json            # explicit seal 이후
```

Derived correlation은 raw runtime이나 provider sidecar evidence를 다시 쓰지 않습니다.

## Privacy

ExecWeave는 local-first이며 capture, content blob, graph, report, viewer는 기본적으로 로컬에 남습니다. **OS runtime collector**는 file content나 raw read/write byte buffer를 의도적으로 수집하지 않습니다. 이 boundary를 v0.6.9에서 도입된 **provider full-fidelity content store**와 혼동하면 안 됩니다. 지원 hook/API가 prompt, tool argument/result, model response, reasoning/thinking text, shell output, file content 등을 명시적으로 제공하면 ExecWeave는 그 값을 완전하게 저장할 수 있습니다.

Conversation isolation은 attribution/display 규칙이지 redaction boundary가 아닙니다. provider가 Agent 1의 내용을 Agent 2에게 명시적으로 보내면 해당 routed evidence는 참여 endpoint에 나타날 수 있습니다. content가 secret-redacted되었다고 가정하지 마세요. Command, path, endpoint metadata, identifier, model metadata, prompt, tool value, content blob은 모두 민감할 수 있습니다. 공유하기 전에 run directory 전체를 검토하세요.

## 현재 상태

v0.7.7는 cross-platform runtime collection, materialized execution graph, standalone/live dashboard, 보수적인 provider↔runtime correlation, content-addressed full-fidelity provider evidence, attributable multi-agent execution trace, run-local conversation access, provider-neutral projection의 agent-local conversation isolation, standalone 및 live dashboard의 per-agent conversation focus를 통합합니다. 각 integration은 provider가 실제로 노출한 가장 강한 identity/routing evidence만 보존하고 충분한 증거가 없으면 abstain합니다. Observed evidence와 inference는 설계상 계속 분리됩니다.

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

native OS collector, Agent/IDE adapter, inference gateway, model runtime, evidence/correlation method, privacy/redaction, graph UX, multi-agent conversation attribution, performance evaluation에 대한 contribution을 환영합니다.

## License

v0.6.8부터 ExecWeave는 **PolyForm Noncommercial License 1.0.0**을 사용합니다. 비상업적 사용, 수정, 재배포는 라이선스 조건에 따라 허용됩니다. 상업적 사용에는 licensor의 별도 서면 commercial license가 필요합니다. 자세한 내용은 [`LICENSE`](LICENSE)를 참고하세요.
