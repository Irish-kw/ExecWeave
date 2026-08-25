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
- [x] large-run leaf condensation
- [ ] stronger entity resolution
- [ ] time-window snapshots

### Phase 3
- [x] standalone Viewer
- [x] portable Live Graph
- [x] pan / zoom / drag / search / details
- [ ] progressive cluster expansion
- [ ] Timeline ↔ Graph synchronization

### Security Analysis

```bash
execweave analyze run.graph.json
execweave analyze run.graph.json --output analysis.json
```

현재 rule layer는 sensitive-file access, external endpoint, 같은 process의 possible sensitive-file → network path를 우선 표시합니다.

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

큰 run:

```bash
execweave graph-condense run.graph.json \
  --output run.compact.graph.json \
  --threshold 8
```

single incoming relationship을 가지며 downstream behavior가 없는 file/directory/executable leaf만 collapse합니다. Process, Agent, Session, Socket, Network Endpoint는 기본적으로 collapse하지 않습니다.

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
```

Repeated evidence는 같은 edge로 aggregation되며 `count`가 증가합니다.

## Fake causality를 만들지 않음

Linux syscall-backed evidence는 process-level causal edge를 제공할 수 있습니다. portable filesystem watcher는 session-level observation이므로 `causal: false`를 유지합니다.

Temporal correlation은 causal proof가 아니며 file/network activity의 공존도 data-flow proof가 아닙니다.

## Live Graph

```bash
execweave live --open -- claude
execweave live --port 8765 --open -- claude
```

Live server는 `127.0.0.1`에만 bind합니다. 자세한 내용은 [`docs/live-graph.md`](docs/live-graph.md)를 참고하세요.

## Privacy

ExecWeave는 **local-first**입니다. runtime event, Graph, Viewer는 기본적으로 로컬에 남으며 외부 CDN이 필요하지 않습니다. file content나 `read()` / `write()` byte buffer는 수집하지 않습니다.

## Documentation

- [`Phase 1 — Runtime Collection`](docs/phase-1-runtime-collection.md)
- [`Phase 2 — Execution Graph`](docs/phase-2-execution-graph.md)
- [`Live Graph`](docs/live-graph.md)
- [`Security Analysis`](docs/security-analysis.md)

## Contributing

Linux eBPF, Windows ETW, macOS Endpoint Security, Graph entity resolution, live/large-graph visualization, OpenTelemetry/MCP, privacy/redaction, testing, performance evaluation, 번역 contribution을 환영합니다.

`README.md`가 canonical English source입니다.

## License

[`LICENSE`](LICENSE)를 참고하세요.
