<!-- i18n-nav:start -->
<p align="center">
  <strong>English</strong> |
  <a href="codex-hooks.zh-TW.md">繁體中文</a> |
  <a href="codex-hooks.zh-CN.md">简体中文</a> |
  <a href="codex-hooks.ja.md">日本語</a> |
  <a href="codex-hooks.ko.md">한국어</a>
</p>
<!-- i18n-nav:end -->

# OpenAI Codex lifecycle hooks

ExecWeave has a native OpenAI Codex lifecycle-hook adapter for adding provider-level semantic evidence to the same local run as OS runtime telemetry.

This integration is intentionally conservative. Codex lifecycle hooks can tell ExecWeave which logical tool call was requested and, for shell execution, which command was declared. They do **not** provide an OS child PID, so ExecWeave never presents Tool → Process attribution from the provider hook as directly observed or causal evidence.

## Current support

ExecWeave currently consumes these Codex lifecycle events:

- `SessionStart`
- `PreToolUse`
- `PostToolUse`

The adapter records only hooks that Codex actually delivers. Unknown lifecycle events are ignored rather than guessed.

### `SessionStart`

When a model name is present, ExecWeave records:

```text
OpenAI Codex --USED_MODEL--> model
```

The adapter does not read or copy transcript-file contents.

### `PreToolUse`

ExecWeave uses the provider's `tool_use_id` as the stable logical tool-call identity:

```text
OpenAI Codex --REQUESTED_TOOL_CALL--> tool_call
tool_call --USES_TOOL--> tool
```

For the canonical Codex `Bash` hook tool, a string `tool_input.command` also produces:

```text
tool_call --DECLARED_COMMAND--> command
```

The declared command is semantic provider evidence. It is useful for later conservative correlation, but it is not proof that a specific OS process executed that command.

### `PostToolUse`

ExecWeave currently records a neutral completion relation:

```text
tool_call --TOOL_CALL_RETURNED--> tool
```

It deliberately does **not** translate `PostToolUse` into `TOOL_CALL_SUCCEEDED` or `TOOL_CALL_FAILED`. The current Codex hook payload does not provide a sufficiently reliable success/failure discriminator for ExecWeave to make that claim safely.

ExecWeave does not store the raw `tool_response` in semantic telemetry. For string responses it stores only the response type and character count.

## Configure Codex

After installing ExecWeave, generate the supported lifecycle-hook configuration fragment:

```bash
execweave-codex-hook --print-config
```

Merge the printed `hooks` object into your Codex `hooks.json` configuration.

The generated configuration registers `execweave-codex-hook` for `SessionStart`, `PreToolUse`, and `PostToolUse`.

The hook adapter is fail-open by default: telemetry problems print a warning but do not intentionally block Codex. For debugging the adapter itself, use:

```bash
execweave-codex-hook --strict
```

## Record one Codex run

Once Codex is configured to invoke the hook, run:

```bash
execweave-codex-record --open -- codex
```

`execweave-codex-record` does not modify Codex configuration. It only binds the child Codex process to a run-specific semantic sidecar using an inherited environment variable.

When lifecycle hooks fire, the run directory contains layered artifacts:

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

If no Codex hook events arrive, the recorder safely falls back to runtime-only artifacts.

## Tool → Process correlation

For a `Bash` declaration such as:

```text
tool_call --DECLARED_COMMAND--> "python task.py"
```

ExecWeave can compare that semantic declaration with bounded runtime process evidence. It emits:

```text
tool_call --CORRELATED_WITH_PROCESS--> process
```

only when one process candidate is uniquely supported by the existing conservative matcher.

Every such bridge remains:

```text
inferred: true
causal: false
```

Ambiguous, unmatched, shell-builtin, compound, or otherwise unsupported calls produce no bridge. The correlated graph stores a run-level correlation summary so the Viewer can distinguish `matched`, `ambiguous`, `no match`, and `unsupported` outcomes instead of treating every missing edge as the same thing.

The Viewer also provides **observed only**, which removes inferred edges before focus traversal and layout.

## Evidence and privacy boundary

ExecWeave's Codex adapter currently stores semantic metadata needed to construct the graph, including:

- Codex session ID
- turn ID when provided
- model name
- tool name
- tool-use ID
- input key names
- declared `Bash` command
- response type / response length for `PostToolUse`

It does not intentionally collect:

- prompt text
- transcript-file contents
- raw `tool_response` contents
- file contents
- provider-derived Tool → Process PIDs

Commands can still contain secrets or sensitive paths. Review artifacts before sharing them.

## Current upstream limitations

Codex lifecycle hooks are evolving. ExecWeave therefore treats this integration as a native semantic adapter, not as proof that every Codex execution mode exposes complete lifecycle coverage.

Known constraints to keep in mind:

1. `PostToolUse` currently does not give ExecWeave a reliable success/failure signal, so the relation is neutral `TOOL_CALL_RETURNED`.
2. Lifecycle-hook dispatch has had recent gaps in some `codex exec` paths. Interactive Codex CLI is the safer initial target for lifecycle-hook telemetry.
3. Some Windows command-execution paths have had reported hook-coverage gaps upstream.
4. Provider hooks do not provide the OS child PID required for directly observed Tool → Process attribution.

These limitations affect semantic coverage, not the independent OS runtime collector. Runtime evidence remains available even when no provider hook fires.

## Design rule

The Codex integration follows the same evidence rule as the rest of ExecWeave:

> Provider semantics describe what the agent said it was doing; OS telemetry describes what the machine actually observed; correlation may connect the two only as an explicit, non-causal inference when the evidence is unique.
