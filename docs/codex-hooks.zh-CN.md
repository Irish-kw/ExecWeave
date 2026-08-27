<!-- i18n-nav:start -->
<p align="center">
  <a href="codex-hooks.md">English</a> |
  <a href="codex-hooks.zh-TW.md">繁體中文</a> |
  <strong>简体中文</strong> |
  <a href="codex-hooks.ja.md">日本語</a> |
  <a href="codex-hooks.ko.md">한국어</a> |
  <a href="codex-hooks.fr.md">Français</a> |
  <a href="codex-hooks.de.md">Deutsch</a> |
  <a href="codex-hooks.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# OpenAI Codex lifecycle hooks

ExecWeave 将 Codex lifecycle-hook evidence 与独立 OS runtime telemetry 并列保存。Provider hook 描述 logical Agent/tool activity，但不会提供建立直接 Tool → Process causality 所需的 OS child PID。

## 当前 hook surface

`execweave-codex-hook --print-config` 当前注册：

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
- `Interrupt`

ExecWeave 不会伪造 upstream 未知或不可用的 event。Hook schema 与 dispatch coverage 可能随 Codex 版本改变。

配置 hook 后记录 run：

```bash
execweave-codex-hook --print-config
execweave-codex-record --open -- codex
```

Recorder 绑定 run-specific semantic sidecar，并把 runtime、semantic、correlated artifacts 分开保存。

## Full-fidelity content

v0.6.5 会把 Codex hook 实际提供的完整 content value 存入本地 content-addressed store；JSONL sidecar 只留下 reference，不 inline 大型内容。

可观察 content 包括完整 `UserPromptSubmit.prompt`、完整 `tool_input`、完整 `PostToolUse.tool_response`、permission-request tool input，以及 hook 提供时的 final assistant/subagent message。Payload 中 application-level value 会原样保存；不要假设 secret 已被 redacted。

已知 transport credentials 只会在 adapter 能识别时从独立 provider-metadata projection 排除。这项过滤不会改写或 sanitize content payload 本身。

`content_complete_from_source: true` 表示保存了 Codex integration point 提供的完整值；不代表 ExecWeave 读取 transcript file、intercept 未暴露的 provider request，或看见 hidden model state。

## Tool identity 与 correlation

Codex 提供 `tool_use_id` 时，ExecWeave 将其作为 logical tool-call identity。Declared command 仍只是 provider semantic evidence。Hook 仍不提供 child OS PID，因此 Tool → Process bridge 只有在 conservative correlation stage 从 runtime evidence 找到唯一受支持 candidate 时才会建立。

```text
inferred: true
causal: false
```

Ambiguous、unmatched、shell-builtin、compound 或 unsupported command 都不会建立 bridge。不能只因为 timestamp 或 command string 相似，就把 provider evidence 升级成 OS attribution。

## Privacy 与 evidence boundary

Codex semantic/content artifact 可能包含 prompt、command、tool argument、tool result、final response、path、identifier 与 application-level secrets。整个 run directory 都应视为敏感数据，分享前请检查。

Adapter 不声称每种 Codex execution mode 都具备完整 lifecycle coverage。Missing hook 只会降低 semantic visibility，不会关闭独立 OS runtime collector。Provider hook 也不能证明 declared command 确实执行、file action 确实发生，或 bytes 在 resources 间流动。
