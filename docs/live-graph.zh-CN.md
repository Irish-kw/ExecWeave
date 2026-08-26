<!-- i18n-nav:start -->
<p align="center">
  <a href="live-graph.md">English</a> |
  <a href="live-graph.zh-TW.md">繁體中文</a> |
  <strong>简体中文</strong> |
  <a href="live-graph.ja.md">日本語</a> |
  <a href="live-graph.ko.md">한국어</a> |
  <a href="live-graph.fr.md">Français</a> |
  <a href="live-graph.de.md">Deutsch</a> |
  <a href="live-graph.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# Live Graph

ExecWeave 可以在 AI Agent 或任意 command 还在执行时，持续把本机 runtime evidence materialize 成 execution graph。

```bash
execweave live --open -- claude
```

## 目前契约

目前 Live MVP **刻意只使用 `portable` collector**。

Linux `strace` backend 是 command 结束后才解析 trace file；它提供更强的 syscall-backed attribution，但目前不是 live event source。ExecWeave 不会把 post-processed evidence 标成 live telemetry。

需要 Linux 较强的 post-run attribution：

```bash
execweave record --backend strace --open -- claude
```

## Data flow

```text
command
  ↓
portable collector
  ↓
events.jsonl
  ↓
partial graph materialization
  ↓
localhost HTTP server
  ↓
/graph.json
  ↓
browser viewer
```

Browser 在 run 进行中轮询 `/graph.json`。每一个 snapshot 都使用与最终 artifact 相同的 Phase 1 event-stream / Phase 2 graph contract。

Command 结束后 ExecWeave 会：

1. 验证完成的 event stream；
2. 写出 `graph.json`；
3. 写出 standalone `viewer.html`；
4. 将 live graph 标记为 finished；
5. 短暂提供 final viewer 后关闭 local server。

## Network exposure

Live server 只绑定：

```text
127.0.0.1
```

不会绑 `0.0.0.0`，预设不应被 LAN 上其他 host 连到。

指定 port：

```bash
execweave live --port 8765 --open -- claude
```

预设 `--port 0` 代表让 OS 自动挑可用的 local port。

## Artifacts

预设 run directory：

```text
.execweave/runs/<session-id>/
├── events.jsonl
├── graph.json
└── viewer.html
```

自订目录：

```bash
execweave live --output-dir my-live-run --open -- claude
```

既有非空 artifact 会被拒绝，不会直接覆写。

## Incomplete snapshots

Live run 期间 `events.jsonl` 本来就尚未完成，因为 session 还没结束。

因此 live snapshot 使用 graph builder 的 `allow_incomplete` mode，但 structural validation 仍有效：malformed JSON、混合 session、非法 entity 或 sequence 破损都不会被当成合法 evidence。

Final graph 只有在 completed-session validation 通过后才建立。

## Portable backend limitations

目前 Live MVP 继承 portable collector 的限制：

- process discovery 是 polling-based；
- 极短命 process 可能被漏掉；
- filesystem change 是 session-correlated，不是 process-attributed；
- per-process network visibility 受 OS 与 permission 影响。

这些限制会保留在 event attribution metadata。Live Viewer 不会把 non-causal observation 升级成 causal edge。

## Viewer baseline

Live / standalone Viewer 共用相同的 Graph evidence model。Standalone Viewer 目前另提供 node/relation filters、causal-only、observed-only、Timeline、focused neighborhood、cluster expansion、Saved Views，以及 observed / non-causal / inferred edge 的独立样式。

## Future native live backends

规划中的 native collector：

- Linux eBPF
- Windows ETW
- macOS Endpoint Security

目标是维持相同 ExecWeave event semantics，同时提升 completeness、process attribution 与 runtime overhead。

## CI coverage

CI 的 `live` smoke path 会启动 local live session、执行短 command、产生 final artifacts、验证 `events.jsonl`，并 summarize graph。Unit/integration tests 也会直接测 localhost `/graph.json` endpoint。
