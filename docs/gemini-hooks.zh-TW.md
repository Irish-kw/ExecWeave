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

ExecWeave 會把 Gemini CLI hook 當成 provider semantic/content evidence，並與獨立收集的 OS runtime evidence 分層保存。Gemini hook 只能說明 provider 明確曝露了什麼，不能單獨證明哪個 OS process 執行了某個 action。

## 目前 hook surface

`execweave-gemini-hook --print-config` 目前註冊：

- `SessionStart`
- `SessionEnd`
- `BeforeAgent`
- `AfterAgent`
- `BeforeModel`
- `AfterModel`
- `BeforeToolSelection`
- `BeforeTool`
- `AfterTool`
- `PreCompress`
- `Notification`

Tool hook 使用 provider matcher surface，產生的 command hook 預設 fail-open。設定後可用：

```bash
execweave-gemini-hook --print-config
execweave-gemini-record --open -- gemini
```

## Full-fidelity content

v0.6.5 會把 Gemini hook 明確提供的完整值保存到本機 content-addressed store。依 event 不同，可能包含 user prompt、完整 model request object、model response/chunk object、tool input、tool response（包含 `llmContent` / `returnDisplay` / provider error fields）、final Agent response，以及 hook 曝露的其他 provider payload values。

JSONL semantic sidecar 只保存 content reference，不 inline 大型值。重複的相同內容會依 SHA-256 去重。

Provider-metadata projection 會排除辨識出的 transport-credential fields，例如 authorization header。但這不會清理 full content 中的 application-level values；若 secret 嵌在 tool input 或 model request 裡，它仍會被保存。

`content_complete_from_source: true` 表示 ExecWeave 完整保存收到的 field/value；不代表 Gemini 曝露了 hidden final wire request、internal model state，或任何 hook payload 中不存在的 stage。

## Tool identity 與 correlation

Gemini 不提供一個由 `BeforeTool` 與 `AfterTool` 共用的 unique tool-call ID，因此 ExecWeave 不會捏造 direct before/after identity edge。Deterministic tool fingerprint 可保留作 diagnostic hint，但重複相同 call 仍是不同 observations。

Gemini hook 也不提供 child OS PID。因此 Tool → Process bridge 只有在獨立 runtime evidence 找到唯一受支持 candidate 時才會導出：

```text
inferred: true
causal: false
```

Ambiguous、unmatched、compound、shell-builtin 或 unsupported command 都不會建立 bridge。

## Privacy 與 evidence boundary

Gemini content artifact 可能包含 prompt、完整 model request/response value、tool input/result、tool 回傳的 file content、MCP/application fields、final response、identifier、command、path 與 embedded secrets。整個 run directory 都應視為敏感資料，分享前請檢查。

ExecWeave 不會因 hook 回報 `transcript_path` 就自動讀取該檔案。保存 provider value 也不能證明 OS execution、完成 file access 或 byte-level data flow。獨立 runtime evidence 與明確標記的 correlation 仍是不同 evidence layer。
