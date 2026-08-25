# Semantic Telemetry

ExecWeave can combine provider/framework semantic events with OS runtime evidence without rewriting the original runtime capture.

The design goal is a graph such as:

```text
agent --CALLED_TOOL--> tool --SPAWNED_PROCESS--> process --OPENED_READ--> file
  |
  +--CALLED_MCP-----> mcp_server
```

The semantic layer explains *which logical Agent/Tool/MCP action was requested*. The runtime layer explains *what the machine actually did*. ExecWeave keeps those evidence sources distinguishable instead of treating framework intent as OS truth.

## Workflow

First capture a normal ExecWeave run:

```bash
execweave run --output run.jsonl -- claude
```

A provider adapter or hook writes a separate semantic sidecar, for example `semantic.jsonl`.

Merge the sidecar into a **new** validated event stream:

```bash
execweave semantic-merge run.jsonl semantic.jsonl \
  --output run.semantic.jsonl

execweave validate run.semantic.jsonl
execweave graph run.semantic.jsonl \
  --output run.semantic.graph.json
execweave view run.semantic.graph.json \
  --output run.semantic.html \
  --open
```

`run.jsonl` is never modified by `semantic-merge`.

## Sidecar record contract

A semantic sidecar record is one JSON object per line. The adapter supplies only the semantic observation:

```json
{
  "timestamp": "2026-08-25T10:00:02.123Z",
  "event_type": "semantic.tool.called",
  "relation": "CALLED_TOOL",
  "source": {
    "type": "agent",
    "id": "agent:Claude Code",
    "name": "Claude Code",
    "attributes": {}
  },
  "target": {
    "type": "tool",
    "id": "tool:claude-code:Bash",
    "name": "Bash",
    "attributes": {
      "provider": "claude-code"
    }
  },
  "attributes": {
    "attribution": "provider_hook",
    "causal": true
  }
}
```

The sidecar does **not** need to provide:

- ExecWeave `session_id`
- ExecWeave `schema_version`
- contiguous `sequence`
- `event_id` (optional; ExecWeave creates one when omitted)

`semantic-merge` injects the runtime session ID, uses the current ExecWeave event schema, sorts semantic/runtime body events by timestamp, reassigns one contiguous sequence, keeps `session.started` first and `session.finished` last, and validates the merged result before committing the output file.

## Recommended semantic entities

ExecWeave's generic entity schema already supports additional node types. Current recommended semantic types are:

| Type | Example ID | Meaning |
| --- | --- | --- |
| `agent` | `agent:Claude Code` | Logical agent/client |
| `tool` | `tool:claude-code:Bash` | Agent-visible tool |
| `mcp_server` | `mcp:github` | MCP server/integration |
| `model` | `model:anthropic:claude-sonnet` | Model identity when the adapter can observe it |
| `process_reference` | `process-pid:1234` | Temporary bridge from semantic telemetry to an OS process |

Entity IDs should be stable enough to deduplicate repeated semantic observations inside one run.

## Tool-to-process bridge

Provider hooks frequently know a PID but not ExecWeave's full process entity ID. Emit a `process_reference`:

```json
{
  "timestamp": "2026-08-25T10:00:02.456Z",
  "event_type": "semantic.tool.process",
  "relation": "SPAWNED_PROCESS",
  "source": {
    "type": "tool",
    "id": "tool:claude-code:Bash",
    "name": "Bash",
    "attributes": {}
  },
  "target": {
    "type": "process_reference",
    "id": "process-pid:1234",
    "name": "1234",
    "attributes": {
      "pid": 1234
    }
  },
  "attributes": {
    "attribution": "provider_hook",
    "causal": true
  }
}
```

During merge, ExecWeave resolves this reference against process entities actually observed in the runtime stream.

Resolution is conservative:

1. an explicit `create_time` can uniquely identify the process;
2. a PID with one runtime candidate resolves directly;
3. for PID reuse, ExecWeave may choose the unique latest process creation time not after the semantic timestamp;
4. otherwise the node remains `process_reference` with `unresolved: true` instead of guessing.

A resolved event records the original-to-runtime process mapping in `attributes.resolved_process_references`.

## MCP example

```json
{
  "timestamp": "2026-08-25T10:00:03Z",
  "event_type": "semantic.mcp.called",
  "relation": "CALLED_MCP",
  "source": {
    "type": "agent",
    "id": "agent:Claude Code",
    "name": "Claude Code",
    "attributes": {}
  },
  "target": {
    "type": "mcp_server",
    "id": "mcp:github",
    "name": "GitHub MCP",
    "attributes": {}
  },
  "attributes": {
    "attribution": "provider_hook",
    "causal": true
  }
}
```

Adapters may add more attributes such as tool-call IDs, provider names, model IDs, MCP tool names, or request/result metadata. Avoid storing secrets or full prompt/tool payloads by default.

## Causality boundary

`semantic-merge` does **not** default semantic events to `causal: true`.

The adapter must decide what its source can actually prove. Examples:

- an authoritative provider hook saying a tool invocation occurred can reasonably mark `agent --CALLED_TOOL--> tool` as causal;
- a timestamp-only guess that a tool caused a process should stay non-causal or omit `causal`;
- OS file/network edges keep their original collector attribution and causality.

Semantic intent is not treated as proof that a file was read, a socket was opened, or bytes were exfiltrated.

## Session boundary

Every semantic timestamp must fall inside the captured runtime session interval. Events outside that interval are rejected. This prevents unrelated provider telemetry from being silently attached to the wrong execution.

## Privacy

Semantic sidecars can contain sensitive data even when ExecWeave itself does not collect file contents. Adapter authors should prefer identifiers and small metadata over full prompts, tool arguments, tool output, credentials, or secret values.

The generic semantic merge layer is provider-agnostic. Provider-specific adapters are separate integrations and should document exactly which upstream fields they consume and what causal guarantees those fields support.
