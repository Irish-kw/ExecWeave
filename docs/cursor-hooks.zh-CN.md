# Cursor Hooks

<!-- i18n-nav:start -->
<p align="center">
  <a href="cursor-hooks.md">English</a> |
  <a href="cursor-hooks.zh-TW.md">繁體中文</a> |
  <strong>简体中文</strong> |
  <a href="cursor-hooks.ja.md">日本語</a> |
  <a href="cursor-hooks.ko.md">한국어</a> |
  <a href="cursor-hooks.fr.md">Français</a> |
  <a href="cursor-hooks.de.md">Deutsch</a> |
  <a href="cursor-hooks.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

ExecWeave 使用 Cursor 的 native hook surface，把 provider semantic/content evidence 加入 run，同时不把这些 evidence 当成 OS causality。

## 快速开始

```bash
execweave-cursor-hook --print-config
execweave-cursor-record --open -- cursor
```

Run-bound recorder 会把 runtime、semantic、correlated artifacts 分开保存。

## Observation surface

v0.6.5 hook configuration 覆盖更完整的 Cursor lifecycle surface，包括 session start/end、tool before/after/failure、subagents、shell 与 MCP execution、file read/edit、prompt submission、compaction/stop、Agent response/thought，以及 Cursor 暴露时的 tab file read/edit events。

Cursor 对 tool hooks 提供稳定 logical tool-call identity；但该 identity 不是 OS PID。

## Full-fidelity content

Cursor 明确提供 content value 时，v0.6.5 会把完整值存入本地 content-addressed store，semantic JSONL event 只保留 reference。

Regression coverage 包括完整 prompt text、tool input/output 与 failure text、shell command/output、MCP command/input/result、read hook 提供的 file content、edit structure、final Agent response、provider-labeled thought text 与 subagent summary。

这些字段仍以 provider observation 保存，并保留 evidence limitation。例如 `beforeReadFile` 提供的 content 不表示 OS read 已完成；edit structure 也不表示完整 post-edit file snapshot，除非 provider 确实提供该 snapshot。

已知 transport credentials 会在有定义的 provider-metadata projection 中过滤。Content value 内嵌的 secret 仍会保存；full-fidelity content 不是通用 secret-redaction layer。

## Tool to process correlation

Cursor hook evidence 不提供 child OS PID。因此 Shell call 只有在独立 runtime evidence 找到唯一受支持 candidate 时才会变成 process bridge：

```text
inferred: true
causal: false
```

Ambiguous 或 unsupported call 不会建立 bridge。Stable provider tool-call identity 只证明 Cursor 内部 logical identity，不等于 machine-level process attribution。

## Privacy 与 evidence boundary

Cursor run evidence 可能包含 prompt、tool argument/result、shell output、file content、edit data、assistant response、provider-labeled thought text、command、path、identifier、MCP values 与 embedded application secrets。分享前请检查完整 run directory。

Cursor hook 只证明 Cursor 在 provider layer 报告或提供了什么；它不能单独证明 declared command 确实执行、特定 process 访问某文件，或 bytes 在 resources 间流动。
