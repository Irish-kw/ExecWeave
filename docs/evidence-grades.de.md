<!-- i18n-nav:start -->
<p align="center">
  <a href="evidence-grades.md">English</a> |
  <a href="evidence-grades.zh-TW.md">繁體中文</a> |
  <a href="evidence-grades.zh-CN.md">简体中文</a> |
  <a href="evidence-grades.ja.md">日本語</a> |
  <a href="evidence-grades.ko.md">한국어</a> |
  <a href="evidence-grades.fr.md">Français</a> |
  <strong>Deutsch</strong> |
  <a href="evidence-grades.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# Evidenzgrade

Die Evidenzgrade von ExecWeave beschreiben, wie stark die Provenance des Ausführungsgraphen ein Finding stützt. Sie beschreiben weder Schweregrad noch Bösartigkeit, Wahrscheinlichkeit oder absolute Korrektheit des Findings.

## Zweck

Finding-Severity und Evidenzstärke sind voneinander unabhängige Dimensionen. Ein Verhalten mit hoher Severity kann nur durch gesampelte Evidenz beobachtet werden, während ein Verhalten mit niedriger Severity eine starke syscall attribution besitzen kann. ExecWeave zeigt deshalb beide Werte getrennt an, anstatt bei schwächerer Erfassung die Severity stillschweigend zu senken.

## Vertrag

| Grade | Bedeutung | Aktuelle Ableitung |
| --- | --- | --- |
| `A` | Direkte, kausale native attribution | Kausale graph edge mit erkannter `syscall` attribution |
| `B` | Direkte, kausale gesampelte process attribution | Kausale edge mit `polling`- oder `process_polling`-Attribution |
| `C` | Session-korrelierte oder ausdrücklich nicht kausale Evidenz | Non-causal edge oder erkannte `session_observation` attribution |
| `D` | Ausdrücklich inferred oder heuristische Evidenz | Edge mit `inferred=true` oder dokumentierter inference method |
| `U` | Unbekannte oder unzureichend klassifizierte Provenance | Fehlender Support/Attribution, unbekanntes oder gemischtes Vocabulary oder sonst nicht klassifizierte Provenance |

Das Vocabulary ist absichtlich konservativ. Ein neuer Backend- oder Attribution-String wird **nicht** automatisch auf einen stärkeren Grade angehoben; bis zur ausdrücklichen Erweiterung des Vertrags bleibt er `U`.

## Ableitung des Findings

Jedes Finding referenziert bereits eine oder mehrere graph edges über `edge_ids`. ExecWeave gradet jede supporting edge anhand der im Graph gespeicherten Provenance-Felder, darunter `causal`, `inferred`, `attributions`, `backends` und `inference_methods`.

Das Finding erhält den **schwächsten Grade seiner supporting edges**. Dadurch kann eine starke Edge ein multi-edge oder delegated Finding mit schwächerem Support nicht künstlich aufwerten. Fehlende supporting edges werden als `U` eingestuft und nicht geraten.

## Severity bleibt unabhängig

Der Evidence Grade überschreibt `severity` niemals. Ein Finding kann zum Beispiel berechtigterweise so aussehen:

```json
{
  "severity": "high",
  "evidence_grade": "B"
}
```

Das bedeutet: Die Regel bewertet das Verhalten als hohe Priorität, während die stützende Beobachtung gesampelte process evidence enthält. Es bedeutet weder „80 % confidence“ noch beweist es bösartige Absicht.

## Konservative Standardwerte

Explizite inference hat Vorrang vor einem causal flag und erhält `D`. Explizit non-causal evidence erhält `C`. Unbekanntes attribution vocabulary erhält `U`, selbst wenn andere Felder stark wirken. Diese Regeln verhindern unbeabsichtigte claim inflation bei zukünftigen Backend-Integrationen.

Der Report enthält außerdem `evidence_basis` für jedes Finding. Analysten können dort Grade, attribution modes, backend labels, inference methods und die Begründung jeder supporting edge prüfen.

## Keine weitergehenden Aussagen

Evidence Grades sind keine Wahrscheinlichkeiten, trust scores, Manipulationsschutz-Garantien oder Korrektheitsbeweise. Sie belegen weder byte-level data flow noch exfiltration, vollständige process coverage oder malicious intent. Solche Claims bleiben durch die zugrunde liegenden Event- und Fidelity-Verträge begrenzt.
