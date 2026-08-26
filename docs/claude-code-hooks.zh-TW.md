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

ExecWeave 內建 Claude Code command-hook adapter，可把 provider semantic telemetry 寫到獨立的本機 JSONL sidecar，並與 OS runtime collection 組合。

它是 runtime collector 的補充，不會取代 portable 或 Linux `strace` collector。

## 目前記錄的 hook events

- `SessionStart`
- `PreToolUse`
- `PostToolUse`
- `PostToolUseFailure`
- `SubagentStart`
- `SubagentStop`

可建立：

```text
Claude Code
  |
  +--REQUESTED_TOOL_CALL--> tool_call
  |                           |
  |                           +--USES_TOOL-------> Bash / Read / Edit / Write / ...
  |                           +--DECLARED_COMMAND-> command
  |                           +--DECLARED_TARGET--> file metadata
  |                           +--VIA_MCP----------> MCP server
  |
  +--SPAWNED_SUBAGENT-------> subagent
  +--USED_MODEL-------------> model
```

Claude Code 的 `mcp__<server>__<tool>` 命名會被拆成獨立 `mcp_server` 與 `tool` node。

## 安裝 hook 設定

先安裝 ExecWeave：

```bash
python -m pip install -e ".[dev]"
```

產生 settings fragment：

```bash
execweave-claude-hook --print-config
```

把輸出的 `hooks` object 合併到 Claude Code 支援的 settings file，例如：

- `~/.claude/settings.json`
- `.claude/settings.json`
- `.claude/settings.local.json`

不要覆寫原本不相關設定。Claude Code 的 `/hooks` menu 可用來確認目前啟用的 hooks。

Adapter 預設 fail-open：telemetry parse/filesystem error 會寫 stderr，但不會刻意阻斷 Agent tool call。`--strict` 只用來 debug adapter，不是 runtime security policy。

## 建議：一行完成 runtime + semantic + correlation

Hooks 安裝後：

```bash
execweave-claude-record --open -- claude
```

Linux `--backend auto` 在可用時仍優先使用 `strace`；macOS/Windows 使用 portable backend。

`execweave-claude-record` 在自己的 CLI process 內綁定 run-specific semantic sidecar path，Claude 與它啟動的 hook command 會繼承，因此同一 repo 同時跑多個 recorder 時不需要靠 timestamp 猜 sidecar 歸屬。

Evidence pipeline：

```text
runtime evidence
    ↓ semantic merge
runtime + semantic evidence
    ↓ conservative correlation
runtime + semantic + inferred correlation
```

Artifacts 分層保存：

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

`--open` 在 semantic evidence 存在時開啟 correlated viewer。若 hooks 未安裝或沒有支援事件，會回報 `semantic_status: "no_events"` / `correlation_status: "not_run_no_semantic_events"`，並安全退回 runtime-only viewer。

有 semantic evidence、但沒有唯一安全 Tool → Process candidate 時，仍會產生 correlated artifacts，狀態是 `completed_no_matches`，但不建立 inferred edge。

預設 correlation window 為 3000 ms，可調整：

```bash
execweave-claude-record \
  --correlation-window-ms 1500 \
  --open \
  -- claude
```

## Standalone hook sidecar

不使用 run-bound recorder 時，預設每個 Claude session 寫到：

```text
<cwd>/.execweave/semantic/claude/<Claude-session-id>.jsonl
```

也可用 `EXECWEAVE_SEMANTIC_SIDECAR` 或 `--sidecar` 明確指定。Parallel standalone sessions 建議使用自動 session-scoped path，不要讓多個 session 共寫同一檔案。

## Advanced manual workflow

```bash
execweave semantic-merge run.jsonl semantic.jsonl \
  --output run.semantic.jsonl
execweave validate run.semantic.jsonl
execweave correlate run.semantic.jsonl \
  --output run.correlated.jsonl
execweave validate run.correlated.jsonl
execweave graph run.correlated.jsonl \
  --output run.correlated.graph.json
execweave view run.correlated.graph.json \
  --output run.correlated.html --open
```

Raw runtime stream 與 semantic sidecar 都保持不變。

## Tool → Process boundary / correlation v0.1

Claude Code hook 能提供 `tool_name`、`tool_use_id` 與 tool input，但**沒有**提供 Bash tool call 真正建立的 child OS PID。

因此 native adapter 不會直接建立：

```text
Bash tool_call --SPAWNED_PROCESS--> process:1234
```

Correlation v0.1 只有在 bounded window 中有唯一 process candidate 時才建立：

```text
tool_call --CORRELATED_WITH_PROCESS--> process
```

規則包括：

- window 可被 tool result / 下一個 declared call 截斷；
- executable/process/cmdline identity 需有明確 evidence；
- canonical path 可用來確認等價 executable path；
- launcher 可使用 exact、non-empty、length-preserving `argv[1:]` fallback；
- 必須只有一個 surviving candidate；
- ambiguous 不產生 bridge；
- shell builtin / compound command 不產生 bridge；
- 不使用 fuzzy version/name matching；
- temporal proximity 單獨永遠不足。

Derived bridge 永遠類似：

```json
{
  "backend": "inference",
  "causal": false,
  "inferred": true,
  "inference_method": "...",
  "confidence": 0.8,
  "confidence_semantics": "heuristic_score_not_probability"
}
```

Viewer 會把 inferred edge 與 observed edge 分開顯示，並提供 Correlation Summary / **observed only** filter。

## Privacy

Native adapter 刻意避免保存高風險 payload：

- 不保存 `Write/Edit` file content；
- 不保存 raw `PostToolUse.tool_response`；
- generic tool input 只保留 key names；
- file tool 保存 declared path，不保存內容；
- Bash/PowerShell command 因 execution explanation 需要而保存，但上限 4096 characters；
- failure text 只保留 bounded summary。

Command/path 本身仍可能包含 token、credential、internal hostname 或其他敏感資訊，分享 artifact 前請檢查。

## Evidence semantics

Claude adapter 直接產生的 semantic edge 會標示：

```json
{
  "backend": "semantic",
  "attribution": "claude_hook",
  "evidence_source": "provider_hook",
  "provider": "claude",
  "causal": false
}
```

這不代表 provider hook 不可靠，而是 provider-level logical relationship 不會被升級成 OS execution-attribution claim。Correlation 則是獨立 derived evidence，保持 `backend: "inference" / inferred: true / causal: false`。

通用契約見 [`Semantic Telemetry`](semantic-telemetry.zh-TW.md)。
