<!-- i18n-nav:start -->
<p align="center">
  <a href="codex-hooks.md">English</a> |
  <a href="codex-hooks.zh-TW.md">繁體中文</a> |
  <a href="codex-hooks.zh-CN.md">简体中文</a> |
  <strong>日本語</strong> |
  <a href="codex-hooks.ko.md">한국어</a> |
  <a href="codex-hooks.fr.md">Français</a> |
  <a href="codex-hooks.de.md">Deutsch</a> |
  <a href="codex-hooks.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# OpenAI Codex Lifecycle Hooks

ExecWeave は OpenAI Codex lifecycle hooks を provider-level semantic evidence として収集する native adapter を提供します。Hook は logical tool call と declared command を示せますが OS child PID は提供しないため、Tool → Process を直接 observed/causal として扱いません。

## Supported events

- `SessionStart`
- `PreToolUse`
- `PostToolUse`

`SessionStart` で model があれば `OpenAI Codex --USED_MODEL--> model`。

`PreToolUse` は `tool_use_id` を stable call identity とし：

```text
OpenAI Codex --REQUESTED_TOOL_CALL--> tool_call
tool_call --USES_TOOL--> tool
tool_call --DECLARED_COMMAND--> command   # Bash の場合
```

`PostToolUse` は neutral な：

```text
tool_call --TOOL_CALL_RETURNED--> tool
```

として記録します。現 payload では reliable success/failure discriminator が不足するため、`SUCCEEDED/FAILED` を推測しません。Raw `tool_response` content も保存しません。

## Setup

```bash
execweave-codex-hook --print-config
```

生成された hooks を Codex `hooks.json` に merge します。Adapter は default fail-open、`--strict` は debug 用です。

## Record

```bash
execweave-codex-record --open -- codex
```

Recorder は Codex child process に run-specific sidecar path を継承させ、runtime/semantic/correlated artifacts を分離して生成します。Hook event が無ければ runtime-only に fallback します。

```text
.events runtime only
semantic.jsonl provider evidence
.events.semantic merged observed evidence
events.correlated.jsonl derived inference
```

## Correlation

Declared `Bash` command と runtime evidence を比較し、unique candidate がある場合のみ：

```text
tool_call --CORRELATED_WITH_PROCESS--> process
```

を生成します。常に `inferred: true`, `causal: false`。Ambiguous/no-match/builtin/compound/unsupported は no edge です。Graph metadata の Correlation Summary で `matched / ambiguous / no match / unsupported` を区別できます。

Viewer の **observed only** は inferred edge を focus/layout 前に除外します。

## Privacy

保存するのは session/turn/model/tool/tool-use ID、input key names、declared Bash command、PostToolUse response type/length など必要な metadata です。Prompt、transcript content、raw tool response、file content、provider-derived child PID は収集しません。

## Upstream limitations

Codex hooks は進化中です。`PostToolUse` outcome signal は限定的で、`codex exec` や一部 Windows path に hook coverage gap が報告されています。これらは semantic coverage の制約であり、独立した OS runtime collector は引き続き動作します。

> Provider semantics は Agent が何をしようとしたか、OS telemetry は machine が何を観測したかを示します。両者をつなぐ場合も unique evidence に基づく explicit non-causal inference として扱います。

詳細は [`Semantic Telemetry`](semantic-telemetry.ja.md)。
