# ExecWeave

<p align="center">
  <a href="README.md">English</a> |
  <a href="README.zh-TW.md">繁體中文</a> |
  <strong>简体中文</strong> |
  <a href="README.ja.md">日本語</a> |
  <a href="README.ko.md">한국어</a>
</p>

**看清 AI Agent 在你的电脑上实际上做了什么。**

ExecWeave 是一个开源、local-first 的 AI Agent runtime observability 项目，把 Agent 的 runtime activity 转成 evidence-backed execution graph。

## 最快开始

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

实时查看：

```bash
execweave live --open -- claude
```

Live MVP 只绑定 `127.0.0.1`，使用 portable collector。结束后仍会保存 `events.jsonl`、`graph.json` 和 `viewer.html`。

Linux 上需要更强 syscall-backed attribution：

```bash
sudo apt-get install strace
execweave record --backend strace --open -- claude
```

## 当前状态

ExecWeave 当前版本为 **v0.4.0**。

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
- [x] node deduplication
- [x] edge aggregation
- [x] graph summary / filtering / path query
- [x] N-hop focused graph artifact
- [x] large-run leaf condensation
- [x] optional exact cluster expansion evidence

### Phase 3
- [x] standalone local viewer
- [x] portable Live Graph
- [x] pan / zoom / drag / search / details
- [x] node type / relation / causal-only filter
- [x] Timeline ↔ Graph synchronization
- [x] evidence-sequence slider + Play/Pause replay
- [x] progressive cluster expansion
- [x] 1-hop / 2-hop focused runtime neighborhood
- [x] browser-local Saved View presets

Phase 3 Viewer baseline 已包含 replay、按需 cluster 展开、focused neighborhood 与本地保存的 view preset。

### Security Analysis

```bash
execweave analyze run.graph.json
execweave analyze run.graph.json --output analysis.json
```

当前规则会标记 sensitive-file access、external endpoint，以及 possible sensitive-file → network path。

这不是 exfiltration 证明。Report 会明确保留：

```json
{
  "data_flow_proven": false,
  "exfiltration_proven": false
}
```

## 手动流程

```bash
execweave doctor
execweave run --output run.jsonl -- claude
execweave validate run.jsonl
execweave graph run.jsonl --output run.graph.json
execweave view run.graph.json --output run.html --open
```

### Focus 一个 runtime neighborhood

```bash
execweave graph-focus run.graph.json PROCESS_NODE_ID \
  --hops 2 \
  --direction both \
  --causal-only \
  --output focused.graph.json

execweave view focused.graph.json --output focused.html --open
```

`--direction` 支持 `in`、`out`、`both`；可重复使用 `--relation` 限制 traversal edge。所有限制都在 traversal **之前**应用，`graph-focus` 只复制原有 node 与 evidence edge，不会创建 shortcut 或新的 causal relationship。

Viewer 中也可点击 node，选择 **Focus 1 hop** 或 **Focus 2 hops**；**Clear focus** 恢复当前 filter 下的完整 Graph。

### 大型 Graph condensation

```bash
execweave graph-condense run.graph.json \
  --output run.compact.graph.json \
  --threshold 8
```

只折叠单一 incoming relationship、且没有 downstream behavior 的 file/directory/executable leaf。Process、Agent、Session、Socket、Network Endpoint 默认不会折叠。

要让 Viewer 可以按需展开 cluster：

```bash
execweave graph-condense run.graph.json \
  --output run.expandable.graph.json \
  --threshold 8 \
  --keep-expansion

execweave view run.expandable.graph.json \
  --output run.expandable.html \
  --open
```

可展开 cluster 使用虚线边框。点击 cluster 后选择 **Expand cluster**，只会展开该 cluster 的原始 member nodes 与 evidence edges；其他 cluster 保持折叠。**Collapse clusters** 可恢复 compact view。

`--keep-expansion` 只是保存原始 observed nodes/edges，不会创建新的 causal relationship。

## Timeline ↔ Graph

Standalone Viewer 根据 Graph edge 的 `first_sequence` / `last_sequence` 提供 **Evidence sequence** 滑杆与 Play/Pause replay。

如果 aggregated edge 在当前 sequence 只包含部分 evidence，Viewer 会显示 `partial`，不会提前显示最终 `count`。

Timeline 可以与 node type、relation、causal-only、search、focused neighborhood 和 progressive cluster expansion 一起使用。

## Saved Views

Viewer 的 **Save view** 会保存当前 node/relation/causal filter、search、timeline 位置、focus 状态和已展开 cluster。

Preset 默认只保存在浏览器本地 storage，并且**只包含 UI state，不包含 Graph node、edge、event evidence、file content 或 prompt**。如果浏览器不允许 local storage，会安全退化为当前页面 session 内的临时 preset。

## Graph-first event model

```text
source --RELATION--> target
```

例如：

```text
session --LAUNCHED--> process
process --SPAWNED--> process
process --OPENED_READ--> file
process --CONNECTED_TO--> network_endpoint
```

ExecWeave 不会把 temporal correlation 当成 causal proof，也不会把 file/network co-occurrence 当成 byte-level data flow。

## Live Graph

```bash
execweave live --open -- claude
execweave live --port 8765 --open -- claude
```

Live server 只绑定 localhost。详细说明见 [`docs/live-graph.md`](docs/live-graph.md)。

## Privacy

ExecWeave 是 **local-first**。Runtime event、Graph、Viewer 默认留在本机；Saved View 只保存 UI state；无外部 CDN；不采集 file content 或 `read()`/`write()` byte buffer。

## 文档

- [`Phase 1 — Runtime Collection`](docs/phase-1-runtime-collection.md)
- [`Phase 2 — Execution Graph`](docs/phase-2-execution-graph.md)
- [`Live Graph`](docs/live-graph.md)
- [`Security Analysis`](docs/security-analysis.md)

## Contributing

欢迎 Linux eBPF、Windows ETW、macOS Endpoint Security、Graph entity resolution、Agent/Tool/MCP semantic telemetry、OpenTelemetry/MCP、privacy/redaction、testing、performance evaluation 和翻译贡献。

## License

见 [`LICENSE`](LICENSE)。