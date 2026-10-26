<!-- i18n-nav:start -->
<p align="center">
  <a href="semantic-telemetry.md">English</a> |
  <a href="semantic-telemetry.zh-TW.md">繁體中文</a> |
  <a href="semantic-telemetry.zh-CN.md">简体中文</a> |
  <strong>日本語</strong> |
  <a href="semantic-telemetry.ko.md">한국어</a> |
  <a href="semantic-telemetry.fr.md">Français</a> |
  <a href="semantic-telemetry.de.md">Deutsch</a> |
  <a href="semantic-telemetry.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# Semantic Telemetry

ExecWeave は provider/framework の semantic observation と独立した OS runtime evidence を組み合わせますが、元の runtime capture は書き換えません。Provider evidence は Agent、tool、gateway、model-runtime integration point が明示的に公開した内容を示し、OS evidence は machine collector が実際に観測した内容を示します。Correlation は常に独立した derived layer であり、自動的に causal proof へ昇格しません。

## Workflow

Provider adapter が run-bound semantic sidecar を書き、その後 ExecWeave が新しい merged stream を検証します。

```bash
execweave semantic-merge run.jsonl semantic.jsonl --output run.semantic.jsonl
execweave validate run.semantic.jsonl
execweave graph run.semantic.jsonl --output run.semantic.graph.json
```

`semantic-merge` は `run.jsonl` を変更しません。Run-bound recorder は runtime、semantic、correlated artifact を別々に保持します。

## v0.6.5 の full-fidelity content

Semantic telemetry は小さな metadata summary だけに限定されません。対応 integration point が content を明示的に提供した場合、v0.6.5 は source から提供された完全な値をローカル content-addressed store に保存し、JSONL event には reference のみを置けます。

```text
<run-root>/content/sha256/<sha256>.<json|txt|bin>
```

Content reference には SHA-256、relative path、media type、byte size、content kind、representation、その integration point から見て complete from source かどうかが記録されます。`complete_from_source: true` は受け取った完全な値を保存したという意味であり、hidden model state、見えていない final wire request、または integration point が提供しなかった field を provider が公開したという意味ではありません。

Native adapters は hook/API surface が明示的に提供する prompts、tool inputs/results、assistant/model responses、明示的な reasoning/thinking text、provider hook が渡す file content、contract が対応する provider request/response objects にこの仕組みを使います。

Content store が失敗しても compact semantic summary は graph materialization に利用できます。Native hook adapter はデフォルト fail-open なので、content-storage failure が Agent operation を意図的に止めることはありません。

## Evidence boundary

Semantic content は observed provider/integration evidence であり OS causality ではありません。保存された tool input は process 実行を証明せず、hook が提供した file body は OS read completion を証明せず、CLI に渡された request/response pair は transparent network interception を意味しません。

Tool → Process bridge は別定義の conservative correlation layer だけが作成でき、常に次を保ちます。

```text
inferred: true
causal: false
```

Unknown/ambiguous attribution では bridge を作りません。File と network observation が同時に存在しても byte-level data flow や exfiltration は推論しません。

## Privacy

Full-fidelity content は本質的に sensitive です。Prompt text、tool arguments、tool output、model responses、file content、application-level secret values が redacted 済みだと**仮定しないでください**。Content store は対応 integration point が提供した完全な値を保存します。

ExecWeave は adapter contract が定義する場合に限り、provider-metadata projection から既知の transport credentials を除外します。これは汎用 secret scanner ではなく、content payload 内の secret を削除しません。Content blobs はデフォルトでローカルに残り graph events に inline されませんが、run evidence の一部なので共有前に確認が必要です。

各 provider-specific document が観測可能 field を定義します。Claude Code、Codex、Antigravity、Cursor、OpenCode、Inference Gateway、Model Runtime の文書を参照してください。
