<!-- i18n-nav:start -->
<p align="center">
  <a href="live-graph.md">English</a> |
  <a href="live-graph.zh-TW.md">繁體中文</a> |
  <a href="live-graph.zh-CN.md">简体中文</a> |
  <a href="live-graph.ja.md">日本語</a> |
  <strong>한국어</strong>
</p>
<!-- i18n-nav:end -->

# Live Graph

ExecWeave는 AI Agent 또는 arbitrary command가 실행 중일 때 local execution graph를 계속 갱신할 수 있습니다.

```bash
execweave live --open -- claude
```

## Current contract

Live MVP는 의도적으로 `portable` collector를 사용합니다. Linux `strace`는 command 종료 후 trace file을 parse하므로 더 강한 syscall attribution을 제공하지만 현재 live source는 아닙니다.

Linux post-run evidence가 더 필요하면:

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

Browser가 `/graph.json`을 polling합니다. Command 종료 후 complete stream을 validate하고 `graph.json` / standalone `viewer.html`을 쓴 뒤 final viewer를 잠시 serve하고 종료합니다.

## Network exposure

Server는 오직 `127.0.0.1`에 bind하며 `0.0.0.0`으로 공개하지 않습니다.

```bash
execweave live --port 8765 --open -- claude
```

기본 `--port 0`은 OS가 사용 가능한 local port를 선택합니다.

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

기존 non-empty artifact는 overwrite하지 않습니다.

## Incomplete snapshots

Run 중 `events.jsonl`은 아직 incomplete이므로 snapshot은 `allow_incomplete`를 사용합니다. 그러나 malformed JSON, session mismatch, invalid entity, broken sequence 같은 structural validation은 계속 적용됩니다. Final graph는 completed-session validation 뒤에만 생성합니다.

## Portable limitations

- process discovery는 polling-based
- short-lived process를 놓칠 수 있음
- filesystem은 session-correlated, process-attributed가 아님
- network visibility는 OS/permission 의존

Viewer는 이런 evidence를 causal edge로 upgrade하지 않습니다.

Standalone Viewer는 node/relation filters, observed-only, Timeline, focus, cluster expansion, Saved Views, inferred edge styling도 제공합니다.

## Future native live backends

Linux eBPF, Windows ETW, macOS Endpoint Security를 같은 ExecWeave event semantics에 연결해 completeness, attribution, overhead를 개선할 예정입니다.

CI는 live session, final artifacts, stream validation, graph summary와 `/graph.json` endpoint를 테스트합니다.
