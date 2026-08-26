# Cursor Hooks

<!-- i18n-nav:start -->
<p align="center">
  <a href="cursor-hooks.md">English</a> |
  <a href="cursor-hooks.zh-TW.md">繁體中文</a> |
  <a href="cursor-hooks.zh-CN.md">简体中文</a> |
  <strong>日本語</strong> |
  <a href="cursor-hooks.ko.md">한국어</a> |
  <a href="cursor-hooks.fr.md">Français</a> |
  <a href="cursor-hooks.de.md">Deutsch</a> |
  <a href="cursor-hooks.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

ExecWeave は Cursor のネイティブ Hook を利用し、Agent / Tool / Command の論理的なセマンティック証拠を実行グラフへ追加します。Provider metadata を OS レベルの因果証拠として扱うことはありません。

## クイックスタート

Hook 設定を生成して Cursor の hook settings に追加します。

```bash
execweave-cursor-hook --print-config
```

次に Cursor の実行を記録します。

```bash
execweave-cursor-record --open -- cursor
```

run-bound recorder は runtime、semantic、correlated artifacts を分離したまま保存します。

## イベント

現在の baseline は次を使用します。

- `sessionStart`
- `preToolUse`
- `postToolUse`
- `postToolUseFailure`

Cursor は安定した `tool_use_id` を提供するため、`preToolUse` と対応する post hook は同一の logical `tool_call` identity を正確に共有できます。

代表的な semantic edge：

```text
agent --USED_MODEL--> model
agent --REQUESTED_TOOL_CALL--> tool_call
tool_call --USES_TOOL--> tool
tool_call --DECLARED_COMMAND--> command
tool_call --DECLARED_TARGET--> file
tool_call --TOOL_CALL_RETURNED--> tool
```

`postToolUseFailure` は `TOOL_CALL_FAILED` として別に表現されます。

## Tool → Process correlation

Cursor Hook は OS child PID を提供しません。そのため Shell call を直接 process edge に変換しません。

Runtime evidence から一意に支持される process が独立に確認できた場合のみ、ExecWeave は次を派生できます。

```text
tool_call --CORRELATED_WITH_PROCESS--> process
```

この bridge は常に：

```text
inferred: true
causal: false
```

候補が曖昧、または未対応なら edge は作成しません。

## プライバシー境界

Adapter は prompt、transcript path、user email、agent message、tool output を保存しません。Model identity、conversation/generation IDs、tool name/use ID、command、declared file path など observability に必要な metadata のみ保持します。

Command や path 自体は機密情報になり得るため、artifact を共有する前に確認してください。

## Evidence boundary

Cursor Hook が証明するのは Cursor が semantic layer で報告した内容だけです。Declared command の実行、declared file の実アクセス、resource 間の data flow は証明しません。実際の runtime behavior は OS collector evidence が基準です。