<!-- i18n-nav:start -->
<p align="center">
  <a href="live-graph.md">English</a> |
  <a href="live-graph.zh-TW.md">繁體中文</a> |
  <a href="live-graph.zh-CN.md">简体中文</a> |
  <strong>日本語</strong> |
  <a href="live-graph.ko.md">한국어</a>
</p>
<!-- i18n-nav:end -->

# Live Graph

ExecWeave は AI Agent / command の実行中に local execution graph を更新できます。

```bash
execweave live --open -- claude
```

## Current contract

Live MVP は意図的に `portable` collector を使います。Linux `strace` は command 終了後に trace を parse するため、強い syscall attribution は持ちますが live source ではありません。

Post-run の強い Linux evidence：

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
partial graph
  ↓
127.0.0.1 HTTP server
  ↓
/graph.json
  ↓
browser
```

Browser は `/graph.json` を polling します。Command 終了後、ExecWeave は complete stream を validate し、`graph.json` / standalone `viewer.html` を書き、final viewer を短時間 serve して終了します。

## Network exposure

Server は `127.0.0.1` のみに bind し、`0.0.0.0` には公開しません。

```bash
execweave live --port 8765 --open -- claude
```

Default port `0` は OS に available local port を選ばせます。

## Artifacts

```text
.execweave/runs/<session-id>/
├── events.jsonl
├── graph.json
└── viewer.html
```

```bash
execweave live --output-dir my-live-run --open -- claude
```

既存 non-empty artifacts は overwrite されません。

## Incomplete snapshot

実行中の `events.jsonl` は自然に incomplete です。Live snapshot は `allow_incomplete` を使いますが、malformed JSON、session mismatch、invalid entity、broken sequence などの structural validation は維持します。Final graph は complete-session validation 後だけ作成します。

## Portable limitations

- process discovery は polling-based
- short-lived process を逃す可能性
- filesystem は session-correlated で process-attributed ではない
- network visibility は OS/permission 依存

Viewer はこれらを causal edge に upgrade しません。

Standalone Viewer は filters、observed-only、Timeline、focus、cluster expansion、Saved Views、inferred edge styling も提供します。

## Future native live backends

Linux eBPF、Windows ETW、macOS Endpoint Security を同じ ExecWeave event semantics に接続し、completeness / attribution / overhead を改善する予定です。

CI は live session、final artifacts、stream validation、graph summary と `/graph.json` endpoint をテストします。
