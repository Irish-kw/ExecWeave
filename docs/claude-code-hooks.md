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

First install ExecWeave so the console script is available:

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

## Sidecar location

By default each Claude session writes to its own file under the project working directory:

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

For parallel sessions, prefer the automatic session-scoped path instead of pointing multiple Claude sessions at one fixed sidecar.

## Build a combined graph

Capture OS runtime behavior normally:

```bash
execweave run --output run.jsonl -- claude
```

With the hooks enabled, Claude writes its semantic sidecar independently while the session runs.

Then merge the appropriate Claude sidecar into a **new** event stream:

```bash
execweave semantic-merge \
  run.jsonl \
  .execweave/semantic/claude/<Claude-session-id>.jsonl \
  --output run.semantic.jsonl

execweave validate run.semantic.jsonl
execweave graph run.semantic.jsonl --output run.semantic.graph.json
execweave view run.semantic.graph.json --output run.semantic.html --open
```

The original `run.jsonl` and Claude sidecar remain unchanged.

## Important Tool → Process limitation

Claude Code's command-hook input identifies the logical tool invocation (`tool_name`, `tool_use_id`, and tool input), but it does not provide the actual child process PID created by a Bash tool call.

Therefore the native adapter intentionally does **not** emit an exact relationship such as:

```text
Bash tool_call --SPAWNED_PROCESS--> process:1234
```

without additional evidence.

You may still see both semantic and OS evidence in the same merged graph:

```text
Claude Code --REQUESTED_TOOL_CALL--> Bash call --DECLARED_COMMAND--> "npm test"

session --LAUNCHED--> Claude process --SPAWNED--> shell/process ...
```

ExecWeave does not claim those paths are the same causal chain merely because their timestamps or command strings look similar. A future correlation layer may add explicit **inferred** bridges with a method/confidence field, but those must remain distinguishable from observed process attribution.

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

Edges produced by the current Claude adapter include:

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

See [`Semantic Telemetry`](semantic-telemetry.md) for the generic merge contract and process-reference rules.
