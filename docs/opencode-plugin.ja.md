# OpenCode Plugin

<!-- i18n-nav:start -->
<p align="center">
  <a href="opencode-plugin.md">English</a> |
  <a href="opencode-plugin.zh-TW.md">繁體中文</a> |
  <a href="opencode-plugin.zh-CN.md">简体中文</a> |
  <strong>日本語</strong> |
  <a href="opencode-plugin.ko.md">한국어</a> |
  <a href="opencode-plugin.fr.md">Français</a> |
  <a href="opencode-plugin.de.md">Deutsch</a> |
  <a href="opencode-plugin.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

ExecWeave は project-local plugin を通じて OpenCode と統合します。OpenCode は tool before/after hook で正確な `sessionID + callID` を公開するため、heuristic pairing なしで一つの logical tool call を識別できます。この identity は provider-level evidence であり OS PID ではありません。

## インストールと記録

```bash
execweave-opencode-plugin --install
execweave-opencode-record --open -- opencode
```

生成された plugin は `.opencode/plugins/execweave.ts` に配置されます。`--force` を明示しない限り ExecWeave は既存 plugin を上書きしません。

## Full observation surface

v0.6.5 は旧 three-event minimal-metadata contract に限定されません。Hook が発火した場合、generated plugin/hook path は chat messages、tool execution before/after、model-context/system transforms、completed assistant text、provider bus events、credential filtering 後の request headers、tool definitions、commands、permission requests、compaction context など OpenCode が公開する content を保存できます。

典型的な logical graph relationship は Agent → tool call、tool call → tool、declared command/target、returned-result observation を引き続き含みます。Content storage は evidence semantics を変更しません。

## Full-fidelity content

OpenCode plugin が提供する完全な値はローカル content-addressed store に保存され、semantic JSONL sidecar から reference されます。Regression coverage には complete chat message/parts、tool args/results、model context、system prompt values、assistant text、provider events、tool definitions、command arguments/parts、permission data、compaction prompts/context が含まれます。

Authorization/cookie など既知の transport credentials は関連 headers/provider-metadata projection から除外されます。一方、tool args、messages、results、その他 content values に埋め込まれた application-level secrets は保存されます。Full-fidelity content が secret-redacted 済みだと仮定しないでください。

## Tool to process correlation

`sessionID + callID` は OpenCode 内部の exact logical call identity を証明しますが、どの OS process が call を実行したかは証明しません。Tool → Process は別途導出される conservative bridge であり、独立 runtime evidence が唯一の supported process を示す場合だけ生成されます。

```text
inferred: true
causal: false
```

Ambiguous / unsupported call では bridge を作りません。

## Privacy と evidence boundary

OpenCode run evidence には prompts/messages、system/context data、tool arguments/output、commands、permission patterns、provider event content、paths、identifiers、application secrets が含まれる可能性があります。Run directory を sensitive として扱い、共有前に確認してください。

Plugin は semantic/provider layer で OpenCode が公開した内容だけを証明します。Runtime collectors が process/file/network observation を独立して確立します。Full-fidelity provider content だけでは command execution、completed file access、byte-level data flow は証明されません。
