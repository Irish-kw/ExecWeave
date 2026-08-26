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

ExecWeave は provider/framework semantic events と OS runtime evidence を同じ graph に配置しながら、どの source が何を証明したかを分離します。Raw runtime capture は変更しません。

```text
agent --REQUESTED_TOOL_CALL--> tool_call --USES_TOOL--> tool
                                                     +--DECLARED_COMMAND--> command
process --OPENED_READ--> file
process --CONNECTED_TO--> network_endpoint
```

Provider hook は logical action、runtime collector は machine-level observation を説明します。Temporal proximity を causal proof に変換しません。

## Workflow

```bash
execweave run --output run.jsonl -- claude
execweave semantic-merge run.jsonl semantic.jsonl --output run.semantic.jsonl
execweave validate run.semantic.jsonl
execweave graph run.semantic.jsonl --output run.semantic.graph.json
```

`run.jsonl` は変更されません。Claude/Codex では run-bound recorder がこの flow を自動化します。

```bash
execweave-claude-record --open -- claude
execweave-codex-record --open -- codex
```

## Sidecar contract

Semantic sidecar は一行一 JSON object で、`timestamp`, `event_type`, `relation`, `source`, `target`, `attributes` を持ちます。ExecWeave の `session_id`, schema version, contiguous `sequence` は adapter が用意する必要はありません。Merge が session injection、timestamp ordering、sequence reassignment と validation を行います。

推奨 entity：`agent`, `tool_call`, `tool`, `mcp_server`, `model`, `command`, 必要時のみ `process_reference`。

## Process reference

Provider が実際に PID を提供した場合だけ `process_reference` を使えます。Create time / unique PID candidate で conservative に resolve し、ambiguous なら `unresolved: true` のままです。

**PID が無い provider から process reference を発明しません。** Command string と timestamp だけでは exact Tool → Process proof になりません。

## Conservative correlation

Declared shell command と bounded runtime evidence から、unique process candidate が一つだけ残る場合に限り：

```text
tool_call --CORRELATED_WITH_PROCESS--> process
```

を derived stream に追加できます。Edge は常に `inferred: true`, `causal: false`。Ambiguous/no-match/builtin/compound/unsupported call には bridge を作りません。Confidence は heuristic score であり probability ではありません。

## Evidence boundary

Provider semantic edge も通常 `causal: false` です。これは hook が信頼できないという意味ではなく、logical relationship を OS execution causality に upgrade しないという意味です。

```text
Agent --REQUESTED_TOOL_CALL--> Bash call
process --OPENED_READ--> file
```

だけでは、exact Tool→Process や file-byte→network flow を証明しません。

Semantic timestamp は captured runtime session interval 内でなければならず、別 run の event は merge されません。

## Privacy

Adapter は prompt、file content、raw tool output、credential などの高リスク payload を避け、identifier と bounded metadata を優先します。Shell command/path 自体は sensitive な場合があるため、共有前に確認してください。

Provider-specific docs：

- [`Claude Code Hooks`](claude-code-hooks.ja.md)
- [`OpenAI Codex Hooks`](codex-hooks.ja.md)
