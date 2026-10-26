<!-- i18n-nav:start -->
<p align="center">
  <a href="claude-code-hooks.md">English</a> |
  <strong>繁體中文</strong> |
  <a href="claude-code-hooks.zh-CN.md">简体中文</a> |
  <a href="claude-code-hooks.ja.md">日本語</a> |
  <a href="claude-code-hooks.ko.md">한국어</a> |
  <a href="claude-code-hooks.fr.md">Français</a> |
  <a href="claude-code-hooks.de.md">Deutsch</a> |
  <a href="claude-code-hooks.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# Claude Code Hooks

ExecWeave 內建 Claude Code command-hook adapter，會把 provider 的 semantic/content evidence 寫入本機 sidecar，並與獨立 OS runtime evidence 分開保存。Provider hook 說明 Claude Code 明確曝露了什麼；它不會取代 portable 或 Linux `strace` collector，也不會單靠 hook 建立 OS process causality。

**目前 hook surface。** `execweave-claude-hook --print-config` 目前會註冊：

- `SessionStart`
- `UserPromptSubmit`
- `MessageDisplay`
- `PreToolUse`
- `PostToolUse`
- `PostToolUseFailure`
- `PostToolBatch`
- `SubagentStart`
- `SubagentStop`
- `Stop`
- `StopFailure`

Hook 預設 fail-open：telemetry/storage error 會被回報，但不會刻意阻擋 Agent operation。除錯時可用 `--strict` 要求 telemetry failure 回傳 non-zero。

## 設定與記錄

安裝 ExecWeave、產生支援的 settings fragment，合併進 Claude Code settings 後使用 run-bound recorder：

```bash
execweave-claude-hook --print-config
execweave-claude-record --open -- claude
```

`execweave-claude-record` 會透過 child environment 綁定每個 run 專屬的 semantic sidecar。Runtime、semantic、correlated evidence 仍是不同 artifacts。

```text
runtime evidence
    ↓ semantic merge
runtime + semantic evidence
    ↓ conservative correlation
runtime + semantic + inferred correlation
```

如果沒有任何受支援 Claude hook event，recorder 會退回 runtime-only artifacts。若已有 semantic evidence，但沒有唯一且足夠支持的 Tool → Process candidate，也不會捏造 bridge。

## v0.6.5 full-fidelity content

Claude adapter 已不再只保留 bounded metadata summary。當 hook 明確提供內容時，v0.6.5 會把來源提供的完整值存進本機 SHA-256 content-addressed store，semantic sidecar 只留下 reference。

Regression coverage 包含：

- 完整 `UserPromptSubmit.prompt`，包含大型值；
- 完整 tool input，包括 `Write`/`Edit` 內容，以及 input object 裡的 application-level values；
- hook 提供時的完整 structured `PostToolUse.tool_response`；
- `PostToolBatch` 提供、model 可見的 tool-result serialization；
- `MessageDisplay` assistant text/delta 與可用 ordering metadata；
- stop events 提供的 main Agent / subagent 最終 assistant message。

已知 transport credentials 只會在 adapter 能辨識的獨立 provider-metadata projection 中被過濾。這**不會**清理 full content 本身。若 secret 存在 prompt、tool input、file body、tool result 或 assistant message 內，就會成為保留的 full-fidelity evidence。

`content_complete_from_source: true` 表示 ExecWeave 完整保存了 Claude hook 提供的值，不代表 ExecWeave 讀取了 hook 未提供的 transcript、觀察到 hidden model state，或捕捉到 payload 中不存在的 provider stage。

## Logical entities 與 tool identity

Claude hook event 可以產生下列 provider-level relationships：

```text
Claude Code --REQUESTED_TOOL_CALL--> tool_call
tool_call --USES_TOOL-------------> tool
tool_call --DECLARED_COMMAND------> command
tool_call --DECLARED_TARGET-------> file metadata
tool_call --VIA_MCP---------------> mcp_server
Claude Code --SPAWNED_SUBAGENT----> subagent
```

Claude hook input 可以用 `tool_use_id` 識別 logical tool invocation，但它不是 OS PID。符合 provider `mcp__<server>__<tool>` 命名規則的 MCP 名稱，會在可用時正規化成獨立 MCP-server/tool entities。

## Tool → Process correlation boundary

Claude command-hook input 不會提供 Bash/PowerShell tool invocation 真正建立的 child process PID，因此 ExecWeave 不會僅憑 provider hook data 建立 observed causal process edge。

只有 bounded runtime matcher 找到唯一受支持 process candidate 時，才可能建立 derived bridge：

```text
tool_call --CORRELATED_WITH_PROCESS--> process
```

所有此類 bridge 都維持：

```json
{
  "causal": false,
  "inferred": true,
  "confidence_semantics": "heuristic_score_not_probability"
}
```

僅有時間接近並不足夠。Ambiguous candidate、unsupported compound command、shell builtin 或 unmatched declaration 都不會產生 bridge；inference 永遠不會被升級成 observed process attribution。

## Layered artifacts

Run-bound Claude capture 可能產生：

```text
.execweave/runs/<run-id>/
├── events.jsonl
├── graph.json
├── viewer.html
├── semantic.jsonl
├── content/sha256/...
├── events.semantic.jsonl
├── graph.semantic.json
├── viewer.semantic.html
├── events.correlated.jsonl
├── graph.correlated.json
└── viewer.correlated.html
```

Correlation 不會重寫原始 runtime 或 provider evidence。

## Standalone sidecar

不使用 run-bound recorder 時，預設 Claude sidecar 會依 session 分開：

```text
<cwd>/.execweave/semantic/claude/<Claude-session-id>.jsonl
```

可使用 `EXECWEAVE_SEMANTIC_SIDECAR` 或 `--sidecar` 覆寫。Parallel capture 建議使用 session/run-specific path。

## Privacy 與 evidence boundary

Claude full-fidelity artifact 可能包含 prompt、command、file path、`Write`/`Edit` body、tool argument/result、assistant text、subagent response、identifier 與 application-level secrets。整個 run directory 都應視為敏感資料，分享前必須檢查。

Provider content 仍只是 provider evidence。保存的 tool input 不代表 tool 確實執行；保存的 file body 不代表某個特定 OS process 曾讀寫；保存的 tool result 也不代表 bytes 已流向其他 resource。更強的 claim 必須由 OS collector 與明確標示的 correlation evidence 支援。

## 手動 merge 與 correlation

若已經有 runtime 與 semantic files，generic pipeline 仍可使用：

```bash
execweave semantic-merge run.jsonl semantic.jsonl --output run.semantic.jsonl
execweave validate run.semantic.jsonl
execweave correlate run.semantic.jsonl --output run.correlated.jsonl
execweave validate run.correlated.jsonl
```

Generic evidence/content contract 與 process-reference rules 請見 [`Semantic Telemetry`](semantic-telemetry.zh-TW.md)。
