<!-- i18n-nav:start -->
<p align="center">
  <a href="phase-1-runtime-collection.md">English</a> |
  <a href="phase-1-runtime-collection.zh-TW.md">繁體中文</a> |
  <a href="phase-1-runtime-collection.zh-CN.md">简体中文</a> |
  <strong>日本語</strong> |
  <a href="phase-1-runtime-collection.ko.md">한국어</a> |
  <a href="phase-1-runtime-collection.fr.md">Français</a> |
  <a href="phase-1-runtime-collection.de.md">Deutsch</a> |
  <a href="phase-1-runtime-collection.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# Phase 1 — Runtime Collection

Phase 1 は、Phase 2 が execution graph に変換できる graph-ready なローカル runtime event stream を確立します。

## Status

**Phase 1 は Linux の reference path と portable fallback について完了しています。**

ExecWeave は現在 2 つの collection backend を提供します。

- `strace` — Linux syscall-backed collection。短命な descendant と、syscall evidence に基づく process-attributed filesystem/network action を取得します。
- `portable` — Linux、macOS、Windows 向けの psutil + watchdog fallback。Process/network event は polling され、filesystem change は session-correlated かつ明示的に non-causal として記録されます。

`auto` は Linux で `strace` がインストールされている場合はそれを優先し、それ以外では `portable` を選択します。

```bash
execweave doctor
execweave run --backend auto -- claude
```

## Install

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

Debian/Ubuntu では Linux reference backend を次でインストールします。

```bash
sudo apt-get install strace
```

その後：

```bash
execweave run -- claude
execweave run -- codex
execweave run -- gemini
execweave run -- opencode
execweave run -- python my_agent.py
```

Event はローカルの次の場所に書き込まれます。

```text
.execweave/runs/<session-id>.jsonl
```

Raw `strace` file はデフォルトで parse 後に削除されます。Debug 用に保持する場合のみ：

```bash
execweave run --keep-native-trace -- claude
```

## End-to-end Phase 1 verification

Phase 1 の run は Phase 2 graph を構築しなくても確認できます。

```bash
execweave doctor
execweave run --output run.jsonl -- python my_agent.py
execweave validate run.jsonl
execweave benchmark --backend auto --iterations 5
```

`execweave validate` は event-stream contract を検証します。確認内容には次が含まれます。

- 有効な JSONL record
- file ごとに 1 つの session ID
- 一意な event ID
- 1 から始まる連続した sequence number
- 有効な timestamp
- 必須 event/entity field
- completed run に正確に 1 つの `session.started` と `session.finished`

正当に `session.finished` を持たない中断 run では：

```bash
execweave validate --allow-incomplete run.jsonl
```

ExecWeave は既存の non-empty output file の再利用もデフォルトで拒否します。これにより、2 回目の run が sequence counter を再開した別 session を同じ event stream に黙って append することを防ぎます。

## Backend capability model

### Linux `strace` backend

Native Phase 1 reference backend は `strace -ff` で descendant を追跡し、syscall-backed edge を記録します。

次のような relationship を生成できます。

```text
session --LAUNCHED--> process
process --SPAWNED--> process
process --EXECUTED--> executable
process --OPENED_READ--> file
process --OPENED_WRITE--> file
process --DELETED--> file
process --RENAMED_TO--> file
process --CHANGED_CWD_TO--> directory
process --CONNECTED_TO--> network_endpoint
process --CONNECT_ATTEMPTED--> network_endpoint
process --EXITED--> ...
```

これらの event には次が含まれます。

```json
{
  "attribution": "syscall",
  "causal": true,
  "backend": "strace"
}
```

`OPENED_READ` と `OPENED_WRITE` は open syscall によって証明された access mode を表します。後続の byte-level `read()` / `write()` が実際に発生したとは主張しません。Byte-level data-flow tracking は後続 collector の責務です。

### Portable backend

Portable backend は command を直接起動し、psutil/watchdog を使用します。

次を生成できます。

```text
session --LAUNCHED--> process
process --SPAWNED--> process
process --CONNECTED_TO--> network_endpoint
session --OBSERVED_FILE_CHANGE--> file
```

Filesystem change は明示的な session observation として保持されます。

```json
{
  "attribution": "session_observation",
  "causal": false
}
```

これにより temporal correlation を causal attribution として提示することを防ぎます。

## Event ordering and identity

JSONL sink は run 内のすべての event に単調増加する `sequence` number を付与します。Timestamp は別に保持されます。

Portable process ID は OS が PID を再利用するため PID + process creation time を使用します。

Linux syscall backend は process ID を ExecWeave session にスコープします。

```text
process:<session-id>:<pid>
```

したがって PID だけから process identity を global に推測することはありません。

`strace` parser は graph event を emit する前に process-parent pre-pass も行います。これにより別々の trace file で child process record と親の `clone()`/`fork()` record が同じ timestamp を持つ場合でも、child を session root と誤認しません。

## Short-lived processes

Portable backend は polling interval の間に開始・終了する process を見逃す可能性があります。

Linux reference backend は process syscall を trace し `strace -ff` で descendant を追跡することで、この Phase 1 gap を解消します。CI には短命な child を起動し `SPAWNED` edge が emit されることを確認する integration test が含まれます。

## Filesystem path attribution

Linux parser は process ごとの working directory を追跡し、一般的な `*at` syscall を処理します。Relative path は利用可能な最良の syscall evidence に対して resolve されます。

一般的でない dirfd pattern では path attribution が不完全な場合があります。Raw syscall name と path は event attribute として保持されるため、downstream consumer は edge がどのように生成されたか監査できます。

## Network attribution

Linux backend は次に対する `connect()` syscall evidence を記録します。

- IPv4
- IPv6
- Unix-domain socket

成功した call は次を生成します。

```text
process --CONNECTED_TO--> endpoint
```

一般的な non-blocking `EINPROGRESS` を含む failed/asynchronous call は次として保持されます。

```text
process --CONNECT_ATTEMPTED--> endpoint
```

Event は syscall result と errno を保持します。したがって ExecWeave は asynchronous connection attempt を confirmed connection と誤報したり、network behavior がなかったと扱ったりしません。

Portable backend は OS が現在の user に公開する場合、per-process socket inspection を使用します。

Permission や coverage が不足する backend で event が存在しないことを、「network action がなかった」証拠として解釈してはいけません。

## Privacy

Runtime telemetry には sensitive path、executable name、command argument、endpoint が含まれる可能性があります。

Phase 1 のデフォルトは次の通りです。

- すべての event data はローカルに留まる
- raw syscall trace file は `--keep-native-trace` を指定しない限り parse 後に削除
- file content は trace しない
- `read()`/`write()` の byte buffer は収集しない
- `execve` argument は argument count を除いて graph event にコピーしない

Session wrapper は ExecWeave に渡した command 自体を記録するため、secret を command line に直接置かないでください。

## Diagnostics

```bash
execweave doctor
```

例：

```json
{
  "auto_selected": "strace",
  "platform": "linux",
  "portable": true,
  "strace": true
}
```

## Overhead benchmark harness

Phase 1 には繰り返し実行可能な smoke benchmark があります。

```bash
execweave benchmark --backend portable --iterations 5
execweave benchmark --backend strace --iterations 5
```

または：

```bash
python benchmarks/phase1_overhead.py
```

Raw baseline/instrumented timing、median、overhead ratio を報告します。これらは環境依存の measurement であり、公開された performance claim ではありません。

## CI contract

GitHub Actions matrix は Linux、macOS、Windows とサポート対象 Python version で動作します。

Unit test と lint に加え、CI は現在次を実行します。

1. `execweave doctor`
2. portable end-to-end run
3. portable stream に対する `execweave validate`
4. Linux `strace` end-to-end run
5. native Linux stream の validation
6. Phase 1 benchmark smoke test

つまり Phase 1 は isolated function だけでなく実際の CLI workflow として検証されています。

## Acceptance criteria

- [x] Explicit ExecWeave session wrapper
- [x] Graph-ready event schema
- [x] Monotonic event sequence numbers
- [x] Root process capture
- [x] Parent/child process capture
- [x] Portable filesystem observation
- [x] Portable per-process network observation
- [x] Linux reliable short-lived process capture
- [x] Linux process-attributed filesystem syscall telemetry
- [x] Linux process-attributed network syscall telemetry
- [x] Preserve asynchronous/failed network connection attempts
- [x] Stable parent attribution across equal-timestamp trace records
- [x] Backend auto-selection and capability diagnostics
- [x] Raw native trace cleanup by default
- [x] Cross-platform portable fallback
- [x] Event-stream integrity validator
- [x] Protection against accidental multi-session append
- [x] Unit tests for parser, validator, and backend selection
- [x] Linux native integration test in CI
- [x] End-to-end CLI smoke validation in CI
- [x] Overhead benchmark harness

## Explicitly out of Phase 1

次は未完了を装うのではなく、明示的に future work としています。

- Windows ETW process-attributed filesystem backend
- macOS Endpoint Security process-attributed backend
- Linux eBPF backend to reduce ptrace overhead
- DNS-to-domain correlation
- byte-level read/write data-flow tracking
- agent/tool/MCP semantic telemetry
- graph materialization and interactive visualization

これらは Phase 1 contract を変更せず同じ event model に接続できます。

## Why `strace` before eBPF?

Phase 1 では process/file/network attribution と event semantics の correctness-oriented reference implementation が必要です。`strace` は inspect しやすく test しやすい上、causality を捏造せず短命 descendant を取得できます。

eBPF backend は overhead を下げ always-on collection に向ける自然な次の最適化ですが、暗黙に別 semantics を定義するのではなく同じ ExecWeave graph event semantics を実装すべきです。

## Contributing

有用な次の contribution には Linux eBPF、Windows ETW、macOS Endpoint Security、path/entity resolution、overhead evaluation、privacy/redaction、reproducible agent workload が含まれます。

新しい collector backend では、proven causal attribution と session-level observation の区別を維持してください。
