<!-- i18n-nav:start -->
<p align="center">
  <a href="phase-1-runtime-collection.md">English</a> |
  <a href="phase-1-runtime-collection.zh-TW.md">繁體中文</a> |
  <strong>简体中文</strong> |
  <a href="phase-1-runtime-collection.ja.md">日本語</a> |
  <a href="phase-1-runtime-collection.ko.md">한국어</a> |
  <a href="phase-1-runtime-collection.fr.md">Français</a> |
  <a href="phase-1-runtime-collection.de.md">Deutsch</a> |
  <a href="phase-1-runtime-collection.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# Phase 1 — Runtime Collection

Phase 1 建立一条可直接转成 Graph 的本机 runtime event stream，供 Phase 2 materialize 成 execution graph。

## 状态

**Phase 1 的 Linux reference path 与 cross-platform portable fallback 已完成。**

ExecWeave 目前提供两种 collector backend：

- `strace` — Linux syscall-backed collector，可抓短生命周期 descendant，并以 syscall evidence 对 process/file/network 行为做 attribution。
- `portable` — Linux、macOS、Windows 的 `psutil + watchdog` fallback。Process/network 以 polling 观察；filesystem change 仅做 session correlation，明确标示为 non-causal。

`auto` 在 Linux 有 `strace` 时优先选它，否则使用 `portable`。

```bash
execweave doctor
execweave run --backend auto -- claude
```

## 安装

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

Debian/Ubuntu 可安装 Linux reference backend：

```bash
sudo apt-get install strace
```

之后可以直接包住任何 command：

```bash
execweave run -- claude
execweave run -- codex
execweave run -- agy
execweave run -- opencode
execweave run -- python my_agent.py
```

事件预设写到：

```text
.execweave/runs/<session-id>.jsonl
```

Raw `strace` 预设解析后删除；只有 debug 时才保留：

```bash
execweave run --keep-native-trace -- claude
```

## Phase 1 end-to-end 验证

```bash
execweave doctor
execweave run --output run.jsonl -- python my_agent.py
execweave validate run.jsonl
execweave benchmark --backend auto --iterations 5
```

`execweave validate` 会检查：

- JSONL record 合法；
- 一个档案只能有一个 session ID；
- event ID 唯一；
- `sequence` 从 1 开始且连续；
- timestamp 合法；
- event/entity 必要栏位存在；
- completed run 恰好有一个 `session.started` 与一个 `session.finished`。

对合法但被中断、没有 `session.finished` 的 run：

```bash
execweave validate --allow-incomplete run.jsonl
```

ExecWeave 预设拒绝重用既有非空 output file，避免第二个 session 被悄悄 append 到 sequence 已重新从 1 开始的同一条 event stream。

## Backend capability model

### Linux `strace` backend

Linux reference backend 使用 `strace -ff` 跟随 descendants，并产生 syscall-backed relationship：

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

相关事件会包含：

```json
{
  "attribution": "syscall",
  "causal": true,
  "backend": "strace"
}
```

`OPENED_READ` / `OPENED_WRITE` 只表示 open syscall 证明的 access mode，**不代表**后续一定真的发生 byte-level `read()` / `write()`。Byte-level data-flow tracking 应由更后面的 collector 负责。

### Portable backend

Portable backend 直接启动 command，再用 `psutil/watchdog` 观察：

```text
session --LAUNCHED--> process
process --SPAWNED--> process
process --CONNECTED_TO--> network_endpoint
session --OBSERVED_FILE_CHANGE--> file
```

Filesystem change 明确保持 session-level observation：

```json
{
  "attribution": "session_observation",
  "causal": false
}
```

因此 ExecWeave 不会把「同一时间附近发生」误包装成 process-level causality。

## Event ordering 与 identity

JSONL sink 会替每笔 event 加上 monotonically increasing `sequence`，timestamp 则独立保留。

Portable process ID 使用 PID + process creation time，因为 OS 会重用 PID。

Linux syscall backend 的 process ID 限定于当次 ExecWeave session：

```text
process:<session-id>:<pid>
```

所以 ExecWeave 不会只根据 PID 做全域 process identity 推论。

`strace` parser 在 emit graph event 前会先做 parent pre-pass，避免 child trace record 与 parent `clone()/fork()` 在不同 trace file 有相同 timestamp 时，把 child 误标为 session root。

## Short-lived process

Portable polling 可能漏掉完全落在 polling interval 之间的极短命 process。

Linux reference backend 透过 process syscall tracing + `strace -ff` 消除这个 Phase 1 缺口。CI 有 integration test 会启动短命 child，并确认产生 `SPAWNED` edge。

## Filesystem path attribution

Linux parser 会追踪每个 process 的 working directory，并处理常见 `*at` syscall。Relative path 会依可取得的最佳 syscall evidence 解成 path。

少见 dirfd pattern 仍可能不完美，因此 raw syscall name/path 会保留在 event attributes，让 downstream consumer 可以 audit edge 如何形成。

## Network attribution

Linux backend 会记录 `connect()` syscall evidence：

- IPv4
- IPv6
- Unix-domain socket

成功时：

```text
process --CONNECTED_TO--> endpoint
```

失败或 asynchronous call（包含常见 non-blocking `EINPROGRESS`）则保留为：

```text
process --CONNECT_ATTEMPTED--> endpoint
```

Event 同时保存 syscall result 与 errno，因此不会把 async attempt 误报成成功连线，也不会直接漏掉。

Portable backend 则在 OS/permission 允许时使用 per-process socket inspection。

缺少某个 event **不能**被解读为「这个 backend 证明没有发生该 network action」。

## Privacy

Runtime telemetry 可能包含敏感 path、executable name、command argument 与 endpoint。

Phase 1 预设：

- event data 全部留在本机；
- raw syscall trace 解析后删除，除非指定 `--keep-native-trace`；
- 不 trace file content；
- 不搜集 `read()/write()` byte buffer；
- `execve` argument 不复制到 graph event，只保留 argument count。

Session wrapper 仍会记录使用者交给 ExecWeave 的 command，因此不要把 secret 直接放在 command line。

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

输出 raw baseline/instrumented timings、median 与 overhead ratio。这些是特定环境的量测，不是正式 performance claim。

## CI contract

GitHub Actions 会在 Linux、macOS、Windows 与支援的 Python 版本上执行：

1. `execweave doctor`
2. portable end-to-end run
3. portable stream validation
4. Linux `strace` end-to-end run
5. native Linux stream validation
6. Phase 1 benchmark smoke test

因此 Phase 1 是以真实 CLI workflow 测试，不只是 isolated Python function。

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

## 明确不属于 Phase 1

以下仍是后续工作，不会假装已完成：

- Windows ETW process-attributed filesystem backend
- macOS Endpoint Security process-attributed backend
- Linux eBPF backend（降低 ptrace overhead）
- DNS-to-domain correlation
- byte-level read/write data-flow tracking
- agent/tool/MCP semantic telemetry
- graph materialization 与 interactive visualization

它们都可以继续使用同一套 event model，而不需要改变 Phase 1 contract。

## 为什么先做 `strace`，不是 eBPF？

Phase 1 需要一个 correctness-oriented、容易 audit 的 process/file/network attribution reference implementation。`strace` 易于检查与测试，也能抓短命 descendant，而不需要先发明新的 causality semantics。

eBPF 是降低 overhead、支援 always-on collection 的自然下一步，但它应该实作相同的 ExecWeave graph event semantics，而不是另起一套。

## Contributing

特别有价值的 contribution 包含 Linux eBPF、Windows ETW、macOS Endpoint Security、path/entity resolution、overhead evaluation、privacy/redaction 与可重现 agent workload。

新增 collector backend 时，请维持「proven causal attribution」与「session-level observation」的区别。
