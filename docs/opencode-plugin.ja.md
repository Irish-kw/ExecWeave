# OpenCode Plugin

<!-- i18n-nav:start -->
<p align="center">
  <a href="opencode-plugin.md">English</a> |
  <a href="opencode-plugin.zh-TW.md">繁體中文</a> |
  <a href="opencode-plugin.zh-CN.md">简体中文</a> |
  <strong>日本語</strong> |
  <a href="opencode-plugin.ko.md">한국어</a> |
  <a href="opencode-plugin.fr.md">Français</a> |
  <a href="opencode-plugin.de.md">Deutsch</a> |
  <a href="opencode-plugin.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

ExecWeave は project-local plugin を通じて OpenCode と統合します。OpenCode は `tool.execute.before` と `tool.execute.after` の両方で正確な `sessionID + callID` を提供するため、同一の logical tool call を heuristic でペアリングする必要がありません。

## インストール

現在のプロジェクトへ生成済み plugin をインストールします。

```bash
execweave-opencode-plugin --install
```

次のファイルが作成されます。

```text
.opencode/plugins/execweave.ts
```

OpenCode はこのディレクトリの project plugin を自動ロードします。既存ファイルがある場合、ExecWeave は `--force` が明示されない限り上書きしません。

次に実行を記録します。

```bash
execweave-opencode-record --open -- opencode
```

## 取得する semantic evidence

現在の baseline が送信する metadata は最小限です。

- `chat.message`
- `tool.execute.before`
- `tool.execute.after`

代表的な Graph relationship：

```text
agent --USED_MODEL--> model
agent --REQUESTED_TOOL_CALL--> tool_call
tool_call --USES_TOOL--> tool
tool_call --DECLARED_COMMAND--> command
tool_call --DECLARED_TARGET--> file
tool_call --TOOL_CALL_RETURNED--> tool
```

OpenCode の `callID` を `tool_call` identity に直接使用します。

## プライバシー境界

OpenCode の after-hook は tool output を参照できますが、ExecWeave が生成する plugin は `output.output` や `output.metadata` を転送しません。

Plugin は arguments を送信前に縮小します。

- `bash`: declared `command` のみ
- file-oriented tools: `filePath`、`file_path`、`path` などの path field のみ
- 必要に応じて working-directory metadata

Raw write content、chat message parts、tool output は ExecWeave hook に送信されません。

## Tool → Process correlation

`callID` は OpenCode 内部の logical call identity を証明しますが、OS PID ではありません。Tool → Process は引き続き保守的な derived bridge であり、runtime evidence が一意に支持する process を示す場合のみ作成されます。

Derived bridge は常に `inferred: true`、`causal: false` です。

## Evidence boundary

Plugin が報告するのは OpenCode semantic intent です。Process/file/network の runtime observation は OS collector が独立して確立します。Provider plugin を declared command や file action が実際に発生した証拠として扱いません。