<!-- i18n-nav:start -->
<p align="center">
  <a href="codex-hooks.md">English</a> |
  <a href="codex-hooks.zh-TW.md">繁體中文</a> |
  <a href="codex-hooks.zh-CN.md">简体中文</a> |
  <a href="codex-hooks.ja.md">日本語</a> |
  <strong>한국어</strong> |
  <a href="codex-hooks.fr.md">Français</a> |
  <a href="codex-hooks.de.md">Deutsch</a> |
  <a href="codex-hooks.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# OpenAI Codex lifecycle hooks

ExecWeave는 OS runtime telemetry와 같은 local run에 provider-level semantic evidence를 추가하는 native OpenAI Codex lifecycle-hook adapter를 제공합니다.

이 integration은 의도적으로 보수적입니다. Codex lifecycle hook은 어떤 logical tool call이 요청되었는지, shell execution의 경우 어떤 command가 선언되었는지 ExecWeave에 알려줄 수 있습니다. 하지만 OS child PID는 제공하지 않으므로 ExecWeave는 provider hook에서 나온 Tool → Process attribution을 directly observed 또는 causal evidence로 표시하지 않습니다.

## Current support

ExecWeave는 현재 다음 Codex lifecycle event를 사용합니다.

- `SessionStart`
- `PreToolUse`
- `PostToolUse`

Adapter는 Codex가 실제로 전달한 hook만 기록합니다. Unknown lifecycle event는 추측하지 않고 무시합니다.

### `SessionStart`

Model name이 있으면 ExecWeave는 다음을 기록합니다.

```text
OpenAI Codex --USED_MODEL--> model
```

Adapter는 transcript file 내용을 읽거나 복사하지 않습니다.

### `PreToolUse`

ExecWeave는 provider의 `tool_use_id`를 stable logical tool-call identity로 사용합니다.

```text
OpenAI Codex --REQUESTED_TOOL_CALL--> tool_call
tool_call --USES_TOOL--> tool
```

Canonical Codex `Bash` hook tool에서 string `tool_input.command`가 있으면 다음도 생성합니다.

```text
tool_call --DECLARED_COMMAND--> command
```

Declared command는 semantic provider evidence입니다. 이후 conservative correlation에는 유용하지만 특정 OS process가 그 command를 실행했다는 증거는 아닙니다.

### `PostToolUse`

ExecWeave는 현재 중립적인 completion relation을 기록합니다.

```text
tool_call --TOOL_CALL_RETURNED--> tool
```

`PostToolUse`를 `TOOL_CALL_SUCCEEDED` 또는 `TOOL_CALL_FAILED`로 의도적으로 변환하지 않습니다. 현재 Codex hook payload에는 그 claim을 안전하게 만들 만큼 reliable한 success/failure discriminator가 없습니다.

ExecWeave는 raw `tool_response`를 semantic telemetry에 저장하지 않습니다. String response의 경우 response type과 character count만 저장합니다.

## Configure Codex

ExecWeave를 설치한 후 지원되는 lifecycle-hook configuration fragment를 생성합니다.

```bash
execweave-codex-hook --print-config
```

출력된 `hooks` object를 Codex `hooks.json` configuration에 merge합니다.

생성된 configuration은 `SessionStart`, `PreToolUse`, `PostToolUse`에 `execweave-codex-hook`를 등록합니다.

Hook adapter는 기본적으로 fail-open입니다. Telemetry problem은 warning을 출력하지만 Codex를 의도적으로 block하지 않습니다. Adapter 자체를 debug하려면:

```bash
execweave-codex-hook --strict
```

## Record one Codex run

Codex가 hook을 invoke하도록 설정한 뒤 다음을 실행합니다.

```bash
execweave-codex-record --open -- codex
```

`execweave-codex-record`는 Codex configuration을 수정하지 않습니다. Inherited environment variable을 사용해 child Codex process를 run-specific semantic sidecar에 bind할 뿐입니다.

Lifecycle hook이 발생하면 run directory에는 layered artifact가 포함됩니다.

```text
.execweave/runs/<run-id>/
├── events.jsonl              # runtime evidence only
├── graph.json                # runtime-only graph
├── viewer.html               # runtime-only viewer
├── semantic.jsonl            # Codex lifecycle-hook evidence only
├── events.semantic.jsonl     # validated runtime + semantic stream
├── graph.semantic.json       # runtime + semantic graph
├── viewer.semantic.html      # runtime + semantic viewer
├── events.correlated.jsonl   # derived stream; observed evidence unchanged
├── graph.correlated.json     # graph with inferred bridges + correlation metadata
└── viewer.correlated.html    # viewer with correlation summary
```

Codex hook event가 도착하지 않으면 recorder는 안전하게 runtime-only artifact로 fallback합니다.

## Tool → Process correlation

다음과 같은 `Bash` declaration의 경우:

```text
tool_call --DECLARED_COMMAND--> "python task.py"
```

ExecWeave는 이 semantic declaration을 bounded runtime process evidence와 비교할 수 있습니다. 기존 conservative matcher가 정확히 하나의 process candidate만 고유하게 지원할 때만 다음을 emit합니다.

```text
tool_call --CORRELATED_WITH_PROCESS--> process
```

이런 bridge는 항상 다음 상태를 유지합니다.

```text
inferred: true
causal: false
```

Ambiguous, unmatched, shell-builtin, compound 또는 기타 unsupported call에서는 bridge를 생성하지 않습니다. Correlated graph는 run-level correlation summary를 저장하므로 Viewer는 모든 missing edge를 같은 것으로 취급하지 않고 `matched`, `ambiguous`, `no match`, `unsupported` 결과를 구분할 수 있습니다.

Viewer에는 **observed only**도 있어 focus traversal과 layout 전에 inferred edge를 제거합니다.

## Evidence and privacy boundary

ExecWeave의 Codex adapter는 graph construction에 필요한 semantic metadata를 현재 저장합니다.

- Codex session ID
- 제공된 경우 turn ID
- model name
- tool name
- tool-use ID
- input key name
- declared `Bash` command
- `PostToolUse`의 response type / response length

의도적으로 수집하지 않는 항목:

- prompt text
- transcript-file contents
- raw `tool_response` contents
- file contents
- provider-derived Tool → Process PID

Command에는 secret이나 sensitive path가 포함될 수 있습니다. Artifact를 공유하기 전에 검토하십시오.

## Current upstream limitations

Codex lifecycle hook은 계속 발전하고 있습니다. 따라서 ExecWeave는 이 integration을 native semantic adapter로 취급하며 모든 Codex execution mode가 완전한 lifecycle coverage를 노출한다는 증거로 취급하지 않습니다.

알아둘 constraint는 다음과 같습니다.

1. `PostToolUse`는 현재 ExecWeave에 reliable한 success/failure signal을 제공하지 않으므로 relation은 중립적인 `TOOL_CALL_RETURNED`입니다.
2. 일부 `codex exec` path에서는 lifecycle-hook dispatch에 최근 gap이 있었습니다. Lifecycle-hook telemetry의 초기 target으로는 interactive Codex CLI가 더 안전합니다.
3. 일부 Windows command-execution path에서도 hook-coverage gap이 보고된 적이 있습니다.
4. Provider hook은 directly observed Tool → Process attribution에 필요한 OS child PID를 제공하지 않습니다.

이 limitation은 semantic coverage에 영향을 주지만 독립적인 OS runtime collector에는 영향을 주지 않습니다. Provider hook이 전혀 발생하지 않아도 runtime evidence는 계속 사용할 수 있습니다.

## Design rule

Codex integration은 ExecWeave의 나머지 부분과 동일한 evidence rule을 따릅니다.

> Provider semantics는 Agent가 무엇을 하고 있다고 말했는지 설명하고, OS telemetry는 machine이 실제로 무엇을 관측했는지 설명합니다. 둘 사이의 correlation은 evidence가 unique할 때만 explicit한 non-causal inference로 연결할 수 있습니다.
