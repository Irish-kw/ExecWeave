<!-- i18n-nav:start -->
<p align="center">
  <strong>English</strong> |
  <a href="claude-code-hooks.zh-TW.md">繁體中文</a> |
  <a href="claude-code-hooks.zh-CN.md">简体中文</a> |
  <a href="claude-code-hooks.ja.md">日本語</a> |
  <a href="claude-code-hooks.ko.md">한국어</a> |
  <a href="claude-code-hooks.fr.md">Français</a> |
  <a href="claude-code-hooks.de.md">Deutsch</a> |
  <a href="claude-code-hooks.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# Claude Code Hooks

ExecWeave includes a native Claude Code command-hook adapter that records provider semantic/content evidence into a local sidecar while keeping it distinct from independent OS runtime evidence. Provider hooks explain what Claude Code exposed; they do not replace the portable or Linux `strace` collector and do not by themselves establish OS process causality.

## Current hook surface

`execweave-claude-hook --print-config` currently registers:

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

The hook configuration is fail-open by default: telemetry/storage errors are reported without intentionally blocking an Agent operation. `--strict` is available when a non-zero telemetry exit is desired for debugging.

## Configure and record

Install ExecWeave, generate the supported settings fragment, merge it into the appropriate Claude Code settings file, then use the run-bound recorder:

```bash
execweave-claude-hook --print-config
execweave-claude-record --open -- claude
```

`execweave-claude-record` binds a unique run-specific semantic sidecar through the child environment. Runtime, semantic, and correlated evidence remain separate artifacts.

```text
runtime evidence
    ↓ semantic merge
runtime + semantic evidence
    ↓ conservative correlation
runtime + semantic + inferred correlation
```

If no supported Claude hook event arrives, the recorder falls back to runtime-only artifacts. If semantic evidence exists but no uniquely supported Tool → Process candidate survives, no bridge is fabricated.

## Full-fidelity content in v0.6.5

The Claude adapter is no longer limited to bounded metadata summaries. When the hook explicitly supplies content, v0.6.5 stores the complete supplied value in the local SHA-256 content-addressed store and puts a reference in the semantic sidecar.

Covered regressions include:

- complete `UserPromptSubmit.prompt`, including large values;
- complete tool input, including `Write`/`Edit` content and application-level values inside the input object;
- complete structured `PostToolUse.tool_response` when supplied;
- model-visible tool-result serialization supplied through `PostToolBatch`;
- `MessageDisplay` assistant text/deltas with available ordering metadata;
- final main-Agent and subagent assistant messages supplied by stop events.

Known transport credentials are filtered from the separate provider-metadata projection where the adapter recognizes them. This filtering does **not** sanitize the full content value itself. A secret embedded in a prompt, tool input, file body, tool result, or assistant message remains part of the preserved full-fidelity evidence.

`content_complete_from_source: true` means ExecWeave stored the complete value supplied by the Claude hook. It does not claim that ExecWeave read an unprovided transcript, observed hidden model state, or captured any provider stage absent from the hook payload.

## Logical entities and tool identity

Claude hook events can materialize provider-level relationships such as:

```text
Claude Code --REQUESTED_TOOL_CALL--> tool_call
tool_call --USES_TOOL-------------> tool
tool_call --DECLARED_COMMAND------> command
tool_call --DECLARED_TARGET-------> file metadata
tool_call --VIA_MCP---------------> mcp_server
Claude Code --SPAWNED_SUBAGENT----> subagent
```

Claude Code's hook input can identify a logical tool invocation with `tool_use_id`, but that ID is not an OS PID. MCP names following the provider's `mcp__<server>__<tool>` convention are normalized into separate MCP-server/tool entities when present.

## Tool → Process correlation boundary

Claude's command-hook input does not provide the actual child process PID created by a Bash/PowerShell tool invocation. ExecWeave therefore does not create an observed causal process edge from provider hook data alone.

A separately derived bridge can be emitted only when the bounded runtime matcher finds exactly one supported process candidate:

```text
tool_call --CORRELATED_WITH_PROCESS--> process
```

Every such bridge remains:

```json
{
  "causal": false,
  "inferred": true,
  "confidence_semantics": "heuristic_score_not_probability"
}
```

Temporal proximity alone is insufficient. Ambiguous candidates, unsupported compound commands, shell builtins, or unmatched declarations produce no bridge. Inference is never upgraded into observed process attribution.

## Layered artifacts

A run-bound Claude capture can produce:

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

The original runtime and provider evidence are not rewritten by correlation.

## Standalone sidecar

Outside the run-bound recorder, the default Claude sidecar is session-scoped:

```text
<cwd>/.execweave/semantic/claude/<Claude-session-id>.jsonl
```

`EXECWEAVE_SEMANTIC_SIDECAR` or `--sidecar` can override that location. Prefer a session/run-specific path for parallel captures.

## Privacy and evidence boundary

Claude full-fidelity artifacts can contain prompts, commands, file paths, `Write`/`Edit` bodies, tool arguments/results, assistant text, subagent responses, identifiers, and application-level secrets. Treat the entire run directory as sensitive and review it before sharing.

Provider content remains provider evidence. A stored tool input does not prove that the tool executed; a stored file body does not prove a particular OS process wrote/read it; a stored tool result does not prove byte-level data flow to another resource. OS collectors and separately marked correlation provide independent evidence for those stronger claims.

## Manual merge and correlation

The generic pipeline remains available when you already have runtime and semantic files:

```bash
execweave semantic-merge run.jsonl semantic.jsonl --output run.semantic.jsonl
execweave validate run.semantic.jsonl
execweave correlate run.semantic.jsonl --output run.correlated.jsonl
execweave validate run.correlated.jsonl
```

See [`Semantic Telemetry`](semantic-telemetry.md) for the generic evidence/content contract and process-reference rules.
