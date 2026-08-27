# Cursor Hooks

<!-- i18n-nav:start -->
<p align="center">
  <a href="cursor-hooks.md">English</a> |
  <strong>繁體中文</strong> |
  <a href="cursor-hooks.zh-CN.md">简体中文</a> |
  <a href="cursor-hooks.ja.md">日本語</a> |
  <a href="cursor-hooks.ko.md">한국어</a> |
  <a href="cursor-hooks.fr.md">Français</a> |
  <a href="cursor-hooks.de.md">Deutsch</a> |
  <a href="cursor-hooks.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

ExecWeave 使用 Cursor 的 native hook surface，把 provider semantic/content evidence 加入 run，同時不把這些 evidence 當成 OS causality。

## 快速開始

```bash
execweave-cursor-hook --print-config
execweave-cursor-record --open -- cursor
```

Run-bound recorder 會把 runtime、semantic、correlated artifacts 分開保存。

## Observation surface

v0.6.5 hook configuration 涵蓋更完整的 Cursor lifecycle surface，包括 session start/end、tool before/after/failure、subagents、shell 與 MCP execution、file read/edit、prompt submission、compaction/stop、Agent response/thought，以及 Cursor 有曝露時的 tab file read/edit events。

Cursor 對 tool hooks 提供穩定 logical tool-call identity；但該 identity 不是 OS PID。

## Full-fidelity content

Cursor 明確提供 content value 時，v0.6.5 會把完整值存入本機 content-addressed store，semantic JSONL event 只保留 reference。

Regression coverage 包含完整 prompt text、tool input/output 與 failure text、shell command/output、MCP command/input/result、read hook 提供的 file content、edit structure、final Agent response、provider-labeled thought text 與 subagent summary。

這些欄位仍以 provider observation 保存，並保留 evidence limitation。例如 `beforeReadFile` 提供的 content 不代表 OS read 已完成；edit structure 也不代表完整 post-edit file snapshot，除非 provider 真的提供該 snapshot。

已知 transport credentials 會在有定義的 provider-metadata projection 中過濾。Content value 內嵌的 secret 仍會被保存；full-fidelity content 不是通用 secret-redaction layer。

## Tool to process correlation

Cursor hook evidence 不提供 child OS PID。因此 Shell call 只有在獨立 runtime evidence 找到唯一受支持 candidate 時才會變成 process bridge：

```text
inferred: true
causal: false
```

Ambiguous 或 unsupported call 不會建立 bridge。Stable provider tool-call identity 只證明 Cursor 內部 logical identity，不等於 machine-level process attribution。

## Privacy 與 evidence boundary

Cursor run evidence 可能包含 prompt、tool argument/result、shell output、file content、edit data、assistant response、provider-labeled thought text、command、path、identifier、MCP values 與 embedded application secrets。分享前請檢查完整 run directory。

Cursor hook 只證明 Cursor 在 provider layer 回報或提供了什麼；它不能單獨證明 declared command 確實執行、特定 process 存取某檔案，或 bytes 在 resources 間流動。
