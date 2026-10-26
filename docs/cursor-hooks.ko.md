# Cursor Hooks

<!-- i18n-nav:start -->
<p align="center">
  <a href="cursor-hooks.md">English</a> |
  <a href="cursor-hooks.zh-TW.md">繁體中文</a> |
  <a href="cursor-hooks.zh-CN.md">简体中文</a> |
  <a href="cursor-hooks.ja.md">日本語</a> |
  <strong>한국어</strong> |
  <a href="cursor-hooks.fr.md">Français</a> |
  <a href="cursor-hooks.de.md">Deutsch</a> |
  <a href="cursor-hooks.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

ExecWeave는 Cursor의 native hook surface를 사용해 provider semantic/content evidence를 run에 추가하지만, 이 evidence를 OS causality로 취급하지 않습니다.

## 빠른 시작

```bash
execweave-cursor-hook --print-config
execweave-cursor-record --open -- cursor
```

Run-bound recorder는 runtime, semantic, correlated artifact를 서로 분리해서 유지합니다.

## Observation surface

v0.6.5 훅 설정은 Cursor가 노출하는 경우 session start/end, tool before/after/failure, subagent, shell 및 MCP 실행, file read/edit, prompt submission, compaction/stop, Agent response/thought 이벤트, tab file read/edit 이벤트를 포함한 더 넓은 lifecycle surface를 다룹니다.

Cursor는 tool hook에 안정적인 논리 tool-call identity를 제공합니다. 이 identity는 OS PID가 아닙니다.

## Full-fidelity 콘텐츠

Cursor가 콘텐츠 값을 명시적으로 제공하면 v0.6.5는 그 전체 값을 로컬 content-addressed store에 저장하고 semantic JSONL에는 참조만 기록합니다.

Regression coverage에는 완전한 prompt text, tool input/output 및 failure text, shell command/output, MCP command/input/result, read hook이 제공한 file content, edit structure, 최종 Agent response, provider가 thought로 표시한 text, subagent summary가 포함됩니다.

이 값들은 provider observation으로 보존되며 evidence limitation도 그대로 유지됩니다. 예를 들어 `beforeReadFile`이 제공한 content는 OS read가 완료되었다는 뜻이 아니고, edit structure 역시 provider가 실제 complete post-edit snapshot을 제공하지 않았다면 전체 수정 후 파일을 증명하지 않습니다.

정의된 곳에서는 알려진 transport credential을 provider-metadata projection에서 필터링합니다. Content value 안에 포함된 secret은 보존됩니다. Full-fidelity content는 일반적인 secret-redaction layer가 아닙니다.

## Tool to process correlation

Cursor 훅 evidence는 자식 OS PID를 제공하지 않습니다. 따라서 Shell 호출은 독립 runtime evidence가 하나의 후보를 유일하게 지지할 때만 process bridge가 됩니다.

```text
inferred: true
causal: false
```

모호하거나 지원되지 않는 호출에는 bridge를 만들지 않습니다. 안정적인 provider tool-call identity는 Cursor 내부의 논리 identity를 증명할 뿐 machine-level process attribution을 증명하지 않습니다.

## Privacy와 evidence boundary

Cursor run evidence에는 prompt, tool argument/result, shell output, file content, edit data, assistant response, provider-labeled thought text, command, path, identifier, MCP value, embedded application secret가 포함될 수 있습니다. 공유 전에 전체 run directory를 검토하십시오.

Cursor 훅은 Cursor가 provider layer에서 보고하거나 제공한 내용만 증명합니다. 그 자체로 선언된 command가 실행되었거나 특정 process가 file에 접근했거나 resource 사이에 byte가 흘렀음을 증명하지 않습니다.
