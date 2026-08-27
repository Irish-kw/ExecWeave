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

ExecWeave は Codex lifecycle-hook evidence を独立した OS runtime telemetry と並べて記録します。Provider hook は logical Agent/tool activity を記述しますが、直接的な Tool → Process causality を主張するために必要な OS child PID は提供しません。

## 現在の hook surface

`execweave-codex-hook --print-config` は現在、次を登録します。

- `PreToolUse`
- `PermissionRequest`
- `PostToolUse`
- `PreCompact`
- `PostCompact`
- `SessionStart`
- `SessionEnd`
- `UserPromptSubmit`
- `SubagentStart`
- `SubagentStop`
- `Stop`
- `Interrupt`

未知または利用できない upstream event は作りません。Hook schema と dispatch coverage は Codex version により変わる可能性があります。

Hook を設定した後、次で run を記録します。

```bash
execweave-codex-hook --print-config
execweave-codex-record --open -- codex
```

Recorder は run-specific semantic sidecar を bind し、runtime、semantic、correlated artifact を分けて保持します。

## Full-fidelity content

v0.6.5 は Codex hook が実際に提供した完全な content value をローカル content-addressed store に保存し、JSONL sidecar には大きな inline copy ではなく reference を記録します。

観測可能な content には完全な `UserPromptSubmit.prompt`、`tool_input`、`PostToolUse.tool_response`、permission-request tool input、hook が提供する final assistant/subagent message が含まれます。Payload 内の application-level values は保存されるため、secret-redacted 済みだと仮定しないでください。

既知の transport credentials は adapter が認識する別の provider-metadata projection から除外されます。この処理は content payload 自体を書き換えたり sanitize したりしません。

`content_complete_from_source: true` は Codex integration point が提供した完全な値を保存したという意味です。ExecWeave が transcript file を読んだ、見えていない provider request を intercept した、hidden model state を観測したという意味ではありません。

## Tool identity と correlation

Codex が `tool_use_id` を提供する場合、ExecWeave はそれを logical tool-call identity として使用します。Declared command は provider semantic evidence のままです。Hook は child OS PID を提供しないため、Tool → Process bridge は conservative correlation stage が runtime evidence から唯一の supported candidate を見つけた場合だけ生成されます。

```text
inferred: true
causal: false
```

Ambiguous、unmatched、shell-builtin、compound、unsupported command は bridge を作りません。Timestamp や command string が似ているだけで provider evidence を OS attribution に昇格させません。

## Privacy と evidence boundary

Codex semantic/content artifact には prompt、command、tool argument/result、final response、path、identifier、application-level secrets が含まれる可能性があります。Run directory 全体を sensitive として扱い、共有前に確認してください。

Adapter はすべての Codex execution mode が完全な lifecycle coverage を公開すると主張しません。Missing hooks は semantic visibility を下げますが、独立した OS runtime collector は無効になりません。また provider hook だけでは declared command の実行、file action の発生、resources 間の byte flow を証明できません。
