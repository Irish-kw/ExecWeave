# Remaining Provider Audit — v0.8.7

日期：2026-09-02
分支：`audit/remaining-providers-v0.8.7`
基準：`main`（Codex 與 Antigravity/AGY 的 provider graph 重整已合併）

## 目的與範圍

這份文件盤點尚未依照 Codex/AGY 成功經驗完成驗證或重整的 provider。這一輪只記錄問題、限制與下一步驗收條件，不修改 provider 實作。

Codex/AGY 目前可作為共同驗收基準：

1. provider 能保留穩定的 agent/session identity。
2. 子代理關係只使用 provider 明確提供、且可驗證的 identity evidence。
3. 同一次 tool invocation 的 request/return 使用同一個穩定 tool-call identity。
4. tool 明確宣告檔案目標時，圖上建立 `tool-call → file` 的 `DECLARED_TARGET` 關係。
5. 子代理的 tool/file 關係歸屬實際子代理，不因檔案系統觀察或缺少 identity 而錯掛到 root agent。
6. full-fidelity/raw evidence 與 graph projection 同時保留；檔案節點能出現在 dashboard 的 File activity/filter。
7. 每個 provider 都有 provider-shaped fixture 或 live acceptance，不能只靠通用 adapter unit test。

## 總覽

| Provider | Tool-call identity | 子代理 identity | 檔案目標關係 | 目前主要問題 | 分類 |
| --- | --- | --- | --- | --- | --- |
| Claude Code | 穩定：`session_id + tool_use_id` | 有 `agent_id` 時可用 | hook 與嚴格驗證的 child transcript 均可建立 | child tool/file projection 已補上；仍需 live 驗收 | 已處理；待 live 驗證 |
| Cursor | 穩定：provider `tool_use_id` | 有 `subagent_id` 時可用 | **已修正**：`Edit` 與明確 path aliases 可建立 declared target | 仍需 live 驗證 child ownership、tab surface 與缺少 ID 時的保守行為 | 已處理，待 live 驗證 |
| OpenCode | 穩定：`sessionID + callID` | 只有明確 `parentID` 才可建立 | plugin hook 與 event-bus projection 均可產生 | plugin/event-bus 共用 canonical tool-call node；仍需 live 驗證 | 已修正；待 live 驗收 |
| Ollama | request/response/exchange identity | root-only by design | 沒有 native tool/file graph | 不是 agent provider；需明確標示能力邊界，避免 UI 顯示 unknown | 設計限制／UX 缺口（P2） |
| llama.cpp / vLLM / LM Studio / OpenAI-compatible runtime | root-only request/response | provider 未提供 | 沒有 native tool/file graph | 應與 agent provider 分開驗收，不應推測隱藏 routing 或子代理 | 設計限制 |

## 詳細盤點

### 1. Claude Code

相關實作：`src/execweave/claude_adapter.py`、`src/execweave/claude_delegation.py`、`src/execweave/claude_hook_cli.py`。

目前已具備：

- 支援 `SessionStart`、`PreToolUse`、`PostToolUse`、`PostToolUseFailure`、`SubagentStart`、`SubagentStop`。
- tool-call identity 使用 `session_id` 與 `tool_use_id`，具備穩定 logical identity。
- payload 有 `agent_id` 時可將 child actor scope 在同一 session 下。
- `Read`、`Edit`、`Write`、`NotebookEdit` 等指定 tool 可產生檔案目標關係。

待處理問題：

- **子代理歸屬依賴 hook payload 的 `agent_id`。** 若 Claude 的 tool hook 沒有帶 `agent_id`，事件會退回 `agent:Claude Code`。目前沒有像 AGY 那樣經 live-verified transcript evidence 做保守 identity correlation 的通用 fallback。不能直接以時間、檔名或 OS runtime 猜測 child ownership。
- **檔案 schema 與 tool allowlist 需要 provider-shaped 驗收。** adapter 目前主要讀 `file_path`/`path`，且只對固定 tool 名稱建立 declared file。Claude 實際使用的 tool variant 或 payload key 若不同，raw content 可能存在，但 graph 不會有 `DECLARED_TARGET`。
- **尚缺子代理寫入 `.md` 的 dashboard acceptance。** 需要確認 child tool-call、`.md` file node、`DECLARED_TARGET`、File activity/filter 與 raw event file button 同時存在，並確認沒有錯掛 root。

建議驗收：

1. root Claude 啟動一個 subagent。
2. child 使用 `Write` 或 `Edit` 寫入 `.md`。
3. 檢查 child-owned tool-call → file edge、File filter 與 raw event file action。
4. 另外測試缺少 `agent_id` 時只保留 root/unknown attribution，不建立猜測性的 child edge。

### 2. Cursor

相關實作：`src/execweave/cursor_adapter.py`、`src/execweave/cursor_full_fidelity.py`、`src/execweave/agent_trace.py`。

目前已具備：

- tool-call identity 使用 provider 提供的 `tool_use_id`，並以 scope 隔離。
- `preToolUse` 與 post/failure event 能回到同一 logical call。
- `subagent_id` 存在時可建立 child lifecycle 與 `OWNED_TOOL_CALL` 關係。
- full-fidelity layer 能保存 tool input/output、file read content、edit structure、subagent summary 等 provider 明確提供的內容。

已確認或待驗證問題：

- **`Edit` tool 未列入 declared file allowlist。** adapter 目前對檔案目標只處理 `Read`、`Write`、`Delete`；因此 Cursor 的 `Edit` 即使 input 有路徑，也可能沒有直接的 `tool-call → file` `DECLARED_TARGET`。
- `afterFileEdit` 的 edit structure/content observation 不等同於該 Edit tool-call 的 declared target edge；raw evidence 存在時，graph 仍可能呈現檔案孤立或只呈現 observation。
- child ownership 依賴每個 hook 都帶 `subagent_id`。目前 full-fidelity 明確不讀 transcript，因此不能把缺少 ID 的事件事後猜回某個 child。
- `beforeTabFileRead`/`afterTabFileEdit` 等 tab surface 與一般 tool surface 需要確認是否使用同一套檔案 identity/graph projection，避免同一檔案出現孤立重複節點。

建議驗收：

1. Cursor subagent 使用 `Edit` 與 `Write` 修改 `.md`。
2. 驗證 child-owned tool-call → file edge、File filter、raw event file action。
3. 驗證 `afterFileEdit` 不會取代或破壞 declared target edge。
4. 測試沒有 `subagent_id` 的 hook，確認系統保守保留 root/unknown attribution。

### 4. OpenCode

相關實作：`src/execweave/opencode_adapter.py`、`src/execweave/opencode_plugin_cli.py`、`src/execweave/agent_trace.py`。

目前已具備：

- plugin tool hook 使用 `sessionID + callID`，具有穩定 tool-call identity。
- plugin `tool.execute.before` 可從 `filePath`、`file_path`、`path` 解析 declared file，並為 bash 保存 declared command。
- event-bus projection 也能保存 tool input/output/error 與 tool identity。
- 只有 OpenCode 明確提供 `parentID`/`parentId` 時，才建立 child session 關係；這個保守原則正確。

已確認或待驗證問題：

- **plugin hook 與 event-bus 是兩條不完全等價的 projection。** plugin before 會建立 `DECLARED_TARGET`，但 event-bus 的 tool-part projection 目前主要建立 `OBSERVED_TOOL_CALL`、`USES_TOOL` 與 content state，沒有同等的 file argument → `DECLARED_TARGET` 處理。相同 run 取決於資料來源，可能得到不同 graph。
- subtask part 可以先建立 `REQUESTED_SUBTASK` 或 agent profile，但 child session/tool ownership 仍需要後續 event 明確帶 `parentID`。不能只因為出現 subtask tool 就把後續工具歸給 child。
- plugin hook 與 event-bus 同時啟用時，需驗證相同 `sessionID + callID` 被去重或合併，避免 duplicate tool/file node、孤立 result 或兩套不一致的 edge。
- 需要真實 OpenCode plugin 安裝與 scope 驗證；若 plugin 沒有載入，測試可能只看到 event-bus 的較弱投影。

建議驗收：

1. 同一個 OpenCode run 同時啟用 plugin hook 與 event-bus。
2. 執行 child task，讓 child 寫入 `.md`，並確認 provider 明確提供 parent session identity。
3. 驗證 child tool-call → file edge、File filter、raw event file action。
4. 對沒有 `parentID` 的事件驗證系統維持 abstain，不建立推測性的 child relationship。
5. 檢查 plugin/event-bus 的同一 call 是否只有一個 canonical tool-call node。

### 5. Ollama 與其他模型 runtime

相關實作：`src/execweave/conversation_records.py`、`src/execweave/conversation_records_ollama.py`、`src/execweave/model_runtime.py`、`src/execweave/model_runtime_cli.py`、`src/execweave/model_runtime_full_fidelity.py`。

目前定位：

- Ollama 是 model runtime integration，不是像 Codex、AGY、Claude 或 Cursor 那樣的 agent/IDE provider hook。
- 支援 `event`、`exchange`、`probe`，可保存 caller-supplied request/response、streaming response 與 `/api/ps` probe evidence。
- conversation projection 已將 Ollama turn 發布在單一 root run 下。
- llama.cpp、vLLM、LM Studio 與 OpenAI-compatible gateway 也應採相同 root-only model-runtime 邊界，除非外部整合明確提供 agent/tool/file identity。

問題與風險：

- **不能以目前的 model-runtime evidence 產生 Codex/AGY 類 child-agent、tool-call 或 file graph。** 模型回應文字不應被推測成實際工具執行或檔案寫入。
- agent trace capability table 目前沒有獨立的 Ollama capability entry；若某個 UI/metadata path 直接查 `agent_trace_visibility("ollama")`，可能得到 unknown fallback，而不是明確的 `provider_root_only`。
- 現有 synthetic tests 覆蓋不少 NDJSON/request-response 行為，但仍需 user-visible acceptance：stream 組裝、request/response pairing、已存在 server、loopback/privacy 邊界與 dashboard 顯示。

建議驗收：

1. 明確顯示 Ollama/runtime 是 root-only，而不是顯示缺少資料的 agent provider。
2. 驗證 streaming response 不遺失、不重複，且 request/response identity 正確。
3. 驗證沒有 tool/file/child edge 被從文字或 model metadata 推測出來。
4. 對其他 local/OpenAI-compatible runtime 使用同一套 root-only acceptance matrix。

## 建議後續 PR 順序

1. **Cursor：** ✅ 已補足 `Edit`/path aliases 的 declared file semantics；仍需加入 child `.md` live acceptance（P1）。
2. **OpenCode：** ✅ 已統一 plugin/event-bus 的 file projection 與 canonical tool-call identity；仍需 live 驗證 explicit `parentID` 下的 child tool/file ownership 與去重（P1）。
3. **Claude：** ✅ 已補上 provider-validated child transcript fallback；仍需 live child hook/file acceptance（P1/P2）。
4. **Ollama/runtime：** 維持明確 root-only capability/UX 與 runtime acceptance，不把設計限制當成 provider graph bug（P2）。

## 本輪結論

本分支已處理 Claude、Cursor 與 OpenCode 的 provider projection 問題：Claude 新增嚴格驗證的 child transcript tool projection；Cursor 補上 `Edit`/path aliases；OpenCode 補上 event-bus tool part 的 file projection，並讓 plugin/event-bus 共用 `sessionID + callID` canonical tool-call node。舊的 Google CLI provider 已移除，AGY 是唯一的 Google CLI provider。這些修正尚未 commit/push。

仍需在真實 provider run 驗證：Claude、Cursor、OpenCode 的 child `.md`、dashboard File activity/filter、raw event file action。Ollama 與其他 model runtime 目前沒有可安全推導 child-agent/tool/file graph 的 provider evidence，維持 root-only 設計；其 live stream/UX acceptance 尚待另行驗收。
