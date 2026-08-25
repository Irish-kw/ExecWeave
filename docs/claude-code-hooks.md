# Claude Code Hooks

ExecWeave includes a native Claude Code command-hook adapter that records provider semantic telemetry into a separate local JSONL sidecar.

The adapter complements OS runtime collection. It does **not** replace the portable or Linux `strace` collector.

## What it records

The current adapter consumes these Claude Code hook events:

- `SessionStart`
- `PreToolUse`
- `PostToolUse`
- `PostToolUseFailure`
- `SubagentStart`
- `SubagentStop`

It can materialize semantic entities such as:

```text
Claude Code
  |
  +--REQUESTED_TOOL_CALL--> tool_call
  |                           |
  |                           +--USES_TOOL-------> Bash / Read / Edit / Write / ...
  |                           +--DECLARED_COMMAND-> command
  |                           +--DECLARED_TARGET--> file metadata
  |                           +--VIA_MCP----------> MCP server
  |
  +--SPAWNED_SUBAGENT-------> subagent
  +--USED_MODEL-------------> model        when SessionStart exposes one
```

MCP tool names following Claude Code's `mcp__<server>__<tool>` convention are normalized into separate `mcp_server` and `tool` nodes.

## Install the hook configuration

First install ExecWeave so the console scripts are available:

```bash
python -m pip install -e ".[dev]"
```

Generate the settings fragment:

```bash
execweave-claude-hook --print-config
```

Merge the generated `hooks` object into one of Claude Code's supported JSON settings files:

- `~/.claude/settings.json` for user-wide hooks
- `.claude/settings.json` for a shareable project configuration
- `.claude/settings.local.json` for project-local configuration that should not be committed

Do not overwrite unrelated Claude Code settings when adding the fragment.

Claude Code's `/hooks` menu can be used to inspect which hooks are currently configured.

The adapter uses command hooks and is fail-open by default: a telemetry parsing or filesystem error is written to stderr but returns success so ExecWeave observability does not block an Agent tool call. `--strict` is available for debugging the hook itself, not as a runtime security policy.

## Recommended: one-command runtime + semantic recording

After the hooks are installed, use the run-bound workflow:

```bash
execweave-claude-record --open -- claude
```

On Linux, `--backend auto` still prefers the stronger `strace` backend when available. On macOS and Windows it uses the portable backend.

`execweave-claude-record` binds a sidecar path that is unique to this ExecWeave run **inside the dedicated CLI process**. Claude and its hook commands inherit that path, so two independently launched ExecWeave Claude-record processes do not need to guess which semantic sidecar belongs to which runtime capture.

If Claude emits semantic hook events, the run directory contains both raw and merged artifacts:

```text
.execweave/runs/<run-id>/
├── events.jsonl              # runtime evidence only
├── graph.json                # runtime-only graph
├── viewer.html               # runtime-only viewer
├── semantic.jsonl            # Claude hook semantic evidence only
├── events.semantic.jsonl     # validated merged stream
├── graph.semantic.json       # runtime + semantic graph
└── viewer.semantic.html      # runtime + semantic viewer
```

`--open` opens `viewer.semantic.html` when semantic evidence was observed. If the hooks are not installed or no supported hook event fires, ExecWeave reports `semantic_status: "no_events"` and falls back to the runtime-only viewer instead of guessing or failing the run.

Choose a directory explicitly if desired:

```bash
execweave-claude-record \
  --output-dir my-claude-run \
  --open \
  -- claude
```

The run-bound workflow preserves the original `events.jsonl`; semantic evidence is merged only into a separate `events.semantic.jsonl`.

## Standalone hook sidecar location

When `execweave-claude-hook` is used outside the run-bound recorder, each Claude session writes by default to:

```text
<cwd>/.execweave/semantic/claude/<Claude-session-id>.jsonl
```

The session ID is sanitized before it is used as a filename.

You can override this with either:

```text
EXECWEAVE_SEMANTIC_SIDECAR
```

or an explicit hook command such as:

```bash
execweave-claude-hook --sidecar /path/to/semantic.jsonl
```

For parallel standalone sessions, prefer the automatic session-scoped path instead of pointing multiple Claude sessions at one fixed sidecar.

## Advanced: manual merge

The generic semantic pipeline remains available when you already have a runtime capture and a semantic sidecar:

```bash
execweave semantic-merge \
  run.jsonl \
  semantic.jsonl \
  --output run.semantic.jsonl

execweave validate run.semantic.jsonl
execweave graph run.semantic.jsonl --output run.semantic.graph.json
execweave view run.semantic.graph.json --output run.semantic.html --open
```

The original runtime stream and semantic sidecar remain unchanged.

## Tool → Process boundary and correlation v0.1

Claude Code's command-hook input identifies the logical tool invocation (`tool_name`, `tool_use_id`, and tool input), but it does not provide the actual child process PID created by a Bash tool call.

Therefore the native adapter intentionally does **not** emit an observed relationship such as:

```text
Bash tool_call --SPAWNED_PROCESS--> process:1234
```

without additional evidence.

You may still see both semantic and OS evidence in the same merged graph:

```text
Claude Code --REQUESTED_TOOL_CALL--> Bash call --DECLARED_COMMAND--> "npm test"

session --LAUNCHED--> Claude process --SPAWNED--> shell/process ...
```

ExecWeave does not claim those paths are the same causal chain merely because their timestamps or command strings look similar.

When an explicit inferred bridge is useful, run:

```bash
execweave correlate run.semantic.jsonl \
  --output run.correlated.jsonl

execweave validate run.correlated.jsonl
execweave graph run.correlated.jsonl \
  --output run.correlated.graph.json
execweave view run.correlated.graph.json \
  --output run.correlated.html \
  --open
```

The v0.1 correlation stage is intentionally conservative:

- the search window is bounded and is clipped by the tool result or next declared tool call when available
- executable identity can be supported by exact executable/process/cmdline evidence
- canonical executable paths may resolve equivalent paths without using fuzzy name matching
- launcher processes may use an exact, non-empty, length-preserving `argv[1:]` match as a fallback
- a bridge is emitted only when exactly one process candidate survives
- ambiguous candidates emit no bridge
- unsupported compound shell commands and shell builtins emit no bridge
- no fuzzy version/name matching is used
- temporal proximity alone is never sufficient

A derived bridge is represented as:

```text
tool_call --CORRELATED_WITH_PROCESS--> process
```

and always carries semantics equivalent to:

```json
{
  "backend": "inference",
  "causal": false,
  "inferred": true,
  "inference_method": "...",
  "confidence": 0.8,
  "confidence_semantics": "heuristic_score_not_probability",
  "supporting_event_ids": ["..."]
}
```

The exact method and score depend on the supporting evidence. The confidence field is a heuristic score used to communicate evidence strength; it is explicitly **not a calibrated probability**.

The standalone Viewer renders inferred relationships separately from causal observed and non-causal observed edges, labels them `· inferred`, and exposes their evidence metadata when selected. An inferred bridge is never upgraded into observed process attribution.

## Privacy behavior

The native adapter intentionally avoids several high-risk payloads:

- `Write`/`Edit` file content is not persisted by the adapter
- `PostToolUse.tool_response` is not persisted
- only input key names are retained for generic tool-call metadata
- file-oriented tools retain the declared file path, not its contents
- Bash/PowerShell commands are retained because they are necessary for execution explanation, but command text is bounded to 4096 characters
- failure text is bounded to a short error summary

Paths and commands can still contain credentials, tokens, customer names, internal hostnames, or other sensitive information. Treat semantic sidecars as sensitive runtime metadata and review them before sharing.

## Evidence semantics

Edges produced directly by the Claude adapter include:

```json
{
  "backend": "semantic",
  "attribution": "claude_hook",
  "evidence_source": "provider_hook",
  "provider": "claude",
  "causal": false
}
```

`causal: false` does not mean the Claude hook was fabricated. It means a provider-level logical relationship is not being promoted to ExecWeave's stronger OS execution-attribution claim.

Correlation events are separate derived evidence with `backend: "inference"`, `inferred: true`, and `causal: false`. They do not modify the raw runtime or Claude hook evidence.

See [`Semantic Telemetry`](semantic-telemetry.md) for the generic merge contract and process-reference rules.