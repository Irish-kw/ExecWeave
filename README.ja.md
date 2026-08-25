# ExecWeave

<p align="center">
  <a href="README.md">English</a> |
  <a href="README.zh-TW.md">繁體中文</a> |
  <a href="README.zh-CN.md">简体中文</a> |
  <strong>日本語</strong> |
  <a href="README.ko.md">한국어</a>
</p>

**AI Agent があなたのマシン上で実際に何をしたのかを可視化します。**

ExecWeave は open-source / local-first の AI Agent runtime observability プロジェクトです。Agent の runtime activity を evidence-backed execution graph に変換します。

## 最速で試す

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

Live Graph:

```bash
execweave live --open -- claude
```

Live MVP は `127.0.0.1` のみに bind し、portable collector を使います。終了後も `events.jsonl`、`graph.json`、`viewer.html` を保存します。

Linux でより強い syscall-backed attribution を使う場合：

```bash
sudo apt-get install strace
execweave record --backend strace --open -- claude
```

## 現在の状態

ExecWeave は現在 **v0.4.0** です。

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

現在の rule layer は sensitive-file access、external endpoint、同一 process における possible sensitive-file → network path を優先表示します。

これは exfiltration の証明ではありません。Report は明示的に以下を保持します。

```json
{
  "data_flow_proven": false,
  "exfiltration_proven": false
}
```

ExecWeave は co-occurrence を byte-level data flow として扱いません。

## 手動 workflow

```bash
execweave doctor
execweave run --output run.jsonl -- claude
execweave validate run.jsonl
execweave graph run.jsonl --output run.graph.json
execweave view run.graph.json --output run.html --open
```

大きな run：

```bash
execweave graph-condense run.graph.json \
  --output run.compact.graph.json \
  --threshold 8
```

single incoming relationship を持ち downstream behavior のない file/directory/executable leaf のみを collapse します。Process、Agent、Session、Socket、Network Endpoint はデフォルトでは collapse しません。

## Graph-first event model

```text
source --RELATION--> target
```

例：

```text
session --LAUNCHED--> process
process --SPAWNED--> process
process --OPENED_READ--> file
process --CONNECTED_TO--> network_endpoint
```

Repeated evidence は同一 edge に aggregation され、`count` が増加します。

## Fake causality を作らない

Linux syscall-backed evidence は process-level causal edge を提供できます。portable filesystem watcher は session-level observation のため `causal: false` を維持します。

Temporal correlation は causal proof ではなく、file/network activity の共起も data-flow proof ではありません。

## Live Graph

```bash
execweave live --open -- claude
execweave live --port 8765 --open -- claude
```

Live server は `127.0.0.1` のみに bind します。詳細は [`docs/live-graph.md`](docs/live-graph.md)。

## Privacy

ExecWeave は **local-first** です。runtime event、Graph、Viewer はデフォルトでローカルに残り、外部 CDN は不要です。file content や `read()` / `write()` byte buffer は収集しません。

## Documentation

- [`Phase 1 — Runtime Collection`](docs/phase-1-runtime-collection.md)
- [`Phase 2 — Execution Graph`](docs/phase-2-execution-graph.md)
- [`Live Graph`](docs/live-graph.md)
- [`Security Analysis`](docs/security-analysis.md)

## Contributing

Linux eBPF、Windows ETW、macOS Endpoint Security、Graph entity resolution、live/large-graph visualization、OpenTelemetry/MCP、privacy/redaction、testing、performance evaluation、翻訳の contribution を歓迎します。

`README.md` が canonical English source です。

## License

[`LICENSE`](LICENSE) を参照してください。
