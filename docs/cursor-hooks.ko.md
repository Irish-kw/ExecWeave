# Cursor Hooks

<p align="center">
  <a href="cursor-hooks.md">English</a> |
  <a href="cursor-hooks.zh-TW.md">繁體中文</a> |
  <a href="cursor-hooks.zh-CN.md">简体中文</a> |
  <a href="cursor-hooks.ja.md">日本語</a> |
  <strong>한국어</strong>
</p>

ExecWeave는 Cursor의 네이티브 Hook을 사용해 Agent / Tool / Command의 논리적 semantic evidence를 실행 그래프에 추가합니다. Provider metadata를 OS 수준의 인과 증거로 취급하지 않습니다.

## 빠른 시작

Hook 설정을 생성해 Cursor hook settings에 추가합니다.

```bash
execweave-cursor-hook --print-config
```

그다음 Cursor 실행을 기록합니다.

```bash
execweave-cursor-record --open -- cursor
```

run-bound recorder는 runtime, semantic, correlated artifacts를 서로 분리해 저장합니다.

## 이벤트

현재 baseline은 다음을 사용합니다.

- `sessionStart`
- `preToolUse`
- `postToolUse`
- `postToolUseFailure`

Cursor는 안정적인 `tool_use_id`를 제공하므로 `preToolUse`와 대응하는 post hook이 동일한 logical `tool_call` identity를 정확히 공유할 수 있습니다.

대표적인 semantic edge:

```text
agent --USED_MODEL--> model
agent --REQUESTED_TOOL_CALL--> tool_call
tool_call --USES_TOOL--> tool
tool_call --DECLARED_COMMAND--> command
tool_call --DECLARED_TARGET--> file
tool_call --TOOL_CALL_RETURNED--> tool
```

`postToolUseFailure`는 `TOOL_CALL_FAILED`로 별도 표현합니다.

## Tool → Process correlation

Cursor Hook은 OS child PID를 제공하지 않습니다. 따라서 Shell call을 직접 process edge로 만들지 않습니다.

Runtime evidence에서 유일하게 지지되는 process가 독립적으로 확인될 때만 ExecWeave가 다음 bridge를 파생할 수 있습니다.

```text
tool_call --CORRELATED_WITH_PROCESS--> process
```

이 bridge는 항상:

```text
inferred: true
causal: false
```

후보가 모호하거나 지원되지 않으면 edge를 만들지 않습니다.

## 프라이버시 경계

Adapter는 prompt, transcript path, user email, agent message, tool output을 저장하지 않습니다. Model identity, conversation/generation IDs, tool name/use ID, command, declared file path처럼 observability에 필요한 metadata만 유지합니다.

Command와 path 자체는 민감할 수 있으므로 artifact를 공유하기 전에 검토해야 합니다.

## Evidence boundary

Cursor Hook이 증명하는 것은 Cursor가 semantic layer에서 보고한 내용뿐입니다. Declared command의 실제 실행, declared file의 실제 접근, resource 간 data flow는 증명하지 않습니다. 실제 runtime behavior의 기준은 OS collector evidence입니다.