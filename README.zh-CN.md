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
- [x] large-run leaf condensation

### Phase 3
- [x] standalone local viewer
- [x] portable Live Graph
- [x] pan / zoom / drag / search / details
- [ ] progressive cluster expansion
- [ ] Timeline ↔ Graph synchronization

### Security Analysis

```bash
execweave analyze run.graph.json
execweave analyze run.graph.json --output analysis.json
```

当前规则会标记 sensitive-file access、external endpoint，以及同一 process 的 possible sensitive-file → network path。

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

大型 run：

```bash
execweave graph-condense run.graph.json \
  --output run.compact.graph.json \
  --threshold 8
```

只折叠单一 incoming relationship、且没有 downstream behavior 的 file/directory/executable leaf。Process、Agent、Session、Socket、Network Endpoint 默认不会折叠。

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

ExecWeave 是 **local-first**。Runtime event、Graph、Viewer 默认留在本机；无外部 CDN；不采集 file content 或 `read()`/`write()` byte buffer。

## 文档

- [`Phase 1 — Runtime Collection`](docs/phase-1-runtime-collection.md)
- [`Phase 2 — Execution Graph`](docs/phase-2-execution-graph.md)
- [`Live Graph`](docs/live-graph.md)
- [`Security Analysis`](docs/security-analysis.md)

## Contributing

欢迎 Linux eBPF、Windows ETW、macOS Endpoint Security、Graph entity resolution、live/large-graph visualization、OpenTelemetry/MCP、privacy/redaction、testing、performance evaluation 和翻译贡献。

## License

见 [`LICENSE`](LICENSE)。
