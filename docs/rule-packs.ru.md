# Rule Packs

<!-- i18n-nav:start -->
<p align="center">
  <a href="rule-packs.md">English</a> |
  <a href="rule-packs.zh-TW.md">繁體中文</a> |
  <a href="rule-packs.zh-CN.md">简体中文</a> |
  <a href="rule-packs.ja.md">日本語</a> |
  <a href="rule-packs.ko.md">한국어</a> |
  <a href="rule-packs.fr.md">Français</a> |
  <a href="rule-packs.de.md">Deutsch</a> |
  <strong>Русский</strong>
</p>
<!-- i18n-nav:end -->

Rule Packs ExecWeave — это ограниченные JSON-политики для добавления локальных, объяснимых observation findings без выполнения стороннего кода. Schema `0.1` намеренно поддерживает только matching одной edge. Встроенные multi-edge correlation rules остаются в коде ExecWeave и не заменяются недоверенными Rule Packs.

## Contract

Один Rule Pack ограничен размером 256 KiB, максимум 128 rules и максимум 16 values для каждого list matcher. Неизвестные поля отклоняются. Идентификаторы pack и rule ограничены по длине и могут содержать только буквы, цифры, `.`, `_` и `-`.

Rule Pack не может определять regular expression, пользовательский summary, произвольные attributes, path/sequence program, code hook или data-flow assertion. Текст finding формируется самим ExecWeave, а все совпадения Rule Pack помечаются как observation-only с обязательными `data_flow_proven=false` и `exfiltration_proven=false`.

## Schema

```json
{
  "rule_pack_schema_version": "0.1",
  "id": "local-policy",
  "rules": [
    {
      "id": "pem-read",
      "severity": "medium",
      "match": {
        "relations": ["OPENED_READ"],
        "source_types": ["process"],
        "target_types": ["file"],
        "target_name_contains": [".pem"],
        "backends": ["strace"],
        "causal": true
      }
    }
  ]
}
```

Каждая rule требует `id`, `severity` и непустой объект `match`. Severity может быть `high`, `medium`, `low` или `info`. Severity не меняет Evidence Grade: Evidence Grade по-прежнему выводится из provenance реально совпавшей canonical graph edge.

## Match semantics

| Matcher | Значение |
| --- | --- |
| `relations` | Точное совпадение edge relation; подходит любое перечисленное значение. |
| `source_types` | Точное совпадение source node type. |
| `target_types` | Точное совпадение target node type. |
| `source_id_contains` | Case-insensitive substring match для source node ID. |
| `target_id_contains` | Case-insensitive substring match для target node ID. |
| `source_name_contains` | Case-insensitive substring match для source node name. |
| `target_name_contains` | Case-insensitive substring match для target node name. |
| `backends` | Требуется пересечение с backend set данной edge. |
| `attributions` | Требуется пересечение с attribution set данной edge. |
| `causal` | Точное boolean-сопоставление значения `causal` у edge. |

Разные matcher fields объединяются через AND. Несколько values внутри одного list являются OR-альтернативами. Ни один matcher не выполняет regex.

## CLI

```bash
execweave-rule-pack graph.json --rule-pack local-policy.json
execweave-rule-pack graph.json --rule-pack base.json --rule-pack team.json --output report.json
```

Несколько packs в одном вызове должны иметь уникальные pack IDs. Вывод расширяет обычный security-analysis report полями `analysis_schema_version: 0.4`, `rule_pack_schema_version`, а также списком загруженных pack IDs и rule counts. Поведение существующей команды `execweave analyze` не меняется.

## Security boundary

Rule Pack — это data, а не plugin. При загрузке pack не импортируются модули, не выполняются команды, не вычисляются expressions и не запускаются regex. Pack может назначить severity наблюдаемому edge pattern, но не может утверждать, что bytes перемещались между ресурсами или что произошла exfiltration. Для таких более сильных утверждений нужны доказательства и логика вне первого Rule Pack contract.
