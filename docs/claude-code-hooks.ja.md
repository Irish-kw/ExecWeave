<!-- i18n-nav:start -->
<p align="center">
  <a href="claude-code-hooks.md">English</a> |
  <a href="claude-code-hooks.zh-TW.md">繁體中文</a> |
  <a href="claude-code-hooks.zh-CN.md">简体中文</a> |
  <strong>日本語</strong> |
  <a href="claude-code-hooks.ko.md">한국어</a> |
  <a href="claude-code-hooks.fr.md">Français</a> |
  <a href="claude-code-hooks.de.md">Deutsch</a> |
  <a href="claude-code-hooks.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# Claude Code Hooks

ExecWeave には Claude Code command-hook adapter が組み込まれており、provider の semantic/content evidence をローカル sidecar に記録し、独立した OS runtime evidence と分離して保持します。Provider hook は Claude Code が明示的に公開した内容を説明しますが、portable / Linux `strace` collector の代替ではなく、hook だけで OS process causality を証明しません。

**現在の hook surface。** `execweave-claude-hook --print-config` は現在、次を登録します。

- `SessionStart`
- `UserPromptSubmit`
- `MessageDisplay`
- `PreToolUse`
- `PostToolUse`
- `PostToolUseFailure`
- `PostToolBatch`
- `SubagentStart`
- `SubagentStop`
- `Stop`
- `StopFailure`

Hook はデフォルトで fail-open です。telemetry/storage error は報告されますが、Agent operation を意図的に停止しません。デバッグ時に telemetry failure を non-zero にしたい場合は `--strict` を使用します。

## 設定と記録

ExecWeave をインストールし、対応 settings fragment を生成して Claude Code settings に merge した後、run-bound recorder を使用します。

```bash
execweave-claude-hook --print-config
execweave-claude-record --open -- claude
```

`execweave-claude-record` は child environment を通じて run ごとに固有の semantic sidecar を bind します。Runtime、semantic、correlated evidence は別 artifact のままです。

```text
runtime evidence
    ↓ semantic merge
runtime + semantic evidence
    ↓ conservative correlation
runtime + semantic + inferred correlation
```

対応する Claude hook event が届かなければ runtime-only artifact に fallback します。Semantic evidence があっても、唯一かつ十分に支持された Tool → Process candidate がなければ bridge は作りません。

## v0.6.5 の full-fidelity content

Claude adapter は bounded metadata summary だけに制限されません。Hook が content を明示的に提供した場合、v0.6.5 は source から提供された完全な値をローカル SHA-256 content-addressed store に保存し、semantic sidecar には reference を記録します。

Regression coverage には以下が含まれます。

- 大きな値を含む完全な `UserPromptSubmit.prompt`；
- `Write`/`Edit` content と input object 内の application-level value を含む完全な tool input；
- 提供された場合の完全な structured `PostToolUse.tool_response`；
- `PostToolBatch` から提供される model-visible tool-result serialization；
- ordering metadata とともに提供される `MessageDisplay` assistant text/delta；
- stop event から提供される main Agent / subagent の最終 assistant message。

既知の transport credential は adapter が認識する別の provider-metadata projection からのみ除外されます。この処理は full content 自体を sanitize しません。Prompt、tool input、file body、tool result、assistant message に secret が含まれていれば、その secret も full-fidelity evidence として保存されます。

`content_complete_from_source: true` は Claude hook が提供した値を ExecWeave が完全に保存したという意味です。Hook が提供していない transcript、hidden model state、payload に存在しない provider stage を観測したという意味ではありません。

## Logical entities と tool identity

Claude hook event は、たとえば次の provider-level relationship を作成できます。

```text
Claude Code --REQUESTED_TOOL_CALL--> tool_call
tool_call --USES_TOOL-------------> tool
tool_call --DECLARED_COMMAND------> command
tool_call --DECLARED_TARGET-------> file metadata
tool_call --VIA_MCP---------------> mcp_server
Claude Code --SPAWNED_SUBAGENT----> subagent
```

`tool_use_id` は logical tool invocation を識別できますが OS PID ではありません。Provider の `mcp__<server>__<tool>` naming convention に一致する MCP 名は、利用可能な場合に独立した MCP-server/tool entity へ正規化されます。

## Tool → Process correlation boundary

Claude command-hook input は Bash/PowerShell tool invocation が実際に作成した child process PID を提供しません。そのため ExecWeave は provider hook data だけから observed causal process edge を作りません。

Bounded runtime matcher が唯一の supported process candidate を見つけた場合のみ、derived bridge を作成できます。

```text
tool_call --CORRELATED_WITH_PROCESS--> process
```

この bridge は常に次の意味を保ちます。

```json
{
  "causal": false,
  "inferred": true,
  "confidence_semantics": "heuristic_score_not_probability"
}
```

Temporal proximity だけでは不十分です。Ambiguous candidate、unsupported compound command、shell builtin、unmatched declaration は bridge を生成しません。Inference が observed process attribution に昇格することはありません。

## Layered artifacts

Run-bound Claude capture は次のような artifact を生成できます。

```text
.execweave/runs/<run-id>/
├── events.jsonl
├── graph.json
├── viewer.html
├── semantic.jsonl
├── content/sha256/...
├── events.semantic.jsonl
├── graph.semantic.json
├── viewer.semantic.html
├── events.correlated.jsonl
├── graph.correlated.json
└── viewer.correlated.html
```

Correlation は元の runtime/provider evidence を書き換えません。

## Standalone sidecar

Run-bound recorder の外では、Claude sidecar はデフォルトで session 単位です。

```text
<cwd>/.execweave/semantic/claude/<Claude-session-id>.jsonl
```

`EXECWEAVE_SEMANTIC_SIDECAR` または `--sidecar` で上書きできます。Parallel capture では session/run-specific path を推奨します。

## Privacy と evidence boundary

Claude full-fidelity artifact には prompt、command、file path、`Write`/`Edit` body、tool argument/result、assistant text、subagent response、identifier、application-level secret が含まれる可能性があります。Run directory 全体を sensitive data として扱い、共有前に確認してください。

Provider content は provider evidence のままです。保存された tool input は tool 実行を証明せず、保存された file body は特定 OS process の read/write を証明せず、保存された tool result は byte-level data flow を証明しません。より強い claim には OS collector と明示的にマークされた correlation evidence が必要です。

## 手動 merge と correlation

Runtime と semantic file が既にある場合、generic pipeline を利用できます。

```bash
execweave semantic-merge run.jsonl semantic.jsonl --output run.semantic.jsonl
execweave validate run.semantic.jsonl
execweave correlate run.semantic.jsonl --output run.correlated.jsonl
execweave validate run.correlated.jsonl
```

Generic evidence/content contract と process-reference rule は [`Semantic Telemetry`](semantic-telemetry.ja.md) を参照してください。
