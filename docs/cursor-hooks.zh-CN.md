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

ExecWeave 使用 Cursor 原生 Hook，将 Agent / Tool / Command 的逻辑语义证据加入执行图，同时不会把 provider metadata 误当成 OS 因果证据。

## 快速开始

生成 Hook 配置并加入 Cursor 的 hook settings：

```bash
execweave-cursor-hook --print-config
```

然后记录一次 Cursor 运行：

```bash
execweave-cursor-record --open -- cursor
```

run-bound recorder 会分别保存 runtime、semantic 与 correlated artifacts。

## 事件

当前 baseline 使用：

- `sessionStart`
- `preToolUse`
- `postToolUse`
- `postToolUseFailure`

Cursor 提供稳定的 `tool_use_id`，因此 `preToolUse` 与对应 post hook 可以共享精确的 logical `tool_call` identity。

典型语义边如下：

```text
agent --USED_MODEL--> model
agent --REQUESTED_TOOL_CALL--> tool_call
tool_call --USES_TOOL--> tool
tool_call --DECLARED_COMMAND--> command
tool_call --DECLARED_TARGET--> file
tool_call --TOOL_CALL_RETURNED--> tool
```

`postToolUseFailure` 会另外表示为 `TOOL_CALL_FAILED`。

## Tool → Process correlation

Cursor Hook 不提供 OS child PID，因此 Shell call 不会直接变成 process edge。

只有当 runtime evidence 能独立找到唯一且有足够支持的 process 时，ExecWeave 才可能派生：

```text
tool_call --CORRELATED_WITH_PROCESS--> process
```

该 bridge 始终为：

```text
inferred: true
causal: false
```

候选模糊或不支持时不会建立 edge。

## 隐私边界

Adapter 默认不保存 prompt、transcript path、用户 email、agent message 或 tool output。只保留 observability 所需的 identifiers 与 declared metadata，例如 model identity、conversation/generation IDs、tool name/use ID、command 和 declared file path。

Command 与 path 本身仍可能敏感，分享 artifacts 前请先检查。

## Evidence boundary

Cursor Hook 只能证明 Cursor 在 semantic layer 报告了什么。它不能证明 declared command 一定执行、declared file 一定被访问，也不能证明数据在资源之间流动。实际 runtime 行为仍以 OS collector evidence 为准。