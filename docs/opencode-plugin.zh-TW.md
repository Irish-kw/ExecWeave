# OpenCode Plugin

<!-- i18n-nav:start -->
<p align="center">
  <a href="opencode-plugin.md">English</a> |
  <strong>繁體中文</strong> |
  <a href="opencode-plugin.zh-CN.md">简体中文</a> |
  <a href="opencode-plugin.ja.md">日本語</a> |
  <a href="opencode-plugin.ko.md">한국어</a> |
  <a href="opencode-plugin.fr.md">Français</a> |
  <a href="opencode-plugin.de.md">Deutsch</a> |
  <a href="opencode-plugin.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

ExecWeave 透過 project-local plugin 與 OpenCode 整合。OpenCode 在 `tool.execute.before` 與 `tool.execute.after` 都提供精確的 `sessionID + callID`，因此同一個 logical tool call 不需要靠 heuristic 配對 lifecycle events。

## 安裝

在目前專案安裝生成的 plugin：

```bash
execweave-opencode-plugin --install
```

它會建立：

```text
.opencode/plugins/execweave.ts
```

OpenCode 會自動載入該目錄下的 project plugin。若檔案已存在，ExecWeave 預設拒絕覆寫，除非明確使用 `--force`。

接著記錄：

```bash
execweave-opencode-record --open -- opencode
```

## 擷取的 semantic evidence

目前 baseline 只送出最小 metadata：

- `chat.message`
- `tool.execute.before`
- `tool.execute.after`

典型 Graph 關係：

```text
agent --USED_MODEL--> model
agent --REQUESTED_TOOL_CALL--> tool_call
tool_call --USES_TOOL--> tool
tool_call --DECLARED_COMMAND--> command
tool_call --DECLARED_TARGET--> file
tool_call --TOOL_CALL_RETURNED--> tool
```

OpenCode 的 `callID` 直接用於 `tool_call` identity。

## 隱私邊界

OpenCode 的 after-hook 可以看到 tool output，但 ExecWeave 生成的 plugin **不會**轉送 `output.output` 或 `output.metadata`。

Plugin 會先縮減 arguments：

- `bash`：只保留 declared `command`
- file-oriented tools：只保留 `filePath`、`file_path`、`path` 等 path 欄位
- 可選的 working-directory metadata

Raw write content、chat message parts 與 tool output 都不會送進 ExecWeave hook。

## Tool → Process correlation

`callID` 能證明 OpenCode 內部的 logical call identity，但它不是 OS PID。Tool → Process 仍然是保守的 derived bridge，只有 runtime evidence 找到唯一且足夠支持的 process 才建立。

Derived bridge 永遠維持 `inferred: true`、`causal: false`。

## Evidence boundary

Plugin 回報的是 OpenCode semantic intent。Process/file/network 的實際 runtime observation 仍由 OS collector 獨立建立。ExecWeave 不會把 provider plugin 當成 declared command 或 file action 已真正發生的證明。