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

# OpenAI Codex lifecycle hooks

ExecWeave は、OS runtime telemetry と同じ local run に provider-level semantic evidence を追加するための native OpenAI Codex lifecycle-hook adapter を提供します。

この integration は意図的に保守的です。Codex lifecycle hook は、どの logical tool call が要求されたか、shell execution ではどの command が宣言されたかを ExecWeave に伝えられます。ただし OS child PID は提供しないため、ExecWeave は provider hook 由来の Tool → Process attribution を directly observed または causal evidence として提示しません。

## Current support

ExecWeave は現在、次の Codex lifecycle event を使用します。

- `SessionStart`
- `PreToolUse`
- `PostToolUse`

Adapter は Codex が実際に deliver した hook だけを記録します。Unknown lifecycle event は推測せず無視します。

### `SessionStart`

Model name が存在する場合、ExecWeave は次を記録します。

```text
OpenAI Codex --USED_MODEL--> model
```

Adapter は transcript file の内容を読み取ったりコピーしたりしません。

### `PreToolUse`

ExecWeave は provider の `tool_use_id` を stable logical tool-call identity として使用します。

```text
OpenAI Codex --REQUESTED_TOOL_CALL--> tool_call
tool_call --USES_TOOL--> tool
```

Canonical Codex `Bash` hook tool では、string の `tool_input.command` があると次も生成します。

```text
tool_call --DECLARED_COMMAND--> command
```

Declared command は semantic provider evidence です。後続の conservative correlation には有用ですが、特定の OS process がその command を実行した証拠ではありません。

### `PostToolUse`

ExecWeave は現在 neutral な completion relation を記録します。

```text
tool_call --TOOL_CALL_RETURNED--> tool
```

`PostToolUse` を `TOOL_CALL_SUCCEEDED` または `TOOL_CALL_FAILED` に意図的に変換しません。現在の Codex hook payload は、その claim を安全に行うのに十分 reliable な success/failure discriminator を提供していません。

ExecWeave は raw `tool_response` を semantic telemetry に保存しません。String response については response type と character count だけを保存します。

## Configure Codex

ExecWeave をインストールした後、対応している lifecycle-hook configuration fragment を生成します。

```bash
execweave-codex-hook --print-config
```

出力された `hooks` object を Codex の `hooks.json` configuration に merge してください。

生成される configuration は `SessionStart`、`PreToolUse`、`PostToolUse` に `execweave-codex-hook` を登録します。

Hook adapter はデフォルトで fail-open です。Telemetry problem は warning を表示しますが、Codex を意図的に block しません。Adapter 自体を debug する場合は：

```bash
execweave-codex-hook --strict
```

## Record one Codex run

Codex が hook を invoke するよう設定した後：

```bash
execweave-codex-record --open -- codex
```

`execweave-codex-record` は Codex configuration を変更しません。Inherited environment variable を使って child Codex process を run-specific semantic sidecar に bind するだけです。

Lifecycle hook が発火すると、run directory には layered artifact が含まれます。

```text
.execweave/runs/<run-id>/
├── events.jsonl              # runtime evidence only
├── graph.json                # runtime-only graph
├── viewer.html               # runtime-only viewer
├── semantic.jsonl            # Codex lifecycle-hook evidence only
├── events.semantic.jsonl     # validated runtime + semantic stream
├── graph.semantic.json       # runtime + semantic graph
├── viewer.semantic.html      # runtime + semantic viewer
├── events.correlated.jsonl   # derived stream; observed evidence unchanged
├── graph.correlated.json     # graph with inferred bridges + correlation metadata
└── viewer.correlated.html    # viewer with correlation summary
```

Codex hook event が届かない場合、recorder は安全に runtime-only artifact へ fallback します。

## Tool → Process correlation

次のような `Bash` declaration の場合：

```text
tool_call --DECLARED_COMMAND--> "python task.py"
```

ExecWeave はその semantic declaration を bounded runtime process evidence と比較できます。既存の conservative matcher により 1 つの process candidate だけが一意に support された場合のみ、次を emit します。

```text
tool_call --CORRELATED_WITH_PROCESS--> process
```

そのような bridge は常に：

```text
inferred: true
causal: false
```

のままです。

Ambiguous、unmatched、shell-builtin、compound、その他 unsupported な call では bridge を生成しません。Correlated graph は run-level correlation summary を保持するため、Viewer はすべての missing edge を同じものとして扱わず、`matched`、`ambiguous`、`no match`、`unsupported` を区別できます。

Viewer には **observed only** もあり、focus traversal と layout の前に inferred edge を除去します。

## Evidence and privacy boundary

ExecWeave の Codex adapter は graph construction に必要な semantic metadata を現在保存します。

- Codex session ID
- 提供された場合の turn ID
- model name
- tool name
- tool-use ID
- input key name
- declared `Bash` command
- `PostToolUse` の response type / response length

意図的に収集しないもの：

- prompt text
- transcript-file contents
- raw `tool_response` contents
- file contents
- provider-derived Tool → Process PID

Command には secret や sensitive path が含まれる可能性があります。Artifact を共有する前に review してください。

## Current upstream limitations

Codex lifecycle hook は進化中です。そのため ExecWeave はこの integration を native semantic adapter として扱い、すべての Codex execution mode が完全な lifecycle coverage を公開する証拠とは扱いません。

Known constraint：

1. `PostToolUse` は現在 reliable な success/failure signal を ExecWeave に与えないため、relation は neutral な `TOOL_CALL_RETURNED` です。
2. 一部の `codex exec` path では lifecycle-hook dispatch に最近 gap がありました。Lifecycle-hook telemetry の初期 target としては interactive Codex CLI の方が安全です。
3. 一部の Windows command-execution path でも hook-coverage gap が報告されています。
4. Provider hook は directly observed Tool → Process attribution に必要な OS child PID を提供しません。

これらの limitation は semantic coverage に影響しますが、独立した OS runtime collector には影響しません。Provider hook が一切発火しなくても runtime evidence は利用できます。

## Design rule

Codex integration は ExecWeave の他部分と同じ evidence rule に従います。

> Provider semantics は Agent が何をしていると述べたかを説明し、OS telemetry は machine が実際に何を観測したかを説明します。両者の correlation は evidence が unique な場合にのみ、explicit な non-causal inference として接続できます。
