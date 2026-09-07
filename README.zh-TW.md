# ExecWeave

<!-- i18n-nav:start -->
<p align="center">
  <a href="README.md">English</a> |
  <strong>繁體中文</strong> |
  <a href="README.zh-CN.md">简体中文</a> |
  <a href="README.ja.md">日本語</a> |
  <a href="README.ko.md">한국어</a> |
  <a href="README.fr.md">Français</a> |
  <a href="README.de.md">Deutsch</a> |
  <a href="README.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

<p align="center">
  <a href="https://pypi.org/project/execweave/"><img src="https://img.shields.io/pypi/v/execweave" alt="PyPI"></a>
  <a href="https://github.com/Irish-kw/ExecWeave/actions/workflows/ci.yml"><img src="https://github.com/Irish-kw/ExecWeave/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue" alt="Python 3.10+">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-PolyForm%20Noncommercial-blue" alt="License"></a>
</p>

**看清楚 AI Agent 在你的電腦上實際做了什麼。**

ExecWeave 是一個 local-first 的 AI Agent 與 AI 開發工具可觀測性專案。它把 Provider 層的語意資訊與作業系統層的執行證據整合到同一個互動式 Execution Graph 中，同時保留不同證據層級之間的界線。

> **Event 是證據；Graph 是由證據物化出的檢視。**

<p align="center">
  <img src="docs/assets/codex.gif" alt="ExecWeave 即時 Dashboard 示範" width="100%">
</p>

## 為什麼需要 ExecWeave

Agent 可以告訴你它呼叫了某個工具、修改了某個檔案，或連線到某個服務。這些 Provider 語意很有價值，但不等於作業系統真正觀察到的行為。ExecWeave 的核心目標就是把兩者放在同一個畫面中檢查，同時不把不同強度的證據混為一談。

- **Live 與完成後使用同一套 Dashboard。** 執行中頁面、完成後結果與獨立 `viewer.html` 使用相同的 Graph 與對話模型。
- **理解 Provider 語意。** Provider 有提供 hook、rollout transcript、plugin 或 runtime API 時，就使用可驗證的原生資訊。
- **觀察 OS runtime。** 可獨立觀察 Process、File 與 Network endpoint，而不只依賴 Agent 自己回報。
- **證據分層。** Direct observation、exact identity、保守推論與 causal claim 不會被壓成同一種關係。
- **Local-first。** Run artifacts 預設留在本機，除非你自行複製或分享。
- **不限定單一 Agent。** 即使沒有專用 Provider adapter，也可以包住一般本機指令進行 runtime 觀察。

## 安裝

從 PyPI 安裝：

```bash
python -m pip install -U execweave
```

開發版本：

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

## 快速開始

任何本機指令都可以包在 `execweave live` 後面：

```bash
execweave live --open -- claude
execweave live --open -- codex
execweave live --open -- antigravity
execweave live --open -- cursor
execweave live --open -- opencode
execweave live --open -- python my_agent.py
```

若主要目的是產生完成後的 artifacts：

```bash
execweave record --open -- python my_agent.py
```

若希望程式保留在目前 terminal 互動，同時另外開啟觀察介面：

```bash
execweave top -- codex
```

### Provider integration 授權

部分 Agent 或 IDE 第一次啟用本機 hook / plugin 時會要求授權。如果你希望看到 Prompt、Response、Tool、Model 與 Conversation 等 Provider-level evidence，請允許 ExecWeave integration。若不允許，OS runtime 觀察仍可能正常運作，但 Provider 語意覆蓋會較少。

Google Antigravity 目前實際 CLI 指令為 `agy`；ExecWeave 同時接受 `antigravity` 作為較好記的 alias。

Windows 上直接輸入 `cursor` 時，ExecWeave 會依照使用者 PATH 指向的 Cursor 安裝位置處理；若你明確提供 launcher path，ExecWeave 會保留該路徑。

## Ollama

ExecWeave 支援兩種常見的本機 Ollama 使用方式。

### Managed server capture

先透過 ExecWeave 啟動 Ollama Server：

```bash
execweave live --open -- ollama serve
```

接著在另一個 terminal 正常使用 Ollama：

```bash
ollama run deepseek-r1:1.5b
```

SDK、OpenAI-compatible local request 與送到 managed local endpoint 的 `curl` request，也可以被關聯到同一個 ExecWeave run。第二個 terminal 不需要再包一層 ExecWeave。

Managed relay 只處理本機 loopback endpoint，不會改寫 wildcard 或對外暴露的 Ollama listener。

### Direct client capture

若 Ollama Server 已經在執行，也可以直接包住 client：

```bash
execweave live --open -- ollama run deepseek-r1:1.5b
```

這個模式不會幫你啟動 Ollama Server，因此仍需要一個可連線的 upstream server。

## Dashboard

Dashboard 的設計目標是讓大型、多 Agent 執行仍然可讀，同時不修改底層 evidence。

- **Execution graph：** Agent、Process、File、Network endpoint、Tool、Model/runtime entity 與支援的關係。
- **Conversation rounds：** 新舊輪次都維持在正確 Agent 下，不會因為後續回覆而把舊內容覆蓋掉。
- **Node details：** 可檢查 Process identity、File history、Network endpoint、Tool 與 Provider conversation content。
- **穩定的 Live update：** Run 狀態變化時原頁面持續更新，不需要整頁替換。
- **大型 Graph folding：** 節點過多時可折疊較舊成員，同時保留可檢查性。
- **Selection-focused layout：** 選取 Agent 或 runtime object 後，會弱化與目前目標無關的 Graph traffic。

大型執行可以使用下列參數調整：

```text
--fold-budget N
--viewer-max-nodes N
--viewer-max-edges N
--viewer-max-dom-elements N
```

## 支援的整合

| Integration | OS runtime 觀察 | 專用 evidence |
| --- | --- | --- |
| Claude Code | 由 ExecWeave 啟動時支援 | native hooks 與 Provider 提供的 conversation/tool content |
| OpenAI Codex | 支援 | lifecycle hooks、validated rollout transcripts、可觀察時的 agent/subagent routing |
| Google Antigravity | 支援 | passive hooks 與可觀察時的 conversation/subagent routing |
| Cursor | 支援 | native hooks 與可觀察時的 task/subagent routing |
| OpenCode | 支援 | project plugin、session/task routing、Provider 提供的 plugin content |
| Ollama | 支援 | managed local relay 與 model-runtime evidence |
| llama.cpp | 支援 | model-runtime event/exchange/probe |
| vLLM | 支援 | model-runtime event/exchange/probe |
| LM Studio | 本機程序可觀察時 | model-runtime catalog/runtime evidence |
| LiteLLM Proxy | 本機 proxy 可觀察時 | gateway metadata 與 event integration |
| OpenRouter | 只能觀察本機 client，無法觀察遠端 service process | caller-supplied gateway event/exchange evidence |

Tool-call ID、session ID、rollout thread ID、subagent route 等 Provider identifier 是邏輯身份，不等於 OS PID。ExecWeave 只有在證據足夠時才會把不同層連起來。

## Evidence model

ExecWeave 將 evidence 分成幾個主要層級：

```text
Agent / IDE semantics 與 supplied content
                ↓
Inference gateway / routing evidence
                ↓
Model runtime / inference-server evidence
                ↓
OS runtime evidence: process / file / network
```

只有底層 telemetry 足以支持 causal claim 時，關係才應被標示為 causal。保守推論會明確保留 derived 標記，例如：

```text
inferred: true
causal: false
```

共享 exact request identity 可以證明 identity，但不代表 causal：

```text
identity_exact: true
inferred: false
causal: false
```

如果 attribution 仍有歧義，ExecWeave 應該不建立 edge，而不是猜一條更強的關係。

### Full-fidelity supplied content

支援的 Provider hook、plugin 或 API 可以把 Provider 明確提供的完整值保存在本機 SHA-256 content-addressed store：

```text
<run-root>/content/sha256/<sha256>.<json|txt|bin>
```

內容可能包含 Prompt、Message、Request/Response object、Tool input/result、Assistant response、Provider 明確暴露的 reasoning text、Shell output 與 supplied file content。

`complete_from_source: true` 代表 ExecWeave 保存了該 integration point 所提供的完整內容；不代表 ExecWeave 能看到未暴露的模型內部狀態或 Provider 內部資料。

## 常用指令

### Agent / IDE recorder

```bash
execweave-claude-record --open -- claude
execweave-codex-record --open -- codex
execweave-antigravity-record --open -- antigravity
execweave-cursor-record --open -- cursor
execweave-opencode-plugin --install
execweave-opencode-record --open -- opencode
```

### Gateway 與 model runtime

```bash
execweave-inference-gateway event --gateway openrouter --sidecar gateway.jsonl
execweave-inference-gateway exchange --gateway openrouter --sidecar gateway.jsonl
execweave-model-runtime event --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime exchange --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime probe --runtime ollama --sidecar model-runtime.jsonl
```

`event` 表示單側 event evidence。`exchange` 保存由 caller 提供的 request/response pair，不宣稱透明攔截 wire traffic。

### Runtime、Graph、安全與完整性

```bash
execweave doctor
execweave run --backend portable -- your-command
execweave run --backend strace -- your-command
execweave graph-summary run.graph.json
execweave graph-filter run.graph.json --causal-only --output causal.graph.json
execweave graph-focus run.graph.json NODE_ID --hops 2 --output focused.graph.json
execweave path run.graph.json SOURCE TARGET --causal-only
execweave analyze run.graph.json --output analysis.json
execweave-rule-pack graph.json --rule-pack local-policy.json --output report.json
execweave-integrity seal .execweave/runs/<run-id>
execweave-integrity verify .execweave/runs/<run-id>
```

## Run artifacts

Provider-integrated run 可能包含：

```text
.execweave/runs/<run-id>/
├── events.jsonl
├── graph.json
├── viewer.html
├── semantic.jsonl
├── content/sha256/...
├── conversations.md
├── conversations.json
├── events.semantic.jsonl
├── graph.semantic.json
├── viewer.semantic.html
├── events.correlated.jsonl
├── graph.correlated.json
├── viewer.correlated.html
└── integrity.json
```

Raw observation 與 derived semantic/correlation output 會維持分離。

## 限制與隱私

- Portable collector 可在 Linux、macOS、Windows 使用。Portable filesystem observation 屬於 session-correlated evidence，不一定能形成 process-causal attribution；polling 也可能漏掉非常短暫的活動。
- Linux 另外提供 `strace` reference backend，可在支援的執行中取得更強的 syscall-attributed evidence。
- Provider semantic coverage 完全取決於該 integration 真正暴露的資訊。未暴露的 Prompt、hidden reasoning、遠端 Provider internals 與 routing 無法被可靠重建。
- Full-fidelity Provider content 可能包含 Credential、Secret、Source code、Prompt、Tool value、Model response、Shell output 與 File content。
- Conversation isolation 是 attribution 規則，不是 redaction boundary。Provider 明確路由的內容可能合理地出現在多個參與者上。
- 本機 integrity manifest 可以檢查相對於 manifest 的檔案變化，但如果 evidence 與 manifest 都位於同一個可寫 trust boundary，就不是 adversary-resistant trusted logging system。
- 分享前請檢查完整 run directory。

## 開發

執行測試：

```bash
python -m pytest
```

執行 lint：

```bash
python -m ruff check .
```

歡迎提出 Issue 與 Pull Request。新增 integration 時，請明確區分「直接觀察」、「Provider 提供」與「推導所得」的 evidence。

## 授權

ExecWeave 使用 **PolyForm Noncommercial License 1.0.0**。完整條款請見 [LICENSE](LICENSE)。
