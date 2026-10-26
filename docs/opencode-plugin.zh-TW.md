# OpenCode Plugin

<!-- i18n-nav:start -->
<p align="center">
  <a href="opencode-plugin.md">English</a> |
  <strong>繁體中文</strong> |
  <a href="opencode-plugin.zh-CN.md">简体中文</a> |
  <a href="opencode-plugin.ja.md">日本語</a> |
  <a href="opencode-plugin.ko.md">한국어</a> |
  <a href="opencode-plugin.fr.md">Français</a> |
  <a href="opencode-plugin.de.md">Deutsch</a> |
  <a href="opencode-plugin.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

ExecWeave 透過 project-local plugin 整合 OpenCode。OpenCode 在 tool before/after hook 上提供精確 `sessionID + callID`，因此單一 logical tool call 可直接識別，不需要 heuristic pairing。這仍只是 provider-level identity evidence，不是 OS PID。

## 安裝與記錄

```bash
execweave-opencode-plugin --install
execweave-opencode-record --open -- opencode
```

產生的 plugin 會安裝在 `.opencode/plugins/execweave.ts`。除非明確提供 `--force`，ExecWeave 不會覆寫既有 plugin。

## 完整 observation surface

v0.6.5 已不再受限於舊的三-event minimal-metadata contract。當 OpenCode hook 有觸發時，generated plugin/hook path 可以保留 chat messages、tool execution before/after、model-context/system transforms、completed assistant text、provider bus events、credential filtering 後的 request headers、tool definitions、commands、permission requests 與 compaction context 等 OpenCode 明確曝露的內容。

典型 logical graph relationship 仍包括 Agent → tool call、tool call → tool、declared command/target 與 returned-result observation。Content storage 不會改變其 evidence semantics。

## Full-fidelity content

OpenCode plugin 提供的完整值會存入本機 content-addressed store，再由 semantic JSONL sidecar reference。Regression coverage 包含完整 chat message/parts、tool args/results、model context、system prompt values、assistant text、provider events、tool definitions、command arguments/parts、permission data 與 compaction prompt/context。

Authorization/cookie 等已知 transport credentials 會從相關 headers/provider-metadata projection 過濾；但 tool args、message、result 或其他 content value 中的 application-level secrets 仍會保存。不要假設 full-fidelity content 已完成 secret redaction。

## Tool to process correlation

`sessionID + callID` 只證明 OpenCode 內部 exact logical call identity，不能證明哪個 OS process 執行了該 call。Tool → Process 仍是另外 derivation 的 conservative bridge，且只有獨立 runtime evidence 找到唯一受支持 process 時才會建立。

```text
inferred: true
causal: false
```

Ambiguous 或 unsupported call 不會建立 bridge。

## Privacy 與 evidence boundary

OpenCode run evidence 可能包含 prompt/message、system/context data、tool argument/output、command、permission pattern、provider event content、path、identifier 與 application secrets。整個 run directory 都應視為敏感資料，分享前請檢查。

Plugin 只證明 OpenCode 在 semantic/provider layer 明確曝露了什麼。Runtime collector 會獨立建立 process/file/network observation；full-fidelity provider content 不能單獨證明 command execution、完成 file access 或 byte-level data flow。
