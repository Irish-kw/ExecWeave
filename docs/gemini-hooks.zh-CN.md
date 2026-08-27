<!-- i18n-nav:start -->
<p align="center">
  <a href="gemini-hooks.md">English</a> |
  <a href="gemini-hooks.zh-TW.md">繁體中文</a> |
  <strong>简体中文</strong> |
  <a href="gemini-hooks.ja.md">日本語</a> |
  <a href="gemini-hooks.ko.md">한국어</a> |
  <a href="gemini-hooks.fr.md">Français</a> |
  <a href="gemini-hooks.de.md">Deutsch</a> |
  <a href="gemini-hooks.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# Gemini CLI Hooks

ExecWeave 将 Gemini CLI hook 作为 provider semantic/content evidence，并与独立采集的 OS runtime evidence 分层保存。Gemini hook 只能说明 provider 明确暴露了什么，不能单独证明哪个 OS process 执行了某个 action。

## 当前 hook surface

`execweave-gemini-hook --print-config` 当前注册：

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

Tool hook 使用 provider matcher surface，生成的 command hook 默认 fail-open。配置后可使用：

```bash
execweave-gemini-hook --print-config
execweave-gemini-record --open -- gemini
```

## Full-fidelity content

v0.6.5 将 Gemini hook 明确提供的完整值保存到本地 content-addressed store。根据 event 不同，可包括 user prompt、完整 model request object、model response/chunk object、tool input、tool response（包括 `llmContent` / `returnDisplay` / provider error fields）、final Agent response，以及 hook 暴露的其他 provider payload values。

JSONL semantic sidecar 只保存 content reference，不 inline 大型值。重复的相同内容按 SHA-256 去重。

Provider-metadata projection 会排除识别出的 transport-credential fields，例如 authorization header。但这不会清理 full content 中的 application-level values；若 secret 嵌在 tool input 或 model request 中，它仍会被保存。

`content_complete_from_source: true` 表示 ExecWeave 完整保存收到的 field/value；不代表 Gemini 暴露了 hidden final wire request、internal model state，或 hook payload 中不存在的 stage。

## Tool identity 与 correlation

Gemini 不提供一个由 `BeforeTool` 和 `AfterTool` 共享的 unique tool-call ID，因此 ExecWeave 不会伪造 direct before/after identity edge。Deterministic tool fingerprint 可作为 diagnostic hint，但重复相同 call 仍是不同 observations。

Gemini hook 也不提供 child OS PID。因此 Tool → Process bridge 只有在独立 runtime evidence 找到唯一受支持 candidate 时才会导出：

```text
inferred: true
causal: false
```

Ambiguous、unmatched、compound、shell-builtin 或 unsupported command 都不会建立 bridge。

## Privacy 与 evidence boundary

Gemini content artifact 可能包含 prompt、完整 model request/response value、tool input/result、tool 返回的 file content、MCP/application fields、final response、identifier、command、path 与 embedded secrets。整个 run directory 都应视为敏感数据，分享前请检查。

ExecWeave 不会因为 hook 报告 `transcript_path` 就自动读取该文件。保存 provider value 也不能证明 OS execution、完成 file access 或 byte-level data flow。独立 runtime evidence 与明确标记的 correlation 仍是不同 evidence layer。
