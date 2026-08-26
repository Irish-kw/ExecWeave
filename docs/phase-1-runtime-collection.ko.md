<!-- i18n-nav:start -->
<p align="center">
  <a href="phase-1-runtime-collection.md">English</a> |
  <a href="phase-1-runtime-collection.zh-TW.md">繁體中文</a> |
  <a href="phase-1-runtime-collection.zh-CN.md">简体中文</a> |
  <a href="phase-1-runtime-collection.ja.md">日本語</a> |
  <strong>한국어</strong> |
  <a href="phase-1-runtime-collection.fr.md">Français</a> |
  <a href="phase-1-runtime-collection.de.md">Deutsch</a> |
  <a href="phase-1-runtime-collection.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# Phase 1 — Runtime Collection

Phase 1은 Phase 2가 execution graph로 변환할 수 있는 graph-ready 로컬 runtime event stream을 구축합니다.

## Status

**Phase 1은 Linux reference path와 portable fallback에 대해 완료되었습니다.**

ExecWeave는 현재 두 가지 collection backend를 제공합니다.

- `strace` — Linux syscall-backed collection. 짧게 실행되는 descendant와 syscall evidence에 기반한 process-attributed filesystem/network action을 수집합니다.
- `portable` — Linux, macOS, Windows용 psutil + watchdog fallback. Process/network event는 polling되고 filesystem change는 session-correlated이며 명시적으로 non-causal로 기록됩니다.

`auto`는 Linux에서 `strace`가 설치되어 있으면 이를 우선하고, 그렇지 않으면 `portable`을 선택합니다.

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

Debian/Ubuntu에서는 Linux reference backend를 다음과 같이 설치합니다.

```bash
sudo apt-get install strace
```

그다음:

```bash
execweave run -- claude
execweave run -- codex
execweave run -- gemini
execweave run -- opencode
execweave run -- python my_agent.py
```

Event는 로컬의 다음 위치에 기록됩니다.

```text
.execweave/runs/<session-id>.jsonl
```

Raw `strace` file은 기본적으로 parse 후 삭제됩니다. Debugging을 위해 유지하려는 경우에만:

```bash
execweave run --keep-native-trace -- claude
```

## End-to-end Phase 1 verification

Phase 2 graph를 아직 만들지 않아도 Phase 1 run을 검증할 수 있습니다.

```bash
execweave doctor
execweave run --output run.jsonl -- python my_agent.py
execweave validate run.jsonl
execweave benchmark --backend auto --iterations 5
```

`execweave validate`는 event-stream contract를 검증하며 다음을 포함합니다.

- 유효한 JSONL record
- file당 하나의 session ID
- 고유한 event ID
- 1부터 시작하는 연속 sequence number
- 유효한 timestamp
- 필수 event/entity field
- completed run에서 정확히 하나의 `session.started`와 하나의 `session.finished`

정상적으로 `session.finished`가 없는 중단 run의 경우:

```bash
execweave validate --allow-incomplete run.jsonl
```

ExecWeave는 기존 non-empty output file의 재사용도 기본적으로 거부합니다. 따라서 두 번째 run이 sequence counter를 다시 시작한 새 session을 동일 event stream에 조용히 append하지 못합니다.

## Backend capability model

### Linux `strace` backend

Native Phase 1 reference backend는 `strace -ff`로 descendant를 추적하고 syscall-backed edge를 기록합니다.

다음과 같은 relationship을 생성할 수 있습니다.

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

이 event들은 다음을 포함합니다.

```json
{
  "attribution": "syscall",
  "causal": true,
  "backend": "strace"
}
```

`OPENED_READ`와 `OPENED_WRITE`는 open syscall이 증명한 access mode를 나타냅니다. 이후 실제 byte-level `read()` 또는 `write()`가 발생했다고 주장하지 않습니다. Byte-level data-flow tracking은 이후 collector의 책임입니다.

### Portable backend

Portable backend는 command를 직접 실행하고 psutil/watchdog를 사용합니다.

다음을 생성할 수 있습니다.

```text
session --LAUNCHED--> process
process --SPAWNED--> process
process --CONNECTED_TO--> network_endpoint
session --OBSERVED_FILE_CHANGE--> file
```

Filesystem change는 명시적인 session observation으로 유지됩니다.

```json
{
  "attribution": "session_observation",
  "causal": false
}
```

이를 통해 temporal correlation을 causal attribution으로 표현하지 않습니다.

## Event ordering and identity

JSONL sink는 run의 모든 event에 단조 증가하는 `sequence` number를 부여합니다. Timestamp는 별도로 유지됩니다.

OS가 PID를 재사용하므로 portable process ID는 PID + process creation time을 사용합니다.

Linux syscall backend는 process ID를 ExecWeave session 범위로 제한합니다.

```text
process:<session-id>:<pid>
```

따라서 PID만으로 process identity를 global하게 추론하지 않습니다.

`strace` parser는 graph event를 emit하기 전에 process-parent pre-pass도 수행합니다. 별도 trace file에서 child process record와 부모 `clone()`/`fork()` record가 같은 timestamp를 가지더라도 child를 session root로 잘못 표시하는 것을 방지합니다.

## Short-lived processes

Portable backend는 polling interval 사이에서 시작되고 종료되는 process를 놓칠 수 있습니다.

Linux reference backend는 process syscall을 trace하고 `strace -ff`로 descendant를 추적하여 이 Phase 1 gap을 제거합니다. CI에는 짧게 실행되는 child를 시작하고 `SPAWNED` edge가 emit되는지 확인하는 integration test가 포함됩니다.

## Filesystem path attribution

Linux parser는 process별 working directory를 추적하고 일반적인 `*at` syscall을 처리합니다. Relative path는 사용할 수 있는 최선의 syscall evidence에 대해 resolve됩니다.

드문 dirfd pattern에서는 path attribution이 불완전할 수 있습니다. Raw syscall name과 path는 event attribute로 유지되므로 downstream consumer가 edge가 어떻게 만들어졌는지 감사할 수 있습니다.

## Network attribution

Linux backend는 다음에 대한 `connect()` syscall evidence를 기록합니다.

- IPv4
- IPv6
- Unix-domain socket

성공한 call은 다음을 생성합니다.

```text
process --CONNECTED_TO--> endpoint
```

일반적인 non-blocking `EINPROGRESS`를 포함한 failed/asynchronous call은 다음으로 보존됩니다.

```text
process --CONNECT_ATTEMPTED--> endpoint
```

Event는 syscall result와 errno를 유지합니다. 따라서 ExecWeave는 asynchronous connection attempt를 confirmed connection으로 잘못 보고하거나 network behavior가 전혀 없었다고 처리하지 않습니다.

Portable backend는 OS가 현재 user에게 노출하는 경우 per-process socket inspection을 사용합니다.

Permission이나 coverage가 제한된 backend에서 event가 없다는 사실을 network action이 없었다는 증거로 해석해서는 안 됩니다.

## Privacy

Runtime telemetry에는 sensitive path, executable name, command argument, endpoint가 포함될 수 있습니다.

Phase 1의 기본 동작은 다음과 같습니다.

- 모든 event data는 로컬에 유지
- raw syscall trace file은 `--keep-native-trace`를 요청하지 않으면 parse 후 삭제
- file content는 trace하지 않음
- `read()`/`write()` byte buffer는 수집하지 않음
- `execve` argument는 argument count를 제외하고 graph event에 복사하지 않음

Session wrapper는 ExecWeave에 전달된 command 자체는 기록하므로 secret을 command line에 직접 넣지 않는 것이 좋습니다.

## Diagnostics

```bash
execweave doctor
```

예:

```json
{
  "auto_selected": "strace",
  "platform": "linux",
  "portable": true,
  "strace": true
}
```

## Overhead benchmark harness

Phase 1에는 반복 가능한 smoke benchmark가 포함됩니다.

```bash
execweave benchmark --backend portable --iterations 5
execweave benchmark --backend strace --iterations 5
```

또는:

```bash
python benchmarks/phase1_overhead.py
```

Raw baseline/instrumented timing, median, overhead ratio를 보고합니다. 이는 환경별 measurement이며 공개된 performance claim이 아닙니다.

## CI contract

GitHub Actions matrix는 Linux, macOS, Windows와 지원되는 Python version에서 실행됩니다.

Unit test와 lint 외에도 CI는 현재 다음을 수행합니다.

1. `execweave doctor`
2. portable end-to-end run
3. portable stream에 대한 `execweave validate`
4. Linux `strace` end-to-end run
5. native Linux stream validation
6. Phase 1 benchmark smoke test

따라서 Phase 1은 isolated function뿐 아니라 실제 CLI workflow로 검증됩니다.

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

다음 항목은 완료된 것처럼 표시하지 않고 명시적으로 future work로 남겨 둡니다.

- Windows ETW process-attributed filesystem backend
- macOS Endpoint Security process-attributed backend
- Linux eBPF backend to reduce ptrace overhead
- DNS-to-domain correlation
- byte-level read/write data-flow tracking
- agent/tool/MCP semantic telemetry
- graph materialization and interactive visualization

이 기능들은 Phase 1 contract를 변경하지 않고 동일 event model에 연결할 수 있습니다.

## Why `strace` before eBPF?

Phase 1에는 process/file/network attribution과 event semantics에 대한 correctness-oriented reference implementation이 필요합니다. `strace`는 inspect하기 쉽고 test하기 쉬우며 causality를 만들어내지 않고 짧게 실행되는 descendant를 포착합니다.

eBPF backend는 overhead를 낮추고 always-on collection으로 가기 위한 자연스러운 다음 최적화지만, 별도의 semantics를 암묵적으로 정의하지 않고 동일한 ExecWeave graph event semantics를 구현해야 합니다.

## Contributing

유용한 다음 contribution에는 Linux eBPF, Windows ETW, macOS Endpoint Security, path/entity resolution, overhead evaluation, privacy/redaction, reproducible agent workload가 포함됩니다.

새 collector backend에서는 proven causal attribution과 session-level observation의 구분을 유지하세요.
