# Rule Packs

<!-- i18n-nav:start -->
<p align="center">
  <a href="rule-packs.md">English</a> |
  <a href="rule-packs.zh-TW.md">繁體中文</a> |
  <a href="rule-packs.zh-CN.md">简体中文</a> |
  <a href="rule-packs.ja.md">日本語</a> |
  <a href="rule-packs.ko.md">한국어</a> |
  <a href="rule-packs.fr.md">Français</a> |
  <strong>Deutsch</strong> |
  <a href="rule-packs.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

ExecWeave Rule Packs sind begrenzte JSON-Richtlinien, mit denen lokale, erklärbare observation findings hinzugefügt werden können, ohne Code von Drittanbietern auszuführen. Schema `0.1` unterstützt absichtlich nur das Matching einer einzelnen edge. Eingebaute multi-edge correlation rules bleiben im ExecWeave-Code und werden nicht durch nicht vertrauenswürdige Rule Packs ersetzt.

## Contract

Ein Rule Pack ist auf 256 KiB, höchstens 128 rules und höchstens 16 values pro list matcher begrenzt. Unbekannte Felder werden abgelehnt. Pack- und rule identifiers sind längenbegrenzt und dürfen nur Buchstaben, Ziffern, `.`, `_` und `-` enthalten.

Rule Packs dürfen keine regular expressions, benutzerdefinierten summaries, beliebigen attributes, path/sequence programs, code hooks oder data-flow assertions definieren. ExecWeave erzeugt den Finding-Text selbst und markiert Rule-Pack-Matches immer als observation-only mit `data_flow_proven=false` und `exfiltration_proven=false`.

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

Jede rule benötigt `id`, `severity` und ein nicht leeres `match` object. Severity ist `high`, `medium`, `low` oder `info`. Severity verändert den Evidence Grade nicht; der Evidence Grade wird weiterhin aus der Provenance der tatsächlich gematchten canonical graph edge abgeleitet.

## Match semantics

| Matcher | Bedeutung |
| --- | --- |
| `relations` | Exakter Match der edge relation; jeder gelistete Wert kann matchen. |
| `source_types` | Exakter Match des source node type. |
| `target_types` | Exakter Match des target node type. |
| `source_id_contains` | Case-insensitive substring match auf der source node ID. |
| `target_id_contains` | Case-insensitive substring match auf der target node ID. |
| `source_name_contains` | Case-insensitive substring match auf dem source node name. |
| `target_name_contains` | Case-insensitive substring match auf dem target node name. |
| `backends` | Erfordert eine Schnittmenge mit dem backend set der edge. |
| `attributions` | Erfordert eine Schnittmenge mit dem attribution set der edge. |
| `causal` | Exakter boolescher Match des `causal`-Werts der edge. |

Verschiedene matcher fields werden mit AND kombiniert. Mehrere values innerhalb einer list sind OR-Alternativen. Kein matcher wertet regex aus.

## CLI

```bash
execweave-rule-pack graph.json --rule-pack local-policy.json
execweave-rule-pack graph.json --rule-pack base.json --rule-pack team.json --output report.json
```

Mehrere Packs in einem Aufruf müssen eindeutige pack IDs besitzen. Die Ausgabe erweitert den normalen security-analysis report um `analysis_schema_version: 0.4`, `rule_pack_schema_version` sowie die geladenen pack IDs und rule counts. Das bestehende Verhalten von `execweave analyze` bleibt unverändert.

## Security boundary

Ein Rule Pack ist data, kein plugin. Beim Laden werden keine Module importiert, keine Commands ausgeführt, keine Expressions evaluiert und keine regex ausgeführt. Ein Pack kann einem beobachteten edge pattern eine severity zuweisen, aber nicht behaupten, dass Bytes zwischen Ressourcen übertragen wurden oder dass eine Exfiltration stattgefunden hat. Solche stärkeren Aussagen benötigen Beweise und Logik außerhalb dieses ersten Rule-Pack-Contracts.
