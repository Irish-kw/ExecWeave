# OpenCode Plugin

<!-- i18n-nav:start -->
<p align="center">
  <a href="opencode-plugin.md">English</a> |
  <a href="opencode-plugin.zh-TW.md">繁體中文</a> |
  <a href="opencode-plugin.zh-CN.md">简体中文</a> |
  <a href="opencode-plugin.ja.md">日本語</a> |
  <strong>한국어</strong> |
  <a href="opencode-plugin.fr.md">Français</a> |
  <a href="opencode-plugin.de.md">Deutsch</a> |
  <a href="opencode-plugin.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

ExecWeave는 project-local plugin을 통해 OpenCode와 통합됩니다. OpenCode는 tool before/after hook에서 정확한 `sessionID + callID` 값을 노출하므로 heuristic pairing 없이 하나의 논리 tool call을 식별할 수 있습니다. 이 identity는 provider-level evidence이며 OS PID가 아닙니다.

## 설치와 기록

```bash
execweave-opencode-plugin --install
execweave-opencode-record --open -- opencode
```

생성된 plugin은 `.opencode/plugins/execweave.ts`에 설치됩니다. `--force`를 명시하지 않으면 기존 plugin을 덮어쓰지 않습니다.

## 전체 observation surface

v0.6.5는 예전의 세 이벤트 minimal-metadata contract에 제한되지 않습니다. 생성된 plugin/hook 경로는 해당 훅이 실행될 때 chat message, tool execution before/after, model-context/system transform, 완료된 assistant text, provider bus event, credential filtering 후 request header, tool definition, command, permission request, compaction context 등 OpenCode가 노출한 content를 보존할 수 있습니다.

논리 graph relation은 계속 Agent → tool call, tool call → tool, declared command/target, returned-result observation 등을 포함합니다. Content storage는 이들의 evidence semantics를 바꾸지 않습니다.

## Full-fidelity 콘텐츠

OpenCode plugin이 제공한 완전한 값은 로컬 content-addressed store에 저장되고 semantic JSONL sidecar에서는 참조됩니다. Regression coverage에는 complete chat message/part, tool args/result, model context, system prompt, assistant text, provider event, tool definition, command argument/part, permission data, compaction prompt/context가 포함됩니다.

Authorization/cookie 같은 알려진 transport credential은 관련 header/provider-metadata projection에서 필터링됩니다. Tool args, message, result 또는 다른 content value 안의 application-level secret은 보존됩니다. Full-fidelity content가 secret-redacted 되었다고 가정하지 마십시오.

## Tool to process correlation

`sessionID + callID`는 OpenCode 내부의 정확한 논리 call identity를 증명하지만 어떤 OS process가 이를 실행했는지는 증명하지 않습니다. Tool → Process는 별도의 보수적 derived bridge이며 독립 runtime evidence가 하나의 process를 유일하게 지지할 때만 생성됩니다.

```text
inferred: true
causal: false
```

모호하거나 지원되지 않는 call에는 bridge가 없습니다.

## Privacy와 evidence boundary

OpenCode run evidence에는 prompt/message, system/context data, tool argument/output, command, permission pattern, provider event content, path, identifier, application secret가 포함될 수 있습니다. 공유 전에 run directory를 민감한 자료로 취급하고 검토하십시오.

Plugin은 OpenCode가 semantic/provider layer에서 노출한 내용만 증명합니다. Runtime collector는 process/file/network observation을 독립적으로 확립합니다. Full-fidelity provider content만으로 command execution, completed file access 또는 byte-level data flow를 증명할 수는 없습니다.
