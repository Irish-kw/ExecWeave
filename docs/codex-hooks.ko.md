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

# OpenAI Codex Lifecycle Hooks

ExecWeave는 OpenAI Codex lifecycle hook을 provider-level semantic evidence로 수집하는 native adapter를 제공합니다. Hook은 logical tool call과 declared command를 알려줄 수 있지만 OS child PID는 제공하지 않으므로 Tool → Process를 직접 observed/causal evidence로 표시하지 않습니다.

## Supported events

- `SessionStart`
- `PreToolUse`
- `PostToolUse`

`SessionStart`에 model이 있으면 `OpenAI Codex --USED_MODEL--> model`을 기록합니다.

`PreToolUse`는 `tool_use_id`를 stable call identity로 사용합니다.

```text
OpenAI Codex --REQUESTED_TOOL_CALL--> tool_call
tool_call --USES_TOOL--> tool
tool_call --DECLARED_COMMAND--> command   # Bash
```

`PostToolUse`는 중립적인:

```text
tool_call --TOOL_CALL_RETURNED--> tool
```

로 기록합니다. 현재 payload에는 충분히 reliable한 success/failure discriminator가 없으므로 `SUCCEEDED/FAILED`를 추측하지 않습니다. Raw `tool_response` content도 저장하지 않습니다.

## Setup

```bash
execweave-codex-hook --print-config
```

출력된 hooks를 Codex `hooks.json`에 merge합니다. Adapter는 기본 fail-open이고 `--strict`는 debug용입니다.

## Record

```bash
execweave-codex-record --open -- codex
```

Recorder는 Codex child process에 run-specific sidecar path를 상속시키고 runtime/semantic/correlated artifacts를 분리해 생성합니다. Hook event가 없으면 runtime-only로 안전하게 fallback합니다.

## Correlation

Declared Bash command와 runtime evidence를 비교해 unique candidate가 있을 때만:

```text
tool_call --CORRELATED_WITH_PROCESS--> process
```

를 생성합니다. 항상 `inferred: true`, `causal: false`입니다. Ambiguous/no-match/builtin/compound/unsupported call은 no edge입니다. Correlated graph metadata의 Correlation Summary는 `matched / ambiguous / no match / unsupported`를 구분합니다.

Viewer의 **observed only**는 focus/layout 전에 inferred edge를 제거합니다.

## Privacy

Session/turn/model/tool/tool-use ID, input key names, declared Bash command, PostToolUse response type/length 같은 필요한 metadata만 보존합니다. Prompt, transcript content, raw response, file content, provider-derived child PID는 수집하지 않습니다.

## Upstream limitations

Codex hooks는 계속 발전 중입니다. `PostToolUse` outcome signal은 제한적이며 일부 `codex exec` 또는 Windows execution path에 hook coverage gap이 보고된 적이 있습니다. 이는 semantic coverage 제한이며 독립 OS runtime collector는 계속 동작합니다.

> Provider semantics는 Agent가 무엇을 하려고 했는지, OS telemetry는 machine이 무엇을 관찰했는지 설명합니다. 둘을 연결할 때도 unique evidence에 기반한 explicit non-causal inference로만 표현합니다.

자세한 내용은 [`Semantic Telemetry`](semantic-telemetry.ko.md).
