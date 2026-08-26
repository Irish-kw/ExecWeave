<!-- i18n-nav:start -->
<p align="center">
  <a href="semantic-telemetry.md">English</a> |
  <a href="semantic-telemetry.zh-TW.md">繁體中文</a> |
  <a href="semantic-telemetry.zh-CN.md">简体中文</a> |
  <strong>日本語</strong> |
  <a href="semantic-telemetry.ko.md">한국어</a> |
  <a href="semantic-telemetry.fr.md">Français</a> |
  <a href="semantic-telemetry.de.md">Deutsch</a> |
  <a href="semantic-telemetry.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# Semantic Telemetry

ExecWeave は、元の runtime capture を書き換えることなく、provider/framework の semantic event と OS runtime evidence を組み合わせられます。

設計上の目標は、logical Agent/Tool/MCP evidence と machine-level の process/file/network evidence を同じ graph に配置しつつ、どの source が各 relationship を証明したのかを保持することです。

```text
agent --REQUESTED_TOOL_CALL--> tool_call --USES_TOOL--> tool
                                                     |
                                                     +--DECLARED_COMMAND--> command

process --OPENED_READ--> file
process --CONNECTED_TO--> network_endpoint
```

Provider hook は「どの logical action が要求されたか」を説明できます。Runtime collector は「machine が実際に何を観測したか」を説明します。ExecWeave は両者の temporal proximity を黙って causal proof に変換しません。

## Workflow

まず通常の ExecWeave run を capture します。

```bash
execweave run --output run.jsonl -- claude
```

Provider adapter または hook は、例えば `semantic.jsonl` のような別 semantic sidecar を書きます。

Sidecar を **新しい** validated event stream に merge します。

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

`run.jsonl` は `semantic-merge` によって変更されません。

## Sidecar record contract

Semantic sidecar record は 1 行 1 JSON object です。Adapter は semantic observation だけを供給します。

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

Sidecar は次を提供する必要がありません。

- ExecWeave `session_id`
- ExecWeave `schema_version`
- contiguous `sequence`
- `event_id`（optional。省略時は ExecWeave が生成）

`semantic-merge` は runtime session ID を注入し、現在の ExecWeave event schema を使い、semantic/runtime body event を timestamp 順に sort し、1 本の contiguous sequence を再割り当てし、`session.started` を先頭、`session.finished` を末尾に保ち、output file を commit する前に merged result を validate します。

## Recommended semantic entities

ExecWeave の generic entity schema は追加 node type をすでにサポートしています。

| Type | Example ID | Meaning |
| --- | --- | --- |
| `agent` | `agent:Claude Code` | Logical agent/client |
| `tool_call` | `tool-call:claude:session:tool-use-id` | 1 回の具体的な logical tool invocation |
| `tool` | `tool:claude:Bash` | Agent から見える tool |
| `mcp_server` | `mcp-server:claude:github` | MCP server/integration |
| `model` | `model:claude:claude-sonnet` | Provider が公開した場合の model identity |
| `command` | `command:sha256:...` | Semantic hook が宣言した command metadata |
| `process_reference` | `process-pid:1234` | Upstream source が実際に PID を提供した場合の optional bridge |

Entity ID は、1 run 内で repeated semantic observation を deduplicate できる程度に安定している必要があります。

## Optional process-reference bridge

一部の provider/framework adapter は child PID を知っていても、ExecWeave の完全な process entity ID を知らない場合があります。その場合、観測された PID を持つ `process_reference` を emit できます。

Merge 中、ExecWeave はこの reference を runtime stream で実際に観測された process entity に対して resolve します。Resolution は保守的です。

1. 明示的な `create_time` が process を一意に識別できる；
2. PID に runtime candidate が 1 つだけなら直接 resolve；
3. PID reuse がある場合、semantic timestamp より後ではない最新の process creation time が一意なら選択可能；
4. それ以外は推測せず `process_reference` を `unresolved: true` のまま保持。

Resolved event は元の reference から runtime process への mapping を `attributes.resolved_process_references` に記録します。

**Provider が PID を公開していない場合は `process_reference` を emit しないでください。** Command string と近い process timestamp だけでは exact Tool → Process relationship を主張できません。

現在の Claude Code native hook adapter はこのルールに従います。Claude の hook input は tool call を識別しますが child process PID を公開しないため、adapter は `tool_call --SPAWNED_PROCESS--> process` edge を捏造しません。

## Evidence and causality boundary

現在の provider adapter は、provider hook が logical tool event の発生を authoritative に報告した場合でも semantic edge を `causal: false` として mark します。ExecWeave では `causal: true` は、単に 2 つの logical object が関連しているという事実より強い execution-level attribution に予約されています。

そのため次の statement は分離されたままです。

```text
Claude Code --REQUESTED_TOOL_CALL--> Bash call       semantic provider evidence
process     --OPENED_READ---------> ~/.ssh/id_ed25519 OS runtime evidence
```

この 2 つの observation だけでは次を証明しません。

```text
Bash call --caused--> that exact process
file bytes --flowed to--> a network endpoint
```

将来の semantic/runtime correlation layer は method と confidence を明示的に公開し、observed OS attribution と区別可能なままでなければなりません。

## Session boundary

すべての semantic timestamp は captured runtime session interval 内に存在しなければなりません。Interval 外の event は reject されます。これにより無関係な provider telemetry が誤った execution に黙って attach されることを防ぎます。

## Privacy

ExecWeave 自体が file content を収集しなくても、semantic sidecar には sensitive metadata が含まれる可能性があります。Adapter author は full prompt、tool argument、tool output、credential、secret value より identifier と bounded metadata を優先すべきです。

Claude Code adapter は `Write` content や `tool_response` を意図的に保存しません。Declared shell command は execution explanation の中心であるため保持されますが、size は bounded であり sensitive metadata として扱う必要があります。

Generic semantic merge layer は provider-agnostic です。Provider-specific adapter は別 integration であり、どの upstream field を利用し、どの claim を支持するかを正確に document しなければなりません。

最初の native provider adapter については [`Claude Code Hooks`](claude-code-hooks.ja.md) を参照してください。
