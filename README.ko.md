# ExecWeave

<p align="center">
  <a href="README.md">English</a> |
  <a href="README.zh-TW.md">繁體中文</a> |
  <a href="README.zh-CN.md">简体中文</a> |
  <a href="README.ja.md">日本語</a> |
  <strong>한국어</strong>
</p>

**AI 에이전트가 실제로 머신에서 무엇을 했는지 확인하세요.**

ExecWeave는 AI 에이전트 활동을 인터랙티브 execution graph로 변환하는 local-first 오픈소스 observability 프로젝트입니다. Observed evidence와 inference를 명확히 분리합니다.

> **Event is ground truth. The graph is a materialized view.**

## Installation

ExecWeave v0.6.0은 표준 Python wheel / sdist로 패키징되어 있습니다. GitHub 쪽은 PyPI-ready이며, 첫 Trusted Publisher release 전까지 GitHub에서 직접 pip install할 수 있습니다.

```bash
python -m pip install "execweave @ git+https://github.com/Irish-kw/ExecWeave.git@main"
```

개발 설치:

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

첫 PyPI release 이후:

```bash
python -m pip install execweave
```

## Performance / footprint

Reference benchmark는 editable source가 아니라 실제 설치된 wheel에서 실행됩니다. X축은 additional peak process-tree RSS, Y축은 runtime overhead, bubble 면적은 run당 median artifact size입니다. 두 축 모두 낮음→높음이며 왼쪽 아래가 선호 영역입니다.

![ExecWeave overhead trade-off](docs/benchmarks/v0.6.0-github-actions.svg)

Reference environment: GitHub Actions Ubuntu runner, Intel Xeon Platinum 8573C, 4 logical CPUs, Python 3.12.14, `n=7`.

| Profile | Median wall time | Runtime overhead | Additional peak RSS | Median artifacts/run |
| --- | ---: | ---: | ---: | ---: |
| ExecWeave OFF | 236.221 ms | 0.0% | 0.0 MB | 0 KB |
| Portable ON | 391.580 ms | 65.768% | 27.852 MB | 741.355 KB |
| Strace ON | 1226.076 ms | 419.038% | 37.653 MB | 572.838 KB |

같은 build에서 wheel은 약 **113 KB**, sdist는 약 **198 KB**, 설치된 ExecWeave distribution은 약 **849 KB**였습니다. Python과 dependency footprint는 제외합니다.

이 수치는 매우 짧고 file/process-heavy한 **reference microbenchmark** 결과이며 모든 Agent workload에 대한 일반적 overhead 주장이 아닙니다. 실제 배포 전 target host와 대표 workload에서 다시 실행해야 합니다.

```bash
execweave-overhead --iterations 7 --strace auto \
  --output-json benchmark-results.json \
  --output-svg benchmark-overhead.svg
```

Raw data / methodology: [`docs/benchmarks/`](docs/benchmarks/).

## Evidence layers

```text
Agent / IDE semantic evidence
          ↓
Inference gateway / routing evidence
          ↓
Model runtime / inference-server evidence
          ↓
OS runtime evidence: process / file / network
```

기반 telemetry가 직접 뒷받침할 때만 relationship을 causal이라고 표시합니다.

## Integrations

Agent / IDE: Claude Code, OpenAI Codex, Gemini CLI, Cursor, OpenCode.

Inference Gateway: OpenRouter, LiteLLM Proxy. Requested model / resolved model / provider / deployment을 서로 다른 evidence로 보존하며 authoritative metadata가 없으면 routing fact를 추측하지 않습니다.

Model Runtime: Ollama, llama.cpp, vLLM, LM Studio. Prompt / generated content / reasoning content는 저장하지 않습니다. Sensitive local model path는 redact합니다. LM Studio catalog는 `ADVERTISES_MODEL`로 표현하며 catalog visibility를 loaded-memory evidence로 간주하지 않습니다.

Tool → Process correlation은 항상:

```text
inferred: true
causal: false
```

ambiguous / no-match이면 edge를 만들지 않습니다.

Gateway와 Model Runtime 양쪽에 명시적 shared request identity가 있을 때만 `SAME_INFERENCE_REQUEST`를 생성할 수 있습니다:

```text
identity_exact: true
inferred: false
causal: false
```

Raw shared ID는 저장하지 않고 SHA-256-derived identity hash만 보존합니다.

## Runtime evidence

Portable collector는 Linux / macOS / Windows에서 동작하고 Linux에는 syscall-backed `strace` reference backend가 있습니다.

```bash
execweave doctor
execweave run --backend portable -- your-command
execweave run --backend strace -- your-command
```

Portable filesystem observation은 process-causal이 아니라 session-correlated입니다. Future native collectors는 Linux eBPF, Windows ETW, macOS Endpoint Security를 계획하고 있습니다.

## Viewer / Graph / Security

Standalone Viewer는 local self-contained이며 pan/zoom, inspection, filters, **observed only**, search, Timeline replay, cluster expansion, focused neighborhood, Saved Views, 명시적 edge semantics를 지원합니다.

```bash
execweave graph-summary run.graph.json
execweave graph-focus run.graph.json NODE_ID --hops 2 --output focused.graph.json
execweave analyze run.graph.json --output analysis.json
```

Security findings는 evidence limit를 유지하며 possible sensitive-file → network path를 byte-level exfiltration 증명으로 취급하지 않습니다.

## Current status

ExecWeave는 현재 **v0.6.0**입니다. Runtime collection, execution graph, 5개 Agent/IDE integration, OpenRouter/LiteLLM, Ollama/llama.cpp/vLLM/LM Studio, exact Gateway ↔ Runtime identity, PyPI-ready packaging, reference overhead benchmark, cross-platform CI가 baseline에 포함됩니다.

## Privacy

ExecWeave는 local-first입니다. Runtime events, semantic sidecars, graphs, reports, Viewers는 기본적으로 로컬에 남습니다. File content나 raw read/write buffers를 의도적으로 수집하지 않습니다. Artifact를 공유하기 전에 command, path, endpoint, identifier, model metadata를 검토하세요.

## Documentation

- [`Phase 1 — Runtime Collection`](docs/phase-1-runtime-collection.ko.md)
- [`Phase 2 — Execution Graph`](docs/phase-2-execution-graph.ko.md)
- [`Semantic Telemetry`](docs/semantic-telemetry.ko.md)
- [`Inference Gateway`](docs/inference-gateway.ko.md)
- [`Model Runtime`](docs/model-runtime.ko.md)
- [`Performance Benchmarks`](docs/benchmarks/README.md)
- [`Security Analysis`](docs/security-analysis.ko.md)

## License

[`LICENSE`](LICENSE)를 참조하세요.
