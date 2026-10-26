<!-- i18n-nav:start -->
<p align="center">
  <a href="codex-hooks.md">English</a> |
  <a href="codex-hooks.zh-TW.md">繁體中文</a> |
  <a href="codex-hooks.zh-CN.md">简体中文</a> |
  <a href="codex-hooks.ja.md">日本語</a> |
  <strong>한국어</strong> |
  <a href="codex-hooks.fr.md">Français</a> |
  <a href="codex-hooks.de.md">Deutsch</a> |
  <a href="codex-hooks.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# OpenAI Codex 라이프사이클 훅

ExecWeave는 Codex 라이프사이클 훅 증거를 독립적인 OS 런타임 텔레메트리와 나란히 기록합니다. Provider 훅은 논리적인 Agent/도구 활동을 설명하지만, 직접적인 Tool → Process 인과관계를 주장하는 데 필요한 OS 자식 PID를 제공하지는 않습니다.

## 현재 훅 범위

`execweave-codex-hook --print-config`는 현재 다음 이벤트를 등록합니다.

- `PreToolUse`
- `PermissionRequest`
- `PostToolUse`
- `PreCompact`
- `PostCompact`
- `SessionStart`
- `SessionEnd`
- `UserPromptSubmit`
- `SubagentStart`
- `SubagentStop`
- `Stop`

업스트림에 없거나 사용할 수 없는 이벤트를 ExecWeave가 만들어내지는 않습니다. Codex 버전에 따라 훅 스키마와 디스패치 범위가 달라질 수 있습니다.

다음처럼 훅을 구성하고 한 번의 실행을 기록할 수 있습니다.

```bash
execweave-codex-hook --print-config
execweave-codex-record --open -- codex
```

Recorder는 실행별 semantic sidecar를 바인딩하고 runtime, semantic, correlated artifact를 서로 분리해서 유지합니다.

## Full-fidelity 콘텐츠

v0.6.5는 Codex 훅이 실제로 제공한 완전한 콘텐츠 값을 로컬 content-addressed store에 저장합니다. JSONL sidecar에는 큰 값을 직접 넣는 대신 참조를 기록합니다.

관측 가능한 콘텐츠에는 완전한 `UserPromptSubmit.prompt`, `tool_input`, `PostToolUse.tool_response`, permission-request의 tool input, 그리고 해당 필드가 훅에 전달될 때의 최종 assistant/subagent 메시지가 포함될 수 있습니다. 이 payload 안의 application-level 값은 그대로 보존되므로 secret-redacted 되었다고 가정하면 안 됩니다.

Adapter가 인식하는 알려진 transport credential은 별도의 provider-metadata projection에서 제외됩니다. 이 필터링은 콘텐츠 payload 자체를 다시 쓰거나 정제하지 않습니다.

`content_complete_from_source: true`는 Codex integration point가 제공한 전체 값을 저장했다는 뜻입니다. ExecWeave가 transcript 파일을 읽었다거나, 보이지 않는 provider request를 가로챘다거나, hidden model state를 관측했다는 뜻은 아닙니다.

## Tool identity와 correlation

Codex가 `tool_use_id`를 제공하면 ExecWeave는 이를 논리적인 tool-call identity로 사용합니다. 선언된 command는 provider semantic evidence로 남습니다. 훅은 여전히 자식 OS PID를 제공하지 않으므로 Tool → Process bridge는 독립적인 런타임 증거에서 하나의 후보가 유일하게 지지될 때만 보수적 correlation 단계가 생성합니다.

```text
inferred: true
causal: false
```

모호하거나, 매칭되지 않거나, shell builtin/compound/unsupported command인 경우 bridge를 만들지 않습니다. 시간이나 command 문자열이 비슷하다는 이유만으로 provider evidence를 OS attribution으로 승격하지 않습니다.

## Privacy와 evidence boundary

Codex semantic/content artifact에는 prompt, command, tool argument/result, 최종 응답, path, identifier, application-level secret가 포함될 수 있습니다. 공유하기 전에 전체 run directory를 민감한 자료로 취급하고 검토하십시오.

Adapter는 모든 Codex 실행 모드가 완전한 lifecycle coverage를 제공한다고 주장하지 않습니다. 훅이 빠지면 semantic visibility가 줄어들지만 독립적인 OS runtime collector는 계속 동작합니다. Provider 훅만으로 선언된 command가 실행되었다거나, file action이 실제로 발생했다거나, resource 사이에 byte가 흘렀다고 증명할 수는 없습니다.
