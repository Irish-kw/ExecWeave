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

ExecWeave は Cursor の native hook surface を使って provider semantic/content evidence を run に追加し、その evidence を OS causality として扱いません。

## クイックスタート

```bash
execweave-cursor-hook --print-config
execweave-cursor-record --open -- cursor
```

Run-bound recorder は runtime、semantic、correlated artifact を別々に保持します。

## Observation surface

v0.6.5 hook configuration はより広い Cursor lifecycle surface をカバーします。Session start/end、tool before/after/failure、subagent、shell/MCP execution、file read/edit、prompt submission、compaction/stop、Agent response/thought、Cursor が公開する場合の tab file read/edit events が含まれます。

Cursor は tool hooks に stable logical tool-call identity を提供しますが、その identity は OS PID ではありません。

## Full-fidelity content

Cursor が content value を明示的に提供する場合、v0.6.5 は完全な supplied value をローカル content-addressed store に保存し、semantic JSONL event には reference のみを置きます。

Regression coverage には complete prompt text、tool input/output と failure text、shell command/output、MCP command/input/result、read hook が提供する file content、edit structures、final Agent responses、provider-labeled thought text、subagent summaries が含まれます。

これらは provider observation として保存され、evidence limitation も維持されます。たとえば `beforeReadFile` が提供する content は OS read completion を主張せず、edit structure は provider が実際に提供しない限り complete post-edit file snapshot を主張しません。

既知の transport credentials は定義された provider-metadata projection から除外されます。Content value に埋め込まれた secret は保存されます。Full-fidelity content は汎用 secret-redaction layer ではありません。

## Tool to process correlation

Cursor hook evidence は child OS PID を提供しません。したがって Shell call は独立 runtime evidence が唯一の supported candidate を示す場合だけ process bridge になります。

```text
inferred: true
causal: false
```

Ambiguous / unsupported call では bridge を作りません。Stable provider tool-call identity は Cursor 内部の logical identity を証明するだけで、machine-level process attribution ではありません。

## Privacy と evidence boundary

Cursor run evidence には prompt、tool arguments/results、shell output、file content、edit data、assistant responses、provider-labeled thought text、commands、paths、identifiers、MCP values、embedded application secrets が含まれる可能性があります。共有前に run directory 全体を確認してください。

Cursor hook は provider layer で Cursor が報告または提供した内容だけを証明します。それだけで declared command の実行、特定 process による file access、resources 間の byte flow を証明することはできません。
