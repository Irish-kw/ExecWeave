# ExecWeave

<p align="center">
  <a href="README.md">English</a> |
  <a href="README.zh-TW.md">繁體中文</a> |
  <strong>简体中文</strong> |
  <a href="README.ja.md">日本語</a> |
  <a href="README.ko.md">한국어</a>
</p>

**看清 AI Agent 在你的电脑上实际上做了什么。**

ExecWeave 是一个开源、local-first 的 AI Agent runtime observability 项目。它把本机 Agent 的运行行为转换成 execution graph，而不是让用户阅读冗长的 CLI 日志。

ExecWeave 收集 Agent、session、process、file、executable、socket 和 network endpoint 之间的关系，将事件 materialize 成 Graph，并可生成可直接在浏览器打开的独立本地 HTML viewer。

> **把不透明的 AI Agent 执行过程，变成人真正能理解的图。**

## 当前状态

### Phase 1 — Runtime Collection

**Linux reference path 与跨平台 portable fallback 已完成。**

目前包括：graph-ready JSONL、单调递增 sequence、process tree、Linux syscall-backed 短生命周期 process、process-attributed filesystem/network evidence、非阻塞/失败 connect attempt、跨平台 portable fallback、causal/non-causal 语义、event validator、diagnostics、benchmark 与 CI。

### Phase 2 — Execution Graph

**核心 Graph materialization 与 query layer 已实现。**

- validated JSONL → graph JSON
- node deduplication
- repeated edge aggregation
- temporal first/last metadata
- evidence event IDs
- causality preservation
- graph summary/filter
- directed path query

### Phase 3 — Interactive Viewer

**本地 Viewer MVP 已实现。**

- standalone HTML
- 无 CDN / 外部 JavaScript 依赖
- pan / zoom / node drag
- node / edge 详情
- graph search
- causal / non-causal edge 区分

实时跟随 Agent 执行更新 Graph 仍是后续工作。

## 快速开始

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

Debian / Ubuntu：

```bash
sudo apt-get install strace
```

完整流程：

```bash
execweave doctor
execweave run --output run.jsonl -- claude
execweave validate run.jsonl
execweave graph run.jsonl --output run.graph.json
execweave view run.graph.json --output run.html --open
```

也支持：

```bash
execweave run --output run.jsonl -- codex
execweave run --output run.jsonl -- gemini
execweave run --output run.jsonl -- opencode
execweave run --output run.jsonl -- python my_agent.py
```

## Graph-first event model

每个 runtime observation 表示为：

```text
source --RELATION--> target
```

例如：

```text
session --LAUNCHED--> process
process --SPAWNED--> process
process --EXECUTED--> executable
process --OPENED_READ--> file
process --OPENED_WRITE--> file
process --CONNECTED_TO--> network_endpoint
process --CONNECT_ATTEMPTED--> network_endpoint
```

Phase 2 会聚合重复 evidence。同一 process 对同一 file 发生 17 次相同行为时，Graph 保存一条 edge 加 `count = 17`，而不是 17 条重叠线。

## 不制造假的因果关系

Linux syscall evidence 可产生：

```text
process --OPENED_WRITE--> file
```

并标记 `causal: true`。

Portable filesystem watcher 只能证明：

```text
session --OBSERVED_FILE_CHANGE--> file
```

因此标记 `causal: false`。ExecWeave 不会把时间相关性伪装成因果证明。

## Backend

### `strace`

Linux reference backend 使用 `strace -ff` 跟踪 descendants，将 process/filesystem/network syscall evidence 转成 graph-ready events。

Raw trace 默认解析后删除：

```bash
execweave run --keep-native-trace -- claude
```

### `portable`

使用 psutil + watchdog，可在 Linux、macOS、Windows 运行。较弱的 filesystem attribution 会保持 non-causal，而不会被伪装成 process-level 因果关系。

`auto` 默认在 Linux 有 `strace` 时优先选择 `strace`，否则选择 `portable`。

## Event stream 验证

```bash
execweave validate run.jsonl
```

被中断的 run：

```bash
execweave validate --allow-incomplete run.jsonl
```

Validator 检查 JSON、schema、event ID、session ID、sequence、timestamp、entity fields 与 session lifecycle。

## Graph 查询

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

详细 Graph contract：[`docs/phase-2-execution-graph.md`](docs/phase-2-execution-graph.md)。

## Interactive Viewer

```bash
execweave view run.graph.json --output run.html --open
```

当前支持缩放、平移、拖动 node、搜索以及点击 node/edge 查看 evidence。Viewer 是 standalone local HTML，不依赖外部 CDN。

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
- [ ] 更强 entity resolution
- [ ] Time-window snapshot
- [ ] Large-run evidence indexing

### Phase 3

- [x] Standalone local Viewer MVP
- [x] Pan / zoom / drag / search / details
- [ ] Live graph updates
- [ ] Timeline ↔ Graph
- [ ] Large graph clustering

## Privacy

ExecWeave 是 **local-first**。Event、Graph 与 Viewer 默认都留在本机；Viewer 不依赖 CDN；file contents 与 read/write byte buffers 不会被收集。Runtime metadata 仍可能包含敏感路径、命令和 endpoint，分享前请检查。

## Contributing

**非常欢迎贡献。**

重点方向包括 Linux eBPF、Windows ETW、macOS Endpoint Security、Graph entity resolution、large-graph UX、OpenTelemetry/MCP、privacy/redaction、reproducible workloads、performance evaluation 和文档翻译。

> **特别欢迎早期 contributor。**

## Documentation

- [`Phase 1 — Runtime Collection`](docs/phase-1-runtime-collection.md)
- [`Phase 2 — Execution Graph`](docs/phase-2-execution-graph.md)

## License

See [`LICENSE`](LICENSE).
