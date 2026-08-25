# Cursor Hooks

<p align="center">
  <a href="cursor-hooks.md">English</a> |
  <strong>繁體中文</strong> |
  <a href="cursor-hooks.zh-CN.md">简体中文</a> |
  <a href="cursor-hooks.ja.md">日本語</a> |
  <a href="cursor-hooks.ko.md">한국어</a>
</p>

ExecWeave 使用 Cursor 原生 Hook，把 Agent / Tool / Command 的邏輯語意證據加入執行圖，同時不把 provider metadata 誤當成 OS 因果證據。

## 快速開始

產生 Hook 設定並加入 Cursor 的 hook settings：

```bash
execweave-cursor-hook --print-config
```

接著記錄一次 Cursor 執行：

```bash
execweave-cursor-record --open -- cursor
```

run-bound recorder 會分開保存 runtime、semantic 與 correlated artifacts。

## 事件

目前 baseline 使用：

- `sessionStart`
- `preToolUse`
- `postToolUse`
- `postToolUseFailure`

Cursor 提供穩定的 `tool_use_id`，因此 `preToolUse` 與對應 post hook 可以共享精確的 logical `tool_call` identity。

典型語意邊如下：

```text
agent --USED_MODEL--> model
agent --REQUESTED_TOOL_CALL--> tool_call
tool_call --USES_TOOL--> tool
tool_call --DECLARED_COMMAND--> command
tool_call --DECLARED_TARGET--> file
tool_call --TOOL_CALL_RETURNED--> tool
```

`postToolUseFailure` 會另外表示為 `TOOL_CALL_FAILED`。

## Tool → Process correlation

Cursor Hook 不提供 OS child PID，因此 Shell call 不會直接變成 process edge。

只有當 runtime evidence 能獨立找到唯一且足夠支持的 process 時，ExecWeave 才可能衍生：

```text
tool_call --CORRELATED_WITH_PROCESS--> process
```

此 bridge 永遠是：

```text
inferred: true
causal: false
```

候選模糊或不支援時不建立 edge。

## 隱私邊界

Adapter 預設不保存 prompt、transcript path、使用者 email、agent message 或 tool output。只保留 observability 必要的 identifiers 與 declared metadata，例如 model identity、conversation/generation IDs、tool name/use ID、command 與 declared file path。

Command 與 path 本身仍可能敏感，分享 artifacts 前請先檢查。

## Evidence boundary

Cursor Hook 只能證明 Cursor 在 semantic layer 回報了什麼。它不能證明 declared command 一定執行、declared file 一定被存取，也不能證明資料在資源之間流動。實際 runtime 行為仍以 OS collector evidence 為準。