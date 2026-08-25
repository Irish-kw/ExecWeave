<!-- i18n-nav:start -->
<p align="center">
  <a href="phase-1-runtime-collection.md">English</a> |
  <a href="phase-1-runtime-collection.zh-TW.md">繁體中文</a> |
  <a href="phase-1-runtime-collection.zh-CN.md">简体中文</a> |
  <strong>日本語</strong> |
  <a href="phase-1-runtime-collection.ko.md">한국어</a>
</p>
<!-- i18n-nav:end -->

# Phase 1 — Runtime Collection

Phase 1 は、Phase 2 が execution graph に変換できるローカルの graph-ready runtime event stream を構築します。

## 状態

**Linux reference path と cross-platform portable fallback は実装済みです。**

- `strace` — Linux syscall-backed collector。短命な descendant process と process-attributed file/network evidence を取得します。
- `portable` — Linux/macOS/Windows 向け `psutil + watchdog` fallback。Process/network は polling、filesystem change は session-level observation として `causal: false` で記録します。

`auto` は Linux で `strace` が利用可能なら優先します。

```bash
execweave doctor
execweave run --backend auto -- claude
```

## インストール

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

Debian/Ubuntu:

```bash
sudo apt-get install strace
```

任意の command を記録できます。

```bash
execweave run -- claude
execweave run -- codex
execweave run -- gemini
execweave run -- opencode
execweave run -- python my_agent.py
```

Event は通常 `.execweave/runs/<session-id>.jsonl` に保存されます。Raw `strace` は parse 後に削除され、`--keep-native-trace` の場合のみ保持されます。

## Validation

```bash
execweave run --output run.jsonl -- python my_agent.py
execweave validate run.jsonl
execweave benchmark --backend auto --iterations 5
```

Validator は JSONL、単一 session、unique event ID、1 から始まる contiguous `sequence`、timestamp、entity/event fields、`session.started` / `session.finished` を検証します。

中断 run は：

```bash
execweave validate --allow-incomplete run.jsonl
```

既存の non-empty output への暗黙 append は拒否されます。

## Linux `strace` evidence

代表的な relation：

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

Syscall-backed edge は通常 `attribution: "syscall"`, `causal: true`, `backend: "strace"` を持ちます。

`OPENED_READ` / `OPENED_WRITE` は open syscall の access mode を示すだけで、実際の byte-level `read()` / `write()` を証明しません。

## Portable evidence

```text
session --LAUNCHED--> process
process --SPAWNED--> process
process --CONNECTED_TO--> network_endpoint
session --OBSERVED_FILE_CHANGE--> file
```

Filesystem change は：

```json
{
  "attribution": "session_observation",
  "causal": false
}
```

時間的な近接を process causality として表示しません。

## Ordering と identity

JSONL sink は monotonically increasing `sequence` を付与します。Portable process identity は PID + creation time、Linux syscall path は `process:<session-id>:<pid>` を使用します。PID 単体を global identity として扱いません。

`strace` parser は parent pre-pass を行い、同 timestamp の `clone()/fork()` と child trace による誤 attribution を防ぎます。

## Short-lived process / path / network

Portable polling は非常に短命な process を逃す場合があります。Linux reference backend は `strace -ff` で descendants を追跡し、CI でも短命 child の `SPAWNED` evidence を検証します。

Linux parser は per-process cwd と一般的な `*at` syscall を扱います。Network は IPv4/IPv6/Unix socket の `connect()` を記録し、成功は `CONNECTED_TO`、`EINPROGRESS` など failed/asynchronous attempt は `CONNECT_ATTEMPTED` として保持します。

Event が存在しないことは、coverage/permission が限定された backend で「何も起きなかった」証明にはなりません。

## Privacy

- data は local-first
- raw syscall trace は原則削除
- file content を収集しない
- raw `read()/write()` buffer を収集しない
- `execve` arguments は graph event に全文コピーしない

ただし wrapper に渡した command 自体は metadata なので、secret を command line に直接置かないでください。

## CI / benchmark

CI は Linux/macOS/Windows、Python 3.10/3.12 で validator、portable workflow、Linux `strace` integration と benchmark smoke を実行します。

```bash
execweave benchmark --backend portable --iterations 5
execweave benchmark --backend strace --iterations 5
```

結果は環境依存の measurement であり、公開 performance claim ではありません。

## Phase 1 外の項目

Windows ETW、macOS Endpoint Security、Linux eBPF、DNS/domain correlation、byte-level data flow、より高度な semantic/runtime correlation は別の layer として同じ event contract に接続します。

`strace` は correctness-oriented reference implementation として採用されています。eBPF は将来、同じ semantics を低 overhead / always-on collection で実装する方向です。
