# OpenCode Plugin

<!-- i18n-nav:start -->
<p align="center">
  <a href="opencode-plugin.md">English</a> |
  <a href="opencode-plugin.zh-TW.md">繁體中文</a> |
  <strong>简体中文</strong> |
  <a href="opencode-plugin.ja.md">日本語</a> |
  <a href="opencode-plugin.ko.md">한국어</a> |
  <a href="opencode-plugin.fr.md">Français</a> |
  <a href="opencode-plugin.de.md">Deutsch</a> |
  <a href="opencode-plugin.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

ExecWeave 通过 project-local plugin 与 OpenCode 集成。OpenCode 在 `tool.execute.before` 与 `tool.execute.after` 中都提供精确的 `sessionID + callID`，因此同一个 logical tool call 不需要依赖 heuristic 来配对 lifecycle events。

## 安装

在当前项目安装生成的 plugin：

```bash
execweave-opencode-plugin --install
```

它会创建：

```text
.opencode/plugins/execweave.ts
```

OpenCode 会自动加载该目录下的 project plugin。若文件已存在，ExecWeave 默认拒绝覆盖，除非明确使用 `--force`。

随后记录运行：

```bash
execweave-opencode-record --open -- opencode
```

## 捕获的 semantic evidence

当前 baseline 只发送最小 metadata：

- `chat.message`
- `tool.execute.before`
- `tool.execute.after`

典型 Graph 关系：

```text
agent --USED_MODEL--> model
agent --REQUESTED_TOOL_CALL--> tool_call
tool_call --USES_TOOL--> tool
tool_call --DECLARED_COMMAND--> command
tool_call --DECLARED_TARGET--> file
tool_call --TOOL_CALL_RETURNED--> tool
```

OpenCode 的 `callID` 直接用于 `tool_call` identity。

## 隐私边界

OpenCode 的 after-hook 可以看到 tool output，但 ExecWeave 生成的 plugin **不会**转发 `output.output` 或 `output.metadata`。

Plugin 会先缩减 arguments：

- `bash`：只保留 declared `command`
- file-oriented tools：只保留 `filePath`、`file_path`、`path` 等 path 字段
- 可选的 working-directory metadata

Raw write content、chat message parts 和 tool output 都不会发送给 ExecWeave hook。

## Tool → Process correlation

`callID` 能证明 OpenCode 内部的 logical call identity，但它不是 OS PID。Tool → Process 仍是保守的 derived bridge，仅在 runtime evidence 找到唯一且有足够支持的 process 时建立。

Derived bridge 始终保持 `inferred: true`、`causal: false`。

## Evidence boundary

Plugin 报告的是 OpenCode semantic intent。Process/file/network 的实际 runtime observation 仍由 OS collector 独立建立。ExecWeave 不会把 provider plugin 当作 declared command 或 file action 已真正发生的证明。