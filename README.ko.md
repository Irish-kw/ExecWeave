# ExecWeave

<p align="center">
  <a href="README.md">English</a> |
  <a href="README.zh-TW.md">繁體中文</a> |
  <a href="README.zh-CN.md">简体中文</a> |
  <a href="README.ja.md">日本語</a> |
  <strong>한국어</strong>
</p>

**AI Agent가 내 컴퓨터에서 실제로 무엇을 했는지 확인하세요.**

ExecWeave는 로컬 AI Agent의 runtime activity를 execution graph로 변환하는 open-source / local-first observability 프로젝트입니다. 긴 CLI log를 읽는 대신 Agent, session, process, file, executable, socket, network endpoint 사이의 관계를 기록하고 Graph로 materialize한 뒤, 브라우저에서 열 수 있는 standalone HTML viewer를 생성합니다.

> **불투명한 AI Agent 실행을 사람이 이해할 수 있는 Graph로 바꿉니다.**

## 현재 상태

### Phase 1 — Runtime Collection

**Linux reference path와 cross-platform portable fallback이 완료되었습니다.**

현재 graph-ready JSONL, monotonic sequence, root/descendant process capture, Linux syscall-backed short-lived process capture, process-attributed filesystem/network evidence, non-blocking/failed connect attempt 보존, portable fallback, causal/non-causal semantics, validator, diagnostics, benchmark, CI를 제공합니다.

### Phase 2 — Execution Graph

**Graph materialization 및 query layer의 첫 번째 core가 구현되었습니다.**

- validated JSONL → graph JSON
- node deduplication
- repeated edge aggregation
- temporal first/last metadata
- evidence event IDs
- causality preservation
- graph summary / filter
- directed path query

### Phase 3 — Interactive Viewer

**로컬 Viewer MVP가 구현되었습니다.**

- standalone HTML
- CDN / external JavaScript dependency 없음
- pan / zoom / node drag
- node / edge details
- graph search
- causal / non-causal edge visualization

Agent가 실행되는 동안 Graph를 live update하는 기능은 향후 작업입니다.

## Quick start

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

Debian / Ubuntu에서 Linux reference backend를 사용하려면:

```bash
sudo apt-get install strace
```

전체 흐름:

```bash
execweave doctor
execweave run --output run.jsonl -- claude
execweave validate run.jsonl
execweave graph run.jsonl --output run.graph.json
execweave view run.graph.json --output run.html --open
```

Codex, Gemini CLI, OpenCode 또는 임의의 Python Agent도 실행할 수 있습니다.

```bash
execweave run --output run.jsonl -- codex
execweave run --output run.jsonl -- gemini
execweave run --output run.jsonl -- opencode
execweave run --output run.jsonl -- python my_agent.py
```

## Graph-first event model

각 runtime observation은 다음 형식으로 표현됩니다.

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

Phase 2는 repeated evidence를 aggregate합니다. 같은 process가 같은 file을 17번 open했다면 17개의 겹치는 edge 대신 하나의 edge와 `count = 17`을 저장합니다.

## Fake causality를 만들지 않습니다

Linux syscall evidence는 다음을 증명할 수 있습니다.

```text
process --OPENED_WRITE--> file
```

이 경우 `causal: true`로 기록합니다.

반면 portable filesystem watcher가 증명할 수 있는 것은 다음 정도입니다.

```text
session --OBSERVED_FILE_CHANGE--> file
```

따라서 `causal: false`로 유지합니다. ExecWeave는 temporal correlation을 causal proof로 승격하지 않습니다.

## Backend

### `strace`

Linux reference backend는 `strace -ff`로 descendant process를 추적하고 process/filesystem/network syscall evidence를 graph-ready event로 변환합니다.

Raw trace는 기본적으로 parsing 후 삭제됩니다.

```bash
execweave run --keep-native-trace -- claude
```

### `portable`

psutil + watchdog를 사용하며 Linux / macOS / Windows에서 동작합니다. native sensor보다 약한 filesystem attribution은 명시적으로 non-causal 상태로 유지됩니다.

`auto`는 Linux에서 `strace`가 사용 가능하면 `strace`, 그렇지 않으면 `portable`을 선택합니다.

## Event stream validation

```bash
execweave validate run.jsonl
```

Interrupted run:

```bash
execweave validate --allow-incomplete run.jsonl
```

Validator는 JSON, schema, event ID, session ID, sequence, timestamp, entity fields, session lifecycle을 검사합니다.

## Graph query

```bash
execweave graph-summary run.graph.json
```

```bash
execweave graph-filter run.graph.json --output causal.graph.json --causal-only
```

```bash
execweave graph-filter run.graph.json \
  --output process-network.graph.json \
  --node-type process \
  --node-type network_endpoint
```

```bash
execweave path run.graph.json SOURCE_NODE_ID TARGET_NODE_ID --causal-only
```

자세한 Graph contract: [`docs/phase-2-execution-graph.md`](docs/phase-2-execution-graph.md)

## Interactive Viewer

```bash
execweave view run.graph.json --output run.html --open
```

Viewer는 standalone local HTML이며 zoom, pan, node drag, search, node/edge details를 지원합니다. 외부 CDN이 필요하지 않습니다.

## Roadmap

### Phase 1

- [x] Runtime event schema / collection
- [x] Linux short-lived process capture
- [x] Causal semantics
- [x] Validation / diagnostics / benchmark
- [x] Cross-platform portable fallback
- [ ] Linux eBPF
- [ ] Windows ETW
- [ ] macOS Endpoint Security

### Phase 2

- [x] Event → Graph
- [x] Node dedup / edge aggregation
- [x] Temporal metadata
- [x] Summary / filter / path query
- [ ] Stronger entity resolution
- [ ] Time-window snapshot
- [ ] Large-run evidence indexing

### Phase 3

- [x] Standalone local Viewer MVP
- [x] Pan / zoom / drag / search / details
- [ ] Live graph update
- [ ] Timeline ↔ Graph synchronization
- [ ] Large graph clustering

## Privacy

ExecWeave는 **local-first**입니다. Event, Graph, Viewer는 기본적으로 로컬에 남으며 Viewer는 CDN을 필요로 하지 않습니다. file contents와 read/write byte buffer는 수집하지 않습니다. 공유 전 runtime metadata에 민감한 path / command / endpoint가 포함되어 있지 않은지 확인하세요.

## Contributing

**Contribution을 환영합니다.**

Linux eBPF, Windows ETW, macOS Endpoint Security, Graph entity resolution, large-graph UX, OpenTelemetry/MCP, privacy/redaction, reproducible workload, performance evaluation, documentation translation 등의 기여를 환영합니다.

> **Early contributors are especially welcome.**

## Documentation

- [`Phase 1 — Runtime Collection`](docs/phase-1-runtime-collection.md)
- [`Phase 2 — Execution Graph`](docs/phase-2-execution-graph.md)

## License

See [`LICENSE`](LICENSE).
