# ExecWeave

<p align="center">
  <a href="README.md">English</a> |
  <a href="README.zh-TW.md">繁體中文</a> |
  <strong>简体中文</strong> |
  <a href="README.ja.md">日本語</a> |
  <a href="README.ko.md">한국어</a>
</p>

**看清 AI Agent 在你的电脑上实际上做了什么。**

ExecWeave 是一个开源、local-first 的 AI Agent runtime observability 项目。它把 Agent 的 runtime activity 转成有 evidence 支撑的 execution graph，而不是让用户阅读成百上千行 CLI 日志。

> **把不透明的 AI Agent 执行过程，变成人真正能理解的图。**

## 最快开始

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

### Agent 运行时实时查看 Graph

```bash
execweave live --open -- claude
```

Live MVP 只绑定 `127.0.0.1`，使用 portable collector，在 Agent 运行期间持续更新浏览器中的 Graph。Agent 退出后仍会保存：

```text
.execweave/runs/<session-id>/
├── events.jsonl
├── graph.json
└── viewer.html
```

目前 Linux `strace` backend 在 command 结束后才解析，因此不会被伪装成 live telemetry。

### Linux 上需要更强的 syscall-backed attribution

```bash
sudo apt-get install strace
execweave record --backend strace --open -- claude
```

其他示例：

```bash
execweave live --open -- codex
execweave live --open -- gemini
execweave live --open -- opencode
execweave record --open -- python my_agent.py
```

## 当前状态

ExecWeave 当前版本为 **v0.3.0**。

### Phase 1 — Runtime Collection

Linux reference path 与跨平台 portable fallback 已完成第一版：

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

已实现：

- validated JSONL → graph JSON
- node deduplication
- repeated edge aggregation
- temporal metadata
- evidence event IDs
- graph summary / filtering
- directed path query
- large-run leaf-resource condensation

### Phase 3 — Interactive Viewer

已实现：

- standalone local HTML viewer
- localhost live graph MVP
- 无 CDN / 外部 JavaScript
- pan / zoom / node drag
- node / edge detail
- search
- causal / non-causal styling
- directional layout

Progressive cluster expansion 与 Timeline ↔ Graph synchronization 仍是后续工作。

## 手动流程

```bash
execweave doctor
execweave run --output run.jsonl -- claude
execweave validate run.jsonl
execweave graph run.jsonl --output run.graph.json
execweave view run.graph.json --output run.html --open
```

大型 run 可以先压缩重复 leaf resource：

```bash
execweave graph-condense run.graph.json \
  --output run.compact.graph.json \
  --threshold 8

execweave view run.compact.graph.json --output run.compact.html --open
```

只会折叠具有单一 incoming relationship、且没有 downstream behavior 的 file/directory/executable leaf。Process、Agent、Session、Socket、Network Endpoint 默认不会被折叠。

## Graph-first event model

```text
source --RELATION--> target
```

示例：

```text
session --LAUNCHED--> process
process --SPAWNED--> process
process --EXECUTED--> executable
process --OPENED_READ--> file
process --OPENED_WRITE--> file
process --CONNECTED_TO--> network_endpoint
process --CONNECT_ATTEMPTED--> network_endpoint
```

重复 evidence 会聚合为一条 edge 并增加 `count`，而不是画出大量重叠线。

## 不制造假的因果关系

Linux syscall evidence 可以产生：

```text
process --OPENED_WRITE--> file
```

并标记：

```json
{"attribution":"syscall","causal":true}
```

Portable filesystem watcher 只能证明 session 期间发生变化，因此使用：

```text
session --OBSERVED_FILE_CHANGE--> file
```

并标记 `causal: false`。ExecWeave 不会把 temporal correlation 当成 causal proof。

## Live Graph

```bash
execweave live --open -- claude
execweave live --port 8765 --open -- claude
execweave live --linger 10 --open -- claude
```

Live HTTP server 只绑定 `127.0.0.1`，默认不会暴露到 LAN。详细契约见 [`docs/live-graph.md`](docs/live-graph.md)。

## Privacy

ExecWeave 是 **local-first**：runtime event、Graph 与 Viewer 默认都留在本机；不需要外部 CDN；不收集 file content 或 `read()`/`write()` byte buffer；raw Linux syscall trace 默认解析后删除。

Runtime metadata 仍可能包含敏感 path、command、endpoint，分享 artifact 前请检查。

## Roadmap

### Phase 1
- [x] Runtime collection contract
- [x] Linux reference backend
- [x] Portable fallback
- [x] Event validation / causality semantics
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

**非常欢迎贡献 ExecWeave。** 特别需要 Linux eBPF、Windows ETW、macOS Endpoint Security、Graph entity resolution、live/large-graph visualization、OpenTelemetry/MCP、privacy/redaction、测试与性能评估方面的贡献。

`README.md` 是 canonical English source，欢迎继续增加和维护翻译。

## License

见 [`LICENSE`](LICENSE)。
