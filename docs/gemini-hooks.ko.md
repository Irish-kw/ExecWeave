<!-- i18n-nav:start -->
<p align="center">
  <a href="gemini-hooks.md">English</a> |
  <a href="gemini-hooks.zh-TW.md">繁體中文</a> |
  <a href="gemini-hooks.zh-CN.md">简体中文</a> |
  <a href="gemini-hooks.ja.md">日本語</a> |
  <strong>한국어</strong> |
  <a href="gemini-hooks.fr.md">Français</a> |
  <a href="gemini-hooks.de.md">Deutsch</a> |
  <a href="gemini-hooks.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# Gemini CLI Hooks

ExecWeave는 Gemini CLI 훅을 provider semantic/content evidence로 수집하고, 이 계층을 독립적으로 수집한 OS runtime evidence와 분리해서 유지합니다. Gemini 훅은 provider가 무엇을 노출했는지를 설명하지만, 그 자체로 어떤 OS process가 동작을 수행했는지를 증명하지는 않습니다.

## 현재 훅 범위

`execweave-gemini-hook --print-config`는 현재 다음 이벤트를 등록합니다.

- `SessionStart`
- `SessionEnd`
- `BeforeAgent`
- `AfterAgent`
- `BeforeModel`
- `AfterModel`
- `BeforeToolSelection`
- `BeforeTool`
- `AfterTool`
- `PreCompress`
- `Notification`

Tool 훅은 provider matcher surface를 사용하며 생성된 command hook은 기본적으로 fail-open입니다. 다음처럼 구성하고 기록할 수 있습니다.

```bash
execweave-gemini-hook --print-config
execweave-gemini-record --open -- gemini
```

## Full-fidelity 콘텐츠

v0.6.5는 Gemini 훅이 명시적으로 제공한 완전한 값을 로컬 content-addressed store에 저장합니다. 이벤트에 따라 user prompt, 전체 model request object, model response/chunk object, tool input, `llmContent` / `returnDisplay` / provider error field를 포함한 tool response, 최종 Agent response 및 훅이 제공한 기타 provider payload가 포함될 수 있습니다.

JSONL semantic sidecar에는 큰 값을 직접 넣는 대신 content reference를 기록합니다. 동일한 값은 SHA-256 기준으로 deduplicate됩니다.

Provider-metadata projection은 authorization header 같은 인식 가능한 transport-credential field를 제외합니다. 하지만 이 필터링은 full content 안의 application-level 값을 정제하지 않습니다. 예를 들어 tool input이나 model request 안에 secret이 들어 있으면 full fidelity의 일부로 그대로 보존됩니다.

`content_complete_from_source: true`는 ExecWeave가 전달받은 전체 field/value를 저장했다는 뜻입니다. Gemini가 hidden final wire request, internal model state 또는 훅 payload에 없던 단계를 노출했다는 뜻은 아닙니다.

## Tool identity와 correlation

Gemini는 `BeforeTool`과 `AfterTool` 사이에 공유되는 하나의 unique tool-call ID를 제공하지 않습니다. ExecWeave는 따라서 직접적인 before/after identity edge를 만들어내지 않습니다. Deterministic tool fingerprint는 진단 hint로 남을 수 있지만 반복된 동일 호출은 별개의 observation입니다.

Gemini 훅은 자식 OS PID도 제공하지 않습니다. 따라서 Tool → Process bridge는 독립적인 runtime evidence가 하나의 후보만 유일하게 지지할 때만 파생됩니다.

```text
inferred: true
causal: false
```

모호하거나, 매칭되지 않거나, compound/shell-builtin/unsupported command인 경우 bridge를 생성하지 않습니다.

## Privacy와 evidence boundary

Gemini content artifact에는 prompt, 전체 model request/response 값, tool input/result, tool이 반환한 file content, MCP/application field, 최종 response, identifier, command, path, embedded secret가 포함될 수 있습니다. 공유 전에 run directory 전체를 민감한 자료로 취급하고 검토하십시오.

훅이 `transcript_path`를 보고했다는 이유만으로 ExecWeave가 이를 자동으로 읽지는 않습니다. 저장된 provider value 역시 OS 실행, 완료된 file access 또는 byte-level data flow를 증명하지 않습니다. 독립 runtime evidence와 명시적으로 표시된 correlation은 별도 계층으로 유지됩니다.
