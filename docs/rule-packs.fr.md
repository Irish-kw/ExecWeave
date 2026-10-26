# Rule Packs

<!-- i18n-nav:start -->
<p align="center">
  <a href="rule-packs.md">English</a> |
  <a href="rule-packs.zh-TW.md">繁體中文</a> |
  <a href="rule-packs.zh-CN.md">简体中文</a> |
  <a href="rule-packs.ja.md">日本語</a> |
  <a href="rule-packs.ko.md">한국어</a> |
  <strong>Français</strong> |
  <a href="rule-packs.de.md">Deutsch</a> |
  <a href="rule-packs.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

Les Rule Packs ExecWeave sont des politiques JSON bornées permettant d'ajouter des observation findings locaux et explicables sans exécuter de code tiers. Le schéma `0.1` ne prend volontairement en charge que le matching d'une seule edge. Les règles de corrélation multi-edge intégrées restent dans le code ExecWeave et ne sont pas remplacées par des Rule Packs non fiables.

## Contract

Un Rule Pack est limité à 256 KiB, 128 rules au maximum et 16 values au maximum par list matcher. Les champs inconnus sont refusés. Les identifiants de pack et de rule sont bornés et ne peuvent contenir que des lettres, chiffres, `.`, `_` et `-`.

Les Rule Packs ne peuvent pas définir de regular expression, de summary personnalisée, d'attributes arbitraires, de programme path/sequence, de code hook ni d'assertion de data flow. ExecWeave génère le texte du finding et marque toujours les matches Rule Pack comme observation-only avec `data_flow_proven=false` et `exfiltration_proven=false`.

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

Chaque rule exige `id`, `severity` et un objet `match` non vide. La severity doit être `high`, `medium`, `low` ou `info`. La severity ne modifie pas l'Evidence Grade : celui-ci reste dérivé de la provenance de la canonical graph edge qui a réellement matché.

## Match semantics

| Matcher | Signification |
| --- | --- |
| `relations` | Correspondance exacte de la relation de l'edge ; toute valeur listée peut matcher. |
| `source_types` | Correspondance exacte du type du source node. |
| `target_types` | Correspondance exacte du type du target node. |
| `source_id_contains` | Substring match insensible à la casse sur l'ID du source node. |
| `target_id_contains` | Substring match insensible à la casse sur l'ID du target node. |
| `source_name_contains` | Substring match insensible à la casse sur le nom du source node. |
| `target_name_contains` | Substring match insensible à la casse sur le nom du target node. |
| `backends` | Nécessite une intersection avec le backend set de l'edge. |
| `attributions` | Nécessite une intersection avec l'attribution set de l'edge. |
| `causal` | Correspondance booléenne exacte de la valeur `causal` de l'edge. |

Les différents champs matcher sont combinés par AND. Plusieurs values dans une même list sont des alternatives OR. Aucun matcher n'évalue de regex.

## CLI

```bash
execweave-rule-pack graph.json --rule-pack local-policy.json
execweave-rule-pack graph.json --rule-pack base.json --rule-pack team.json --output report.json
```

Plusieurs packs chargés dans une même invocation doivent avoir des pack IDs uniques. La sortie étend le security-analysis report normal avec `analysis_schema_version: 0.4`, `rule_pack_schema_version` et la liste des pack IDs chargés avec leur rule count. Le comportement existant de `execweave analyze` reste inchangé.

## Security boundary

Un Rule Pack est de la data, pas un plugin. Son chargement n'importe aucun module, n'exécute aucune commande, n'évalue aucune expression et n'exécute aucune regex. Un pack peut attribuer une severity à un pattern d'edge observé, mais il ne peut pas affirmer que des bytes ont circulé entre des ressources ou qu'une exfiltration a eu lieu. Ces affirmations plus fortes exigent des preuves et une logique en dehors de ce premier contrat Rule Pack.
