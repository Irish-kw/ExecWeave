<!-- i18n-nav:start -->
<p align="center">
  <a href="codex-hooks.md">English</a> |
  <strong>繁體中文</strong> |
  <a href="codex-hooks.zh-CN.md">简体中文</a> |
  <a href="codex-hooks.ja.md">日本語</a> |
  <a href="codex-hooks.ko.md">한국어</a> |
  <a href="codex-hooks.fr.md">Français</a> |
  <a href="codex-hooks.de.md">Deutsch</a> |
  <a href="codex-hooks.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# OpenAI Codex Lifecycle Hooks

ExecWeave 提供 OpenAI Codex lifecycle-hook adapter，將 provider-level semantic evidence 加到與 OS runtime telemetry 相同的本機 run 中。

這個 integration 採保守設計。Codex hook 可以告訴 ExecWeave 哪個 logical tool call 被要求，以及 shell execution 宣告了什麼 command；它**不提供 OS child PID**，因此 provider hook 不會被呈現成直接 observed / causal 的 Tool → Process attribution。

## 目前支援

ExecWeave 接收：

- `SessionStart`
- `PreToolUse`
- `PostToolUse`

只記錄 Codex 實際送達的 lifecycle events；未知 event 會被忽略，不猜測。

### `SessionStart`

若 payload 有 model：

```text
OpenAI Codex --USED_MODEL--> model
```

Adapter 不讀取 transcript file 內容。

### `PreToolUse`

Provider 的 `tool_use_id` 會作為 stable logical tool-call identity：

```text
OpenAI Codex --REQUESTED_TOOL_CALL--> tool_call
tool_call --USES_TOOL--> tool
```

Canonical `Bash` tool 若有 string `tool_input.command`：

```text
tool_call --DECLARED_COMMAND--> command
```

這是 semantic evidence，可供 conservative correlation 使用，但不是特定 OS process 執行該 command 的證明。

### `PostToolUse`

目前只記錄中性 relation：

```text
tool_call --TOOL_CALL_RETURNED--> tool
```

不轉成 `TOOL_CALL_SUCCEEDED` / `TOOL_CALL_FAILED`，因為目前 payload 沒有足夠可靠的 success/failure discriminator。

Raw `tool_response` 不會存入 semantic telemetry；string response 只保存 type 與 character count。

## 設定 Codex

安裝 ExecWeave 後：

```bash
execweave-codex-hook --print-config
```

把輸出的 `hooks` object 合併到 Codex `hooks.json`。目前 generator 會註冊 `SessionStart`、`PreToolUse`、`PostToolUse`。

Hook adapter 預設 fail-open；telemetry 問題只警告，不刻意阻斷 Codex。Debug adapter 本身時可用：

```bash
execweave-codex-hook --strict
```

## 一行記錄 Codex run

設定好 hooks 後：

```bash
execweave-codex-record --open -- codex
```

Recorder 不修改 Codex configuration，只透過 inherited environment variable 將 child Codex process 綁到 run-specific semantic sidecar。

Hook 有觸發時會得到分層 artifacts：

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

如果沒有 Codex hook event，recorder 安全退回 runtime-only artifacts。

## Tool → Process correlation

例如：

```text
tool_call --DECLARED_COMMAND--> "python task.py"
```

ExecWeave 會將 semantic declaration 與 bounded runtime process evidence 比對，只有 matcher 找到**唯一且有足夠證據支持的候選**時，才產生：

```text
tool_call --CORRELATED_WITH_PROCESS--> process
```

所有 bridge 都保持：

```text
inferred: true
causal: false
```

Ambiguous、unmatched、shell builtin、compound 或 unsupported call 不會建立 bridge。

Correlated graph 會保存 run-level Correlation Summary，讓 Viewer 區分 `matched / ambiguous / no match / unsupported`，而不是把所有缺 edge 都當成同一原因。Viewer 的 **observed only** 會在 focus traversal/layout 前移除 inferred edges。

## Evidence / privacy boundary

目前 Codex adapter 只保存建圖需要的 semantic metadata，例如：

- Codex session ID
- turn ID（若有）
- model name
- tool name
- tool-use ID
- input key names
- declared `Bash` command
- `PostToolUse` response type / length

不主動收集：

- prompt text
- transcript-file content
- raw `tool_response`
- file content
- provider-derived Tool → Process PID

Command 本身仍可能含 secret/path，分享 artifacts 前請檢查。

## 目前 upstream limitations

Codex lifecycle hooks 仍在演進，因此 ExecWeave 把這項功能定位為 native semantic adapter，而不是宣稱每種 Codex execution mode 都有完整 lifecycle coverage。

目前需要注意：

1. `PostToolUse` 沒有足夠可靠 outcome signal，因此只標 `TOOL_CALL_RETURNED`。
2. 部分 `codex exec` path 曾有 lifecycle hook dispatch gap；初期 interactive Codex CLI 是較安全的 target。
3. 部分 Windows command execution path 曾出現 upstream hook-coverage gap。
4. Provider hook 沒有 OS child PID，因此不能提供直接 observed Tool → Process attribution。

這些限制只影響 semantic coverage；獨立 OS runtime collector 即使 hook 沒觸發仍能工作。

## Design rule

> Provider semantics 描述 Agent 說它要做什麼；OS telemetry 描述機器實際觀察到什麼；只有 evidence 唯一且充分時，correlation 才能以 explicit、non-causal inference 把兩者連起來。

通用 contract 見 [`Semantic Telemetry`](semantic-telemetry.zh-TW.md)。
