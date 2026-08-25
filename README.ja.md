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

Phase 3 の Viewer baseline は replay、必要時の cluster expansion、focused neighborhood、ローカル Saved View を含みます。

### Security Analysis

```bash
execweave analyze run.graph.json
execweave analyze run.graph.json --output analysis.json
```

現在の rule layer は sensitive-file access、external endpoint、possible sensitive-file → network path を優先表示します。

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

### Runtime neighborhood に focus する

```bash
execweave graph-focus run.graph.json PROCESS_NODE_ID \
  --hops 2 \
  --direction both \
  --causal-only \
  --output focused.graph.json

execweave view focused.graph.json --output focused.html --open
```

`--direction` は `in`、`out`、`both` を指定できます。`--relation` を複数回使って traversal edge を限定できます。制約は traversal **前**に適用され、`graph-focus` は既存の node と evidence edge だけをコピーします。Shortcut や新しい causal relationship は生成しません。

Viewer でも node をクリックして **Focus 1 hop** / **Focus 2 hops** を選択できます。**Clear focus** で現在の filter 条件下の全 Graph に戻ります。

### Large Graph condensation

```bash
execweave graph-condense run.graph.json \
  --output run.compact.graph.json \
  --threshold 8
```

single incoming relationship を持ち downstream behavior のない file/directory/executable leaf のみを collapse します。Process、Agent、Session、Socket、Network Endpoint はデフォルトでは collapse しません。

Viewer で cluster を必要なときだけ展開するには：

```bash
execweave graph-condense run.graph.json \
  --output run.expandable.graph.json \
  --threshold 8 \
  --keep-expansion

execweave view run.expandable.graph.json \
  --output run.expandable.html \
  --open
```

Expandable cluster は dashed outline で表示されます。Cluster をクリックして **Expand cluster** を選ぶと、その cluster だけが元の member nodes と evidence edges に置き換わります。他の cluster は collapsed のままです。**Collapse clusters** で compact view に戻せます。

`--keep-expansion` は元の observed nodes/edges を保存するだけで、新しい causal relationship は生成しません。

## Timeline ↔ Graph

Standalone Viewer は Graph edge の `first_sequence` / `last_sequence` を使って **Evidence sequence** slider と Play/Pause replay を提供します。

Aggregated edge に現在の sequence より後の evidence が残っている場合は `partial` と表示し、最終 `count` を過去の時点へ先取りして表示しません。

Timeline は node type、relation、causal-only、search、focused neighborhood、progressive cluster expansion と組み合わせて使用できます。

## Saved Views

Viewer の **Save view** は現在の node/relation/causal filter、search、timeline position、focus、expanded clusters を保存します。

Preset はデフォルトで browser-local storage に保存され、**UI state のみを保持します。Graph node、edge、event evidence、file content、prompt は保存しません**。Local storage が利用できない場合は、現在の page session 内だけの preset に安全にフォールバックします。

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

ExecWeave は **local-first** です。runtime event、Graph、Viewer はデフォルトでローカルに残ります。Saved View は UI state だけを保存します。外部 CDN は不要で、file content や `read()` / `write()` byte buffer は収集しません。

## Documentation

- [`Phase 1 — Runtime Collection`](docs/phase-1-runtime-collection.md)
- [`Phase 2 — Execution Graph`](docs/phase-2-execution-graph.md)
- [`Live Graph`](docs/live-graph.md)
- [`Security Analysis`](docs/security-analysis.md)

## Contributing

Linux eBPF、Windows ETW、macOS Endpoint Security、Graph entity resolution、Agent/Tool/MCP semantic telemetry、OpenTelemetry/MCP、privacy/redaction、testing、performance evaluation、翻訳の contribution を歓迎します。

`README.md` が canonical English source です。

## License

[`LICENSE`](LICENSE) を参照してください。