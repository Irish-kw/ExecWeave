# ExecWeave

[![PyPI](https://img.shields.io/pypi/v/execweave?label=PyPI)](https://pypi.org/project/execweave/)
[![Python](https://img.shields.io/pypi/pyversions/execweave?label=Python)](https://pypi.org/project/execweave/)
[![CI](https://github.com/Irish-kw/ExecWeave/actions/workflows/ci.yml/badge.svg)](https://github.com/Irish-kw/ExecWeave/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/Irish-kw/ExecWeave?style=flat&label=Stars)](https://github.com/Irish-kw/ExecWeave/stargazers)

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

**AI 에이전트가 실제로 머신에서 무엇을 했는지 확인하세요.**

ExecWeave는 AI 에이전트 활동을 인터랙티브 execution graph로 변환하면서 observed evidence와 inference를 명확히 분리하는 오픈소스 local-first observability 프로젝트입니다.

> **Event가 ground truth이며, Graph는 materialized view입니다.**

<p align="center">
  <img src="docs/assets/execweave-viewer.png" alt="ExecWeave Live execution graph" width="100%">
</p>

## 설치

ExecWeave는 표준 Python wheel/sdist 형태로 PyPI에 공개되어 있습니다. 최신 release 설치:

```bash
python -m pip install -U execweave
```

`main` branch에는 현재 PyPI release보다 더 새로운 patch가 포함될 수 있습니다. 최신 mainline build를 직접 테스트하려면:

```bash
python -m pip install --upgrade --force-reinstall "execweave @ git+https://github.com/Irish-kw/ExecWeave.git@main"
```

개발용 설치:

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

Claude Code, OpenAI Codex, Gemini CLI를 실시간으로 관찰:

```bash
# Claude Code
execweave live --open -- claude

# OpenAI Codex
execweave live --open -- codex

# Gemini CLI
execweave live --open -- gemini
```

또는 전체 artifact pipeline을 생성합니다.

```bash
execweave record --open -- python my_agent.py
```

## 성능과 footprint

ExecWeave에는 실제 설치된 wheel에서 실행되는 재현 가능한 package-level overhead benchmark가 포함되어 있습니다. Reference plot은 모델 quality/cost 비교에서 자주 쓰이는 trade-off 형식을 따릅니다.

- **X축:** 추가 peak process-tree RSS, 낮음 → 높음.
- **Y축:** runtime overhead, 낮음 → 높음.
- **Bubble 면적:** run당 median artifact size.
- **선호 영역:** 왼쪽 아래.

![ExecWeave overhead trade-off](docs/benchmarks/v0.6.0-github-actions.svg)

Reference environment: GitHub Actions Ubuntu runner, Intel Xeon Platinum 8573C, 4 logical CPUs, Python 3.12.14, `n=7`.

| Profile | Median wall time | Runtime overhead | Additional peak RSS | Median artifacts/run |
| --- | ---: | ---: | ---: | ---: |
| ExecWeave OFF | 236.221 ms | 0.0% | 0.0 MB | 0 KB |
| Portable ON | 391.580 ms | 65.768% | 27.852 MB | 741.355 KB |
| Strace ON | 1226.076 ms | 419.038% | 37.653 MB | 572.838 KB |

같은 build에서 약 **113 KB wheel**과 **198 KB sdist**가 생성되었습니다. 설치된 ExecWeave distribution 자체는 약 **849 KB**이며 Python과 dependency footprint는 제외합니다.

이 수치는 의도적으로 짧고 file/process-heavy한 **reference microbenchmark** 결과이며 모든 workload에 대한 일반적 성능 주장이 아닙니다. 비계측 baseline이 수백 밀리초에 불과하기 때문에 percentage overhead가 크게 보입니다. 용량 계획 전에 대상 호스트와 대표 workload에서 `execweave-overhead`를 다시 실행하세요.

```bash
execweave-overhead \
  --iterations 7 \
  --strace auto \
  --output-json benchmark-results.json \
  --output-svg benchmark-overhead.svg
```

Raw reference data와 방법론: [`docs/benchmarks/`](docs/benchmarks/).

## Evidence layers

ExecWeave는 서로 다른 네 개의 evidence layer를 하나의 trace로 평탄화하지 않고 의도적으로 분리합니다.

```text
Agent / IDE semantic evidence
          ↓
Inference gateway / routing evidence
          ↓
Model runtime / inference-server evidence
          ↓
OS runtime evidence: process / file / network
```

기반 telemetry가 해당 주장을 뒷받침할 때만 relationship을 causal로 표시합니다.

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

Cursor는 안정적인 `tool_use_id`를 제공하므로 pre/post hooks 사이에 exact logical tool-call identity를 설정할 수 있습니다.

### OpenCode

```bash
execweave-opencode-plugin --install
execweave-opencode-record --open -- opencode
```

Project-local OpenCode plugin은 exact `sessionID + callID` identity를 사용하며 tool output을 의도적으로 전달하지 않습니다.

Provider-integrated run은 runtime, semantic, correlated artifacts를 분리하여 보존합니다. Tool → Process bridge는 항상 보수적인 derived evidence로 유지됩니다.

```text
inferred: true
causal: false
```

Evidence가 ambiguous하면 edge를 만들지 않습니다.

## Inference gateway integrations

OpenRouter와 LiteLLM Proxy는 local model runtime이 아니라 `inference_gateway`로 모델링됩니다.

```bash
execweave-inference-gateway event \
  --gateway litellm \
  --requested-model assistant \
  --resolved-model azure/gpt-5 \
  --provider-name Azure \
  --deployment-id deployment-west \
  --sidecar gateway.jsonl
```

ExecWeave는 requested model, resolved model, routed provider, deployment identity를 서로 다른 evidence로 보존합니다. Provider/deployment edge는 authoritative metadata가 제공된 경우에만 생성하며 model-name prefix에서 추측하지 않습니다.

Caller가 Gateway와 Model Runtime observation 사이의 명시적인 shared identity를 알고 있다면 layer를 합치지 않고 두 request node를 연결할 수 있습니다.

```bash
execweave-inference-link \
  --gateway litellm \
  --gateway-request-id gw-123 \
  --runtime vllm \
  --runtime-request-id rt-456 \
  --shared-request-id trace-789 \
  --sidecar inference.jsonl
```

`SAME_INFERENCE_REQUEST`는 exact identity evidence이며 causal evidence가 아닙니다.

```text
identity_exact: true
inferred: false
causal: false
```

Raw shared request ID는 저장하지 않고 SHA-256-derived identity hash만 보존합니다.

## Model runtime integrations

현재 model-runtime integrations는 **Ollama**, **llama.cpp**, **vLLM**, **LM Studio**입니다.

```bash
execweave-model-runtime event --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime llamacpp --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime vllm --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime lmstudio --sidecar model-runtime.jsonl
```

OpenAI-compatible runtimes는 response/usage와 model-catalog parsing을 공유하면서 runtime-specific evidence semantics를 유지합니다. Prompt, generated content, reasoning content는 저장하지 않습니다. Sensitive local model path는 redaction되며 llama.cpp는 GGUF path에 더 엄격한 redaction을 적용합니다.

LM Studio model-catalog visibility는 `ADVERTISES_MODEL`로 표현하며 model weights가 메모리에 로드되었다는 증거로 취급하지 않습니다.

## Runtime evidence

Portable collector는 Linux, macOS, Windows에서 동작합니다. Linux에는 syscall-backed `strace` reference backend도 있습니다.

```bash
execweave doctor
execweave run --backend portable -- your-command
execweave run --backend strace -- your-command
```

v0.6.1부터 child command는 실행 전에 공통 cross-platform launcher resolver를 거칩니다. Linux와 macOS는 일반적인 PATH executable 동작을 유지합니다. Windows는 PATH/PATHEXT를 통해 `.exe`, `.cmd`, `.bat`를 해석하며 명시적인 `.ps1` launcher는 PowerShell로 실행합니다. 전용 Windows CI는 `cmd.exe`와 Windows PowerShell 모두에서 Codex/Cursor recorder를 실행하며, 전체 Cursor semantic/correlation integration은 일반 Windows, macOS, Ubuntu matrix에서도 계속 검증됩니다.

Portable filesystem watching은 session-correlated이며 process-causal이 아닙니다. 매우 짧은 process는 polling interval 사이에서 누락될 수 있습니다. Linux `strace` path는 command 종료 후 process-attributed syscall evidence를 제공합니다.

향후 native collector로 Linux eBPF, Windows ETW, macOS Endpoint Security를 계획하고 있습니다.

## v0.6.2 safety patch

v0.6.2는 evidence semantics나 graph schema 0.1을 바꾸지 않고 long-running/high-cardinality session의 resource safety를 강화합니다.

- filesystem root, user home, users-home parent처럼 지나치게 넓은 recursive filesystem scope는 그대로 recursive observation하지 않습니다. Process, network, semantic collection은 계속할 수 있습니다.
- Standalone/Live Viewer는 safety budget(1,500 nodes, 4,000 edges, 또는 추정 5,000 SVG elements)을 넘으면 SVG materialization을 중단하여 browser memory exhaustion을 방지합니다. Canonical `graph.json` evidence artifact는 완전하게 유지됩니다.
- Viewer layout/fit은 임의로 큰 array를 `Math.min` / `Math.max`에 spread하지 않으며 node dragging 중 edge redraw는 animation-frame throttling됩니다.
- Live server는 byte offset 이후의 `events.jsonl` 추가 bytes만 tail하고 in-memory `GraphAccumulator`를 incremental하게 갱신합니다. `/graph.json` polling은 전체 event history를 다시 재생하지 않으며 newline이 없는 incomplete trailing JSONL line은 buffer합니다.
- event-count 또는 aggregate-count만 변할 때는 full topology redraw 없이 Live stats/edge labels만 갱신합니다. Viewer budget을 넘은 뒤 live `/graph.json`은 counts-only compact payload로 전환하지만 collection과 최종 canonical validation/full `graph.json`은 계속됩니다.

이것은 polling + incremental-ingestion safety patch이며 SSE, SQLite, Rust, Canvas architecture migration이 아닙니다.

## Layered artifacts

Provider-integrated run은 다음 artifacts를 생성할 수 있습니다.

```text
.execweave/runs/<run-id>/
├── events.jsonl
├── graph.json
├── viewer.html
├── semantic.jsonl
├── events.semantic.jsonl
├── graph.semantic.json
├── viewer.semantic.html
├── events.correlated.jsonl
├── graph.correlated.json
└── viewer.correlated.html
```

Derived correlation layer는 raw evidence를 다시 쓰지 않습니다.

## Interactive Viewer

Standalone Viewer는 local이고 self-contained입니다. 현재 baseline에는 pan/zoom, draggable nodes, node/edge inspection, node-type/relation/causal filters, **observed only**, search, evidence-sequence replay, progressive cluster expansion, focused neighborhoods, Saved Views, 명시적 edge semantics, Correlation Summary가 포함됩니다.

## Graph operations

```bash
execweave graph-summary run.graph.json
execweave graph-filter run.graph.json --output causal.graph.json --causal-only
execweave graph-focus run.graph.json NODE_ID --hops 2 --output focused.graph.json
execweave path run.graph.json SOURCE TARGET --causal-only
execweave graph-condense run.graph.json --output compact.graph.json --threshold 8 --keep-expansion
```

## Security analysis

```bash
execweave analyze run.graph.json --output analysis.json
```

Security finding은 evidence limit를 명확히 유지합니다. Possible sensitive-file → network path는 byte-level exfiltration이 증명되었다는 뜻이 아닙니다.

```json
{
  "data_flow_proven": false,
  "exfiltration_proven": false
}
```

## 현재 상태

ExecWeave `main`은 현재 **v0.6.2**이며 활발히 개발 중입니다.

Baseline에는 runtime collection, graph materialization/querying, standalone/live Viewer, Claude/Codex/Gemini/Cursor/OpenCode semantic integrations, 보수적인 Tool → Process correlation, OpenRouter/LiteLLM gateway metadata, Ollama/llama.cpp/vLLM/LM Studio runtime metadata, exact Gateway ↔ Model Runtime request identity, 공개된 PyPI wheel/sdist packaging, 재현 가능한 overhead benchmarking, cross-platform command-launcher compatibility, large-graph browser safety guards, incremental Live JSONL tail/cache, Python 3.10/3.12 cross-platform CI가 포함됩니다.

## Privacy

ExecWeave는 local-first입니다. Runtime events, semantic sidecars, graphs, reports, Viewers는 기본적으로 로컬에 남습니다. File contents나 raw read/write byte buffers는 의도적으로 수집하지 않습니다. Native adapters도 기본적으로 prompts/transcripts/tool output을 피하지만 commands, paths, endpoint metadata, identifiers, model metadata에는 민감한 정보가 포함될 수 있습니다.

Artifacts를 공유하기 전에 검토하세요.

## 문서

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
- [`Performance Benchmarks`](docs/benchmarks/README.md)
- [`Security Analysis`](docs/security-analysis.ko.md)

## Contributing

특히 native OS collectors, 추가 Agent/IDE adapters, inference gateways, model runtimes, entity/correlation methods, privacy/redaction, graph UX, performance evaluation 관련 기여를 환영합니다.

## License

[`LICENSE`](LICENSE)를 참조하세요.