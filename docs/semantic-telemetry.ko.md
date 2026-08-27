<!-- i18n-nav:start -->
<p align="center">
  <a href="semantic-telemetry.md">English</a> |
  <a href="semantic-telemetry.zh-TW.md">繁體中文</a> |
  <a href="semantic-telemetry.zh-CN.md">简体中文</a> |
  <a href="semantic-telemetry.ja.md">日本語</a> |
  <strong>한국어</strong> |
  <a href="semantic-telemetry.fr.md">Français</a> |
  <a href="semantic-telemetry.de.md">Deutsch</a> |
  <a href="semantic-telemetry.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# Semantic Telemetry

ExecWeave는 provider/framework semantic observation과 독립적인 OS runtime evidence를 결합하지만 원본 runtime capture를 다시 쓰지 않습니다. Provider evidence는 Agent, tool, gateway, model-runtime integration point가 명시적으로 노출한 내용을 설명하고, OS evidence는 machine collector가 실제로 관측한 내용을 설명합니다. Correlation은 항상 별도의 derived layer이며 자동으로 causal proof로 승격되지 않습니다.

## Workflow

Provider adapter가 run-bound semantic sidecar를 기록한 뒤 ExecWeave가 새로운 merged stream을 검증합니다.

```bash
execweave semantic-merge run.jsonl semantic.jsonl --output run.semantic.jsonl
execweave validate run.semantic.jsonl
execweave graph run.semantic.jsonl --output run.semantic.graph.json
```

`semantic-merge`는 `run.jsonl`을 수정하지 않습니다. Run-bound recorder는 runtime, semantic, correlated artifact를 별도 파일로 보존합니다.

## v0.6.5 full-fidelity content

Semantic telemetry는 작은 metadata summary에만 제한되지 않습니다. 지원되는 integration point가 content를 명시적으로 제공하면 v0.6.5는 source가 제공한 전체 값을 로컬 content-addressed store에 저장하고 JSONL event에는 reference만 둘 수 있습니다.

```text
<run-root>/content/sha256/<sha256>.<json|txt|bin>
```

Content reference는 SHA-256, relative path, media type, byte size, content kind, representation, 해당 integration point 기준 complete from source 여부를 기록합니다. `complete_from_source: true`는 받은 전체 값을 보존했다는 뜻이며 hidden model state, 보이지 않은 final wire request, integration point가 전달하지 않은 field까지 provider가 노출했다는 뜻은 아닙니다.

Native adapter는 hook/API surface가 명시적으로 제공한 prompts, tool inputs/results, assistant/model responses, 명시적으로 제공된 reasoning/thinking text, provider hook이 제공한 file content, contract가 지원하는 provider request/response objects에 이 방식을 사용합니다.

Content store가 실패해도 compact semantic summary는 graph materialization에 사용할 수 있습니다. Native hook adapter는 기본 fail-open이므로 content-storage failure가 Agent operation을 의도적으로 차단하지 않습니다.

## Evidence boundary

Semantic content는 observed provider/integration evidence이지 OS causality가 아닙니다. 저장된 tool input이 process 실행을 증명하지 않고, hook이 제공한 file body가 OS read completion을 증명하지 않으며, CLI에 제공된 request/response pair가 transparent network interception을 의미하지도 않습니다.

Tool → Process bridge는 별도로 정의된 conservative correlation layer에서만 생성되며 다음을 유지합니다.

```text
inferred: true
causal: false
```

Unknown 또는 ambiguous attribution은 bridge를 만들지 않습니다. File과 network observation이 함께 존재한다고 해서 byte-level data flow나 exfiltration을 추론하지 않습니다.

## Privacy

Full-fidelity content는 본질적으로 sensitive합니다. Prompt text, tool arguments, tool output, model responses, file content, application-level secret values가 redacted되었다고 **가정하지 마세요**. Content store는 지원되는 integration point가 제공한 전체 값을 보존합니다.

ExecWeave는 adapter contract가 정의한 경우에만 provider-metadata projection에서 알려진 transport credentials를 필터링합니다. 이는 범용 secret scanner가 아니며 content payload 안의 secret을 제거하지 않습니다. Content blob은 기본적으로 로컬에 남고 graph event에 inline되지 않지만 여전히 run evidence의 일부이므로 공유 전 검토가 필요합니다.

각 provider-specific 문서가 관측 가능한 field를 정의합니다. Claude Code, Codex, Gemini, Cursor, OpenCode, Inference Gateway, Model Runtime 문서를 참고하세요.
