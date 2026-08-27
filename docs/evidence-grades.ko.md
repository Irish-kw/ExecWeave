<!-- i18n-nav:start -->
<p align="center">
  <a href="evidence-grades.md">English</a> |
  <a href="evidence-grades.zh-TW.md">繁體中文</a> |
  <a href="evidence-grades.zh-CN.md">简体中文</a> |
  <a href="evidence-grades.ja.md">日本語</a> |
  <strong>한국어</strong> |
  <a href="evidence-grades.fr.md">Français</a> |
  <a href="evidence-grades.de.md">Deutsch</a> |
  <a href="evidence-grades.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# Evidence Grade

ExecWeave의 Evidence Grade는 실행 그래프의 provenance가 finding을 얼마나 강하게 뒷받침하는지를 나타냅니다. 이는 심각도, 악의성, 확률, 또는 finding의 정답 여부를 뜻하지 않습니다.

## 목적

Finding의 severity와 증거 강도는 서로 독립적인 축입니다. 높은 severity의 행동이 sampling 기반 증거로만 관찰될 수 있고, 반대로 낮은 severity의 행동이 강한 syscall attribution을 가질 수도 있습니다. 따라서 ExecWeave는 두 값을 따로 노출하며 수집 능력이 약하다는 이유만으로 severity를 낮추지 않습니다.

## Contract

| Grade | 의미 | 현재 도출 방식 |
| --- | --- | --- |
| `A` | 직접적이며 causal한 native attribution | 인식된 `syscall` attribution을 가진 causal graph edge |
| `B` | 직접적이며 causal한 sampled process attribution | `polling` 또는 `process_polling` attribution을 가진 causal edge |
| `C` | session-correlated 또는 명시적 non-causal evidence | non-causal edge 또는 `session_observation` attribution |
| `D` | 명시적으로 inferred / heuristic인 evidence | `inferred=true` 또는 inference method가 기록된 edge |
| `U` | provenance가 알 수 없거나 분류 정보가 부족함 | support/attribution 누락, 혼합·미지의 vocabulary, 기타 미분류 provenance |

이 vocabulary는 의도적으로 보수적입니다. 새로운 backend나 attribution 문자열은 자동으로 높은 grade로 승격되지 않으며, contract가 명시적으로 확장되기 전까지 `U`로 남습니다.

## Finding 도출 방식

각 finding은 `edge_ids`를 통해 하나 이상의 graph edge를 참조합니다. ExecWeave는 graph에 보존된 `causal`, `inferred`, `attributions`, `backends`, `inference_methods` 같은 provenance 필드로 각 supporting edge를 grade합니다.

Finding 전체에는 **supporting edge 중 가장 약한 grade**를 적용합니다. 따라서 강한 edge 하나가 더 약한 support를 포함한 multi-edge 또는 delegated finding 전체를 과도하게 강한 증거로 보이게 만들 수 없습니다. supporting edge가 없으면 추측하지 않고 `U`로 처리합니다.

## Severity와의 독립성

Evidence grade는 `severity`를 변경하지 않습니다. 예를 들어 다음 조합은 유효합니다.

```json
{
  "severity": "high",
  "evidence_grade": "B"
}
```

이는 rule상 행동의 우선순위가 high이지만 supporting observation에 sampled process evidence가 포함된다는 뜻입니다. “80% confidence”나 악의성의 증명을 뜻하지 않습니다.

## 보수적 기본값

명시적 inference는 causal flag보다 우선하며 `D`가 됩니다. 명시적 non-causal evidence는 `C`입니다. 알 수 없는 attribution vocabulary는 다른 field가 강해 보여도 `U`입니다. 이는 향후 backend 통합 시 claim inflation을 막기 위한 규칙입니다.

Report에는 finding별 `evidence_basis`도 포함되어 각 edge의 grade, attribution modes, backend labels, inference methods, 그리고 grade 이유를 확인할 수 있습니다.

## 의미하지 않는 것

Evidence grade는 probability, trust score, tamper-resistance guarantee, correctness proof가 아닙니다. byte-level data flow, exfiltration, complete process coverage, malicious intent도 입증하지 않습니다. 이러한 claim은 underlying event와 fidelity contract를 따릅니다.
