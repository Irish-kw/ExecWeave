# ExecWeave

<p align="center">
  <a href="README.md">English</a> |
  <a href="README.zh-TW.md">繁體中文</a> |
  <a href="README.zh-CN.md">简体中文</a> |
  <a href="README.ja.md">日本語</a> |
  <strong>한국어</strong>
</p>

**AI Agent가 내 컴퓨터에서 실제로 무엇을 했는지 확인하세요.**

ExecWeave는 open-source / local-first AI Agent runtime observability 프로젝트입니다. Agent의 runtime activity를 evidence-backed execution graph로 바꾸어, 수백 줄의 CLI log 대신 process, file, executable, socket, network endpoint 사이의 관계를 이해할 수 있게 합니다.

> **불투명한 AI Agent 실행을 사람이 이해할 수 있는 Graph로 바꿉니다.**

## 가장 빠르게 시작하기

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

### Agent 실행 중 Live Graph 보기

```bash
execweave live --open -- claude
```

Live MVP는 `127.0.0.1`에만 bind하며 portable collector를 사용해 Agent가 실행되는 동안 브라우저 Graph를 계속 업데이트합니다. 종료 후에도 다음 artifact를 저장합니다.

```text
.execweave/runs/<session-id>/
├── events.jsonl
├── graph.json
└── viewer.html
```

현재 Linux `strace` backend는 command 종료 후 trace를 parse하므로 live telemetry로 표시하지 않습니다.

### Linux에서 더 강한 syscall-backed attribution 사용

```bash
sudo apt-get install strace
execweave record --backend strace --open -- claude
```

다른 예시:

```bash
execweave live --open -- codex
execweave live --open -- gemini
execweave live --open -- opencode
execweave record --open -- python my_agent.py
```

## 현재 상태

ExecWeave는 현재 **v0.3.0**입니다.

### Phase 1 — Runtime Collection

Linux reference path와 cross-platform portable fallback의 첫 실용 버전이 구현되어 있습니다.

- graph-ready JSONL event stream
- monotonic sequence
- root / descendant process capture
- Linux syscall-backed short-lived process capture
- process-attributed filesystem/network evidence
- non-blocking / failed connection attempt
- Linux / macOS / Windows portable fallback
- causal / non-causal attribution
- validator / diagnostics / benchmark / CI configuration

### Phase 2 — Execution Graph

구현됨:

- validated JSONL → graph JSON
- node deduplication
- repeated edge aggregation
- temporal metadata
- evidence event IDs
- graph summary / filtering
- directed path query
- large-run leaf-resource condensation

### Phase 3 — Interactive Viewer

구현됨:

- standalone local HTML viewer
- localhost Live Graph MVP
- CDN / external JavaScript 불필요
- pan / zoom / node drag
- node / edge detail
- search
- causal / non-causal styling
- directional layout

Progressive cluster expansion과 Timeline ↔ Graph synchronization은 향후 작업입니다.

## 수동 workflow

```bash
execweave doctor
execweave run --output run.jsonl -- claude
execweave validate run.jsonl
execweave graph run.jsonl --output run.graph.json
execweave view run.graph.json --output run.html --open
```

큰 run에서는 반복되는 leaf resource를 먼저 묶을 수 있습니다.

```bash
execweave graph-condense run.graph.json \
  --output run.compact.graph.json \
  --threshold 8

execweave view run.compact.graph.json --output run.compact.html --open
```

single incoming relationship을 가지고 downstream behavior가 없는 file/directory/executable leaf만 collapse 대상입니다. Process, Agent, Session, Socket, Network Endpoint는 기본적으로 collapse하지 않습니다.

## Graph-first event model

```text
source --RELATION--> target
```

예시:

```text
session --LAUNCHED--> process
process --SPAWNED--> process
process --EXECUTED--> executable
process --OPENED_READ--> file
process --OPENED_WRITE--> file
process --CONNECTED_TO--> network_endpoint
process --CONNECT_ATTEMPTED--> network_endpoint
```

같은 relation의 repeated evidence는 한 edge로 aggregation되며 `count`가 증가합니다.

## Fake causality를 만들지 않음

Linux syscall evidence는 process-level attribution을 증명할 수 있습니다. 반면 portable filesystem watcher는 session 중 변경이 있었다는 사실만 증명할 수 있으므로 `causal: false` session observation으로 유지합니다.

ExecWeave는 temporal correlation을 causal proof처럼 표시하지 않습니다.

## Live Graph

```bash
execweave live --open -- claude
execweave live --port 8765 --open -- claude
execweave live --linger 10 --open -- claude
```

Live HTTP server는 `127.0.0.1`에만 bind하며 기본적으로 LAN에 노출되지 않습니다. 자세한 내용은 [`docs/live-graph.md`](docs/live-graph.md)를 참고하세요.

## Privacy

ExecWeave는 **local-first**입니다. runtime event, Graph, Viewer는 기본적으로 로컬에 남고 외부 CDN이 필요하지 않습니다. file content나 `read()` / `write()` byte buffer는 수집하지 않습니다. raw Linux syscall trace는 기본적으로 parse 후 삭제합니다.

Runtime metadata에는 sensitive path, command, endpoint가 포함될 수 있으므로 artifact 공유 전에 확인하세요.

## Roadmap

### Phase 1
- [x] Runtime collection contract
- [x] Linux reference backend
- [x] Portable fallback
- [x] Validation / causality semantics
- [ ] Linux eBPF
- [ ] Windows ETW
- [ ] macOS Endpoint Security

### Phase 2
- [x] Event → Graph
- [x] Deduplication / aggregation / query
- [x] Large-run leaf condensation
- [ ] Stronger entity resolution
- [ ] Time-window snapshots

### Phase 3
- [x] Standalone Viewer
- [x] Portable Live Graph
- [x] Initial large-graph condensation
- [ ] Progressive cluster expansion
- [ ] Timeline ↔ Graph synchronization

## Contributing

**ExecWeave contribution을 환영합니다.** Linux eBPF, Windows ETW, macOS Endpoint Security, Graph entity resolution, live/large-graph visualization, OpenTelemetry/MCP, privacy/redaction, testing, performance evaluation 분야의 contribution을 특히 환영합니다.

`README.md`가 canonical English source이며 번역 추가와 유지보수도 환영합니다.

## License

[`LICENSE`](LICENSE)를 참고하세요.
