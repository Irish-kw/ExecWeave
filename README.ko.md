# ExecWeave

<p align="center">
  <a href="README.md">English</a> |
  <a href="README.zh-TW.md">繁體中文</a> |
  <a href="README.zh-CN.md">简体中文</a> |
  <a href="README.ja.md">日本語</a> |
  <strong>한국어</strong>
</p>

**AI Agent가 내 컴퓨터에서 실제로 무엇을 했는지 확인하세요.**

ExecWeave는 open-source / local-first AI Agent runtime observability 프로젝트입니다. Agent의 runtime activity를 evidence-backed execution graph로 바꿉니다.

## 가장 빠르게 시작하기

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

Live Graph:

```bash
execweave live --open -- claude
```

Live MVP는 `127.0.0.1`에만 bind하며 portable collector를 사용합니다. 종료 후에도 `events.jsonl`, `graph.json`, `viewer.html`을 저장합니다.

### Claude Code: runtime + semantic graph

ExecWeave에는 Claude Code native hook adapter가 있어 Agent / Tool / MCP / Model의 logical evidence를 runtime evidence와 같은 run에 저장할 수 있습니다.

```bash
execweave-claude-hook --print-config
execweave-claude-record --open -- claude
```

Semantic hook이 실행되면 같은 run directory에 runtime-only, semantic-only, merged artifacts를 분리해 저장합니다. `semantic.jsonl`, `events.semantic.jsonl`, `graph.semantic.json`, `viewer.semantic.html`이 생성됩니다.

Claude hook은 logical tool call을 알 수 있지만 실제 Bash child PID를 제공하지 않습니다. 따라서 ExecWeave는 Tool → Process를 직접 observed 또는 causal edge로 가장하지 않습니다.

보수적인 bridge가 필요할 때는 correlation stage를 명시적으로 실행할 수 있습니다.

```bash
execweave correlate run.semantic.jsonl \
  --output run.correlated.jsonl
execweave graph run.correlated.jsonl \
  --output run.correlated.graph.json
execweave view run.correlated.graph.json \
  --output run.correlated.html \
  --open
```

`CORRELATED_WITH_PROCESS`는 bounded tool-call window 안에서 후보가 **유일**하고 exact executable / process / cmdline identity evidence가 있을 때만 생성됩니다. macOS Python framework 같은 launcher process의 경우에도 완전히 동일한 non-empty `argv[1:]`만 fallback으로 허용합니다. 후보가 여러 개이거나 match가 없으면 edge를 생성하지 않습니다.

모든 correlation edge는 `inferred: true`, `causal: false`를 유지하고 inference method, supporting event IDs, heuristic confidence를 기록합니다. Confidence는 probability가 아닙니다.

Linux에서 더 강한 syscall-backed attribution을 사용하려면:

```bash
sudo apt-get install strace
execweave record --backend strace --open -- claude
```

## 현재 상태

ExecWeave는 현재 **v0.4.0**입니다.

### Phase 1
- [x] graph-ready JSONL
- [x] process capture
- [x] Linux syscall-backed filesystem/network evidence
- [x] portable fallback
- [x] validation / diagnostics / benchmark / CI configuration
- [ ] Linux eBPF
- [ ] Windows ETW
- [ ] macOS Endpoint Security

### Phase 2
- [x] Event → Graph
- [x] deduplication / aggregation / query
- [x] N-hop focused graph artifact
- [x] large-run leaf condensation
- [x] optional exact cluster expansion evidence
- [ ] stronger entity resolution
- [ ] time-window snapshots

### Phase 3
- [x] standalone Viewer
- [x] portable Live Graph
- [x] pan / zoom / drag / search / details
- [x] node type / relation / causal-only filter
- [x] Timeline ↔ Graph synchronization
- [x] evidence-sequence slider + Play/Pause replay
- [x] progressive cluster expansion
- [x] 1-hop / 2-hop focused runtime neighborhood
- [x] browser-local Saved View presets
- [x] causal observed / non-causal observed / inferred 독립 styling
- [x] inferred edge에 `· inferred` 명시

### Semantic Telemetry

- [x] provider-agnostic semantic JSONL sidecar
- [x] raw runtime evidence를 변경하지 않는 validated `semantic-merge`
- [x] `agent` / `tool_call` / `tool` / `mcp_server` / `model` / `command` entities
- [x] provider가 PID를 실제로 제공할 때만 conservative `process_reference` resolution
- [x] Claude Code native session/tool/subagent/model hooks
- [x] MCP name normalization
- [x] Linux / macOS / Windows의 run-bound `execweave-claude-record`
- [x] conservative Tool → Process correlation v0.1
- [x] unique-candidate hard requirement; ambiguous / no-match에서는 edge를 생성하지 않음
- [x] inference method / supporting event IDs / bounded time window / heuristic confidence
- [x] correlation edge는 항상 `causal: false`

추가 provider adapter, 더 강한 identity resolution, 더 풍부한 correlation evidence는 향후 작업입니다.

### Security Analysis

```bash
execweave analyze run.graph.json
execweave analyze run.graph.json --output analysis.json
```

현재 rule layer는 sensitive-file access, external endpoint, possible sensitive-file → network path를 우선 표시합니다.

이는 exfiltration 증명이 아닙니다. Report는 명시적으로 다음 값을 유지합니다.

```json
{
  "data_flow_proven": false,
  "exfiltration_proven": false
}
```

ExecWeave는 co-occurrence를 byte-level data flow로 취급하지 않습니다.

## 수동 workflow

```bash
execweave doctor
execweave run --output run.jsonl -- claude
execweave validate run.jsonl
execweave graph run.jsonl --output run.graph.json
execweave view run.graph.json --output run.html --open
```

### Semantic sidecar merge

```bash
execweave semantic-merge run.jsonl semantic.jsonl \
  --output run.semantic.jsonl
```

### Semantic tool call과 runtime process evidence correlate

```bash
execweave correlate run.semantic.jsonl \
  --output run.correlated.jsonl
execweave graph run.correlated.jsonl \
  --output run.correlated.graph.json
```

이 단계는 새로운 derived stream을 만들며 input evidence를 수정하지 않습니다. `CORRELATED_WITH_PROCESS`는 bounded evidence가 정해진 heuristic 아래에서 하나의 후보만 지지한다는 의미이며 provider가 PID를 제공했다는 뜻도, causality가 증명되었다는 뜻도 아닙니다.

### Runtime neighborhood에 focus하기

```bash
execweave graph-focus run.graph.json PROCESS_NODE_ID \
  --hops 2 \
  --direction both \
  --causal-only \
  --output focused.graph.json

execweave view focused.graph.json --output focused.html --open
```

`--direction`은 `in`, `out`, `both`를 지원합니다. `--relation`을 반복해 traversal edge를 제한할 수 있습니다. 모든 제한은 traversal **전에** 적용되며 `graph-focus`는 기존 node와 evidence edge만 복사합니다. Shortcut이나 새로운 causal relationship을 만들지 않습니다.

Viewer에서도 node를 클릭해 **Focus 1 hop** / **Focus 2 hops**를 선택할 수 있습니다. **Clear focus**로 현재 filter 조건의 전체 Graph로 돌아갑니다.

### Large Graph condensation

```bash
execweave graph-condense run.graph.json \
  --output run.compact.graph.json \
  --threshold 8
```

single incoming relationship을 가지며 downstream behavior가 없는 file/directory/executable leaf만 collapse합니다. Process, Agent, Session, Socket, Network Endpoint는 기본적으로 collapse하지 않습니다.

Viewer에서 cluster를 필요할 때만 펼치려면:

```bash
execweave graph-condense run.graph.json \
  --output run.expandable.graph.json \
  --threshold 8 \
  --keep-expansion

execweave view run.expandable.graph.json \
  --output run.expandable.html \
  --open
```

Expandable cluster는 dashed outline으로 표시됩니다. Cluster를 클릭한 뒤 **Expand cluster**를 선택하면 해당 cluster만 원래 member nodes와 evidence edges로 바뀌며 다른 cluster는 collapsed 상태를 유지합니다. **Collapse clusters**로 compact view에 복귀할 수 있습니다.

`--keep-expansion`은 원래 observed nodes/edges를 보존할 뿐 새로운 causal relationship을 만들지 않습니다.

## Timeline ↔ Graph

Standalone Viewer는 Graph edge의 `first_sequence` / `last_sequence`를 사용해 **Evidence sequence** slider와 Play/Pause replay를 제공합니다.

Aggregated edge에 현재 sequence 이후의 evidence가 남아 있다면 `partial`로 표시하며, 최종 `count`를 과거 시점에 미리 노출하지 않습니다.

Timeline은 node type, relation, causal-only, search, focused neighborhood, progressive cluster expansion과 함께 사용할 수 있습니다.

## Saved Views

Viewer의 **Save view**는 현재 node/relation/causal filter, search, timeline 위치, focus 상태, expanded clusters를 저장합니다.

Preset은 기본적으로 browser-local storage에 저장되며 **UI state만 포함합니다. Graph node, edge, event evidence, file content, prompt는 저장하지 않습니다**. Local storage를 사용할 수 없으면 현재 page session 안에서만 유지되는 preset으로 안전하게 fallback합니다.

## Graph-first event model

```text
source --RELATION--> target
```

예시:

```text
session --LAUNCHED--> process
process --SPAWNED--> process
process --OPENED_READ--> file
process --CONNECTED_TO--> network_endpoint
agent --REQUESTED_TOOL_CALL--> tool_call
tool_call --DECLARED_COMMAND--> command
tool_call --CORRELATED_WITH_PROCESS--> process   # inferred only
```

Repeated evidence는 같은 edge로 aggregation되며 `count`가 증가합니다.

## Fake causality를 만들지 않음

Linux syscall-backed evidence는 process-level causal edge를 제공할 수 있습니다. portable filesystem watcher는 session-level observation이므로 `causal: false`를 유지합니다.

Claude hook이 child PID를 제공하지 않으면 semantic evidence를 OS attribution으로 취급하지 않습니다. Correlation stage가 유일한 후보를 찾더라도 edge는 `inferred: true` / `causal: false`를 유지합니다. 단순한 시간적 근접성만으로는 부족하며 ambiguous이면 edge를 생성하지 않습니다.

file/network activity의 공존 역시 byte-level data-flow proof가 아닙니다.

## Live Graph

```bash
execweave live --open -- claude
execweave live --port 8765 --open -- claude
```

Live server는 `127.0.0.1`에만 bind합니다. 자세한 내용은 [`docs/live-graph.ko.md`](docs/live-graph.ko.md)를 참고하세요.

## Privacy

ExecWeave는 **local-first**입니다. runtime event, Graph, Viewer, semantic sidecar, merged graph는 기본적으로 로컬에 남습니다. Saved View는 UI state만 저장합니다. 외부 CDN이 필요하지 않으며 file content나 `read()` / `write()` byte buffer는 수집하지 않습니다.

Runtime / semantic metadata에는 민감한 path, command, endpoint, provider identifier가 포함될 수 있습니다. Artifact를 공유하기 전에 확인하세요.

## Documentation

- [`Phase 1 — Runtime Collection`](docs/phase-1-runtime-collection.ko.md)
- [`Phase 2 — Execution Graph`](docs/phase-2-execution-graph.ko.md)
- [`Live Graph`](docs/live-graph.ko.md)
- [`Semantic Telemetry`](docs/semantic-telemetry.ko.md)
- [`Claude Code Hooks`](docs/claude-code-hooks.ko.md)
- [`Security Analysis`](docs/security-analysis.ko.md)

## Contributing

Linux eBPF, Windows ETW, macOS Endpoint Security, Graph entity resolution, 추가 Agent/Tool/MCP provider adapter, 더 강한 semantic/runtime correlation evidence, OpenTelemetry/MCP, privacy/redaction, testing, performance evaluation, 번역 contribution을 환영합니다.

`README.md`가 canonical English source입니다.

## License

[`LICENSE`](LICENSE)를 참고하세요.