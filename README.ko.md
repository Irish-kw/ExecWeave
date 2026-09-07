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

ExecWeave는 AI Agent와 AI 개발 도구를 위한 local-first observability 프로젝트입니다. Provider 수준의 semantic evidence와 운영체제 runtime evidence를 하나의 인터랙티브 Execution Graph로 결합하면서도, 서로 다른 증거 계층을 명확하게 분리합니다.

> **Event는 증거이고, Graph는 그 증거로부터 materialize된 view입니다.**

<p align="center">
  <img src="docs/assets/codex.gif" alt="ExecWeave live dashboard demo" width="100%">
</p>

## 왜 ExecWeave인가

Agent는 도구를 사용했다거나 파일을 수정했다거나 서비스에 연결했다고 말할 수 있습니다. 이런 Provider semantic evidence는 유용하지만, 운영체제가 실제로 관측한 동작과 동일하지는 않습니다. ExecWeave는 두 종류의 정보를 함께 보여 주되, 증거의 강도를 섞지 않습니다.

- **Live와 Finished에 동일한 Dashboard 사용.** 실행 중 화면, 완료된 run, standalone `viewer.html`이 동일한 Graph 및 conversation model을 사용합니다.
- **Provider-aware semantics.** Hook, rollout transcript, plugin, runtime API가 제공될 때 이를 사용합니다.
- **OS runtime evidence.** Process, File, Network endpoint를 Provider semantics와 독립적으로 관측할 수 있습니다.
- **Evidence-aware attribution.** Direct observation, exact identity, 보수적 inference, causal claim을 구분합니다.
- **Local-first storage.** 사용자가 직접 공유하지 않는 한 run artifacts는 로컬에 남습니다.
- **특정 Agent에 종속되지 않음.** 전용 Provider adapter가 없어도 일반 로컬 command를 감싸 runtime을 관측할 수 있습니다.

## 설치

PyPI에서 설치:

```bash
python -m pip install -U execweave
```

개발 환경:

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

## 빠른 시작

어떤 로컬 command든 `execweave live` 뒤에 붙일 수 있습니다:

```bash
execweave live --open -- claude
execweave live --open -- codex
execweave live --open -- antigravity
execweave live --open -- cursor
execweave live --open -- opencode
execweave live --open -- python my_agent.py
```

완료 후 artifact 생성이 주목적이라면:

```bash
execweave record --open -- python my_agent.py
```

현재 terminal에서 프로그램과 계속 상호작용하면서 별도 overview를 보고 싶다면:

```bash
execweave top -- codex
```

### Provider integration 승인

일부 Agent와 IDE는 로컬 hook 또는 plugin을 처음 활성화할 때 권한을 요청합니다. Prompt, Response, Tool, Model, Conversation 같은 Provider-level evidence가 필요하다면 ExecWeave integration을 승인하세요. 승인하지 않아도 OS runtime 관측은 가능할 수 있지만 semantic coverage는 줄어듭니다.

Google Antigravity의 실제 CLI command는 현재 `agy`입니다. ExecWeave는 기억하기 쉬운 alias로 `antigravity`도 허용합니다.

Windows에서 bare `cursor`를 사용하면 ExecWeave는 사용자의 PATH가 가리키는 Cursor 설치 위치를 따릅니다. 명시적으로 지정한 launcher path는 그대로 유지됩니다.

## Ollama

ExecWeave는 두 가지 대표적인 로컬 Ollama workflow를 지원합니다.

### Managed server capture

ExecWeave를 통해 Ollama Server를 실행합니다:

```bash
execweave live --open -- ollama serve
```

다른 terminal에서는 평소처럼 Ollama를 사용합니다:

```bash
ollama run deepseek-r1:1.5b
```

SDK, OpenAI-compatible local request, managed local endpoint로 보내는 `curl` request도 같은 ExecWeave run에 연결될 수 있습니다. 두 번째 terminal을 다시 ExecWeave로 감쌀 필요는 없습니다.

Managed relay는 local loopback endpoint에만 적용되며 wildcard 또는 외부 공개 listener를 재작성하지 않습니다.

### Direct client capture

Ollama Server가 이미 실행 중이라면 client를 직접 감쌀 수 있습니다:

```bash
execweave live --open -- ollama run deepseek-r1:1.5b
```

이 모드는 Ollama Server를 시작하지 않으므로 접근 가능한 upstream server가 필요합니다.

## Dashboard

Dashboard는 대규모 multi-agent run에서도 원본 evidence를 바꾸지 않고 읽기 쉽게 유지하도록 설계되어 있습니다.

- **Execution graph:** Agent, Process, File, Network endpoint, Tool, Model/runtime entity 및 지원되는 relation.
- **Conversation rounds:** 최신/이전 round가 올바른 Agent에 유지되며 후속 message로 덮어쓰이지 않습니다.
- **Node details:** Process identity, File history, Network endpoint, Tool, Provider conversation content를 검사할 수 있습니다.
- **Stable live updates:** Run 상태가 변해도 같은 document 안에서 업데이트됩니다.
- **Large-run folding:** node 수가 많을 때 오래된 member를 접으면서도 검사 가능하게 유지합니다.
- **Selection-focused layout:** 선택한 Agent 또는 runtime object와 무관한 Graph traffic을 약화합니다.

대규모 run은 다음 옵션으로 조정할 수 있습니다:

```text
--fold-budget N
--viewer-max-nodes N
--viewer-max-edges N
--viewer-max-dom-elements N
```

## 지원 integration

| Integration | OS runtime 관측 | Specialized evidence |
| --- | --- | --- |
| Claude Code | ExecWeave 아래에서 실행할 때 | native hooks 및 Provider supplied conversation/tool content |
| OpenAI Codex | 지원 | lifecycle hooks, validated rollout transcripts, 노출된 agent/subagent routing |
| Google Antigravity | 지원 | passive hooks 및 노출된 conversation/subagent routing |
| Cursor | 지원 | native hooks 및 노출된 task/subagent routing |
| OpenCode | 지원 | project plugin, session/task routing, supplied plugin content |
| Ollama | 지원 | managed local relay 및 model-runtime evidence |
| llama.cpp | 지원 | model-runtime event/exchange/probe |
| vLLM | 지원 | model-runtime event/exchange/probe |
| LM Studio | local process를 관측할 수 있을 때 | model-runtime catalog/runtime evidence |
| LiteLLM Proxy | local proxy를 관측할 수 있을 때 | gateway metadata / event integration |
| OpenRouter | local client만 관측 가능 | caller-supplied gateway event/exchange evidence |

Tool-call ID, session ID, rollout thread ID, subagent route 같은 Provider identifier는 logical identity이며 OS PID가 아닙니다. ExecWeave는 증거가 충분한 경우에만 계층을 연결합니다.

## Evidence model

ExecWeave는 evidence를 다음과 같은 주요 계층으로 나눕니다:

```text
Agent / IDE semantics 및 supplied content
                ↓
Inference gateway / routing evidence
                ↓
Model runtime / inference-server evidence
                ↓
OS runtime evidence: process / file / network
```

Telemetry가 인과 관계를 실제로 뒷받침할 때만 relation을 causal로 표시합니다. 보수적인 bridge는 derived evidence로 명시됩니다:

```text
inferred: true
causal: false
```

Exact shared request identity는 identity를 입증할 수 있지만 causal을 입증하지는 않습니다:

```text
identity_exact: true
inferred: false
causal: false
```

Attribution이 모호하면 ExecWeave는 더 강한 관계를 추측하지 않고 edge를 만들지 않습니다.

### Full-fidelity supplied content

지원되는 hook, plugin, API가 명시적으로 제공한 전체 값은 로컬 SHA-256 content-addressed store에 저장할 수 있습니다:

```text
<run-root>/content/sha256/<sha256>.<json|txt|bin>
```

Integration에 따라 Prompt, Message, Request/Response object, Tool input/result, Assistant response, 노출된 reasoning text, Shell output, supplied file content가 포함될 수 있습니다.

`complete_from_source: true`는 해당 integration point가 전달한 전체 값을 저장했다는 뜻입니다. 노출되지 않은 model state나 Provider 내부 데이터를 관측했다는 뜻은 아닙니다.

## 자주 쓰는 command

### Agent / IDE recorder

```bash
execweave-claude-record --open -- claude
execweave-codex-record --open -- codex
execweave-antigravity-record --open -- antigravity
execweave-cursor-record --open -- cursor
execweave-opencode-plugin --install
execweave-opencode-record --open -- opencode
```

### Gateway / model runtime

```bash
execweave-inference-gateway event --gateway openrouter --sidecar gateway.jsonl
execweave-inference-gateway exchange --gateway openrouter --sidecar gateway.jsonl
execweave-model-runtime event --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime exchange --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime probe --runtime ollama --sidecar model-runtime.jsonl
```

`event`는 단방향 event evidence입니다. `exchange`는 caller가 제공한 request/response pair를 저장하며 transparent wire interception을 주장하지 않습니다.

### Runtime / Graph / Security / Integrity

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

## Run artifacts

Provider-integrated run에는 다음 파일이 포함될 수 있습니다:

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
└── integrity.json
```

Raw observation과 derived semantic/correlation output은 분리된 상태로 유지됩니다.

## 제한 및 개인정보

- Portable collector는 Linux, macOS, Windows에서 동작합니다. Portable filesystem observation은 항상 process-causal한 것이 아니라 session-correlated이며, polling은 매우 짧은 activity를 놓칠 수 있습니다.
- Linux에는 지원되는 execution에서 더 강한 syscall-attributed evidence를 제공하는 `strace` reference backend도 있습니다.
- Provider semantic coverage는 각 integration이 실제로 노출하는 정보에 달려 있습니다. 노출되지 않은 Prompt, hidden reasoning, remote Provider internals, routing은 안정적으로 재구성할 수 없습니다.
- Full-fidelity content에는 Credential, Secret, Source code, Prompt, Tool value, Model response, Shell output, File content가 포함될 수 있습니다.
- Conversation isolation은 attribution rule이지 redaction boundary가 아닙니다. Provider가 명시적으로 route한 content는 여러 participant에 나타날 수 있습니다.
- Local integrity manifest는 manifest 기준 변경을 감지하지만 evidence와 manifest가 동일한 writable trust boundary에 있으면 adversary-resistant trusted logging이 아닙니다.
- 공유하기 전에 전체 run directory를 검토하세요.

## 개발

테스트:

```bash
python -m pytest
```

Lint:

```bash
python -m ruff check .
```

Issue와 Pull Request를 환영합니다. 새 integration에서는 직접 관측한 evidence, Provider supplied evidence, derived evidence를 명확히 구분해 주세요.

## 라이선스

ExecWeave는 **PolyForm Noncommercial License 1.0.0**으로 배포됩니다. 전체 조건은 [LICENSE](LICENSE)를 참조하세요.
