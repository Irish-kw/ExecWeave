# ExecWeave

<p align="center">
  <a href="README.md">English</a> |
  <a href="README.zh-TW.md">繁體中文</a> |
  <a href="README.zh-CN.md">简体中文</a> |
  <strong>日本語</strong> |
  <a href="README.ko.md">한국어</a>
</p>

**AI Agent があなたのマシン上で実際に何をしたのかを可視化します。**

ExecWeave は、ローカル AI Agent の runtime activity を execution graph に変換する、open-source / local-first の observability プロジェクトです。長い CLI log を読む代わりに、Agent、session、process、file、executable、socket、network endpoint の関係を記録し、Graph として materialize し、ブラウザで開ける standalone HTML viewer を生成します。

> **不透明な AI Agent の実行を、人間が理解できる Graph にする。**

## 現在の状態

### Phase 1 — Runtime Collection

**Linux reference path と cross-platform portable fallback は完成しています。**

現在は graph-ready JSONL、monotonic sequence、root/descendant process capture、Linux syscall-backed short-lived process capture、process-attributed filesystem/network evidence、non-blocking/failed connect attempt、portable fallback、causal/non-causal semantics、validator、diagnostics、benchmark、CI を提供します。

### Phase 2 — Execution Graph

**Graph materialization と query layer の最初のコアを実装済みです。**

- validated JSONL → graph JSON
- node deduplication
- repeated edge aggregation
- temporal first/last metadata
- evidence event IDs
- causality preservation
- graph summary / filter
- directed path query

### Phase 3 — Interactive Viewer

**ローカル Viewer MVP を実装済みです。**

- standalone HTML
- CDN / external JavaScript dependency なし
- pan / zoom / node drag
- node / edge details
- graph search
- causal / non-causal edge visualization

Agent 実行中の live update は今後の作業です。

## Quick start

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

Debian / Ubuntu で Linux reference backend を使う場合：

```bash
sudo apt-get install strace
```

完全な流れ：

```bash
execweave doctor
execweave run --output run.jsonl -- claude
execweave validate run.jsonl
execweave graph run.jsonl --output run.graph.json
execweave view run.graph.json --output run.html --open
```

Codex、Gemini CLI、OpenCode、任意の Python Agent なども実行できます。

```bash
execweave run --output run.jsonl -- codex
execweave run --output run.jsonl -- gemini
execweave run --output run.jsonl -- opencode
execweave run --output run.jsonl -- python my_agent.py
```

## Graph-first event model

各 runtime observation は次の形式です。

```text
source --RELATION--> target
```

例：

```text
session --LAUNCHED--> process
process --SPAWNED--> process
process --EXECUTED--> executable
process --OPENED_READ--> file
process --OPENED_WRITE--> file
process --CONNECTED_TO--> network_endpoint
process --CONNECT_ATTEMPTED--> network_endpoint
```

Phase 2 は repeated evidence を aggregate します。同じ process が同じ file を 17 回 open した場合、17 本の重複 edge ではなく、1 本の edge と `count = 17` を保存します。

## Fake causality を作らない

Linux syscall evidence では：

```text
process --OPENED_WRITE--> file
```

を `causal: true` として表現できます。

一方、portable filesystem watcher が証明できるのは：

```text
session --OBSERVED_FILE_CHANGE--> file
```

までなので `causal: false` とします。ExecWeave は temporal correlation を causal proof に格上げしません。

## Backend

### `strace`

Linux reference backend は `strace -ff` で descendants を追跡し、process/filesystem/network syscall evidence を graph-ready event に変換します。

Raw trace はデフォルトで parsing 後に削除されます。

```bash
execweave run --keep-native-trace -- claude
```

### `portable`

psutil + watchdog を使い、Linux / macOS / Windows で動作します。native sensor より弱い filesystem attribution は明示的に non-causal のまま保持します。

`auto` は Linux で `strace` が利用できる場合は `strace` を、そうでなければ `portable` を選択します。

## Event stream validation

```bash
execweave validate run.jsonl
```

Interrupted run：

```bash
execweave validate --allow-incomplete run.jsonl
```

Validator は JSON、schema、event ID、session ID、sequence、timestamp、entity fields、session lifecycle を検証します。

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

詳細：[`docs/phase-2-execution-graph.md`](docs/phase-2-execution-graph.md)

## Interactive Viewer

```bash
execweave view run.graph.json --output run.html --open
```

Viewer は standalone local HTML で、zoom、pan、node drag、search、node/edge details をサポートします。外部 CDN は必要ありません。

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

ExecWeave は **local-first** です。Event、Graph、Viewer はデフォルトでローカルに残り、Viewer は CDN を必要としません。file contents と read/write byte buffers は収集しません。共有前に runtime metadata に機密 path / command / endpoint が含まれていないか確認してください。

## Contributing

**Contributions are very welcome.**

Linux eBPF、Windows ETW、macOS Endpoint Security、Graph entity resolution、large-graph UX、OpenTelemetry/MCP、privacy/redaction、reproducible workload、performance evaluation、documentation translation などを歓迎します。

> **Early contributors are especially welcome.**

## Documentation

- [`Phase 1 — Runtime Collection`](docs/phase-1-runtime-collection.md)
- [`Phase 2 — Execution Graph`](docs/phase-2-execution-graph.md)

## License

See [`LICENSE`](LICENSE).
