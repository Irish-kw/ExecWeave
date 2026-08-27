<!-- i18n-nav:start -->
<p align="center">
  <a href="evidence-grades.md">English</a> |
  <a href="evidence-grades.zh-TW.md">繁體中文</a> |
  <a href="evidence-grades.zh-CN.md">简体中文</a> |
  <a href="evidence-grades.ja.md">日本語</a> |
  <a href="evidence-grades.ko.md">한국어</a> |
  <a href="evidence-grades.fr.md">Français</a> |
  <a href="evidence-grades.de.md">Deutsch</a> |
  <strong>Русский</strong>
</p>
<!-- i18n-nav:end -->

# Градации доказательств

Градации доказательств ExecWeave показывают, насколько сильно provenance графа выполнения поддерживает finding. Они не описывают тяжесть, злонамеренность, вероятность или абсолютную правильность finding.

## Назначение

Severity finding и сила доказательств — независимые измерения. Поведение с высокой severity может наблюдаться только через выборочные механизмы, тогда как поведение с низкой severity может иметь сильную syscall attribution. Поэтому ExecWeave показывает оба значения отдельно и не понижает severity только из-за более слабого механизма сбора.

## Контракт

| Grade | Значение | Текущее правило вывода |
| --- | --- | --- |
| `A` | Прямая причинная native attribution | Causal graph edge с распознанной `syscall` attribution |
| `B` | Прямая причинная sampled process attribution | Causal edge с `polling` или `process_polling` attribution |
| `C` | Session-correlated или явно non-causal evidence | Non-causal edge либо распознанная `session_observation` attribution |
| `D` | Явно inferred или heuristic evidence | Edge имеет `inferred=true` либо содержит inference method |
| `U` | Неизвестная или недостаточно классифицированная provenance | Отсутствует support/attribution, vocabulary неизвестен или смешан, либо provenance ещё не классифицирована |

Vocabulary намеренно консервативен. Новый backend или attribution string **не** повышается автоматически до более сильного grade; до явного расширения контракта он остаётся `U`.

## Вывод для finding

Каждый finding уже ссылается на один или несколько graph edges через `edge_ids`. ExecWeave оценивает каждую supporting edge по сохранённым в графе полям provenance, включая `causal`, `inferred`, `attributions`, `backends` и `inference_methods`.

Finding получает **самый слабый grade среди supporting edges**. Это не позволяет одной сильной edge «отмыть» multi-edge или delegated finding, в котором остальная поддержка слабее. Отсутствующая supporting edge получает `U`, а не предполагаемое значение.

## Severity остаётся независимой

Evidence grade никогда не переписывает `severity`. Например, finding может корректно иметь вид:

```json
{
  "severity": "high",
  "evidence_grade": "B"
}
```

Это означает, что правило считает поведение высокоприоритетным, но supporting observation включает sampled process evidence. Это не означает «80% confidence» и не доказывает malicious intent.

## Консервативные значения по умолчанию

Явная inference имеет приоритет над causal flag и получает `D`. Явно non-causal evidence получает `C`. Неизвестный attribution vocabulary получает `U`, даже если другие поля выглядят сильными. Эти правила предотвращают случайное claim inflation при будущих интеграциях backend.

Report также содержит `evidence_basis` для каждого finding, чтобы аналитик мог проверить grade каждой edge, attribution modes, backend labels, inference methods и причину присвоенного grade.

## Что grades не доказывают

Evidence grades не являются вероятностями, trust scores, гарантиями tamper resistance или доказательствами корректности. Они не устанавливают byte-level data flow, exfiltration, complete process coverage или malicious intent. Эти claims по-прежнему ограничены базовыми event и fidelity contract.
