<!-- i18n-nav:start -->
<p align="center">
  <a href="phase-1-runtime-collection.md">English</a> |
  <strong>繁體中文</strong> |
  <a href="phase-1-runtime-collection.zh-CN.md">简体中文</a> |
  <a href="phase-1-runtime-collection.ja.md">日本語</a> |
  <a href="phase-1-runtime-collection.ko.md">한국어</a> |
  <a href="phase-1-runtime-collection.fr.md">Français</a> |
  <a href="phase-1-runtime-collection.de.md">Deutsch</a> |
  <a href="phase-1-runtime-collection.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# Phase 1 — Runtime Collection

Phase 1 建立一條可直接轉成 Graph 的本機 runtime event stream，供 Phase 2 materialize 成 execution graph。

## 狀態

**Phase 1 的 Linux reference path 與 cross-platform portable fallback 已完成。**

ExecWeave 目前提供兩種 collector backend：

- `strace` — Linux syscall-backed collector，可抓短生命週期 descendant，並以 syscall evidence 對 process/file/network 行為做 attribution。
- `portable` — Linux、macOS、Windows 的 `psutil + watchdog` fallback。Process/network 以 polling 觀察；filesystem change 僅做 session correlation，明確標示為 non-causal。

`auto` 在 Linux 有 `strace` 時優先選它，否則使用 `portable`。

```bash
execweave doctor
execweave run --backend auto -- claude
```

## 安裝

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

Debian/Ubuntu 可安裝 Linux reference backend：

```bash
sudo apt-get install strace
```

之後可以直接包住任何 command：

```bash
execweave run -- claude
execweave run -- codex
execweave run -- agy
execweave run -- opencode
execweave run -- python my_agent.py
```

事件預設寫到：

```text
.execweave/runs/<session-id>.jsonl
```

Raw `strace` 預設解析後刪除；只有 debug 時才保留：

```bash
execweave run --keep-native-trace -- claude
```

## Phase 1 end-to-end 驗證

```bash
execweave doctor
execweave run --output run.jsonl -- python my_agent.py
execweave validate run.jsonl
execweave benchmark --backend auto --iterations 5
```

`execweave validate` 會檢查：

- JSONL record 合法；
- 一個檔案只能有一個 session ID；
- event ID 唯一；
- `sequence` 從 1 開始且連續；
- timestamp 合法；
- event/entity 必要欄位存在；
- completed run 恰好有一個 `session.started` 與一個 `session.finished`。

對合法但被中斷、沒有 `session.finished` 的 run：

```bash
execweave validate --allow-incomplete run.jsonl
```

ExecWeave 預設拒絕重用既有非空 output file，避免第二個 session 被悄悄 append 到 sequence 已重新從 1 開始的同一條 event stream。

## Backend capability model

### Linux `strace` backend

Linux reference backend 使用 `strace -ff` 跟隨 descendants，並產生 syscall-backed relationship：

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

相關事件會包含：

```json
{
  "attribution": "syscall",
  "causal": true,
  "backend": "strace"
}
```

`OPENED_READ` / `OPENED_WRITE` 只表示 open syscall 證明的 access mode，**不代表**後續一定真的發生 byte-level `read()` / `write()`。Byte-level data-flow tracking 應由更後面的 collector 負責。

### Portable backend

Portable backend 直接啟動 command，再用 `psutil/watchdog` 觀察：

```text
session --LAUNCHED--> process
process --SPAWNED--> process
process --CONNECTED_TO--> network_endpoint
session --OBSERVED_FILE_CHANGE--> file
```

Filesystem change 明確保持 session-level observation：

```json
{
  "attribution": "session_observation",
  "causal": false
}
```

因此 ExecWeave 不會把「同一時間附近發生」誤包裝成 process-level causality。

## Event ordering 與 identity

JSONL sink 會替每筆 event 加上 monotonically increasing `sequence`，timestamp 則獨立保留。

Portable process ID 使用 PID + process creation time，因為 OS 會重用 PID。

Linux syscall backend 的 process ID 限定於當次 ExecWeave session：

```text
process:<session-id>:<pid>
```

所以 ExecWeave 不會只根據 PID 做全域 process identity 推論。

`strace` parser 在 emit graph event 前會先做 parent pre-pass，避免 child trace record 與 parent `clone()/fork()` 在不同 trace file 有相同 timestamp 時，把 child 誤標為 session root。

## Short-lived process

Portable polling 可能漏掉完全落在 polling interval 之間的極短命 process。

Linux reference backend 透過 process syscall tracing + `strace -ff` 消除這個 Phase 1 缺口。CI 有 integration test 會啟動短命 child，並確認產生 `SPAWNED` edge。

## Filesystem path attribution

Linux parser 會追蹤每個 process 的 working directory，並處理常見 `*at` syscall。Relative path 會依可取得的最佳 syscall evidence 解成 path。

少見 dirfd pattern 仍可能不完美，因此 raw syscall name/path 會保留在 event attributes，讓 downstream consumer 可以 audit edge 如何形成。

## Network attribution

Linux backend 會記錄 `connect()` syscall evidence：

- IPv4
- IPv6
- Unix-domain socket

成功時：

```text
process --CONNECTED_TO--> endpoint
```

失敗或 asynchronous call（包含常見 non-blocking `EINPROGRESS`）則保留為：

```text
process --CONNECT_ATTEMPTED--> endpoint
```

Event 同時保存 syscall result 與 errno，因此不會把 async attempt 誤報成成功連線，也不會直接漏掉。

Portable backend 則在 OS/permission 允許時使用 per-process socket inspection。

缺少某個 event **不能**被解讀為「這個 backend 證明沒有發生該 network action」。

## Privacy

Runtime telemetry 可能包含敏感 path、executable name、command argument 與 endpoint。

Phase 1 預設：

- event data 全部留在本機；
- raw syscall trace 解析後刪除，除非指定 `--keep-native-trace`；
- 不 trace file content；
- 不蒐集 `read()/write()` byte buffer；
- `execve` argument 不複製到 graph event，只保留 argument count。

Session wrapper 仍會記錄使用者交給 ExecWeave 的 command，因此不要把 secret 直接放在 command line。

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

```bash
execweave benchmark --backend portable --iterations 5
execweave benchmark --backend strace --iterations 5
```

或：

```bash
python benchmarks/phase1_overhead.py
```

輸出 raw baseline/instrumented timings、median 與 overhead ratio。這些是特定環境的量測，不是正式 performance claim。

## CI contract

GitHub Actions 會在 Linux、macOS、Windows 與支援的 Python 版本上執行：

1. `execweave doctor`
2. portable end-to-end run
3. portable stream validation
4. Linux `strace` end-to-end run
5. native Linux stream validation
6. Phase 1 benchmark smoke test

因此 Phase 1 是以真實 CLI workflow 測試，不只是 isolated Python function。

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

## 明確不屬於 Phase 1

以下仍是後續工作，不會假裝已完成：

- Windows ETW process-attributed filesystem backend
- macOS Endpoint Security process-attributed backend
- Linux eBPF backend（降低 ptrace overhead）
- DNS-to-domain correlation
- byte-level read/write data-flow tracking
- agent/tool/MCP semantic telemetry
- graph materialization 與 interactive visualization

它們都可以繼續使用同一套 event model，而不需要改變 Phase 1 contract。

## 為什麼先做 `strace`，不是 eBPF？

Phase 1 需要一個 correctness-oriented、容易 audit 的 process/file/network attribution reference implementation。`strace` 易於檢查與測試，也能抓短命 descendant，而不需要先發明新的 causality semantics。

eBPF 是降低 overhead、支援 always-on collection 的自然下一步，但它應該實作相同的 ExecWeave graph event semantics，而不是另起一套。

## Contributing

特別有價值的 contribution 包含 Linux eBPF、Windows ETW、macOS Endpoint Security、path/entity resolution、overhead evaluation、privacy/redaction 與可重現 agent workload。

新增 collector backend 時，請維持「proven causal attribution」與「session-level observation」的區別。
