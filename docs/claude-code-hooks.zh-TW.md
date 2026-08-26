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

ExecWeave 內建 Claude Code command-hook adapter，可把 provider semantic telemetry 寫到獨立的本機 JSONL sidecar。

這個 adapter 是 OS runtime collection 的補充，**不會**取代 portable 或 Linux `strace` collector。

## 目前記錄的 hook events

目前 adapter 接收以下 Claude Code hook events：

- `SessionStart`
- `PreToolUse`
- `PostToolUse`
- `PostToolUseFailure`
- `SubagentStart`
- `SubagentStop`

可 materialize 的 semantic entities 例如：

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
  +--USED_MODEL-------------> model        when SessionStart exposes one
```

符合 Claude Code `mcp__<server>__<tool>` 命名慣例的 MCP tool name，會被正規化成獨立的 `mcp_server` 與 `tool` node。

## 安裝 hook 設定

先安裝 ExecWeave，讓 console scripts 可用：

```bash
python -m pip install -e ".[dev]"
```

產生 settings fragment：

```bash
execweave-claude-hook --print-config
```

把輸出的 `hooks` object 合併到 Claude Code 支援的 JSON settings file 之一：

- `~/.claude/settings.json`：user-wide hooks
- `.claude/settings.json`：可分享的 project configuration
- `.claude/settings.local.json`：不應 commit 的 project-local configuration

加入 fragment 時不要覆寫不相關的 Claude Code settings。

Claude Code 的 `/hooks` menu 可用來檢查目前已設定哪些 hooks。

Adapter 使用 command hooks，預設為 fail-open：telemetry parsing 或 filesystem error 會寫到 stderr，但回傳 success，避免 ExecWeave observability 阻斷 Agent tool call。`--strict` 只用於 debug hook 本身，不是 runtime security policy。

## 建議：一行完成 runtime + semantic + correlation

Hooks 安裝後，使用 run-bound workflow：

```bash
execweave-claude-record --open -- claude
```

Linux 上 `--backend auto` 在可用時仍優先使用較強的 `strace` backend；macOS 與 Windows 使用 portable backend。

`execweave-claude-record` 會在專用 CLI process **內部**綁定這次 ExecWeave run 專屬的 sidecar path。Claude 和它啟動的 hook commands 都會繼承該 path，因此兩個獨立啟動的 ExecWeave Claude-record process 不需要猜哪個 semantic sidecar 屬於哪次 runtime capture。

如果 Claude emit semantic hook events，recorder 會執行三個明確 evidence stages：

```text
runtime evidence
    ↓ semantic merge
runtime + semantic evidence
    ↓ conservative correlation
runtime + semantic + inferred correlation
```

Run directory 會把每個 stage 分開保存：

```text
.execweave/runs/<run-id>/
├── events.jsonl              # runtime evidence only
├── graph.json                # runtime-only graph
├── viewer.html               # runtime-only viewer
├── semantic.jsonl            # Claude hook semantic evidence only
├── events.semantic.jsonl     # validated runtime + semantic stream
├── graph.semantic.json       # runtime + semantic graph
├── viewer.semantic.html      # runtime + semantic viewer
├── events.correlated.jsonl   # runtime + semantic + inferred bridges
├── graph.correlated.json     # graph including inferred bridges
└── viewer.correlated.html    # viewer with inferred edges styled separately
```

有 semantic evidence 時，`--open` 會開啟 `viewer.correlated.html`。如果 hooks 未安裝或沒有任何支援的 hook event 發生，ExecWeave 會回報 `semantic_status: "no_events"`、`correlation_status: "not_run_no_semantic_events"`，並 fallback 到 runtime-only viewer。

如果 semantic evidence 存在，但沒有唯一且安全的 Tool → Process candidate 存活，ExecWeave 仍會產生 correlated artifacts，並標示 `correlation_status: "completed_no_matches"`。不會憑空建立 inferred edge。

Default maximum correlation window 是 3000 ms，可明確調整：

```bash
execweave-claude-record \
  --correlation-window-ms 1500 \
  --open \
  -- claude
```

如有需要也可明確指定 directory：

```bash
execweave-claude-record \
  --output-dir my-claude-run \
  --open \
  -- claude
```

Run-bound workflow 會保留 `events.jsonl`、`semantic.jsonl` 與 `events.semantic.jsonl`；correlation 只寫入獨立的 `events.correlated.jsonl` stream。

## Standalone hook sidecar location

在 run-bound recorder 外單獨使用 `execweave-claude-hook` 時，每個 Claude session 預設寫到：

```text
<cwd>/.execweave/semantic/claude/<Claude-session-id>.jsonl
```

Session ID 會先 sanitize 再用作 filename。

可用以下 environment variable 覆寫：

```text
EXECWEAVE_SEMANTIC_SIDECAR
```

或明確指定 hook command：

```bash
execweave-claude-hook --sidecar /path/to/semantic.jsonl
```

Parallel standalone sessions 建議使用自動的 session-scoped path，不要讓多個 Claude session 指向同一個固定 sidecar。

## Advanced: manual merge and correlation

如果已經有 runtime capture 與 semantic sidecar，generic semantic/correlation pipeline 仍可手動使用：

```bash
execweave semantic-merge \
  run.jsonl \
  semantic.jsonl \
  --output run.semantic.jsonl

execweave validate run.semantic.jsonl

execweave correlate run.semantic.jsonl \
  --output run.correlated.jsonl

execweave validate run.correlated.jsonl
execweave graph run.correlated.jsonl \
  --output run.correlated.graph.json
execweave view run.correlated.graph.json \
  --output run.correlated.html \
  --open
```

原始 runtime stream 與 semantic sidecar 都保持不變。

## Tool → Process boundary and correlation v0.1

Claude Code command-hook input 能識別 logical tool invocation（`tool_name`、`tool_use_id` 與 tool input），但**不提供** Bash tool call 真正建立的 child process PID。

因此 native adapter 刻意**不會**在缺乏額外 evidence 時 emit observed relationship，例如：

```text
Bash tool_call --SPAWNED_PROCESS--> process:1234
```

即使如此，同一個 merged graph 中仍可能同時看到 semantic 與 OS evidence：

```text
Claude Code --REQUESTED_TOOL_CALL--> Bash call --DECLARED_COMMAND--> "npm test"

session --LAUNCHED--> Claude process --SPAWNED--> shell/process ...
```

ExecWeave 不會只因 timestamp 或 command string 看起來相似，就宣稱這些 path 是同一條 causal chain。

v0.1 correlation stage 刻意保守：

- search window 有明確 bound，且可在 tool result 或下一個 declared tool call 出現時提前截斷；
- executable identity 可由 exact executable/process/cmdline evidence 支持；
- canonical executable path 可 resolve equivalent path，而不使用 fuzzy name matching；
- launcher process 可把 exact、non-empty、length-preserving `argv[1:]` match 作為 fallback；
- 只有恰好一個 process candidate 存活時才 emit bridge；
- ambiguous candidate 不 emit bridge；
- unsupported compound shell command 與 shell builtin 不 emit bridge；
- 不使用 fuzzy version/name matching；
- temporal proximity 單獨永遠不足。

Derived bridge 表示為：

```text
tool_call --CORRELATED_WITH_PROCESS--> process
```

並永遠帶有等價於以下的 semantics：

```json
{
  "backend": "inference",
  "causal": false,
  "inferred": true,
  "inference_method": "...",
  "confidence": 0.8,
  "confidence_semantics": "heuristic_score_not_probability",
  "supporting_event_ids": ["..."]
}
```

實際 method 與 score 取決於 supporting evidence。`confidence` 是用來表達 evidence strength 的 heuristic score，明確**不是 calibrated probability**。

Standalone Viewer 會把 inferred relationship 與 causal observed / non-causal observed edge 分開 render，標示 `· inferred`，並在選取時顯示其 evidence metadata。Inferred bridge 永遠不會被升級成 observed process attribution。

## Privacy behavior

Native adapter 刻意避免保存多種高風險 payload：

- 不保存 `Write`/`Edit` file content；
- 不保存 `PostToolUse.tool_response`；
- generic tool-call metadata 只保留 input key names；
- file-oriented tools 保留 declared file path，不保留內容；
- Bash/PowerShell command 因 execution explanation 所需而保留，但 command text 上限為 4096 characters；
- failure text 只保留短而 bounded 的 error summary。

Path 與 command 仍可能含 credential、token、customer name、internal hostname 或其他 sensitive information。Semantic sidecar 應視為 sensitive runtime metadata，分享前請 review。

## Evidence semantics

Claude adapter 直接產生的 edge 包含：

```json
{
  "backend": "semantic",
  "attribution": "claude_hook",
  "evidence_source": "provider_hook",
  "provider": "claude",
  "causal": false
}
```

`causal: false` 不代表 Claude hook 是捏造的，而是 provider-level logical relationship 不會被提升為 ExecWeave 較強的 OS execution-attribution claim。

Correlation event 是獨立的 derived evidence，帶有 `backend: "inference"`、`inferred: true`、`causal: false`。它們不會修改 raw runtime 或 Claude hook evidence。

Generic merge contract 與 process-reference rules 請見 [`Semantic Telemetry`](semantic-telemetry.zh-TW.md)。
