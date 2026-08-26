<!-- i18n-nav:start -->
<p align="center">
  <a href="semantic-telemetry.md">English</a> |
  <a href="semantic-telemetry.zh-TW.md">繁體中文</a> |
  <strong>简体中文</strong> |
  <a href="semantic-telemetry.ja.md">日本語</a> |
  <a href="semantic-telemetry.ko.md">한국어</a> |
  <a href="semantic-telemetry.fr.md">Français</a> |
  <a href="semantic-telemetry.de.md">Deutsch</a> |
  <a href="semantic-telemetry.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# Semantic Telemetry

ExecWeave 可以把 provider/framework 的 semantic events 与 OS runtime evidence 放进同一个 execution graph，同时保留「是哪一个 evidence source 证明了这条关系」。原始 runtime capture 不会被覆写。

```text
agent --REQUESTED_TOOL_CALL--> tool_call --USES_TOOL--> tool
                                                     |
                                                     +--DECLARED_COMMAND--> command

process --OPENED_READ--> file
process --CONNECTED_TO--> network_endpoint
```

Provider hook 说明的是「logical action 被要求执行什么」；runtime collector 说明的是「机器实际观察到什么」。ExecWeave 不会把时间接近直接变成 causal proof。

## Workflow

先收一般 runtime：

```bash
execweave run --output run.jsonl -- claude
```

Provider adapter/hook 写到独立 `semantic.jsonl` sidecar，再 merge 成**新的** event stream：

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

`run.jsonl` 永远不会被 `semantic-merge` 修改。

Claude Code / OpenAI Codex 的 run-bound recorder 已经把这个流程自动化：

```bash
execweave-claude-record --open -- claude
execweave-codex-record --open -- codex
```

## Sidecar record contract

一笔 semantic sidecar record 是一行 JSON：

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

Adapter 不必提供 ExecWeave `session_id`、`schema_version`、contiguous `sequence`；`event_id` 也可省略。`semantic-merge` 会注入 runtime session、使用目前 schema、依时间重排 body events、重新配置连续 sequence，保持 `session.started` 第一、`session.finished` 最后，并在 commit output 前验证整条 stream。

## 建议 semantic entities

| Type | Example ID | 意义 |
| --- | --- | --- |
| `agent` | `agent:Claude Code` | logical agent/client |
| `tool_call` | `tool-call:claude:session:tool-use-id` | 一次具体 tool invocation |
| `tool` | `tool:claude:Bash` | Agent 可见的 tool |
| `mcp_server` | `mcp-server:claude:github` | MCP server/integration |
| `model` | `model:claude:claude-sonnet` | provider 有提供时的 model identity |
| `command` | `command:sha256:...` | semantic hook 宣告的 command metadata |
| `process_reference` | `process-pid:1234` | 上游真的提供 PID 时才可使用的 bridge |

Entity ID 应足以在同一 run 内稳定 deduplicate semantic observations。

## Optional process-reference bridge

只有 provider/framework **真的知道 child PID** 时，才可产生 `process_reference`。

Merge 时 ExecWeave 会保守解析：

1. explicit `create_time` 可唯一识别 process；
2. PID 只有一个 runtime candidate 时直接解析；
3. PID reuse 时，可选出 semantic timestamp 之前唯一且最近的 creation time；
4. 否则保留 `process_reference` 并标记 `unresolved: true`，不硬猜。

**Provider 没有提供 PID 时，不要建立 `process_reference`。** Command string + nearby timestamp 不足以证明 exact Tool → Process relationship。

目前 Claude Code 与 Codex native hook 都遵守这个规则。

## Tool → Process conservative correlation

对没有 child PID、但 provider 有宣告 shell command 的情况，ExecWeave 可额外建立独立 derived stream：

```bash
execweave correlate run.semantic.jsonl \
  --output run.correlated.jsonl
```

只在 bounded window 内有**唯一且有明确 executable / argv evidence 支援**的 process candidate 时，才产生：

```text
tool_call --CORRELATED_WITH_PROCESS--> process
```

任何这类 edge 都是：

```text
inferred: true
causal: false
```

Ambiguous、no-match、shell builtin、compound command 或 unsupported call 都不产生 bridge。Heuristic confidence 不是 calibrated probability。

## Evidence / causality boundary

Provider adapter 直接产生的 semantic edge 即使可靠地表示 logical relationship，仍标 `causal: false`。在 ExecWeave 中，`causal: true` 保留给更强的 execution-level attribution。

因此：

```text
Claude Code --REQUESTED_TOOL_CALL--> Bash call       provider semantic evidence
process     --OPENED_READ---------> ~/.ssh/id_ed25519 OS runtime evidence
```

不能直接推导：

```text
Bash call --caused--> that exact process
file bytes --flowed to--> a network endpoint
```

Derived correlation 也必须清楚标示 method/confidence，并与 observed OS evidence 分开。

## Session boundary

每个 semantic timestamp 都必须落在 captured runtime session interval 内。超出 interval 的 event 会被拒绝，避免不同 run 的 provider telemetry 被错误合并。

## Privacy

Semantic sidecar 也可能包含敏感 metadata。Adapter 应优先保存 identifier 与 bounded metadata，而不是完整 prompt、tool argument、tool output、credential 或 secret。

Claude adapter 不保存 `Write/Edit` content 或 raw `tool_response`；Codex adapter 也不保存 prompt/transcript/raw response content。Shell command 因为是 execution explanation 的核心 evidence 会保留，但仍可能含 secret，分享前必须检查。

Provider-specific contract：

- [`Claude Code Hooks`](claude-code-hooks.zh-CN.md)
- [`OpenAI Codex Hooks`](codex-hooks.zh-CN.md)
