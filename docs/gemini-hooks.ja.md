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

ExecWeave は Gemini CLI hook を provider semantic/content evidence として取り込み、独立して収集した OS runtime evidence と分離して保持します。Gemini hook は provider が明示的に公開した内容を説明しますが、それだけでどの OS process が action を実行したかを証明しません。

## 現在の hook surface

`execweave-gemini-hook --print-config` は現在、次を登録します。

- `SessionStart`
- `SessionEnd`
- `BeforeAgent`
- `AfterAgent`
- `BeforeModel`
- `AfterModel`
- `BeforeToolSelection`
- `BeforeTool`
- `AfterTool`
- `PreCompress`
- `Notification`

Tool hook は provider matcher surface を使い、生成される command hook はデフォルトで fail-open です。設定後は次で記録します。

```bash
execweave-gemini-hook --print-config
execweave-gemini-record --open -- gemini
```

## Full-fidelity content

v0.6.5 は Gemini hook が明示的に提供する完全な値をローカル content-addressed store に保存します。Event に応じて user prompt、完全な model request object、model response/chunk object、tool input、`llmContent` / `returnDisplay` / provider error fields を含む tool response、final Agent response、その他 hook が公開する provider payload values を含められます。

JSONL semantic sidecar には大きな値を inline せず content reference を保存します。同一 content は SHA-256 で deduplicate されます。

Provider-metadata projection は authorization header など認識済み transport-credential fields を除外しますが、full content 内の application-level values は sanitize しません。Tool input や model request に secret が埋め込まれていれば、その値も保存されます。

`content_complete_from_source: true` は受け取った field/value 全体を保存したという意味であり、Gemini が hidden final wire request、internal model state、hook payload にない stage を公開したという意味ではありません。

## Tool identity と correlation

Gemini は `BeforeTool` と `AfterTool` が共有する unique tool-call ID を提供しないため、ExecWeave は direct before/after identity edge を作りません。Deterministic tool fingerprint は diagnostic hint として残せますが、同一 call の繰り返しは別々の observations のままです。

Gemini hook は child OS PID も提供しません。そのため Tool → Process bridge は独立 runtime evidence が唯一の supported candidate を示す場合だけ導出されます。

```text
inferred: true
causal: false
```

Ambiguous、unmatched、compound、shell-builtin、unsupported command は bridge を作りません。

## Privacy と evidence boundary

Gemini content artifact には prompts、完全な model request/response values、tool inputs/results、tool が返す file content、MCP/application fields、final responses、identifiers、commands、paths、embedded secrets が含まれる可能性があります。Run directory 全体を sensitive として扱い、共有前に確認してください。

Hook が `transcript_path` を報告しただけで ExecWeave が自動的にその file を読むことはありません。保存された provider value も OS execution、completed file access、byte-level data flow を証明しません。独立 runtime evidence と明示的な correlation は別 layer のままです。
