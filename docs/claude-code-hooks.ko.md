<!-- i18n-nav:start -->
<p align="center">
  <a href="claude-code-hooks.md">English</a> |
  <a href="claude-code-hooks.zh-TW.md">繁體中文</a> |
  <a href="claude-code-hooks.zh-CN.md">简体中文</a> |
  <a href="claude-code-hooks.ja.md">日本語</a> |
  <strong>한국어</strong> |
  <a href="claude-code-hooks.fr.md">Français</a> |
  <a href="claude-code-hooks.de.md">Deutsch</a> |
  <a href="claude-code-hooks.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# Claude Code Hooks

ExecWeave에는 Claude Code command-hook adapter가 내장되어 provider의 semantic/content evidence를 로컬 sidecar에 기록하고 독립적인 OS runtime evidence와 분리해 보존합니다. Provider hook은 Claude Code가 명시적으로 노출한 내용을 설명하지만 portable 또는 Linux `strace` collector를 대체하지 않으며 hook만으로 OS process causality를 입증하지 않습니다.

**현재 hook surface.** `execweave-claude-hook --print-config`는 현재 다음을 등록합니다.

- `SessionStart`
- `UserPromptSubmit`
- `MessageDisplay`
- `PreToolUse`
- `PostToolUse`
- `PostToolUseFailure`
- `PostToolBatch`
- `SubagentStart`
- `SubagentStop`
- `Stop`
- `StopFailure`

Hook은 기본적으로 fail-open입니다. telemetry/storage error는 보고되지만 Agent operation을 의도적으로 막지 않습니다. 디버깅 시 telemetry failure를 non-zero로 만들려면 `--strict`를 사용합니다.

## 설정과 기록

ExecWeave를 설치하고 지원되는 settings fragment를 생성해 Claude Code settings에 merge한 뒤 run-bound recorder를 사용합니다.

```bash
execweave-claude-hook --print-config
execweave-claude-record --open -- claude
```

`execweave-claude-record`는 child environment를 통해 run별 고유 semantic sidecar를 bind합니다. Runtime, semantic, correlated evidence는 서로 다른 artifact로 유지됩니다.

```text
runtime evidence
    ↓ semantic merge
runtime + semantic evidence
    ↓ conservative correlation
runtime + semantic + inferred correlation
```

지원되는 Claude hook event가 없으면 runtime-only artifact로 fallback합니다. Semantic evidence가 있어도 유일하고 충분히 뒷받침되는 Tool → Process candidate가 없으면 bridge를 만들지 않습니다.

## v0.6.5 full-fidelity content

Claude adapter는 더 이상 bounded metadata summary에만 제한되지 않습니다. Hook이 content를 명시적으로 제공하면 v0.6.5는 source가 제공한 전체 값을 로컬 SHA-256 content-addressed store에 저장하고 semantic sidecar에는 reference를 남깁니다.

Regression coverage에는 다음이 포함됩니다.

- 큰 값을 포함한 전체 `UserPromptSubmit.prompt`;
- `Write`/`Edit` content와 input object 내부 application-level value를 포함한 전체 tool input;
- 제공된 경우 전체 structured `PostToolUse.tool_response`;
- `PostToolBatch`가 제공한 model-visible tool-result serialization;
- ordering metadata와 함께 제공되는 `MessageDisplay` assistant text/delta;
- stop event에서 제공되는 main Agent / subagent의 최종 assistant message.

알려진 transport credential은 adapter가 인식하는 별도 provider-metadata projection에서만 제거됩니다. 이 동작은 full content 자체를 sanitize하지 않습니다. Prompt, tool input, file body, tool result, assistant message 안에 secret이 있으면 그 secret도 full-fidelity evidence로 보존됩니다.

`content_complete_from_source: true`는 Claude hook이 제공한 값을 ExecWeave가 완전히 저장했다는 뜻입니다. Hook이 제공하지 않은 transcript, hidden model state, payload에 없는 provider stage까지 관측했다는 뜻은 아닙니다.

## Logical entities와 tool identity

Claude hook event는 예를 들어 다음 provider-level relationship을 만들 수 있습니다.

```text
Claude Code --REQUESTED_TOOL_CALL--> tool_call
tool_call --USES_TOOL-------------> tool
tool_call --DECLARED_COMMAND------> command
tool_call --DECLARED_TARGET-------> file metadata
tool_call --VIA_MCP---------------> mcp_server
Claude Code --SPAWNED_SUBAGENT----> subagent
```

`tool_use_id`는 logical tool invocation을 식별할 수 있지만 OS PID는 아닙니다. Provider의 `mcp__<server>__<tool>` naming convention에 맞는 MCP 이름은 가능한 경우 독립적인 MCP-server/tool entity로 정규화됩니다.

## Tool → Process correlation boundary

Claude command-hook input은 Bash/PowerShell tool invocation이 실제로 만든 child process PID를 제공하지 않습니다. 따라서 ExecWeave는 provider hook data만으로 observed causal process edge를 만들지 않습니다.

Bounded runtime matcher가 유일한 supported process candidate를 찾은 경우에만 derived bridge를 만들 수 있습니다.

```text
tool_call --CORRELATED_WITH_PROCESS--> process
```

모든 bridge는 다음 의미를 유지합니다.

```json
{
  "causal": false,
  "inferred": true,
  "confidence_semantics": "heuristic_score_not_probability"
}
```

Temporal proximity만으로는 충분하지 않습니다. Ambiguous candidate, unsupported compound command, shell builtin, unmatched declaration은 bridge를 만들지 않습니다. Inference가 observed process attribution으로 승격되는 일도 없습니다.

## Layered artifacts

Run-bound Claude capture는 다음과 같은 artifact를 만들 수 있습니다.

```text
.execweave/runs/<run-id>/
├── events.jsonl
├── graph.json
├── viewer.html
├── semantic.jsonl
├── content/sha256/...
├── events.semantic.jsonl
├── graph.semantic.json
├── viewer.semantic.html
├── events.correlated.jsonl
├── graph.correlated.json
└── viewer.correlated.html
```

Correlation은 원본 runtime/provider evidence를 다시 쓰지 않습니다.

## Standalone sidecar

Run-bound recorder 외부에서는 Claude sidecar가 기본적으로 session별로 분리됩니다.

```text
<cwd>/.execweave/semantic/claude/<Claude-session-id>.jsonl
```

`EXECWEAVE_SEMANTIC_SIDECAR` 또는 `--sidecar`로 덮어쓸 수 있습니다. Parallel capture에는 session/run-specific path를 권장합니다.

## Privacy와 evidence boundary

Claude full-fidelity artifact에는 prompt, command, file path, `Write`/`Edit` body, tool argument/result, assistant text, subagent response, identifier, application-level secret이 포함될 수 있습니다. Run directory 전체를 sensitive data로 취급하고 공유 전에 검토하세요.

Provider content는 여전히 provider evidence입니다. 저장된 tool input이 tool 실행을 증명하지 않고, 저장된 file body가 특정 OS process의 read/write를 증명하지 않으며, 저장된 tool result가 byte-level data flow를 증명하지도 않습니다. 더 강한 claim은 OS collector와 명시적으로 표시된 correlation evidence가 필요합니다.

## 수동 merge와 correlation

Runtime 및 semantic file이 이미 있다면 generic pipeline을 사용할 수 있습니다.

```bash
execweave semantic-merge run.jsonl semantic.jsonl --output run.semantic.jsonl
execweave validate run.semantic.jsonl
execweave correlate run.semantic.jsonl --output run.correlated.jsonl
execweave validate run.correlated.jsonl
```

Generic evidence/content contract와 process-reference rule은 [`Semantic Telemetry`](semantic-telemetry.ko.md)를 참고하세요.
