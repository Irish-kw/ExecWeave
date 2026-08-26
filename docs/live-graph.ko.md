<!-- i18n-nav:start -->
<p align="center">
  <a href="live-graph.md">English</a> |
  <a href="live-graph.zh-TW.md">繁體中文</a> |
  <a href="live-graph.zh-CN.md">简体中文</a> |
  <a href="live-graph.ja.md">日本語</a> |
  <strong>한국어</strong> |
  <a href="live-graph.fr.md">Français</a> |
  <a href="live-graph.de.md">Deutsch</a> |
  <a href="live-graph.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# Live Graph

ExecWeave는 AI Agent 또는 임의의 command가 아직 실행 중일 때 local execution graph를 stream할 수 있습니다.

```bash
execweave live --open -- claude
```

## Current contract

Live MVP는 의도적으로 `portable` collector를 사용합니다.

Linux `strace` backend는 현재 command 종료 후 trace file을 parse합니다. 더 강한 syscall-backed attribution을 제공하지만 현재 구현에서는 live event source가 아닙니다. ExecWeave는 post-processed evidence를 live telemetry라고 표시하지 않습니다.

더 강한 Linux post-run attribution을 사용하려면:

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

Run이 active한 동안 browser는 `/graph.json`을 polling합니다. 각 snapshot은 final artifact에서 사용하는 것과 동일한 Phase 1 event-stream contract와 Phase 2 graph contract로 만들어집니다.

Command가 종료되면 ExecWeave는:

1. completed event stream을 validate하고;
2. `graph.json`을 쓰고;
3. standalone `viewer.html`을 쓰고;
4. live graph를 finished로 mark하고;
5. local server를 종료하기 전에 final viewer를 잠시 serve합니다.

## Network exposure

Live server는 다음 address에만 bind합니다.

```text
127.0.0.1
```

`0.0.0.0`으로 공개되지 않으며 LAN의 다른 host에서 접근하는 용도가 아닙니다.

Port를 명시적으로 선택하려면:

```bash
execweave live --port 8765 --open -- claude
```

기본 port `0`은 OS가 사용 가능한 local port를 선택하게 합니다.

## Artifacts

기본 run directory는 다음과 같습니다.

```text
.execweave/runs/<session-id>/
├── events.jsonl
├── graph.json
└── viewer.html
```

다른 directory를 선택하려면:

```bash
execweave live --output-dir my-live-run --open -- claude
```

기존 non-empty artifact는 overwrite하지 않고 거부합니다.

## Incomplete snapshots

Live run 중에는 session이 아직 끝나지 않았으므로 `events.jsonl`이 의도적으로 incomplete입니다.

따라서 live graph snapshot은 graph builder의 `allow_incomplete` mode를 사용합니다. 하지만 structural validation은 그대로 적용됩니다. Malformed JSON, inconsistent session, invalid entity, broken sequence ordering은 valid graph evidence로 취급하지 않습니다.

Final graph는 정상 complete-session validation이 성공한 뒤에만 만들어집니다.

## Portable-backend limitations

현재 live MVP는 portable collector의 guarantee를 그대로 가집니다.

- process discovery는 polling-based;
- 매우 짧게 실행되는 process는 놓칠 수 있음;
- filesystem change는 process-attributed가 아니라 session-correlated;
- per-process network inspection은 OS visibility와 permission에 의존.

이 limitation은 event attribution metadata에 계속 표시됩니다. Live Viewer는 non-causal observation을 causal edge로 upgrade하지 않습니다.

## Future native live backends

예정된 collector는 다음과 같습니다.

- Linux eBPF;
- Windows ETW;
- macOS Endpoint Security.

목표는 동일한 ExecWeave event semantics를 유지하면서 completeness, process attribution, runtime overhead를 개선하는 것입니다.

## CI coverage

Repository CI configuration에는 다음을 수행하는 `live` smoke path가 포함됩니다.

- local live session 시작;
- 짧은 command 실행;
- final artifact 작성;
- `events.jsonl` validate;
- resulting graph summarize.

Unit/integration test는 localhost `/graph.json` endpoint도 직접 exercise합니다.
