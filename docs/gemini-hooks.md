<!-- i18n-nav:start -->
<p align="center">
  <strong>English</strong> |
  <a href="gemini-hooks.zh-TW.md">繁體中文</a> |
  <a href="gemini-hooks.zh-CN.md">简体中文</a> |
  <a href="gemini-hooks.ja.md">日本語</a> |
  <a href="gemini-hooks.ko.md">한국어</a> |
  <a href="gemini-hooks.fr.md">Français</a> |
  <a href="gemini-hooks.de.md">Deutsch</a> |
  <a href="gemini-hooks.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# Gemini CLI Hooks

ExecWeave can ingest Gemini CLI lifecycle/tool hooks as provider semantic evidence and combine them with independently collected OS runtime evidence.

The adapter is intentionally conservative: Gemini hook evidence describes what the provider reports at the Agent / Tool layer. It does not by itself prove which OS process performed the work.

## Supported hook events

The current adapter consumes:

- `SessionStart`
- `BeforeTool`
- `AfterTool`

Gemini CLI sends hook input as JSON on `stdin`. A successful command hook must return valid JSON on `stdout`; ExecWeave therefore returns exactly `{}` on success and sends warnings only to `stderr`.

Generate a settings fragment with:

```bash
execweave-gemini-hook --print-config
```

Merge the resulting `hooks` object into Gemini CLI `settings.json`.

The generated configuration observes all tools with `BeforeTool` / `AfterTool` matchers and does not block or rewrite the tool call.

## One-command recording

After the hooks are configured:

```bash
execweave-gemini-record --open -- gemini
```

The recorder binds the Gemini child process to a run-specific semantic sidecar through `EXECWEAVE_SEMANTIC_SIDECAR`, then uses the shared provider-record pipeline:

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

A provider-integrated run can produce:

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

Raw runtime and provider sidecar evidence remain separate. Correlation creates a derived stream rather than rewriting observed input evidence.

## Event mapping

### Session start

`SessionStart` becomes provider-session evidence:

```text
Gemini CLI --STARTED_PROVIDER_SESSION--> provider_session
```

ExecWeave keeps session metadata needed for attribution but does not read or copy the transcript referenced by `transcript_path`.

### BeforeTool

A `BeforeTool` hook produces semantic relationships such as:

```text
Gemini CLI --REQUESTED_TOOL_CALL--> tool_call
tool_call --USES_TOOL--> tool
```

For the built-in `run_shell_command` tool, `tool_input.command` is represented as:

```text
tool_call --DECLARED_COMMAND--> command
```

This command evidence can participate in the same conservative Tool → Process correlation used by the other provider adapters.

For selected file tools such as `read_file`, `write_file`, and `replace`, ExecWeave may record the declared target path as semantic metadata. It does not capture the file contents.

### MCP tools

When Gemini CLI supplies `mcp_context`, ExecWeave uses the explicit provider-reported server/tool identity:

```text
tool_call --VIA_MCP--> mcp_server
mcp_server --EXPOSES_TOOL--> tool
```

The adapter does not persist MCP launch command, arguments, or URL from `mcp_context`, because those fields can contain sensitive connection metadata or credentials.

### AfterTool

`AfterTool` is recorded as a separate `tool_result` observation.

If `tool_response.error` is non-empty, the adapter records a provider-reported error signal. Otherwise it records a neutral returned-result signal.

ExecWeave does **not** store raw `llmContent`, `returnDisplay`, or the provider error body.

## No unique Gemini tool-call ID

The current Gemini CLI hook input schema provides `tool_name`, `tool_input`, and optional MCP context, but it does not expose a unique tool-call ID that is shared by `BeforeTool` and `AfterTool`.

ExecWeave therefore does **not** assert a direct BeforeTool → AfterTool identity edge.

Each `BeforeTool` request is given a timestamp-scoped local identity. `AfterTool` creates an independent result node. Both may carry a deterministic `tool_fingerprint` derived from tool name + normalized input as a diagnostic hint, but that fingerprint is **not treated as call identity**. Repeated identical commands must remain distinguishable.

## Tool → Process correlation

Gemini hooks do not provide the child OS PID needed to prove Tool → Process attribution.

A correlated graph may contain:

```text
tool_call --CORRELATED_WITH_PROCESS--> process
```

only when the existing bounded matcher finds one uniquely supported process candidate from independent runtime evidence.

Every such bridge remains:

```text
inferred: true
causal: false
```

Ambiguous, unmatched, compound, shell-builtin, or unsupported commands produce no bridge.

The correlated Viewer exposes matched / ambiguous / no-match / unsupported counts so a missing edge is not silently interpreted as “nothing happened.”

## Privacy boundary

The native Gemini adapter intentionally avoids:

- prompt contents
- transcript contents
- raw tool result contents
- raw provider error bodies
- MCP command / argument / URL details
- file contents

It can still retain metadata such as command text, declared file paths, tool names, session identifiers, and MCP server/tool names. Review artifacts before sharing them.

## Failure behavior

`execweave-gemini-hook` is fail-open by default. Telemetry failures are written to `stderr` and do not intentionally block the Gemini tool call.

Use `--strict` only when a non-zero telemetry exit is desired.

## Current upstream contract

This adapter follows the current Gemini CLI hook reference:

- https://github.com/google-gemini/gemini-cli/blob/main/docs/hooks/reference.md
- https://github.com/google-gemini/gemini-cli/blob/main/docs/hooks/index.md

Provider hook schemas can evolve. ExecWeave records only fields actually delivered by the provider and keeps independent OS runtime collection useful even when semantic hooks are unavailable.

See also [`Semantic Telemetry`](semantic-telemetry.md).
