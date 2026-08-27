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

ExecWeave 通过 project-local plugin 集成 OpenCode。OpenCode 在 tool before/after hook 上提供精确 `sessionID + callID`，因此单个 logical tool call 可以直接识别，不需要 heuristic pairing。这仍只是 provider-level identity evidence，不是 OS PID。

## 安装与记录

```bash
execweave-opencode-plugin --install
execweave-opencode-record --open -- opencode
```

生成的 plugin 安装在 `.opencode/plugins/execweave.ts`。除非明确提供 `--force`，ExecWeave 不会覆盖已有 plugin。

## 完整 observation surface

v0.6.5 已不再受限于旧的三-event minimal-metadata contract。当 OpenCode hook 触发时，generated plugin/hook path 可以保存 chat messages、tool execution before/after、model-context/system transforms、completed assistant text、provider bus events、credential filtering 后的 request headers、tool definitions、commands、permission requests 与 compaction context 等 OpenCode 明确暴露的内容。

典型 logical graph relationship 仍包括 Agent → tool call、tool call → tool、declared command/target 与 returned-result observation。Content storage 不会改变其 evidence semantics。

## Full-fidelity content

OpenCode plugin 提供的完整值会存入本地 content-addressed store，再由 semantic JSONL sidecar reference。Regression coverage 包括完整 chat message/parts、tool args/results、model context、system prompt values、assistant text、provider events、tool definitions、command arguments/parts、permission data 与 compaction prompt/context。

Authorization/cookie 等已知 transport credentials 会从相关 headers/provider-metadata projection 过滤；但 tool args、message、result 或其他 content value 中的 application-level secrets 仍会保存。不要假设 full-fidelity content 已完成 secret redaction。

## Tool to process correlation

`sessionID + callID` 只证明 OpenCode 内部 exact logical call identity，不能证明哪个 OS process 执行了该 call。Tool → Process 仍是另外 derivation 的 conservative bridge，且只有独立 runtime evidence 找到唯一受支持 process 时才会建立。

```text
inferred: true
causal: false
```

Ambiguous 或 unsupported call 不会建立 bridge。

## Privacy 与 evidence boundary

OpenCode run evidence 可能包含 prompt/message、system/context data、tool argument/output、command、permission pattern、provider event content、path、identifier 与 application secrets。整个 run directory 都应视为敏感数据，分享前请检查。

Plugin 只证明 OpenCode 在 semantic/provider layer 明确暴露了什么。Runtime collector 会独立建立 process/file/network observation；full-fidelity provider content 不能单独证明 command execution、完成 file access 或 byte-level data flow。
