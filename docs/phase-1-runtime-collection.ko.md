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

Phase 1은 Phase 2가 execution graph로 materialize할 수 있는 로컬 graph-ready runtime event stream을 구축합니다.

## 상태

**Linux reference path와 cross-platform portable fallback이 구현되어 있습니다.**

- `strace` — Linux syscall-backed collector. 짧게 실행되는 descendant와 process-attributed filesystem/network evidence를 수집합니다.
- `portable` — Linux/macOS/Windows용 `psutil + watchdog` fallback. Process/network는 polling으로 관찰하고 filesystem change는 session-level observation으로 `causal: false`를 유지합니다.

`auto`는 Linux에서 `strace`가 있으면 우선 사용합니다.

```bash
execweave doctor
execweave run --backend auto -- claude
```

## 설치

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

Debian/Ubuntu:

```bash
sudo apt-get install strace
```

```bash
execweave run -- claude
execweave run -- codex
execweave run -- gemini
execweave run -- opencode
execweave run -- python my_agent.py
```

Event는 기본적으로 `.execweave/runs/<session-id>.jsonl`에 저장됩니다. Raw `strace`는 parse 후 삭제되며 `--keep-native-trace`를 요청했을 때만 유지됩니다.

## End-to-end validation

```bash
execweave run --output run.jsonl -- python my_agent.py
execweave validate run.jsonl
execweave benchmark --backend auto --iterations 5
```

Validator는 JSONL 구조, 단일 session ID, unique event ID, 1부터 시작하는 contiguous `sequence`, timestamp, 필수 entity/event fields, completed run의 `session.started` / `session.finished`를 확인합니다.

중단된 run:

```bash
execweave validate --allow-incomplete run.jsonl
```

기존 non-empty output에 새 session을 몰래 append하는 것도 기본적으로 거부합니다.

## Linux `strace` evidence

대표 relation:

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
```

Syscall-backed event는 보통 `attribution: "syscall"`, `causal: true`, `backend: "strace"`를 가집니다.

`OPENED_READ` / `OPENED_WRITE`는 open syscall의 access mode만 증명하며 실제 byte-level `read()` / `write()`까지 증명하지 않습니다.

## Portable evidence

```text
session --LAUNCHED--> process
process --SPAWNED--> process
process --CONNECTED_TO--> network_endpoint
session --OBSERVED_FILE_CHANGE--> file
```

Filesystem change는 다음처럼 유지됩니다.

```json
{
  "attribution": "session_observation",
  "causal": false
}
```

즉 시간적 근접성을 process causality로 포장하지 않습니다.

## Ordering / identity

JSONL sink는 monotonically increasing `sequence`를 부여합니다. Portable process identity는 PID + creation time, Linux syscall backend는 `process:<session-id>:<pid>`를 사용합니다. PID만으로 global identity를 추론하지 않습니다.

`strace` parser는 parent pre-pass를 수행해 동일 timestamp의 `clone()/fork()`와 child trace가 잘못된 root attribution을 만들지 않도록 합니다.

## Short-lived process / path / network

Portable polling은 매우 짧은 process를 놓칠 수 있습니다. Linux reference backend는 `strace -ff`로 descendant를 추적하며 CI가 short-lived child의 `SPAWNED` evidence를 검증합니다.

Linux parser는 per-process cwd와 일반적인 `*at` syscall을 처리합니다. Network `connect()`는 IPv4/IPv6/Unix socket을 수집하며 성공은 `CONNECTED_TO`, `EINPROGRESS` 같은 failed/asynchronous attempt는 `CONNECT_ATTEMPTED`로 보존합니다.

Coverage나 permission이 제한된 backend에서 event가 없다는 사실은 “그 행동이 없었다”는 증명이 아닙니다.

## Privacy

- event data는 local-first
- raw syscall trace는 기본 삭제
- file content 미수집
- raw `read()/write()` byte buffer 미수집
- `execve` arguments를 graph event에 전체 복사하지 않음

다만 wrapper에 전달한 command 자체는 metadata이므로 secret을 command line에 직접 넣지 않는 것이 좋습니다.

## CI / benchmark

CI는 Linux/macOS/Windows, Python 3.10/3.12에서 portable workflow, validator, Linux `strace` integration, benchmark smoke를 실행합니다.

```bash
execweave benchmark --backend portable --iterations 5
execweave benchmark --backend strace --iterations 5
```

수치는 환경별 measurement이며 공식 performance claim이 아닙니다.

## Phase 1 범위 밖

Windows ETW, macOS Endpoint Security, Linux eBPF, DNS/domain correlation, byte-level data flow 등은 같은 event contract에 연결되는 후속 layer입니다.

`strace`는 correctness-oriented reference implementation이며 eBPF는 향후 동일 semantics를 더 낮은 overhead로 구현하는 방향입니다.
