> Codex + AGY는 전체 재정비가 완료되었습니다. 나머지 provider는 아직 수정이 완료되지 않았습니다.

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

<p align="center">
  <a href="https://pypi.org/project/execweave/"><img src="https://img.shields.io/pypi/v/execweave" alt="PyPI"></a>
  <a href="https://github.com/Irish-kw/ExecWeave/actions/workflows/ci.yml"><img src="https://github.com/Irish-kw/ExecWeave/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue" alt="Python 3.10+">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-PolyForm%20Noncommercial-blue" alt="License"></a>
</p>

**AI Agent가 내 컴퓨터에서 실제로 무엇을 했는지 확인하세요.**

ExecWeave는 source-available, local-first observability 프로젝트입니다. AI Agent 활동을 interactive execution graph로 바꾸고 observed evidence, provider가 명시적으로 제공한 content, derived inference를 분리해서 보여 줍니다.

> **Event가 ground truth이고 Graph는 materialized view입니다.**

<p align="center">
  <img src="docs/assets/codex.gif" alt="ExecWeave animated live demo" width="100%">
</p>

이 README는 **v0.8.7**을 설명합니다.

## 왜 ExecWeave인가

- **하나의 로컬 inspection surface.** Live run, 완료된 run, standalone `viewer.html`이 같은 dashboard renderer를 사용해 graph, logs, conversation, node details를 한 화면에 모읍니다.
- **Evidence-aware 설계.** Direct observation, identity link, 보수적인 inference, causal claim을 같은 종류의 관계로 섞지 않습니다.
- **Provider-aware이지만 숨은 동작을 만들어내지 않습니다.** Provider가 실제로 노출한 routing / identity evidence만 사용하며, 없는 evidence는 없는 그대로 둡니다.
- **특정 Agent 전용이 아닙니다.** OS-runtime telemetry는 어떤 로컬 command에도 적용할 수 있고, 지원되는 provider adapter가 있을 때 더 풍부한 semantic evidence를 추가합니다.

## 설치

PyPI에서 최신 공개 package를 설치합니다.

```bash
python -m pip install -U execweave
```

개발용 설치:

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

## 60초 빠른 시작

Live OS-runtime telemetry는 **어떤 로컬 command에도** 사용할 수 있습니다. 아래 Agent/runtime 이름은 예시일 뿐 whitelist가 아닙니다.

```bash
execweave live --open -- claude
execweave live --open -- codex
execweave live --open -- antigravity
execweave live --open -- cursor
execweave live --open -- opencode
execweave live --open -- ollama serve
execweave live --open -- python my_agent.py
```

> **Hook 권한 요청이 나오면 허용하세요.** 첫 provider-integrated run에서 Agent/IDE가 ExecWeave의 로컬 Hook integration을 활성화해도 되는지 물을 수 있습니다. **Allow / Yes**를 선택하세요. 허용하지 않아도 OS-runtime telemetry는 동작할 수 있지만 provider-level tool, model, conversation, supplied-content observability는 줄어들거나 사용할 수 없을 수 있습니다.

Google Antigravity의 현재 CLI command는 `agy`입니다. ExecWeave는 friendly alias로 `antigravity`도 받아 `agy`로 해석합니다. Cursor의 `execweave live --open -- cursor`는 먼저 일반 PATH launcher를 찾고, 없으면 macOS / Windows의 표준 Cursor desktop application binary를 시도합니다.

Finalized run artifacts를 만들려면:

```bash
execweave record --open -- python my_agent.py
```

Agent를 시작 terminal에서 계속 대화형으로 사용하면서 detached overview를 열려면:

```bash
execweave top -- codex
```

## Dashboard

ExecWeave는 run이 끝날 때 다른 viewer로 전환하지 않습니다. Live, finished, standalone viewing 모두 같은 dashboard model을 사용합니다.

- **Execution graph:** agents, processes, files, network endpoints, tools, model/runtime entities와 지원되는 semantic relations를 표시합니다.
- **Conversation rounds:** 최신 round는 바로 읽을 수 있고, 이전 round도 개별적으로 펼칠 수 있어 새 reply에 덮이지 않습니다.
- **Node details:** process node는 command / PID context, file node는 path / history context, network node는 endpoint / process context를 보여 줍니다.
- **Large-run readability:** type별 예산을 넘으면 최신 member는 직접 표시하고 이전 member는 inspection 가능한 aggregate로 접습니다. 기준은 `--fold-budget N`으로 설정합니다.
- **Selection clarity:** multi-agent layout은 안정적인 root / child hierarchy를 유지하고 agent 선택 시 관련 없는 edges를 흐리게 표시합니다.

### v0.8.3 Dashboard 변경점

v0.8.3은 raw evidence를 바꾸지 않으면서 dense / multi-round run의 가독성을 개선합니다.

- conversation panel을 round 단위로 바꿔 오래된 prompt와 최신 reply가 잘못 짝지어지는 문제를 제거;
- 사용자가 명시적으로 선택한 open / closed state를 800 ms Live refresh 뒤에도 유지;
- subagent response를 실제로 생성한 agent에 계속 귀속;
- process, file, network 선택 시 빈 detail panel이 뜨는 문제 제거;
- 높은 cardinality의 node type을 설정 가능한 예산에 따라 fold해 수백·수천 node가 graph를 뒤덮지 않도록 처리;
- lifecycle return edge가 root / child rank를 왜곡하지 않도록 하고 공유 tool/model traffic의 routed geometry를 더 명확하게 구성.

이 변경들은 presentation-layer에만 해당합니다. Raw graph evidence는 바뀌지 않으며 Live, finished, `viewer.html`은 계속 같은 renderer를 공유합니다.

## 지원 Integrations

| Integration | ExecWeave 아래에서 실행했을 때의 OS-runtime observation | Specialized evidence |
| --- | --- | --- |
| Claude Code | Yes | native hooks + full-fidelity supplied hook content + provider가 노출할 때 exact subagent results |
| OpenAI Codex | Yes | lifecycle hooks + validated rollout transcripts + agent-local task/message/final-response routing |
| Google Antigravity / Antigravity CLI | Yes | passive native hooks + 검증 가능한 경우 conversation/subagent routing |
| Cursor | Yes | native hooks + 사용 가능한 경우 exact subagent task/summary routing |
| OpenCode | Yes | project plugin + session/task routing + full-fidelity supplied plugin content |
| Ollama | Yes | `execweave-model-runtime event/exchange/probe --runtime ollama` |
| llama.cpp | Yes | `execweave-model-runtime event/exchange/probe --runtime llamacpp` |
| vLLM | Yes | `execweave-model-runtime event/exchange/probe --runtime vllm` |
| LM Studio | 로컬 process를 ExecWeave 아래에서 시작한 경우에만 | `execweave-model-runtime event/exchange/probe --runtime lmstudio` |
| LiteLLM Proxy | 설정된 proxy를 ExecWeave 아래에서 시작한 경우 Yes | metadata-oriented gateway callback/event integration |
| OpenRouter | remote service process가 아니라 로컬 client를 관찰 | `execweave-inference-gateway event/exchange/generation --gateway openrouter` |

Cursor `tool_use_id`, Codex rollout thread identity, OpenCode `sessionID + callID` 같은 stable provider identifier는 logical provider identity를 증명하지만 OS PID는 아닙니다. Cross-agent content는 provider가 명시적인 route, delegation, result를 노출할 때만 표시됩니다. Gateway / local runtime이 root request/response만 노출하면 root-only로 유지되며 ExecWeave가 subagent나 hidden routing을 만들어내지 않습니다.

OpenRouter `exchange`는 caller-supplied request+response evidence이며 transparent wire interception이 아닙니다. LiteLLM Proxy는 현재 baseline에서 더 좁은 metadata-oriented integration입니다. 새로운 Google CLI 사용에는 Antigravity (`agy`)를 사용해야 합니다.

## Evidence model

ExecWeave는 모든 signal을 하나의 trace로 평탄화하지 않고 evidence layer 경계를 유지합니다.

```text
Agent / IDE semantic + supplied content evidence
          ↓
Inference gateway / routing evidence
          ↓
Model runtime / inference-server evidence
          ↓
OS runtime evidence: process / file / network
```

Relationship를 causal이라고 표시하는 것은 하위 telemetry가 그 claim을 실제로 뒷받침할 때뿐입니다. 보수적인 Tool → Process bridge는 derived evidence로 유지됩니다.

```text
inferred: true
causal: false
```

Gateway와 Model Runtime 사이의 exact shared request identity는 identity evidence이지 causal evidence가 아닙니다.

```text
identity_exact: true
inferred: false
causal: false
```

모호하면 edge를 만들지 않습니다.

### Full-fidelity supplied content

**v0.6.9**부터 지원되는 integration point는 provider / hook / API가 명시적으로 전달한 전체 값을 로컬 SHA-256 content-addressed store에 저장하고 semantic event stream에는 reference만 남길 수 있습니다.

```text
<run-root>/content/sha256/<sha256>.<json|txt|bin>
```

Integration에 따라 prompt/message, request/response object, tool input/result, assistant response, 명시적으로 노출된 reasoning/thinking text, shell/MCP output, provider hook이 제공한 file content 등을 저장할 수 있습니다.

`complete_from_source: true`는 해당 integration point가 전달한 값을 완전하게 저장했다는 뜻일 뿐입니다. Hidden model state, 공개되지 않은 provider-side stage, 관찰하지 않은 final wire request, intercept하지 않은 bytes를 봤다는 의미는 **아닙니다**.

## 자주 쓰는 명령

### Agent / IDE recorders

```bash
execweave-claude-record --open -- claude
execweave-codex-record --open -- codex
execweave-antigravity-record --open -- antigravity
execweave-cursor-record --open -- cursor
execweave-opencode-plugin --install
execweave-opencode-record --open -- opencode
```

### Gateways와 model runtimes

```bash
execweave-inference-gateway event --gateway openrouter --sidecar gateway.jsonl
execweave-inference-gateway exchange --gateway openrouter --sidecar gateway.jsonl
execweave-inference-gateway event --gateway litellm --sidecar gateway.jsonl

execweave-model-runtime event --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime exchange --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime probe --runtime ollama --sidecar model-runtime.jsonl
```

`event`는 response-only evidence입니다. `exchange`는 caller-supplied request+response object를 저장하지만 transparent interception을 주장하지 않습니다. Runtime catalog relation은 source-specific 의미를 유지하며 `LOADED_MODEL`, `SERVES_MODEL`, `ADVERTISES_MODEL`은 서로 바꿔 쓸 수 없습니다. LM Studio catalog visibility는 `ADVERTISES_MODEL`이며 weights가 memory에 resident했다는 증거가 아닙니다.

### Runtime, graph, security, integrity

```bash
execweave doctor
execweave run --backend portable -- your-command
execweave run --backend strace -- your-command
execweave graph-summary run.graph.json
execweave graph-filter run.graph.json --causal-only --output causal.graph.json
execweave graph-focus run.graph.json NODE_ID --hops 2 --output focused.graph.json
execweave path run.graph.json SOURCE TARGET --causal-only
execweave analyze run.graph.json --output analysis.json
execweave-rule-pack graph.json --rule-pack local-policy.json --output report.json
execweave-integrity seal .execweave/runs/<run-id>
execweave-integrity verify .execweave/runs/<run-id>
```

Security finding의 evidence grade는 severity와 독립적입니다. 현재 grade는 `A`, `B`, `C`, `D`, `U`이며 probability나 trust score가 아니라 evidence-strength category입니다. Rule pack은 bounded / explainable single-edge observation policy이며 third-party code를 실행하지 않고 byte-level exfiltration을 증명할 수도 없습니다.

## Run artifacts

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
└── integrity.json            # after an explicit seal
```

Derived correlation은 raw runtime이나 provider sidecar evidence를 덮어쓰지 않습니다.

## 제한과 개인정보 보호

- Portable collector는 Linux, macOS, Windows에서 동작합니다. Portable filesystem observation은 session-correlated이지 process-causal이 아니며 polling은 매우 짧은 activity를 놓칠 수 있습니다.
- Linux에는 syscall-backed `strace` reference backend도 있어 지원되는 execution에서 더 강한 process-attributed syscall evidence를 제공합니다.
- Native Linux eBPF, Windows ETW, macOS Endpoint Security collector는 planned work이며 현재 기능으로 주장하지 않습니다.
- Full-fidelity provider content는 prompt, tool value, model response, shell output, supplied file 안의 secret도 저장할 수 있습니다. ExecWeave는 범용 secret scanner나 content redactor가 **아닙니다**.
- Conversation isolation은 attribution/display rule이지 redaction boundary가 아닙니다. Provider가 content를 다른 agent로 명시적으로 route하면 참여 endpoint에 그 content가 보이는 것은 정상입니다.
- Commands, paths, endpoints, identifiers, model metadata, prompts, tool values, content blobs는 모두 민감할 수 있습니다. 공유 전 run directory 전체를 검토하세요.
- Local integrity seal은 manifest 대비 file change를 감지할 수 있지만 evidence와 manifest가 같은 writable trust boundary에 있으면 adversary-resistant tamper evidence라고 부를 수 없습니다.

## 성능

ExecWeave에는 bounded filesystem/viewer protection, incremental Live JSONL tailing, large-graph safety guard, detached Top, 설정된 provider integration용 provisional live sidecar가 포함됩니다.

재현 가능한 incremental `GraphAccumulator` reference result는 문서화된 GitHub Actions workload의 1M synthetic events에서 **164,273 ev/s**를 기록합니다. 이는 graph-accumulation benchmark이며 end-to-end collector / browser throughput이 아닙니다.

대표적인 host/workload에서 package-level benchmark를 실행하세요.

```bash
execweave-overhead --iterations 7 --strace auto --output-json benchmark-results.json
execweave-scalability
```

Reference data와 methodology는 [`docs/benchmarks/`](docs/benchmarks/)에 있습니다.

## 문서

| 영역 | 문서 |
| --- | --- |
| Runtime과 graph | [`Phase 1 — Runtime Collection`](docs/phase-1-runtime-collection.md) · [`Phase 2 — Execution Graph`](docs/phase-2-execution-graph.md) · [`Live Graph`](docs/live-graph.md) · [`Semantic Telemetry`](docs/semantic-telemetry.md) |
| Agent / IDE integrations | [`Claude Code`](docs/claude-code-hooks.md) · [`OpenAI Codex`](docs/codex-hooks.md) · [`Google Antigravity`](docs/antigravity-hooks.md) · [`Cursor`](docs/cursor-hooks.md) · [`OpenCode`](docs/opencode-plugin.md) |
| Gateways와 runtimes | [`Inference Gateway / OpenRouter / LiteLLM`](docs/inference-gateway.md) · [`Model Runtime / Ollama / llama.cpp / vLLM / LM Studio`](docs/model-runtime.md) |
| Trust와 analysis | [`Runtime Threat Model`](docs/runtime-threat-model.md) · [`Evidence Grades`](docs/evidence-grades.md) · [`Rule Packs`](docs/rule-packs.md) · [`Run Integrity`](docs/run-integrity.md) · [`Security Analysis`](docs/security-analysis.md) |
| Performance | [`Benchmarks`](docs/benchmarks/README.md) |

## 기여

Native OS collector, Agent/IDE adapter, inference gateway, model runtime, evidence/correlation method, privacy/redaction, graph UX, multi-agent conversation attribution, performance evaluation 관련 기여를 환영합니다.

## 라이선스

v0.6.8부터 ExecWeave는 **PolyForm Noncommercial License 1.0.0**을 사용합니다. 비상업적 사용, 수정, 재배포는 라이선스 조건에 따라 허용됩니다. 상업적 사용에는 licensor와의 별도 서면 commercial license가 필요합니다. 자세한 내용은 [`LICENSE`](LICENSE)를 참조하세요.
