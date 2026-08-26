<!-- i18n-nav:start -->
<p align="center">
  <a href="gemini-hooks.md">English</a> |
  <strong>繁體中文</strong> |
  <a href="gemini-hooks.zh-CN.md">简体中文</a> |
  <a href="gemini-hooks.ja.md">日本語</a> |
  <a href="gemini-hooks.ko.md">한국어</a> |
  <a href="gemini-hooks.fr.md">Français</a> |
  <a href="gemini-hooks.de.md">Deutsch</a> |
  <a href="gemini-hooks.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# Gemini CLI Hooks

ExecWeave 可以接收 Gemini CLI 的 lifecycle/tool hooks，將它們視為 provider semantic evidence，再與獨立蒐集的 OS runtime evidence 放進同一個執行圖中。

這個 adapter 刻意保持保守：Gemini hook 描述的是 Agent / Tool layer 自己回報的語意行為，不會單靠 hook 就宣稱某一個 OS process 實際執行了該動作。

## 目前支援的 hook events

目前接收：

- `SessionStart`
- `BeforeTool`
- `AfterTool`

Gemini CLI 會以 `stdin` 傳入 JSON。Command hook 成功時，`stdout` 必須是合法 JSON；因此 `execweave-gemini-hook` 成功時只輸出 `{}`，警告只寫到 `stderr`。

產生設定片段：

```bash
execweave-gemini-hook --print-config
```

把輸出的 `hooks` object 合併到 Gemini CLI 的 `settings.json`。

產生的設定只做觀測，不會 block 或 rewrite tool call。

## 一鍵記錄

Hook 設定完成後：

```bash
execweave-gemini-record --open -- gemini
```

Recorder 會透過 `EXECWEAVE_SEMANTIC_SIDECAR` 把這次 Gemini child process 綁到 run-specific sidecar，再進入共用 provider-record pipeline：

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

有 provider telemetry 的 run 可產生：

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

Raw runtime 與 provider sidecar 仍保持分離；correlation 產生新的 derived stream，不回頭改寫 observed evidence。

## Event mapping

### SessionStart

`SessionStart` 會變成：

```text
Gemini CLI --STARTED_PROVIDER_SESSION--> provider_session
```

ExecWeave 會保留 attribution 所需的 session metadata，但不會讀取或複製 `transcript_path` 所指向的 transcript。

### BeforeTool

`BeforeTool` 會產生：

```text
Gemini CLI --REQUESTED_TOOL_CALL--> tool_call
tool_call --USES_TOOL--> tool
```

對內建 `run_shell_command`，`tool_input.command` 會成為：

```text
tool_call --DECLARED_COMMAND--> command
```

這份 command evidence 可以進入與其他 provider 共用的 conservative Tool → Process correlation。

對 `read_file`、`write_file`、`replace` 等部分 file tools，ExecWeave 可記錄 provider 宣告的 target path，但不會蒐集 file content。

### MCP tools

當 Gemini CLI 提供 `mcp_context` 時，ExecWeave 使用 provider 明確回報的 server/tool identity：

```text
tool_call --VIA_MCP--> mcp_server
mcp_server --EXPOSES_TOOL--> tool
```

Adapter 不保存 `mcp_context` 裡的啟動 command、arguments 或 URL，因為這些欄位可能包含敏感連線資訊或 credential。

### AfterTool

`AfterTool` 會建立獨立的 `tool_result` observation。

若 `tool_response.error` 非空，才記錄 provider-reported error；否則只記錄中性的 returned-result signal。

ExecWeave **不保存** raw `llmContent`、`returnDisplay` 或 provider error body。

## Gemini hook 沒有唯一 tool-call ID

目前 Gemini CLI hook input schema 有 `tool_name`、`tool_input` 與 optional MCP context，但沒有一個能在 `BeforeTool` 與 `AfterTool` 之間共享的 unique tool-call ID。

因此 ExecWeave **不建立假的 BeforeTool → AfterTool identity edge**。

每個 `BeforeTool` request 使用 timestamp-scoped local identity；`AfterTool` 建立獨立 result node。兩者可以帶由 tool name + normalized input 算出的 deterministic `tool_fingerprint` 作為診斷 hint，但這個 fingerprint **不是 call identity**。重複執行完全相同的 command 必須仍能被區分。

## Tool → Process correlation

Gemini hook 不提供可以證明 Tool → Process attribution 的 child OS PID。

只有 existing bounded matcher 從獨立 runtime evidence 找到唯一且有足夠 evidence 支撐的 process candidate 時，correlated graph 才可能出現：

```text
tool_call --CORRELATED_WITH_PROCESS--> process
```

所有 bridge 都維持：

```text
inferred: true
causal: false
```

Ambiguous、no-match、compound、shell builtin 或 unsupported command 都不建 edge。

Correlated Viewer 會顯示 matched / ambiguous / no match / unsupported，讓「沒有線」不會被錯誤理解成「什麼都沒發生」。

## Privacy boundary

Gemini native adapter 刻意不蒐集：

- prompt content
- transcript content
- raw tool result content
- raw provider error body
- MCP command / arguments / URL
- file content

仍可能保存 command text、declared file path、tool name、session identifier、MCP server/tool name 等 metadata。分享 artifact 前請自行檢查。

## Failure behavior

`execweave-gemini-hook` 預設 fail-open。Telemetry 寫入失敗時只在 `stderr` 警告，不會刻意阻擋 Gemini tool call。

只有需要 telemetry failure 回傳 non-zero 時才使用 `--strict`。

## 目前 upstream contract

Adapter 依照目前 Gemini CLI hooks reference：

- https://github.com/google-gemini/gemini-cli/blob/main/docs/hooks/reference.md
- https://github.com/google-gemini/gemini-cli/blob/main/docs/hooks/index.md

Provider schema 未來可能改變。ExecWeave 只記錄 provider 實際送出的欄位；semantic hook 缺失時，獨立的 OS runtime collector 仍可正常工作。

另見 [`Semantic Telemetry`](semantic-telemetry.zh-TW.md)。
