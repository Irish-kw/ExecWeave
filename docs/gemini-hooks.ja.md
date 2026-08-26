<!-- i18n-nav:start -->
<p align="center">
  <a href="gemini-hooks.md">English</a> |
  <a href="gemini-hooks.zh-TW.md">繁體中文</a> |
  <a href="gemini-hooks.zh-CN.md">简体中文</a> |
  <strong>日本語</strong> |
  <a href="gemini-hooks.ko.md">한국어</a> |
  <a href="gemini-hooks.fr.md">Français</a> |
  <a href="gemini-hooks.de.md">Deutsch</a> |
  <a href="gemini-hooks.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# Gemini CLI Hooks

ExecWeave は Gemini CLI の lifecycle/tool hooks を provider semantic evidence として取り込み、独立して収集した OS runtime evidence と同じ execution graph に統合できます。

この adapter は意図的に保守的です。Gemini hook は Agent / Tool layer が報告した意味的な事実であり、それだけで特定の OS process が処理を実行したと証明するものではありません。

## 対応 hook events

現在は以下を取り込みます。

- `SessionStart`
- `BeforeTool`
- `AfterTool`

Gemini CLI は hook input を JSON として `stdin` に渡します。成功時の `stdout` は valid JSON である必要があるため、`execweave-gemini-hook` は成功時に `{}` だけを出力し、warning は `stderr` に書きます。

設定 fragment:

```bash
execweave-gemini-hook --print-config
```

出力された `hooks` object を Gemini CLI の `settings.json` に merge してください。生成設定は telemetry のみを行い、tool call を block / rewrite しません。

## One-command recording

```bash
execweave-gemini-record --open -- gemini
```

Recorder は `EXECWEAVE_SEMANTIC_SIDECAR` で今回の Gemini child process を run-specific sidecar に bind し、共通 provider-record pipeline を使用します。

```text
runtime evidence
      +
Gemini hook evidence
      ↓
validated semantic merge
      ↓
conservative correlation
      ↓
graph + viewer
```

Provider-integrated run では次の artifacts を生成できます。

```text
.execweave/runs/<run-id>/
├── events.jsonl
├── graph.json
├── viewer.html
├── semantic.jsonl
├── events.semantic.jsonl
├── graph.semantic.json
├── viewer.semantic.html
├── events.correlated.jsonl
├── graph.correlated.json
└── viewer.correlated.html
```

Raw runtime と provider sidecar evidence は分離したままです。Correlation は observed input evidence を書き換えるのではなく derived stream を生成します。

## Event mapping

### SessionStart

```text
Gemini CLI --STARTED_PROVIDER_SESSION--> provider_session
```

`transcript_path` が入力に含まれていても、ExecWeave は transcript を読み取ったりコピーしたりしません。

### BeforeTool

```text
Gemini CLI --REQUESTED_TOOL_CALL--> tool_call
tool_call --USES_TOOL--> tool
```

`run_shell_command` の `tool_input.command` は：

```text
tool_call --DECLARED_COMMAND--> command
```

として記録され、保守的な Tool → Process correlation に利用できます。

`read_file` / `write_file` / `replace` などでは declared target path を semantic metadata として記録できますが、file content は収集しません。

### MCP

`mcp_context` がある場合、provider が明示した server/tool identity を利用します。

```text
tool_call --VIA_MCP--> mcp_server
mcp_server --EXPOSES_TOOL--> tool
```

MCP launch command、arguments、URL は sensitive connection metadata や credential を含む可能性があるため artifact に保存しません。

### AfterTool

`AfterTool` は独立した `tool_result` observation として記録します。`tool_response.error` が non-empty の場合のみ provider-reported error を記録し、それ以外は neutral returned-result signal とします。

Raw `llmContent`、`returnDisplay`、error body は保存しません。

## Unique tool-call ID がないこと

現在の Gemini CLI hook schema には `BeforeTool` と `AfterTool` で共有できる unique tool-call ID がありません。

そのため ExecWeave は direct BeforeTool → AfterTool identity edge を生成しません。

`BeforeTool` は timestamp-scoped local identity を持ち、`AfterTool` は独立した result node になります。`tool_fingerprint` は診断 hint としてのみ利用し、call identity とは扱いません。同じ command の繰り返し実行を誤って一つにまとめないためです。

## Tool → Process correlation

Gemini hook は child OS PID を提供しません。独立 runtime evidence から bounded matcher が一意な process candidate を見つけた場合だけ：

```text
tool_call --CORRELATED_WITH_PROCESS--> process
```

を derived edge として生成できます。

常に：

```text
inferred: true
causal: false
```

です。Ambiguous / no-match / compound / shell builtin / unsupported call は edge を生成しません。

Correlated Viewer は matched / ambiguous / no-match / unsupported count を表示するため、missing edge が暗黙に「何も起きなかった」と解釈されることを防ぎます。

## Privacy

Prompt、transcript、raw tool result、raw error body、MCP command/args/URL、file content はデフォルトでは収集しません。一方、command、path、tool name、session identifier、MCP server/tool name などの metadata は機密情報になり得るため、artifact 共有前に確認してください。

## Failure behavior

`execweave-gemini-hook` はデフォルトで fail-open です。Telemetry error は `stderr` に出し、Gemini tool call を意図的に止めません。Non-zero failure が必要な場合のみ `--strict` を使用します。

## Upstream contract

- https://github.com/google-gemini/gemini-cli/blob/main/docs/hooks/reference.md
- https://github.com/google-gemini/gemini-cli/blob/main/docs/hooks/index.md

Provider hook schema は将来変化する可能性があります。ExecWeave は provider が実際に deliver した field のみを記録し、semantic hook が利用できない場合でも独立した OS runtime collection を有用なまま保ちます。

[`Semantic Telemetry`](semantic-telemetry.ja.md) も参照してください。
