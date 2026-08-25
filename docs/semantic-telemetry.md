<!-- i18n-nav:start -->
<p align="center">
  <strong>English</strong> |
  <a href="semantic-telemetry.zh-TW.md">繁體中文</a> |
  <a href="semantic-telemetry.zh-CN.md">简体中文</a> |
  <a href="semantic-telemetry.ja.md">日本語</a> |
  <a href="semantic-telemetry.ko.md">한국어</a>
</p>
<!-- i18n-nav:end -->

# Semantic Telemetry

ExecWeave can combine provider/framework semantic events with OS runtime evidence without rewriting the original runtime capture.

The design goal is to place logical Agent/Tool/MCP evidence and machine-level process/file/network evidence in the same graph while preserving which source proved each relationship.

```text
agent --REQUESTED_TOOL_CALL--> tool_call --USES_TOOL--> tool
                                                     |
                                                     +--DECLARED_COMMAND--> command

process --OPENED_READ--> file
process --CONNECTED_TO--> network_endpoint
```

A provider hook can explain *which logical action was requested*. The runtime collector explains *what the machine actually did*. ExecWeave does not silently turn temporal proximity between the two into causal proof.

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
  "relation": "REQUESTED_TOOL_CALL",
  "source": {
    "type": "agent",
    "id": "agent:Claude Code",
    "name": "Claude Code",
    "attributes": {}
  },
  "target": {
    "type": "tool_call",
    "id": "tool-call:provider:session:call-id",
    "name": "Bash",
    "attributes": {}
  },
  "attributes": {
    "attribution": "provider_hook",
    "evidence_source": "provider_hook",
    "causal": false
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

ExecWeave's generic entity schema already supports additional node types.

| Type | Example ID | Meaning |
| --- | --- | --- |
| `agent` | `agent:Claude Code` | Logical agent/client |
| `tool_call` | `tool-call:claude:session:tool-use-id` | One concrete logical tool invocation |
| `tool` | `tool:claude:Bash` | Agent-visible tool |
| `mcp_server` | `mcp-server:claude:github` | MCP server/integration |
| `model` | `model:claude:claude-sonnet` | Model identity when the provider exposes it |
| `command` | `command:sha256:...` | Declared command metadata from a semantic hook |
| `process_reference` | `process-pid:1234` | Optional bridge when an upstream source actually provides a PID |

Entity IDs should be stable enough to deduplicate repeated semantic observations inside one run.

## Optional process-reference bridge

Some provider/framework adapters may know a child PID but not ExecWeave's full process entity ID. In that case they may emit a `process_reference` with the observed PID.

During merge, ExecWeave resolves such references against process entities actually observed in the runtime stream. Resolution is conservative:

1. an explicit `create_time` can uniquely identify the process;
2. a PID with one runtime candidate resolves directly;
3. for PID reuse, ExecWeave may choose the unique latest process creation time not after the semantic timestamp;
4. otherwise the node remains `process_reference` with `unresolved: true` instead of guessing.

A resolved event records the original-to-runtime process mapping in `attributes.resolved_process_references`.

**Do not emit a `process_reference` when the provider did not expose a PID.** A command string and nearby process timestamp are not enough to claim an exact Tool → Process relationship.

The current Claude Code native hook adapter follows this rule: Claude's hook input identifies tool calls but does not expose the child process PID, so the adapter does not invent `tool_call --SPAWNED_PROCESS--> process` edges.

## Evidence and causality boundary

Current provider adapters mark semantic edges `causal: false` even when a provider hook authoritatively reports that a logical tool event occurred. In ExecWeave, `causal: true` is reserved for stronger execution-level attribution rather than merely saying that two logical objects are related.

This keeps statements such as these separate:

```text
Claude Code --REQUESTED_TOOL_CALL--> Bash call       semantic provider evidence
process     --OPENED_READ---------> ~/.ssh/id_ed25519 OS runtime evidence
```

Those two observations do **not** by themselves prove:

```text
Bash call --caused--> that exact process
file bytes --flowed to--> a network endpoint
```

Any future semantic/runtime correlation layer must expose its method and confidence explicitly and must remain distinguishable from observed OS attribution.

## Session boundary

Every semantic timestamp must fall inside the captured runtime session interval. Events outside that interval are rejected. This prevents unrelated provider telemetry from being silently attached to the wrong execution.

## Privacy

Semantic sidecars can contain sensitive metadata even when ExecWeave itself does not collect file contents. Adapter authors should prefer identifiers and bounded metadata over full prompts, tool arguments, tool output, credentials, or secret values.

The Claude Code adapter intentionally does not persist `Write` content or `tool_response`. Declared shell commands are retained because they are central to execution explanation, but are bounded in size and should still be treated as potentially sensitive metadata.

The generic semantic merge layer is provider-agnostic. Provider-specific adapters are separate integrations and must document exactly which upstream fields they consume and what claims those fields support.

See [`Claude Code Hooks`](claude-code-hooks.md) for the first native provider adapter.
