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

# OpenAI Codex lifecycle hooks

ExecWeave 會把 Codex lifecycle-hook evidence 與獨立 OS runtime telemetry 並列保存。Provider hook 描述 logical Agent/tool activity，但不會提供建立直接 Tool → Process causality 所需的 OS child PID。

## 目前 hook surface

`execweave-codex-hook --print-config` 目前註冊：

- `PreToolUse`
- `PermissionRequest`
- `PostToolUse`
- `PreCompact`
- `PostCompact`
- `SessionStart`
- `SessionEnd`
- `UserPromptSubmit`
- `SubagentStart`
- `SubagentStop`
- `Stop`

ExecWeave 不會捏造 upstream 未知或不可用的 event。Hook schema 與 dispatch coverage 可能隨 Codex 版本改變。

設定 hook 後記錄 run：

```bash
execweave-codex-hook --print-config
execweave-codex-record --open -- codex
```

Recorder 會綁定 run-specific semantic sidecar，並把 runtime、semantic、correlated artifacts 分開保存。

## Full-fidelity content

v0.6.5 會把 Codex hook 實際提供的完整 content value 存入本機 content-addressed store；JSONL sidecar 只留下 reference，不 inline 大型內容。

可觀察 content 包含完整 `UserPromptSubmit.prompt`、完整 `tool_input`、完整 `PostToolUse.tool_response`、permission-request tool input，以及 hook 有提供時的 final assistant/subagent message。Payload 內 application-level value 會原樣保存；不要假設 secret 已被 redacted。

已知 transport credentials 只會在 adapter 能辨識時從獨立 provider-metadata projection 排除。這項過濾不會改寫或 sanitize content payload 本身。

`content_complete_from_source: true` 表示保存了 Codex integration point 提供的完整值；不代表 ExecWeave 讀取 transcript file、intercept 未曝露的 provider request，或看見 hidden model state。

## Tool identity 與 correlation

Codex 提供 `tool_use_id` 時，ExecWeave 會把它當成 logical tool-call identity。Declared command 仍只是 provider semantic evidence。Hook 仍不提供 child OS PID，因此 Tool → Process bridge 只有在 conservative correlation stage 從 runtime evidence 找到唯一受支持 candidate 時才會建立。

```text
inferred: true
causal: false
```

Ambiguous、unmatched、shell-builtin、compound 或 unsupported command 都不會建立 bridge。不能只因 timestamp 或 command string 相似，就把 provider evidence 升級成 OS attribution。

## Privacy 與 evidence boundary

Codex semantic/content artifact 可能包含 prompt、command、tool argument、tool result、final response、path、identifier 與 application-level secrets。整個 run directory 都應視為敏感資料，分享前請檢查。

Adapter 不宣稱每種 Codex execution mode 都具有完整 lifecycle coverage。Missing hook 只會降低 semantic visibility，不會關閉獨立 OS runtime collector。Provider hook 也不能證明 declared command 確實執行、file action 確實發生，或 bytes 在 resources 間流動。
