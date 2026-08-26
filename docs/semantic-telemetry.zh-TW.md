<!-- i18n-nav:start -->
<p align="center">
  <a href="semantic-telemetry.md">English</a> |
  <strong>繁體中文</strong> |
  <a href="semantic-telemetry.zh-CN.md">简体中文</a> |
  <a href="semantic-telemetry.ja.md">日本語</a> |
  <a href="semantic-telemetry.ko.md">한국어</a> |
  <a href="semantic-telemetry.fr.md">Français</a> |
  <a href="semantic-telemetry.de.md">Deutsch</a> |
  <a href="semantic-telemetry.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# Semantic Telemetry

ExecWeave 可以把 provider/framework 的 semantic events 與 OS runtime evidence 放進同一個 execution graph，同時保留「是哪一個 evidence source 證明了這條關係」。原始 runtime capture 不會被覆寫。

```text
agent --REQUESTED_TOOL_CALL--> tool_call --USES_TOOL--> tool
                                                     |
                                                     +--DECLARED_COMMAND--> command

process --OPENED_READ--> file
process --CONNECTED_TO--> network_endpoint
```

Provider hook 說明的是「logical action 被要求執行什麼」；runtime collector 說明的是「機器實際觀察到什麼」。ExecWeave 不會把時間接近直接變成 causal proof。

## Workflow

先收一般 runtime：

```bash
execweave run --output run.jsonl -- claude
```

Provider adapter/hook 寫到獨立 `semantic.jsonl` sidecar，再 merge 成**新的** event stream：

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

`run.jsonl` 永遠不會被 `semantic-merge` 修改。

Claude Code / OpenAI Codex 的 run-bound recorder 已經把這個流程自動化：

```bash
execweave-claude-record --open -- claude
execweave-codex-record --open -- codex
```

## Sidecar record contract

一筆 semantic sidecar record 是一行 JSON：

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

Adapter 不必提供 ExecWeave `session_id`、`schema_version`、contiguous `sequence`；`event_id` 也可省略。`semantic-merge` 會注入 runtime session、使用目前 schema、依時間重排 body events、重新配置連續 sequence，保持 `session.started` 第一、`session.finished` 最後，並在 commit output 前驗證整條 stream。

## 建議 semantic entities

| Type | Example ID | 意義 |
| --- | --- | --- |
| `agent` | `agent:Claude Code` | logical agent/client |
| `tool_call` | `tool-call:claude:session:tool-use-id` | 一次具體 tool invocation |
| `tool` | `tool:claude:Bash` | Agent 可見的 tool |
| `mcp_server` | `mcp-server:claude:github` | MCP server/integration |
| `model` | `model:claude:claude-sonnet` | provider 有提供時的 model identity |
| `command` | `command:sha256:...` | semantic hook 宣告的 command metadata |
| `process_reference` | `process-pid:1234` | 上游真的提供 PID 時才可使用的 bridge |

Entity ID 應足以在同一 run 內穩定 deduplicate semantic observations。

## Optional process-reference bridge

只有 provider/framework **真的知道 child PID** 時，才可產生 `process_reference`。

Merge 時 ExecWeave 會保守解析：

1. explicit `create_time` 可唯一識別 process；
2. PID 只有一個 runtime candidate 時直接解析；
3. PID reuse 時，可選出 semantic timestamp 之前唯一且最近的 creation time；
4. 否則保留 `process_reference` 並標記 `unresolved: true`，不硬猜。

**Provider 沒有提供 PID 時，不要建立 `process_reference`。** Command string + nearby timestamp 不足以證明 exact Tool → Process relationship。

目前 Claude Code 與 Codex native hook 都遵守這個規則。

## Tool → Process conservative correlation

對沒有 child PID、但 provider 有宣告 shell command 的情況，ExecWeave 可額外建立獨立 derived stream：

```bash
execweave correlate run.semantic.jsonl \
  --output run.correlated.jsonl
```

只在 bounded window 內有**唯一且有明確 executable / argv evidence 支援**的 process candidate 時，才產生：

```text
tool_call --CORRELATED_WITH_PROCESS--> process
```

任何這類 edge 都是：

```text
inferred: true
causal: false
```

Ambiguous、no-match、shell builtin、compound command 或 unsupported call 都不產生 bridge。Heuristic confidence 不是 calibrated probability。

## Evidence / causality boundary

Provider adapter 直接產生的 semantic edge 即使可靠地表示 logical relationship，仍標 `causal: false`。在 ExecWeave 中，`causal: true` 保留給更強的 execution-level attribution。

因此：

```text
Claude Code --REQUESTED_TOOL_CALL--> Bash call       provider semantic evidence
process     --OPENED_READ---------> ~/.ssh/id_ed25519 OS runtime evidence
```

不能直接推導：

```text
Bash call --caused--> that exact process
file bytes --flowed to--> a network endpoint
```

Derived correlation 也必須清楚標示 method/confidence，並與 observed OS evidence 分開。

## Session boundary

每個 semantic timestamp 都必須落在 captured runtime session interval 內。超出 interval 的 event 會被拒絕，避免不同 run 的 provider telemetry 被錯誤合併。

## Privacy

Semantic sidecar 也可能包含敏感 metadata。Adapter 應優先保存 identifier 與 bounded metadata，而不是完整 prompt、tool argument、tool output、credential 或 secret。

Claude adapter 不保存 `Write/Edit` content 或 raw `tool_response`；Codex adapter 也不保存 prompt/transcript/raw response content。Shell command 因為是 execution explanation 的核心 evidence 會保留，但仍可能含 secret，分享前必須檢查。

Provider-specific contract：

- [`Claude Code Hooks`](claude-code-hooks.zh-TW.md)
- [`OpenAI Codex Hooks`](codex-hooks.zh-TW.md)
