<!-- i18n-nav:start -->
<p align="center">
  <a href="runtime-threat-model.md">English</a> |
  <a href="runtime-threat-model.zh-TW.md">繁體中文</a> |
  <strong>简体中文</strong> |
  <a href="runtime-threat-model.ja.md">日本語</a> |
  <a href="runtime-threat-model.ko.md">한국어</a> |
  <a href="runtime-threat-model.fr.md">Français</a> |
  <a href="runtime-threat-model.de.md">Deutsch</a> |
  <a href="runtime-threat-model.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# Runtime 威胁模型与已知规避边界

本文定义 ExecWeave v0.6.5 作为可测试契约的一部分所承认的观测限制。这是**可观测性威胁模型**，而不是 sandbox 安全保证：被观测命令可以是不可信的，也可能主动尝试隐藏活动；但假设操作系统内核和 ExecWeave 安装本身没有遭到内核级攻陷。

## Portable backend

Portable backend 使用 psutil snapshot 观测 process/network，并使用 watchdog 观测 filesystem 变化。

- **短生命周期 process：** 如果 child 在两次 process sample 之间启动并退出，可能完全漏掉。配置的 poll interval 也不是 blind window 的保证上限，因为 scheduler delay 可能使实际间隔更长。
- **短生命周期 socket：** 如果连接在两次 socket observation 之间建立并消失，可能漏掉；权限或平台 API 限制也可能隐藏 socket state。
- **比 root command 存活更久的 descendant：** root observation 结束时，如果 child 仍然存活，ExecWeave 不会伪造 exit event；但 portable run 不是 always-on monitor。之后仍存活或被 reparent 的 descendant 所执行的活动超出该已完成 run 的观测窗口。
- **Filesystem attribution：** watchdog 变化是 session-correlated observation，明确标记为 `causal=false`，不能证明某个特定 PID 执行了写入。
- **Negative evidence：** portable backend 中缺少 process/network/filesystem event，不能解释为相关活动没有发生。

## Linux strace backend

strace backend 使用 `strace -ff` 跟踪所启动 command 的 lineage 和选定 syscall 类别。

- 在 traced lineage 内，clone/fork 证据能够保留 portable polling 可能漏掉的短命 descendant。
- 存在受支持的 syscall 证据时，filesystem 和 network event 可以归因到被 trace 的 process。
- 这**不是 OS-wide visibility**。trace lineage 之外的活动、未支持或未解析的 syscall pattern、permission/ptrace 限制以及所选 evidence class 之外的 kernel behavior 都不在能力声明之内。
- open 的 read/write access mode 不等于 byte-level data flow；ExecWeave 不声明知道 process 后续实际读取或写入的内容。

## Specialized hooks 与 direct API integrations

Claude、Codex、Gemini、Cursor、OpenCode、model-runtime、gateway、proxy 和 direct-API integration 可以在明确 integration point 提供更强的 semantic content evidence，但不会揭示 provider-hidden state。

- response-only integration 只能证明提供给 ExecWeave 的 response fields。
- caller-supplied request+response exchange 只能证明该份提供的 exchange；不能声称 transparent wire interception。
- hook coverage 受 upstream agent/IDE 实际暴露给 hook 的数据限制。
- full-fidelity storage 表示完整保存 integration point 实际暴露的内容，不表示完整看见 model provider 或 operating system 的全部状态。

## Regression contract

`tests/test_threat_model.py` 使用 deterministic executable tests 固定以下边界：

1. 仅存在于两次 process sample 之间的 portable child；
2. 仅存在于两次 socket sample 之间的 portable socket；
3. root-process observation 结束时仍存活的 child，不伪造 exit event；
4. portable filesystem change 仍保持 session-correlated、non-causal；
5. 对应的 strace trace case 能为短命 child 保留 `SPAWNED` attribution。

测试刻意不采用“sleep N 毫秒并希望 CI 恰好漏掉”这种 timing race，而是把 blind window 建模为两次 observation 之间的显式状态，因此可在 Linux、macOS、Windows 上稳定复现。

## Missing event 表示什么

Missing event 只表示该 run 的 canonical evidence 中没有这项 observation。在未来某个 backend 明确定义并证明完整的 negative-evidence scope 之前，它不是“事件没有发生”的证据。Finding severity 与 evidence fidelity 必须保持为两个独立维度。
