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

ExecWeave는 Claude Code command-hook event를 semantic JSONL sidecar로 바꾸는 native adapter를 제공합니다. OS runtime collector를 대체하지 않고 logical evidence를 보완합니다.

## Supported hooks

- `SessionStart`
- `PreToolUse`
- `PostToolUse`
- `PostToolUseFailure`
- `SubagentStart`
- `SubagentStop`

```text
Claude Code --REQUESTED_TOOL_CALL--> tool_call
 tool_call --USES_TOOL--> Bash / Read / Edit / Write / ...
 tool_call --DECLARED_COMMAND--> command
 tool_call --DECLARED_TARGET--> file metadata
 tool_call --VIA_MCP--> MCP server
Claude Code --SPAWNED_SUBAGENT--> subagent
Claude Code --USED_MODEL--> model
```

`mcp__<server>__<tool>`은 별도 `mcp_server`와 `tool` node로 normalize합니다.

## Setup

```bash
python -m pip install -e ".[dev]"
execweave-claude-hook --print-config
```

출력된 `hooks` object를 `~/.claude/settings.json`, project `.claude/settings.json` 또는 local settings에 merge합니다. Adapter는 기본 fail-open이고 `--strict`는 adapter debug용이지 security policy가 아닙니다.

## One-command recording

```bash
execweave-claude-record --open -- claude
```

Recorder는 run-specific sidecar path를 child Claude/hook process에 상속시키고 runtime → semantic merge → conservative correlation을 자동 수행합니다.

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

Hook event가 없으면 runtime-only로 fallback합니다. Semantic evidence는 있지만 unique safe process candidate가 없으면 `completed_no_matches`이며 fake edge를 만들지 않습니다.

기본 correlation window는 3000 ms입니다.

```bash
execweave-claude-record --correlation-window-ms 1500 --open -- claude
```

## Tool → Process boundary

Claude hook은 `tool_name`, `tool_use_id`, input을 제공하지만 Bash child OS PID는 제공하지 않습니다. 따라서 native hook 자체가 observed `SPAWNED_PROCESS`를 만들지 않습니다.

Correlation v0.1은 bounded window, exact executable/process/cmdline identity, canonical path, 필요할 때 exact non-empty `argv[1:]` fallback을 사용하며 **후보가 정확히 하나**인 경우에만:

```text
tool_call --CORRELATED_WITH_PROCESS--> process
```

를 생성합니다.

Derived edge는 항상 `backend: inference`, `inferred: true`, `causal: false`. Ambiguous candidate, shell builtin, compound command, fuzzy matching, temporal proximity-only match는 거부합니다.

Viewer는 inferred edge를 별도 스타일로 표시하며 Correlation Summary와 **observed only** filter를 제공합니다.

## Privacy

- `Write/Edit` content 미저장
- raw `tool_response` 미저장
- generic input은 key names 위주
- file tool은 declared path만 보존
- Bash/PowerShell command는 explanation을 위해 보존하지만 4096 chars로 제한
- failure text는 bounded summary

Command/path는 sensitive할 수 있으므로 artifact 공유 전 확인하세요.

Provider semantic edge는 reliable hook evidence여도 `causal: false`로 유지해 OS execution attribution과 분리합니다.

자세한 내용은 [`Semantic Telemetry`](semantic-telemetry.ko.md).
