<!-- i18n-nav:start -->
<p align="center">
  <a href="live-graph.md">English</a> |
  <strong>繁體中文</strong> |
  <a href="live-graph.zh-CN.md">简体中文</a> |
  <a href="live-graph.ja.md">日本語</a> |
  <a href="live-graph.ko.md">한국어</a>
</p>
<!-- i18n-nav:end -->

# Live Graph

ExecWeave 可以在 AI Agent 或任意 command 還在執行時，持續把本機 runtime evidence materialize 成 execution graph。

```bash
execweave live --open -- claude
```

## 目前契約

目前 Live MVP **刻意只使用 `portable` collector**。

Linux `strace` backend 是 command 結束後才解析 trace file；它提供更強的 syscall-backed attribution，但目前不是 live event source。ExecWeave 不會把 post-processed evidence 標成 live telemetry。

需要 Linux 較強的 post-run attribution：

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

Browser 在 run 進行中輪詢 `/graph.json`。每一個 snapshot 都使用與最終 artifact 相同的 Phase 1 event-stream / Phase 2 graph contract。

Command 結束後 ExecWeave 會：

1. 驗證完成的 event stream；
2. 寫出 `graph.json`；
3. 寫出 standalone `viewer.html`；
4. 將 live graph 標記為 finished；
5. 短暫提供 final viewer 後關閉 local server。

## Network exposure

Live server 只綁定：

```text
127.0.0.1
```

不會綁 `0.0.0.0`，預設不應被 LAN 上其他 host 連到。

指定 port：

```bash
execweave live --port 8765 --open -- claude
```

預設 `--port 0` 代表讓 OS 自動挑可用的 local port。

## Artifacts

預設 run directory：

```text
.execweave/runs/<session-id>/
├── events.jsonl
├── graph.json
└── viewer.html
```

自訂目錄：

```bash
execweave live --output-dir my-live-run --open -- claude
```

既有非空 artifact 會被拒絕，不會直接覆寫。

## Incomplete snapshots

Live run 期間 `events.jsonl` 本來就尚未完成，因為 session 還沒結束。

因此 live snapshot 使用 graph builder 的 `allow_incomplete` mode，但 structural validation 仍有效：malformed JSON、混合 session、非法 entity 或 sequence 破損都不會被當成合法 evidence。

Final graph 只有在 completed-session validation 通過後才建立。

## Portable backend limitations

目前 Live MVP 繼承 portable collector 的限制：

- process discovery 是 polling-based；
- 極短命 process 可能被漏掉；
- filesystem change 是 session-correlated，不是 process-attributed；
- per-process network visibility 受 OS 與 permission 影響。

這些限制會保留在 event attribution metadata。Live Viewer 不會把 non-causal observation 升級成 causal edge。

## Viewer baseline

Live / standalone Viewer 共用相同的 Graph evidence model。Standalone Viewer 目前另提供 node/relation filters、causal-only、observed-only、Timeline、focused neighborhood、cluster expansion、Saved Views，以及 observed / non-causal / inferred edge 的獨立樣式。

## Future native live backends

規劃中的 native collector：

- Linux eBPF
- Windows ETW
- macOS Endpoint Security

目標是維持相同 ExecWeave event semantics，同時提升 completeness、process attribution 與 runtime overhead。

## CI coverage

CI 的 `live` smoke path 會啟動 local live session、執行短 command、產生 final artifacts、驗證 `events.jsonl`，並 summarize graph。Unit/integration tests 也會直接測 localhost `/graph.json` endpoint。
