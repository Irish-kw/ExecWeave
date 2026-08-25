# ExecWeave

<p align="center">
  <a href="README.md">English</a> |
  <a href="README.zh-TW.md">繁體中文</a> |
  <a href="README.zh-CN.md">简体中文</a> |
  <strong>日本語</strong> |
  <a href="README.ko.md">한국어</a>
</p>

**AI Agent があなたのマシン上で実際に何をしたのかを可視化します。**

ExecWeave は open-source / local-first の AI Agent runtime observability プロジェクトです。Agent の runtime activity を evidence-backed execution graph に変換し、長い CLI log の代わりに process、file、executable、socket、network endpoint などの関係を可視化します。

> **不透明な AI Agent の実行を、人間が理解できる Graph にする。**

## 最速で試す

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

### Agent 実行中に Live Graph を見る

```bash
execweave live --open -- claude
```

Live MVP は `127.0.0.1` のみに bind し、portable collector から実行中の graph snapshot をブラウザへ更新します。終了後も次の artifact を保存します。

```text
.execweave/runs/<session-id>/
├── events.jsonl
├── graph.json
└── viewer.html
```

現在の Linux `strace` backend は command 終了後に trace を parse するため、live telemetry としては扱いません。

### Linux でより強い syscall-backed attribution を使う

```bash
sudo apt-get install strace
execweave record --backend strace --open -- claude
```

その他：

```bash
execweave live --open -- codex
execweave live --open -- gemini
execweave live --open -- opencode
execweave record --open -- python my_agent.py
```

## 現在の状態

ExecWeave は現在 **v0.3.0** です。

### Phase 1 — Runtime Collection

Linux reference path と cross-platform portable fallback の最初の実用版を実装済みです。

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

実装済み：

- validated JSONL → graph JSON
- node deduplication
- repeated edge aggregation
- temporal metadata
- evidence event IDs
- graph summary / filtering
- directed path query
- large-run leaf-resource condensation

### Phase 3 — Interactive Viewer

実装済み：

- standalone local HTML viewer
- localhost Live Graph MVP
- CDN / external JavaScript 不要
- pan / zoom / node drag
- node / edge detail
- search
- causal / non-causal styling
- directional layout

Progressive cluster expansion と Timeline ↔ Graph synchronization は今後の課題です。

## 手動 workflow

```bash
execweave doctor
execweave run --output run.jsonl -- claude
execweave validate run.jsonl
execweave graph run.jsonl --output run.graph.json
execweave view run.graph.json --output run.html --open
```

大きな run は repetitive leaf resource を先にまとめられます。

```bash
execweave graph-condense run.graph.json \
  --output run.compact.graph.json \
  --threshold 8

execweave view run.compact.graph.json --output run.compact.html --open
```

single incoming relationship を持ち downstream behavior のない file/directory/executable leaf だけが collapse 対象です。Process、Agent、Session、Socket、Network Endpoint はデフォルトでは collapse しません。

## Graph-first event model

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

同じ relation の repeated evidence は 1 本の edge に集約され、`count` が増えます。

## Fake causality を作らない

Linux syscall evidence は process-level attribution を証明できます。一方 portable filesystem watcher は session 中に変更が起きたことしか証明できないため、`causal: false` の session observation として保持します。

ExecWeave は temporal correlation を causal proof として表示しません。

## Live Graph

```bash
execweave live --open -- claude
execweave live --port 8765 --open -- claude
execweave live --linger 10 --open -- claude
```

Live HTTP server は `127.0.0.1` のみに bind し、デフォルトでは LAN に公開されません。詳細は [`docs/live-graph.md`](docs/live-graph.md) を参照してください。

## Privacy

ExecWeave は **local-first** です。runtime event、Graph、Viewer はデフォルトでローカルに残り、外部 CDN は不要です。file content や `read()` / `write()` byte buffer は収集しません。raw Linux syscall trace はデフォルトで parse 後に削除します。

Runtime metadata には sensitive path、command、endpoint が含まれる可能性があるため、artifact を共有する前に確認してください。

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

**ExecWeave への contribution を歓迎します。** Linux eBPF、Windows ETW、macOS Endpoint Security、Graph entity resolution、live/large-graph visualization、OpenTelemetry/MCP、privacy/redaction、testing、performance evaluation などの contribution を特に歓迎します。

`README.md` が canonical English source です。翻訳の追加・更新も歓迎します。

## License

[`LICENSE`](LICENSE) を参照してください。
