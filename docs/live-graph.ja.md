<!-- i18n-nav:start -->
<p align="center">
  <a href="live-graph.md">English</a> |
  <a href="live-graph.zh-TW.md">繁體中文</a> |
  <a href="live-graph.zh-CN.md">简体中文</a> |
  <strong>日本語</strong> |
  <a href="live-graph.ko.md">한국어</a> |
  <a href="live-graph.fr.md">Français</a> |
  <a href="live-graph.de.md">Deutsch</a> |
  <a href="live-graph.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# Live Graph

ExecWeave は AI Agent または任意の command がまだ実行中の間に、local execution graph を stream できます。

```bash
execweave live --open -- claude
```

## Current contract

Live MVP は意図的に `portable` collector を使用します。

Linux `strace` backend は現在 command 終了後に trace file を parse します。より強い syscall-backed attribution を提供しますが、現在の実装では live event source ではありません。ExecWeave は post-processed evidence を live telemetry として扱いません。

より強い Linux post-run attribution が必要な場合：

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

Run が active な間、browser は `/graph.json` を polling します。各 snapshot は final artifact と同じ Phase 1 event-stream contract と Phase 2 graph contract から構築されます。

Command 終了時、ExecWeave は：

1. completed event stream を validate する；
2. `graph.json` を書く；
3. standalone `viewer.html` を書く；
4. live graph を finished として mark する；
5. local server を停止する前に final viewer を短時間 serve する。

## Network exposure

Live server は次の address のみに bind します。

```text
127.0.0.1
```

`0.0.0.0` には公開されず、LAN 上の別 host から到達することを意図していません。

Port を明示する場合：

```bash
execweave live --port 8765 --open -- claude
```

Default の port `0` は available local port を OS に選択させます。

## Artifacts

Default run directory は：

```text
.execweave/runs/<session-id>/
├── events.jsonl
├── graph.json
└── viewer.html
```

別 directory を指定する場合：

```bash
execweave live --output-dir my-live-run --open -- claude
```

既存の non-empty artifact は overwrite せず拒否されます。

## Incomplete snapshots

Live run 中の `events.jsonl` は session がまだ終了していないため、意図的に incomplete です。

したがって live graph snapshot は graph builder の `allow_incomplete` mode を使用します。ただし structural validation は維持されます。Malformed JSON、inconsistent session、invalid entity、broken sequence ordering は valid graph evidence として扱われません。

Final graph は通常の complete-session validation が成功した後にのみ構築されます。

## Portable-backend limitations

現在の live MVP は portable collector の guarantee を引き継ぎます。

- process discovery は polling-based；
- 非常に短命な process は見逃される可能性がある；
- filesystem change は process-attributed ではなく session-correlated；
- per-process network inspection は OS の visibility と permission に依存する。

これらの limitation は event attribution metadata に残ります。Live Viewer は non-causal observation を causal edge に upgrade しません。

## Future native live backends

予定している collector：

- Linux eBPF；
- Windows ETW；
- macOS Endpoint Security。

目標は同じ ExecWeave event semantics を維持したまま completeness、process attribution、runtime overhead を改善することです。

## CI coverage

Repository CI configuration には次を行う `live` smoke path が含まれます。

- local live session を開始；
- 短い command を実行；
- final artifact を書く；
- `events.jsonl` を validate；
- resulting graph を summarize。

Unit/integration test は localhost `/graph.json` endpoint も直接 exercise します。
