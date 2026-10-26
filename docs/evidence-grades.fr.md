<!-- i18n-nav:start -->
<p align="center">
  <a href="evidence-grades.md">English</a> |
  <a href="evidence-grades.zh-TW.md">繁體中文</a> |
  <a href="evidence-grades.zh-CN.md">简体中文</a> |
  <a href="evidence-grades.ja.md">日本語</a> |
  <a href="evidence-grades.ko.md">한국어</a> |
  <strong>Français</strong> |
  <a href="evidence-grades.de.md">Deutsch</a> |
  <a href="evidence-grades.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# Grades de preuve

Les grades de preuve d’ExecWeave indiquent dans quelle mesure la provenance du graphe d’exécution soutient un finding. Ils ne décrivent ni la gravité, ni l’intention malveillante, ni une probabilité, ni la justesse absolue du finding.

## Objectif

La severity d’un finding et la force de sa preuve sont deux dimensions indépendantes. Un comportement de forte severity peut n’être observé qu’au moyen d’un mécanisme échantillonné, alors qu’un comportement de faible severity peut disposer d’une attribution syscall forte. ExecWeave expose donc les deux valeurs séparément au lieu de réduire silencieusement la severity lorsque la collecte est plus faible.

## Contrat

| Grade | Signification | Dérivation actuelle |
| --- | --- | --- |
| `A` | Attribution native directe et causale | Graph edge causal avec attribution `syscall` reconnue |
| `B` | Attribution process directe, causale et échantillonnée | Edge causal avec attribution `polling` ou `process_polling` |
| `C` | Preuve corrélée à la session ou explicitement non causale | Edge non causal ou attribution `session_observation` reconnue |
| `D` | Preuve explicitement inférée ou heuristique | Edge avec `inferred=true` ou avec une inference method enregistrée |
| `U` | Provenance inconnue ou insuffisamment classée | Support ou attribution manquant, vocabulary inconnu/mixte, ou provenance non classée |

Le vocabulary est volontairement conservateur. Un nouveau backend ou une nouvelle chaîne d’attribution n’est **jamais** automatiquement promu vers un grade plus fort ; il reste `U` jusqu’à extension explicite du contrat.

## Dérivation du finding

Chaque finding référence déjà un ou plusieurs graph edges via `edge_ids`. ExecWeave grade chaque supporting edge à partir des champs de provenance conservés dans le graphe, notamment `causal`, `inferred`, `attributions`, `backends` et `inference_methods`.

Le finding reçoit le **grade du supporting edge le plus faible**. Une preuve forte ne peut donc pas « blanchir » un finding multi-edge ou delegated contenant un support plus faible. Un supporting edge absent reçoit `U` au lieu d’être deviné.

## Severity indépendante

Le grade de preuve ne réécrit jamais `severity`. Par exemple, un finding peut légitimement être :

```json
{
  "severity": "high",
  "evidence_grade": "B"
}
```

Cela signifie que le comportement est de haute priorité selon la règle, alors que son observation de support contient une preuve process échantillonnée. Cela ne signifie pas « 80 % de confiance » et ne prouve pas une intention malveillante.

## Valeurs par défaut conservatrices

Une inference explicite prime sur un causal flag et reçoit `D`. Une preuve explicitement non causale reçoit `C`. Un vocabulary d’attribution inconnu reçoit `U`, même si d’autres champs semblent forts. Ces règles évitent l’inflation accidentelle des claims lors de futures intégrations backend.

Le rapport inclut aussi `evidence_basis` pour chaque finding afin que l’analyste puisse inspecter le grade de chaque edge, les attribution modes, les backend labels, les inference methods et la raison du grade.

## Ce que les grades ne prouvent pas

Les grades de preuve ne sont ni des probabilités, ni des trust scores, ni des garanties de résistance à l’altération, ni des preuves de correction. Ils n’établissent pas un byte-level data flow, une exfiltration, une couverture process complète ou une intention malveillante. Ces claims restent gouvernés par les contrats event et fidelity sous-jacents.
