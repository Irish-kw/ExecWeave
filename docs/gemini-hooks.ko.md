<!-- i18n-nav:start -->
<p align="center">
  <a href="gemini-hooks.md">English</a> |
  <a href="gemini-hooks.zh-TW.md">繁體中文</a> |
  <a href="gemini-hooks.zh-CN.md">简体中文</a> |
  <a href="gemini-hooks.ja.md">日本語</a> |
  <strong>한국어</strong> |
  <a href="gemini-hooks.fr.md">Français</a> |
  <a href="gemini-hooks.de.md">Deutsch</a> |
  <a href="gemini-hooks.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# Gemini CLI Hooks

ExecWeave는 Gemini CLI lifecycle/tool hooks를 provider semantic evidence로 수집하고, 독립적으로 수집한 OS runtime evidence와 같은 execution graph에 결합할 수 있습니다.

이 adapter는 의도적으로 보수적입니다. Gemini hook은 Agent / Tool layer가 보고한 semantic evidence이며, 그 자체만으로 특정 OS process가 실제 작업을 수행했다고 증명하지 않습니다.

## 지원 hook events

현재 지원:

- `SessionStart`
- `BeforeTool`
- `AfterTool`

Gemini CLI는 JSON hook input을 `stdin`으로 전달합니다. 성공한 command hook의 `stdout`은 valid JSON이어야 하므로 `execweave-gemini-hook`은 성공 시 `{}`만 출력하고 warning은 `stderr`로 보냅니다.

설정 fragment 생성:

```bash
execweave-gemini-hook --print-config
```

출력된 `hooks` object를 Gemini CLI `settings.json`에 merge합니다. 생성된 hook은 telemetry만 수행하며 tool call을 block하거나 rewrite하지 않습니다.

## One-command recording

```bash
execweave-gemini-record --open -- gemini
```

Recorder는 `EXECWEAVE_SEMANTIC_SIDECAR`를 사용해 이번 Gemini child process를 run-specific sidecar에 bind하고 공통 provider-record pipeline을 사용합니다.

```text
runtime evidence
      +
Gemini hook evidence
      ↓
validated semantic merge
      ↓
conservative correlation
      ↓
graph + viewer
```

Provider-integrated run은 다음 artifacts를 생성할 수 있습니다.

```text
.execweave/runs/<run-id>/
├── events.jsonl
├── graph.json
├── viewer.html
├── semantic.jsonl
├── events.semantic.jsonl
├── graph.semantic.json
├── viewer.semantic.html
├── events.correlated.jsonl
├── graph.correlated.json
└── viewer.correlated.html
```

Raw runtime과 provider sidecar evidence는 분리된 상태를 유지합니다. Correlation은 observed input evidence를 다시 쓰지 않고 derived stream을 생성합니다.

## Event mapping

### SessionStart

```text
Gemini CLI --STARTED_PROVIDER_SESSION--> provider_session
```

입력에 `transcript_path`가 있어도 ExecWeave는 transcript를 읽거나 복사하지 않습니다.

### BeforeTool

```text
Gemini CLI --REQUESTED_TOOL_CALL--> tool_call
tool_call --USES_TOOL--> tool
```

`run_shell_command`의 `tool_input.command`는:

```text
tool_call --DECLARED_COMMAND--> command
```

으로 기록되어 conservative Tool → Process correlation에 참여할 수 있습니다.

`read_file`, `write_file`, `replace` 등 일부 file tool은 declared target path를 semantic metadata로 기록할 수 있지만 file content는 수집하지 않습니다.

### MCP

`mcp_context`가 있으면 provider가 명시적으로 보고한 server/tool identity를 사용합니다.

```text
tool_call --VIA_MCP--> mcp_server
mcp_server --EXPOSES_TOOL--> tool
```

MCP launch command, arguments, URL은 sensitive connection metadata나 credential을 포함할 수 있으므로 artifact에 저장하지 않습니다.

### AfterTool

`AfterTool`은 별도의 `tool_result` observation으로 기록합니다. `tool_response.error`가 non-empty일 때만 provider-reported error를 기록하며, 그 외에는 neutral returned-result signal을 기록합니다.

Raw `llmContent`, `returnDisplay`, error body는 저장하지 않습니다.

## Unique tool-call ID가 없음

현재 Gemini CLI hook schema에는 `BeforeTool`과 `AfterTool`이 공유하는 unique tool-call ID가 없습니다.

따라서 ExecWeave는 direct BeforeTool → AfterTool identity edge를 만들지 않습니다.

`BeforeTool`은 timestamp-scoped local identity를 사용하고 `AfterTool`은 별도 result node를 만듭니다. `tool_fingerprint`는 진단 hint일 뿐 call identity로 사용하지 않습니다. 동일 command가 반복되어도 잘못 하나의 call로 합치지 않기 위해서입니다.

## Tool → Process correlation

Gemini hook은 child OS PID를 제공하지 않습니다. 독립 runtime evidence에서 bounded matcher가 유일하게 지지되는 process candidate를 찾을 때만:

```text
tool_call --CORRELATED_WITH_PROCESS--> process
```

를 derived edge로 만들 수 있습니다.

항상:

```text
inferred: true
causal: false
```

를 유지합니다. Ambiguous / no-match / compound / shell builtin / unsupported call은 edge를 생성하지 않습니다.

Correlated Viewer는 matched / ambiguous / no-match / unsupported count를 표시하므로 missing edge가 조용히 “아무 일도 일어나지 않았다”로 해석되지 않습니다.

## Privacy

Prompt, transcript, raw tool result, raw error body, MCP command/args/URL, file content는 기본적으로 수집하지 않습니다. 하지만 command, path, tool name, session identifier, MCP server/tool name 등의 metadata는 민감할 수 있으므로 artifact 공유 전에 확인하세요.

## Failure behavior

`execweave-gemini-hook`은 기본적으로 fail-open입니다. Telemetry error는 `stderr`로 보내며 Gemini tool call을 의도적으로 차단하지 않습니다. Non-zero telemetry failure가 필요할 때만 `--strict`를 사용합니다.

## Upstream contract

- https://github.com/google-gemini/gemini-cli/blob/main/docs/hooks/reference.md
- https://github.com/google-gemini/gemini-cli/blob/main/docs/hooks/index.md

Provider hook schema는 바뀔 수 있습니다. ExecWeave는 provider가 실제로 전달한 field만 기록하며 semantic hook을 사용할 수 없는 경우에도 독립적인 OS runtime collection을 계속 유용하게 유지합니다.

[`Semantic Telemetry`](semantic-telemetry.ko.md)도 참고하세요.
